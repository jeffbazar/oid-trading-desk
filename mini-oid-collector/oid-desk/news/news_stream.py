#!/usr/bin/env python3
"""OID newsfeed (com.oid.desk.news, 2026-10-20). Mini-only, no extra cost.

Main feed: Alpaca real-time news websocket (Benzinga-sourced, included in Algo Trader Plus):
  wss://stream.data.alpaca.markets/v1beta1/news  (subscribe "*", filtered here)
Safety net: REST /v1beta1/news backfill of today on start + poll every 60 s.
Also reads the x-on-surge X archive (kept posts only) every 60 s; never calls X.
Every item gets a sentiment score -2..+2 (news_sentiment.py; FinBERT when installed, else lexicon).

Writes (~/oid-desk/state/news/):
  latest.json              last 200 followed headlines + 100 market-wide + top X posts + per-ticker by_sym
  news-YYYYMMDD.jsonl      every Alpaca headline today (followed or not), one line per id/update
  sentiment-YYYYMMDD.jsonl every scored item (alpaca + x) with timestamp, for later score-config testing
  status.json
Followed = ~/oid-live-page/sectors.json tickers minus WDC/STX/SNDK/VIX/WTI/BRENT, plus SPY, QQQ.
Keys read from ~/oid-quote/secrets (never printed or logged). Research only; no chat path.
"""
from __future__ import annotations
import asyncio, glob, html, json, os, re, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import news_sentiment as NS  # noqa: E402

PT, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
HOME = Path.home()
VERSION = "oid-news@0.1"
OUT = HOME / "oid-desk/state/news"
SECRETS = HOME / "oid-quote/secrets"
SECTORS = HOME / "oid-live-page/sectors.json"
XARCH = HOME / "oid-data/archive"
WS_URL = "wss://stream.data.alpaca.markets/v1beta1/news"
REST = "https://data.alpaca.markets/v1beta1/news"
EXCLUDE = {"WDC", "STX", "SNDK", "VIX", "WTI", "BRENT"}
EXTRA = {"SPY", "QQQ"}
KEEP_FOLLOWED, KEEP_MARKET, KEEP_X = 200, 100, 25
X_WEIGHT = 0.5  # X posts count half as much as a wire headline in net60


def log(msg):
    print(f"{datetime.now(PT):%H:%M:%S} {msg}", flush=True)


def pt_label(ep, fmt="%-I:%M %p"):
    return datetime.fromtimestamp(ep, PT).strftime(fmt)


def iso_ep(s):
    try:
        s = str(s).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        m = re.match(r"^(.*?T\d\d:\d\d:\d\d)(\.\d+)?(.*)$", s)
        if m:
            frac = (m.group(2) or "")[:7]
            s = m.group(1) + frac + (m.group(3) or "")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        return None


def followed():
    try:
        d = json.loads(SECTORS.read_text())
        out = {str(s).upper() for g in d.get("groups") or [] for s in g.get("tickers") or []}
    except Exception:
        out = set()
    return (out | EXTRA) - EXCLUDE


def creds():
    return (SECRETS / "APCA_API_KEY_ID").read_text().strip(), (SECRETS / "APCA_API_SECRET_KEY").read_text().strip()


def atomic(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


class Feed:
    def __init__(self):
        OUT.mkdir(parents=True, exist_ok=True)
        self.fol = followed()
        self.fol_t = time.time()
        self.day = None
        self.items = {}   # id -> item (today)
        self.x = {}       # post_id -> x item (today)
        self.xkey = None
        self.st = {"ws": "starting", "ws_since_pt": None, "ws_last_msg_pt": None, "ws_items": 0, "rest_items": 0,
                   "backfill_n": 0, "errors": 0, "last_error": None, "x_posts": 0, "method": NS.METHOD}
        self.dirty = True

    # ---- day / files
    def _rollday(self):
        d = datetime.now(PT).strftime("%Y%m%d")
        if d != self.day:
            self.day, self.items, self.x, self.xkey = d, {}, {}, None
            self.st.update(ws_items=0, rest_items=0, backfill_n=0, x_posts=0)
            self._restore()
        return d

    def _restore(self):
        p = OUT / f"news-{self.day}.jsonl"
        if p.exists():
            for ln in p.read_text(errors="replace").splitlines():
                try:
                    it = json.loads(ln)
                    it["headline"] = html.unescape(it.get("headline") or "")
                    self.items[it["id"]] = it
                except Exception:
                    continue
        sp = OUT / f"sentiment-{self.day}.jsonl"
        if sp.exists():  # don't re-log X posts already scored today
            for ln in sp.read_text(errors="replace").splitlines():
                try:
                    r = json.loads(ln)
                    if r.get("kind") == "x":
                        self.x[r["id"]] = None  # placeholder; rebuilt from archive
                except Exception:
                    continue
            self.x = {}
        log(f"restored {len(self.items)} headlines for {self.day}")

    def _append(self, name, row):
        with open(OUT / f"{name}-{self.day}.jsonl", "a") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _logged_x(self):
        sp = OUT / f"sentiment-{self.day}.jsonl"
        s = set()
        if sp.exists():
            for ln in sp.read_text(errors="replace").splitlines():
                if '"kind":"x"' in ln:
                    try:
                        s.add(json.loads(ln)["id"])
                    except Exception:
                        pass
        return s

    # ---- alpaca
    def add(self, n, via):
        self._rollday()
        if time.time() - self.fol_t > 300:
            self.fol, self.fol_t = followed(), time.time()
        nid = str(n.get("id"))
        t = iso_ep(n.get("created_at"))
        if not nid or t is None:
            return False
        if datetime.fromtimestamp(t, PT).strftime("%Y%m%d") != self.day:
            return False
        old = self.items.get(nid)
        upd = n.get("updated_at")
        if old and (old.get("updated_at") == upd or abs((iso_ep(old.get("updated_at")) or 0) - (iso_ep(upd) or 0)) < 1):
            return False  # same version (ws and REST format updated_at differently)
        raw_syms = [str(s).upper() for s in (n.get("symbols") or [])]
        syms = [s for s in raw_syms if s not in EXCLUDE]
        if raw_syms and not syms:
            return False  # only avoided names (WDC/STX/SNDK)
        tick = [s for s in syms if s in self.fol]
        head = html.unescape(" ".join(str(n.get("headline") or "").split()))
        summ = " ".join(re.sub(r"<[^>]+>", " ", str(n.get("summary") or "")).split())[:400]
        doc, per, raw, m = NS.score(head + (". " + summ[:200] if summ and len(head) < 60 else ""), tick or syms[:6])
        it = {"id": nid, "t": round(t, 3), "created_at": n.get("created_at"), "updated_at": upd,
              "time_pt": pt_label(t), "headline": head, "summary": summ, "source": n.get("source") or "alpaca",
              "author": n.get("author"), "url": n.get("url"), "symbols": syms, "tickers": tick, "followed": bool(tick),
              "sent": doc, "sent_by": per, "sent_raw": raw, "sent_method": m, "via": via, "recv_pt": pt_label(time.time(), "%-I:%M:%S %p")}
        self.items[nid] = it
        self._append("news", it)
        self._append("sentiment", {"t": it["t"], "time_pt": pt_label(t, "%Y-%m-%d %I:%M:%S %p PT"), "kind": "alpaca",
                                   "id": nid, "tickers": tick, "symbols": syms, "doc": doc, "sent": per, "raw": raw,
                                   "method": m, "weight": 1.0, "source": it["source"], "headline": head[:200], "writer": VERSION})
        self.st["ws_items" if via == "ws" else "rest_items"] += 1
        self.dirty = True
        return True

    # ---- X archive (read-only)
    def scan_x(self):
        self._rollday()
        ed = datetime.now(ET).strftime("%Y-%m-%d")
        pr = sorted(glob.glob(str(XARCH / f"posts_raw/date={ed}/part-*.jsonl")))
        itf = sorted(glob.glob(str(XARCH / f"item_filter/date={ed}/part-*.jsonl")))
        key = tuple((f, os.path.getsize(f)) for f in pr + itf)
        if key == self.xkey:
            return
        self.xkey = key
        keep = {}
        for f in itf:
            for ln in open(f, errors="replace"):
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                keep[r.get("item_id")] = r
        logged = self._logged_x()
        for f in pr:
            for ln in open(f, errors="replace"):
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                pid = str(r.get("post_id"))
                k = keep.get("x:" + pid)
                if not k or k.get("dropped") or pid in self.x:
                    continue
                try:
                    cash = json.loads(r.get("cashtags") or "[]")
                except Exception:
                    cash = []
                syms = {s.strip().upper() for s in str(r.get("symbols") or "").split(",") if s.strip()}
                syms |= {str(s).upper().lstrip("$") for s in cash if s}
                syms -= EXCLUDE
                tick = sorted(s for s in syms if s in self.fol)
                if not tick:
                    continue
                t = (r.get("created_ns") or 0) / 1e9
                text = html.unescape(" ".join(str(r.get("text") or "").split()))
                eng = int(r.get("like_count") or 0) + 2 * int(r.get("repost_count") or 0) + int(r.get("reply_count") or 0) + int(r.get("quote_count") or 0)
                doc, per, raw, m = NS.score(text[:500], tick)
                x = {"id": pid, "t": round(t, 3), "time_pt": pt_label(t), "text": text[:280], "handle": r.get("author_handle"),
                     "followers": r.get("author_followers"), "tier": k.get("credibility_tier"), "cluster": k.get("cluster_id"),
                     "eng": eng, "likes": r.get("like_count"), "reposts": r.get("repost_count"), "tickers": tick,
                     "url": f"https://x.com/i/status/{pid}", "sent": doc, "sent_by": per, "sent_raw": raw, "sent_method": m}
                self.x[pid] = x
                if pid not in logged:
                    self._append("sentiment", {"t": x["t"], "time_pt": pt_label(t, "%Y-%m-%d %I:%M:%S %p PT"), "kind": "x", "id": pid,
                                               "tickers": tick, "symbols": tick, "doc": doc, "sent": per, "raw": raw, "method": m,
                                               "weight": X_WEIGHT, "source": "x:@" + str(r.get("author_handle")), "headline": text[:200],
                                               "writer": VERSION})
                self.dirty = True
        self.st["x_posts"] = len(self.x)

    def x_top(self):
        seen_c, seen_t, out = set(), set(), []
        for x in sorted(self.x.values(), key=lambda x: (-x["eng"], -x["t"])):
            norm = re.sub(r"https?://\S+|[^a-z0-9 ]", "", x["text"].lower())[:80]
            if (x["cluster"] and x["cluster"] in seen_c) or norm in seen_t:
                continue
            seen_c.add(x["cluster"]); seen_t.add(norm)
            out.append(x)
            if len(out) >= KEEP_X:
                break
        return out

    # ---- output
    def write(self):
        self._rollday()
        now = time.time()
        allv = sorted(self.items.values(), key=lambda i: -i["t"])
        fol = [i for i in allv if i["followed"]]
        by = {}
        for i in fol:
            for s in i["tickers"]:
                b = by.setdefault(s, {"n30": 0, "n60": 0, "net60": 0.0, "n_today": 0, "last_t": None, "heads": []})
                b["n_today"] += 1
                age = now - i["t"]
                if b["last_t"] is None:
                    b.update(last_t=i["t"], last_time_pt=i["time_pt"], last_headline=i["headline"][:160], last_url=i["url"],
                             last_sent=i["sent_by"].get(s, i["sent"]), last_source=i["source"])
                if age <= 1800:
                    b["n30"] += 1
                if age <= 3600:
                    b["n60"] += 1
                    b["net60"] += i["sent_by"].get(s, i["sent"])
                    if len(b["heads"]) < 2:
                        b["heads"].append({"time_pt": i["time_pt"], "headline": i["headline"][:160], "source": i["source"],
                                           "sent": i["sent_by"].get(s, i["sent"]), "url": i["url"]})
        for x in self.x.values():
            if now - x["t"] <= 3600:
                for s in x["tickers"]:
                    b = by.setdefault(s, {"n30": 0, "n60": 0, "net60": 0.0, "n_today": 0, "last_t": None, "heads": []})
                    b["net60"] += X_WEIGHT * x["sent_by"].get(s, x["sent"])
                    b["x60"] = b.get("x60", 0) + 1
        for b in by.values():
            b["net60"] = round(b["net60"], 1)
        self.st["method"] = NS.METHOD
        out = {"as_of_pt": pt_label(now, "%Y-%m-%d %I:%M:%S %p PT"), "as_of": round(now, 2), "writer": VERSION,
               "source": "Alpaca news (Benzinga) websocket + REST backfill; X = x-on-surge archive (kept posts only)",
               "sentiment": {"method": NS.METHOD, "scale": "-2..+2 per ticker", "x_weight": X_WEIGHT, "window_min": 60},
               "status": self.st, "today": len(allv), "today_followed": len(fol),
               "items": fol[:KEEP_FOLLOWED], "market": allv[:KEEP_MARKET], "x_top": self.x_top(), "by_sym": by,
               "followed": sorted(self.fol)}
        atomic(OUT / "latest.json", out)
        atomic(OUT / "status.json", dict(self.st, as_of_pt=out["as_of_pt"], today=len(allv), today_followed=len(fol)))
        self.dirty = False


async def rest_pages(sess, hdr, params, max_pages):
    tok, n = None, 0
    for _ in range(max_pages):
        q = dict(params)
        if tok:
            q["page_token"] = tok
        async with sess.get(REST, headers=hdr, params=q, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                raise RuntimeError(f"rest http {r.status}")
            d = await r.json()
        for it in d.get("news") or []:
            yield it
            n += 1
        tok = d.get("next_page_token")
        if not tok:
            break


async def backfill(feed, sess, hdr):
    feed._rollday()
    start = datetime.now(PT).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = 0
    syms = sorted(feed.fol)
    for i in range(0, len(syms), 40):
        async for it in rest_pages(sess, hdr, {"start": start, "limit": 50, "sort": "desc", "symbols": ",".join(syms[i:i + 40]),
                                               "include_content": "false"}, 30):
            n += feed.add(it, "rest")
    async for it in rest_pages(sess, hdr, {"start": start, "limit": 50, "sort": "desc", "include_content": "false"}, 4):
        n += feed.add(it, "rest")
    feed.st["backfill_n"] = n
    log(f"backfill added {n} (today total {len(feed.items)})")


async def rest_poll(feed, sess, hdr):
    while True:
        await asyncio.sleep(60)
        try:
            start = datetime.fromtimestamp(time.time() - 900, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            async for it in rest_pages(sess, hdr, {"start": start, "limit": 50, "sort": "desc", "include_content": "false"}, 2):
                if feed.add(it, "rest"):
                    log(f"rest caught {it.get('symbols')} {str(it.get('headline'))[:80]}")
        except Exception as e:
            feed.st.update(errors=feed.st["errors"] + 1, last_error=f"rest {type(e).__name__}", last_error_pt=pt_label(time.time()))


async def ws_loop(feed, sess, key, sec):
    back = 2
    while True:
        try:
            async with sess.ws_connect(WS_URL, heartbeat=20, timeout=20) as ws:
                await ws.receive()
                await ws.send_str(json.dumps({"action": "auth", "key": key, "secret": sec}))
                a = json.loads((await ws.receive()).data)
                if not any(x.get("msg") == "authenticated" for x in a):
                    raise RuntimeError(f"auth: {str(a)[:120]}")
                await ws.send_str(json.dumps({"action": "subscribe", "news": ["*"]}))
                feed.st.update(ws="connected", ws_since_pt=pt_label(time.time(), "%-I:%M:%S %p"))
                feed.dirty = True
                log("ws connected + subscribed news *")
                back = 2
                async for m in ws:
                    if m.type != aiohttp.WSMsgType.TEXT:
                        if m.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                        continue
                    for x in json.loads(m.data):
                        if x.get("T") == "n":
                            feed.st["ws_last_msg_pt"] = pt_label(time.time(), "%-I:%M:%S %p")
                            if feed.add(x, "ws"):
                                log(f"ws {x.get('symbols')} {str(x.get('headline'))[:90]}")
                        elif x.get("T") == "error":
                            raise RuntimeError(f"ws error {x.get('code')} {x.get('msg')}")
        except Exception as e:
            feed.st.update(ws="reconnecting", errors=feed.st["errors"] + 1, last_error=f"ws {type(e).__name__}: {str(e)[:80]}",
                           last_error_pt=pt_label(time.time()))
            feed.dirty = True
            log(f"ws down ({type(e).__name__}); retry in {back}s")
        await asyncio.sleep(back)
        back = min(back * 2, 60)


async def periodic(feed):
    last_x, last_w = 0, 0
    while True:
        now = time.time()
        try:
            if now - last_x >= 60:
                last_x = now
                feed.scan_x()
            if feed.dirty or now - last_w >= 15:
                last_w = now
                feed.write()
        except Exception as e:
            feed.st.update(errors=feed.st["errors"] + 1, last_error=f"periodic {type(e).__name__}: {str(e)[:80]}")
            traceback.print_exc()
        await asyncio.sleep(1)


async def main():
    m = NS.init(try_finbert=os.environ.get("OID_NEWS_FINBERT", "1") == "1")
    log(f"{VERSION} start; sentiment={m}")
    feed = Feed()
    feed._rollday()
    key, sec = creds()
    hdr = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
    async with aiohttp.ClientSession() as sess:
        try:
            await backfill(feed, sess, hdr)
        except Exception as e:
            feed.st.update(errors=feed.st["errors"] + 1, last_error=f"backfill {type(e).__name__}: {str(e)[:80]}")
            log(f"backfill failed {type(e).__name__}")
        feed.write()
        await asyncio.gather(ws_loop(feed, sess, key, sec), rest_poll(feed, sess, hdr), periodic(feed))


if __name__ == "__main__":
    asyncio.run(main())
