#!/usr/bin/env python3
"""OID mover alert (2026-10-20): ping Rose (-> Jeffrey) when a live-page ticker runs, so nobody has to watch tape by eye.

Why: 10/20 CRWV ran 57.24 -> 63+ (6:43-7:30 AM PT) and nothing pinged; vol_surge only feeds silent ladder dry runs.

Triggers (universe = ~/oid-live-page/sectors.json minus WDC/STX/SNDK and non-SIP tiles VIX/WTI/BRENT):
  A  move_3pct      last >= +3% above the lowest low of the rolling 30-min window (up), or <= -3% under the
                    highest high (down). Per-symbol overrides in mover-alert.json (TQQQ is 3x levered).
  B  wall_cross     last crosses the FlashAlpha call wall or put wall (either way) vs the previous check.
                    Walls = freshest of the mini's existing FA caches (same merge as the live page); walls older
                    than walls_max_age_min (120) => no B event (A still fires; payload carries walls + stale=true).
Debounce: one alert per ticker per direction per 30 min (A and B share it). Daily cap. RTH weekdays only.
Data: only files/endpoints the mini already has (live page /state.json, collector live 1m bars, FA caches,
x-on-surge X archive). It NEVER calls RH/FA/UW/X, never buys data, never trades.
Delivery: POST event_type=mover_alert to the OID mini event-wake webhook via oid_triggers.read_env/send
(~/.oid/webhook.env, mode 600; URL/key never printed or logged).

  python3 mover_alert.py --loop                 # launchd com.oid.desk.mover-alert (dry unless OID_MOVER_MODE=live)
  python3 mover_alert.py --replay CRWV [--date 2026-10-20]   # dry replay on today's 1m bars, prints alerts, no POST
  python3 mover_alert.py --once                 # one dry check now, prints, no POST
  python3 mover_alert.py --test CRWV            # POST ONE payload tagged TEST (test=true, trade_action=none)
"""
from __future__ import annotations

import argparse, glob, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oid_triggers as T  # noqa: E402  reuse read_env/send (event-wake sender), jload

PT = ZoneInfo("America/Los_Angeles")
HOME = Path.home()
VERSION = "mover-alert@0.1"
DEFAULTS = {
    "enabled": True, "live": True, "interval_s": 15, "rth_pt": ["06:30", "13:00"], "skip_open_min": 1,
    "window_min": 30, "move_pct": 3.0, "per_symbol_move_pct": {"TQQQ": 6.0},
    "debounce_min": 30, "max_per_day": 40, "max_quote_age_s": 90,
    "exclude": ["WDC", "STX", "SNDK", "VIX", "WTI", "BRENT"],
    "wall_buffer_pct": 0.1, "wall_cooldown_min": 20, "wall_recross_suppress_min": 60, "wall_min_move_pct": 0.5, "wall_min_rvol": 1.5, "wall_min_rvol5": 1.2, "walls_max_age_min": 120, "wall_cross": True, "wall_cross_own_debounce": False,
    "news_lookback_min": 60, "timeout_s": 8,
    "sectors": "~/oid-live-page/sectors.json", "livepage_state": "http://127.0.0.1:8791/state.json",
    "bars_live_dir": "~/oid-desk/desk/cache/bars/store/live", "bars_store_dir": "~/oid-desk/desk/cache/bars/store",
    "quotes": "~/oid-desk/desk/cache/mini-quotes.json", "x_archive": "~/oid-data/archive",
    "state_dir": "~/oid-desk/state/mover-alert", "env_file": "~/.oid/webhook.env",
    "wall_files": [["fa-focus-levels", "~/oid-desk/desk/market-data/latest/fa-focus-levels.json"],
                   ["fa-levels", "~/oid-desk/desk/market-data/latest/fa-levels.json"],
                   ["fa-walls-pulse", "~/oid-live-page/data/fa-walls-pulse.json"],
                   ["fa-flow-levels", "~/oid-desk/desk/market-data/latest/fa-flow-levels.json"]],
}


def X(p):
    return Path(os.path.expanduser(p))


def cfg_load(path):
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (T.jload(path, {}) or {}).items() if not str(k).startswith("_")})
    return c


def pt_str(ep, fmt="%-I:%M %p PT"):
    return datetime.fromtimestamp(ep, PT).strftime(fmt)


def iso_ep(s):
    if not s:
        return None
    try:
        s = str(s).strip().replace("Z", "+00:00")
        m = re.match(r"^(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d)(?:\.(\d+))?(.*)$", s)
        if m:  # trim fraction to microseconds (py3.9 fromisoformat rejects nanoseconds); keep the tz suffix intact
            s = m.group(1) + ("." + m.group(2)[:6].ljust(6, "0") if m.group(2) else "") + (m.group(3) or "")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        pass
    try:  # "2026-10-20 7:45:10 AM PT"
        s2 = str(s).replace(" PT", "").replace(" PDT", "").replace(" PST", "")
        for f in ("%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %I:%M %p"):
            try:
                return datetime.strptime(s2, f).replace(tzinfo=PT).timestamp()
            except ValueError:
                continue
    except Exception:
        pass
    return None


def universe(c):
    d = T.jload(X(c["sectors"]), {}) or {}
    ex = {s.upper() for s in c["exclude"]}
    out = []
    for g in d.get("groups") or []:
        for s in g.get("tickers") or []:
            s = str(s).upper()
            if s not in ex and s not in out:
                out.append(s)
    return out


# ---------- data ----------
class Bars:
    """Today's collector 1m bars (live/<SYM>-1m-<YYYYMMDD>.jsonl), cached by size."""

    def __init__(self, c):
        self.dir, self.cache = X(c["bars_live_dir"]), {}

    def get(self, sym, day):
        p = self.dir / f"{sym}-1m-{day}.jsonl"
        try:
            sz = p.stat().st_size
        except OSError:
            return []
        hit = self.cache.get(sym)
        if hit and hit[0] == (day, sz):
            return hit[1]
        rows = []
        for ln in p.read_text().splitlines():
            try:
                b = json.loads(ln)
                b["ep"] = iso_ep(b["t"])
                if b["ep"] is None or any(b.get(k) is None for k in ("h", "l", "c")):
                    continue  # bad/partial bar (null OHLC) -> skip instead of crashing min()/max()
                rows.append(b)
            except Exception:
                continue
        rows.sort(key=lambda b: b["ep"])
        ded = {b["ep"]: b for b in rows}
        rows = [ded[k] for k in sorted(ded)]
        self.cache[sym] = ((day, sz), rows)
        return rows


class Norms:
    """Same-slot 1m volume norms from the collector's 1m store (prior sessions) for replay/fallback rvol."""

    def __init__(self, c):
        self.dir, self.cache = X(c["bars_store_dir"]), {}

    def get(self, sym, day_iso):
        if sym in self.cache:
            return self.cache[sym]
        d = T.jload(self.dir / f"{sym}-1m.json", {}) or {}
        by, sess = {}, set()
        for b in d.get("bars") or []:
            if b.get("d") == day_iso or b.get("slot") is None:
                continue
            sess.add(b.get("d"))
            by.setdefault(int(b["slot"]), []).append(float(b.get("v") or 0))
        n = max(len(sess), 1)
        slot_mean = {k: sum(v) / n for k, v in by.items()}
        cum, run = {}, 0.0
        for k in sorted(slot_mean):
            run += slot_mean[k]
            cum[k] = run
        self.cache[sym] = (slot_mean, cum)
        return self.cache[sym]


def bar_rvols(norms, sym, day_iso, bars, i):
    try:
        slot_mean, cum = norms.get(sym, day_iso)
        b = bars[i]
        s = int(b.get("slot"))
        r1 = (float(b["v"]) / slot_mean[s]) if slot_mean.get(s) else None
        cv = sum(float(x.get("v") or 0) for x in bars[: i + 1])
        rd = (cv / cum[s]) if cum.get(s) else None
        return (round(r1, 2) if r1 else None), (round(rd, 2) if rd else None)
    except Exception:
        return None, None


def merged_walls(c):
    """Freshest record per symbol across the mini's FA caches (same idea as livepage Walls.refresh)."""
    best = {}
    for src, p in c["wall_files"]:
        d = T.jload(X(p), None)
        if not isinstance(d, dict):
            continue
        fa = d.get("as_of") or d.get("as_of_pt")
        if src == "fa-walls-pulse":
            L = d.get("levels") if isinstance(d.get("levels"), dict) and "SPY" not in d else d
        elif src == "fa-focus-levels":
            L = d.get("levels") or {}
        elif src == "fa-levels":
            L = (d.get("payload") or {}).get("levels") or {}
        else:
            L = d.get("payload") or {}
        if not isinstance(L, dict):
            continue
        for sym, v in L.items():
            if not isinstance(v, dict) or not isinstance(sym, str) or not sym.isupper():
                continue
            lv = v.get("levels") if isinstance(v.get("levels"), dict) else v
            cw = lv.get("call_wall", lv.get("live_call_wall"))
            pw = lv.get("put_wall", lv.get("live_put_wall"))
            gf = lv.get("gamma_flip", lv.get("live_gamma_flip"))
            if cw is None and pw is None:
                continue
            t = iso_ep(v.get("as_of") or v.get("fetched_pt") or fa) or 0
            r = {"call_wall": None if cw is None else float(cw), "put_wall": None if pw is None else float(pw),
                 "gamma_flip": None if gf is None else round(float(gf), 2),
                 "gamma_flip_status": lv.get("gamma_flip_status") or v.get("gamma_flip_status"),
                 "source": src, "as_of_ep": t}
            if sym not in best or t > best[sym]["as_of_ep"]:
                best[sym] = r
    return best


def walls_view(w, px, now, c):
    if not w:
        return {"call_wall": None, "put_wall": None, "gamma_flip": None, "source": None, "as_of_pt": None,
                "age_min": None, "stale": True}
    age = (now - w["as_of_ep"]) / 60 if w["as_of_ep"] else None
    dist = lambda k: (round((k / px - 1) * 100, 2) if (k and px) else None)
    return {"call_wall": w["call_wall"], "put_wall": w["put_wall"], "gamma_flip": w["gamma_flip"],
            "gamma_flip_status": w["gamma_flip_status"],
            "call_wall_dist_pct": dist(w["call_wall"]), "put_wall_dist_pct": dist(w["put_wall"]),
            "gamma_flip_dist_pct": dist(w["gamma_flip"]),
            "source": w["source"], "as_of_pt": pt_str(w["as_of_ep"], "%a %-m/%-d %-I:%M %p PT") if w["as_of_ep"] else None,
            "age_min": None if age is None else round(age), "stale": age is None or age > c["walls_max_age_min"]}


class XNews:
    """Latest kept (not spam-filtered) X post per ticker from the x-on-surge archive. Read-only; never fetches X."""

    def __init__(self, c):
        self.root, self.lb = X(c["x_archive"]), c["news_lookback_min"] * 60
        self.key, self.posts = None, []

    def _load(self, day_iso):
        files = sorted(glob.glob(str(self.root / f"posts_raw/date={day_iso}/part-*.jsonl"))) + \
            sorted(glob.glob(str(self.root / f"item_filter/date={day_iso}/part-*.jsonl")))
        key = tuple((f, os.path.getsize(f)) for f in files)
        if key == self.key:
            return
        keep, posts = {}, []
        for f in files:
            if "/item_filter/" not in f:
                continue
            for ln in open(f):
                try:
                    r = json.loads(ln)
                    keep[r["item_id"]] = (not r.get("dropped"), r.get("credibility_tier"))
                except Exception:
                    continue
        for f in files:
            if "/posts_raw/" not in f:
                continue
            for ln in open(f):
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                k = keep.get("x:" + str(r.get("post_id")))
                if not k or not k[0]:
                    continue
                syms = {s.strip().upper() for s in str(r.get("symbols") or "").split(",") if s.strip()}
                syms |= {str(s).upper().lstrip("$") for s in (r.get("cashtags") or []) if s}
                posts.append({"ep": (r.get("created_ns") or 0) / 1e9, "ing": (r.get("ingest_ts_ns") or 0) / 1e9, "syms": syms, "tier": k[1],
                              "text": " ".join(str(r.get("text") or "").split()), "handle": r.get("author_handle"),
                              "id": r.get("post_id")})
        self.key, self.posts = key, posts

    def latest(self, sym, now):
        day_iso = datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d")
        try:
            self._load(day_iso)
        except Exception:
            pass
        hits = [p for p in self.posts if sym in p["syms"] and now - self.lb <= p["ep"] <= now and p["ing"] <= now]
        base = {"source": "X via x-on-surge archive (fetched on surges only; unverified raw X)", "lookback_min": self.lb // 60}
        if not hits:
            return dict(base, status="no news found", headline=None)
        tier_rank = lambda t: int(t[1:]) if t and t[1:].isdigit() else 9
        hits.sort(key=lambda p: (tier_rank(p["tier"]), -p["ep"]))
        p = hits[0]
        return dict(base, status="found", headline=p["text"][:240], author=p["handle"], tier=p["tier"],
                    time_pt=pt_str(p["ep"]), age_min=round((now - p["ep"]) / 60), url=f"https://x.com/i/status/{p['id']}",
                    n_posts=len(hits))


class News:
    """Alpaca/Benzinga headlines (~/oid-desk/state/news/news-YYYYMMDD.jsonl from com.oid.desk.news) for the last
    news_lookback_min, latest 1-2, plus rolling net sentiment (sentiment-YYYYMMDD.jsonl, headlines +-2, X x0.5).
    Falls back to the X archive post (XNews). Read-only; never fetches anything."""

    def __init__(self, c):
        self.dir, self.lb, self.x = X(c.get("news_dir", "~/oid-desk/state/news")), c["news_lookback_min"] * 60, XNews(c)
        self.k = {}
        self.rows = {}

    def _rows(self, name, day):
        p = self.dir / f"{name}-{day}.jsonl"
        try:
            k = (p.name, p.stat().st_size)
        except OSError:
            return []
        if self.k.get(name) == k:
            return self.rows[name]
        out = {}
        for ln in p.read_text(errors="replace").splitlines():
            try:
                r = json.loads(ln)
                out[(r.get("kind"), r.get("id"))] = r  # last write per id wins (updates)
            except Exception:
                continue
        self.k[name], self.rows[name] = k, list(out.values())
        return self.rows[name]

    def latest(self, sym, now):
        day = datetime.fromtimestamp(now, PT).strftime("%Y%m%d")
        heads, net, n = [], 0.0, 0
        try:
            hs = [r for r in self._rows("news", day) if sym in (r.get("symbols") or []) and now - self.lb <= r.get("t", 0) <= now]
            hs.sort(key=lambda r: -r["t"])
            heads = [{"time_pt": r.get("time_pt"), "source": r.get("source"), "sent": (r.get("sent_by") or {}).get(sym, r.get("sent")),
                      "headline": r.get("headline"), "url": r.get("url")} for r in hs[:2]]
            for r in self._rows("sentiment", day):
                if sym in (r.get("tickers") or r.get("symbols") or []) and now - self.lb <= r.get("t", 0) <= now:
                    net += float(r.get("weight", 1)) * float((r.get("sent") or {}).get(sym, r.get("doc") or 0))
                    n += 1
        except Exception:
            pass
        xs = self.x.latest(sym, now)
        base = {"source": "Alpaca news (Benzinga) via com.oid.desk.news; X via x-on-surge archive", "lookback_min": self.lb // 60,
                "net_sent_60m": round(net, 1), "n_scored_60m": n, "headlines": heads, "x": xs}
        if heads:
            return dict(base, status="found", headline=heads[0]["headline"], time_pt=heads[0]["time_pt"], url=heads[0]["url"])
        if xs.get("status") == "found":
            return dict(base, status="x_only", headline=None)
        return dict(base, status="no headline found", headline=None)


def news_line(nw):
    if not isinstance(nw, dict):
        return "no headline found"
    bits = []
    for h in nw.get("headlines") or []:
        s = h.get("sent")
        bits.append(f"{h.get('time_pt')} {h.get('source')} [{'+' if (s or 0) > 0 else ''}{s}] {str(h.get('headline'))[:110]}")
    out = ("news: " + " | ".join(bits)) if bits else f"no headline found ({nw.get('lookback_min', 60)}m)"
    x = nw.get("x") or {}
    if not bits and x.get("status") == "found":
        out += f"; X @{x.get('author')}: {str(x.get('headline'))[:90]}"
    if nw.get("n_scored_60m"):
        v = nw.get("net_sent_60m")
        out += f"; news sentiment 60m {'+' if v > 0 else ''}{v} ({nw['n_scored_60m']} items)"
    return out


# ---------- engine ----------
class Engine:
    def __init__(self, c, dry, state_dir=None, persist=True):
        self.c, self.dry, self.persist = c, dry, persist
        self.sd = X(state_dir or c["state_dir"])
        if persist:
            self.sd.mkdir(parents=True, exist_ok=True)
        self.st = (T.jload(self.sd / "state.json", {}) or {}) if persist else {}
        self.prev = {}  # sym -> last price seen
        self.seen_bar = {}  # sym -> newest closed 1m bar already judged for wall crosses
        self.wst = {}  # sym:wall -> confirmed side / last alert (wall-cross debounce)
        self.wall_supp = []  # suppressed wall crosses (logged)

    def _day(self, now):
        d = datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d")
        if self.st.get("date") != d:
            self.st = {"date": d, "count": 0, "last": {}}
        return d

    def _rv5(self, sym, closed, now):
        """5-min rvol = volume of the last 5 closed 1-min bars / same-slot norm (collector 1m store, prior sessions)."""
        try:
            if not hasattr(self, "_norms"):
                self._norms = Norms(self.c)
            slot_mean, _ = self._norms.get(sym, datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d"))
            last5 = closed[-5:]
            v = sum(float(b.get("v") or 0) for b in last5)
            n = sum(slot_mean.get(int(b.get("slot")), 0) for b in last5 if b.get("slot") is not None)
            return round(v / n, 2) if n else None
        except Exception:
            return None

    def _wall_check(self, sym, name, k, closed, last, lo, hi, rv1, now):
        """2026-10-20 wall-cross debounce (QQQ 719 put wall pinged 11:25 down -0.14% and 11:28 back up +0.04% at 0.3x):
        confirmed side change only = two consecutive 1-min closes >= wall_buffer_pct beyond the wall, or a 5-min close
        beyond it; wall_cooldown_min per ticker per wall; a re-cross back the other way within wall_recross_suppress_min
        is suppressed; dropped when the move off the 30-min high/low < wall_min_move_pct AND 1-min rvol < wall_min_rvol."""
        c = self.c
        buf = float(c.get("wall_buffer_pct", 0.1)) / 100
        up_k, dn_k = k * (1 + buf), k * (1 - buf)
        c1, c2 = float(closed[-1]["c"]), float(closed[-2]["c"])
        side1 = "above" if (c1 >= up_k and c2 >= up_k) else "below" if (c1 <= dn_k and c2 <= dn_k) else None
        side5 = None
        if int(round(closed[-1]["ep"] + 60)) % 300 == 0:  # this 1-min bar completes a 5-min bar; its close = 5-min close
            side5 = "above" if c1 >= up_k else "below" if c1 <= dn_k else None
        side = side1 or side5
        key = f"{sym}:{name}"
        st = self.wst.get(key)
        if st is None or abs(st["k"] - k) > 1e-9:  # first look (or wall moved): learn the side, never alert
            self.wst[key] = {"k": k, "side": "above" if c1 >= k else "below", "last_alert": 0.0, "last_dir": None}
            return None
        if side is None or side == st["side"]:
            return None
        st["side"] = side
        direction = "up" if side == "above" else "down"
        why = None
        if now - st["last_alert"] < float(c.get("wall_cooldown_min", 20)) * 60:
            why = "cooldown"
        elif st["last_dir"] and st["last_dir"] != direction and now - st["last_alert"] < float(c.get("wall_recross_suppress_min", 60)) * 60:
            why = "recross"
        else:
            mv = ((last / lo - 1) * 100) if (direction == "up" and lo) else ((last / hi - 1) * 100) if hi else 0.0
            rv5 = self._rv5(sym, closed, now)
            vol_ok = (rv1 is not None and float(rv1) >= float(c.get("wall_min_rvol", 1.5))) or \
                     (rv5 is not None and rv5 >= float(c.get("wall_min_rvol5", 1.2)))
            # 2026-10-20 wall3: BOTH required = move >= wall_min_move_pct off the 30-min high/low AND (rvol1 >= 1.5x or rvol5 >= 1.2x)
            if abs(mv) < float(c.get("wall_min_move_pct", 0.5)) or not vol_ok:
                why = f"small (move {mv:+.2f}% rvol1 {rv1} rvol5 {rv5})"
        if why:
            self.wall_supp.append({"sym": sym, "wall": name, "k": k, "dir": direction, "why": why, "t": now})
            return None
        st["last_alert"], st["last_dir"] = now, direction
        p0, e0 = (float(closed[-3]["c"]), closed[-3]["ep"] + 60) if side1 else (c2, closed[-2]["ep"] + 60)
        return (direction, f"{name}_cross_{direction}", (c1 / p0 - 1) * 100, p0, e0)

    def evaluate(self, sym, bars, last, last_ep, now, walls, rv1, rvd, news, day_hi=None, day_lo=None):
        """bars: today's 1m bars up to now. Returns an alert dict or None (debounce applied)."""
        c = self.c
        self._day(now)
        w0 = now - c["window_min"] * 60
        win = [b for b in bars if b["ep"] >= w0 - 60 and b["ep"] + 60 <= now + 1]
        if last is None or not win:
            prev = self.prev.get(sym)
            self.prev[sym] = last
            return None
        thr = float(c["per_symbol_move_pct"].get(sym, c["move_pct"]))
        lo_b = min(win, key=lambda b: b["l"]); hi_b = max(win, key=lambda b: b["h"])
        lo, hi = min(lo_b["l"], last), max(hi_b["h"], last)
        fired = []
        up = (last / lo - 1) * 100 if lo else 0
        dn = (last / hi - 1) * 100 if hi else 0
        if up >= thr and lo_b["l"] <= last:
            fired.append(("up", "move_3pct", up, lo_b["l"], lo_b["ep"]))
        if -dn >= thr:
            fired.append(("down", "move_3pct", dn, hi_b["h"], hi_b["ep"]))
        self.prev[sym] = last
        wv = walls_view(walls, last, now, c)
        closed = [b for b in bars if b["ep"] + 60 <= now + 1]
        if c["wall_cross"] and len(closed) >= 3 and not wv["stale"] and self.seen_bar.get(sym) != closed[-1]["ep"]:
            self.seen_bar[sym] = closed[-1]["ep"]  # B is judged on 1-min closes, once per new bar (no tick chatter)
            for name, k in (("call_wall", wv["call_wall"]), ("put_wall", wv["put_wall"])):
                if not k:
                    continue
                f = self._wall_check(sym, name, float(k), closed, last, lo, hi, rv1, now)
                if f:
                    fired.append(f)
        out = None
        for direction in ("up", "down"):
            fs = [f for f in fired if f[0] == direction]
            if not fs:
                continue
            key = f"{sym}:{direction}"
            if now - float(self.st["last"].get(key, 0)) < c["debounce_min"] * 60:
                wf = [f for f in fs if f[1] != "move_3pct"]
                key = f"{sym}:{direction}:" + ",".join(sorted(f[1] for f in wf))
                if not (c.get("wall_cross_own_debounce") and wf) or now - float(self.st["last"].get(key, 0)) < c["debounce_min"] * 60:
                    continue
                fs = wf  # wall cross keyed separately (opt-in)
            if self.st["count"] >= c["max_per_day"]:
                continue
            mv = next((f for f in fs if f[1] == "move_3pct"), None)
            if mv:
                from_px, from_ep = mv[3], mv[4]
            else:  # wall cross only: report move off the window extreme
                from_px, from_ep = (lo_b["l"], lo_b["ep"]) if direction == "up" else (hi_b["h"], hi_b["ep"])
            self.st["last"][key] = now
            self.st["count"] += 1
            out = self.build(sym, direction, [f[1] for f in fs], from_px, from_ep, last, last_ep or now, now, wv,
                             rv1, rvd, news(sym, now) if callable(news) else news, day_hi, day_lo)
            break  # one alert per ticker per check
        return out

    def build(self, sym, direction, triggers, from_px, from_ep, to_px, to_ep, now, wv, rv1, rvd, nw, day_hi, day_lo):
        mv = round((to_px / from_px - 1) * 100, 2) if from_px else None
        trig = [t.replace("move_3pct", f"move_{self.c['per_symbol_move_pct'].get(sym, self.c['move_pct']):g}pct_{self.c['window_min']}m") for t in triggers]
        lv = []
        for n, k in (("CW", wv.get("call_wall")), ("PW", wv.get("put_wall")), ("flip", wv.get("gamma_flip"))):
            if k:
                lv.append(f"{n} {k:g}")
        summary = (f"{sym} {'+' if (mv or 0) >= 0 else ''}{mv}% {from_px:g} ({pt_str(from_ep) if from_ep else '?'}) -> "
                   f"{to_px:g} ({pt_str(to_ep)}); {', '.join(trig)}; " + (" / ".join(lv) or "no walls") +
                   ("" if not wv.get("stale") else " (walls stale)") +
                   f"; rvol 1m {rv1 if rv1 is not None else '?'} day {rvd if rvd is not None else '?'}; " +
                   news_line(nw))
        aid = f"mover-{sym}-{direction}-{datetime.fromtimestamp(now, PT):%Y%m%dT%H%M%S}"
        return {"event_type": "mover_alert", "alert_id": aid, "symbol": sym, "ticker": sym, "seat_id": None,
                "direction": direction, "triggers": trig, "move_pct": mv,
                "from_price": round(from_px, 4) if from_px else None, "from_time_pt": pt_str(from_ep) if from_ep else None,
                "to_price": round(to_px, 4), "to_time_pt": pt_str(to_ep), "window_min": self.c["window_min"],
                "day_high": day_hi, "day_low": day_lo,
                "walls": wv, "rvol_1m": rv1, "rvol_day": rvd, "news": nw, "summary": summary,
                "dry_run": self.dry, "test": False, "tag": "mover-alert", "trade_action": "none",
                "mandate": "research/alert only - not an order", "writer": VERSION,
                "time_pt": pt_str(now, "%Y-%m-%d %I:%M:%S %p PT"), "data_stamp": pt_str(to_ep, "%Y-%m-%d %I:%M:%S %p PT")}

    def save(self):
        if self.persist:
            tmp = self.sd / "state.json.tmp"
            tmp.write_text(json.dumps(self.st))
            tmp.replace(self.sd / "state.json")


def livepage_rows(c):
    try:
        with urllib.request.urlopen(c["livepage_state"], timeout=3) as r:
            d = json.loads(r.read())
        return {x.get("sym"): x for x in d.get("rows") or [] if x.get("sym")}
    except Exception:
        return {}


def post(body, c, log):
    env, why = T.read_env(c["env_file"])
    if not env:
        st = f"not_sent:{why}"
    else:
        try:
            st = T.send(body, env, timeout=c["timeout_s"])
        except Exception as e:
            st = f"error:{type(e).__name__}"  # never log URL/key
    try:
        with open(log, "a") as f:
            f.write(json.dumps({"pt": pt_str(time.time(), "%Y-%m-%d %I:%M:%S %p PT"), "alert_id": body.get("alert_id"),
                                "ticker": body.get("ticker"), "direction": body.get("direction"),
                                "test": body.get("test"), "status": st}) + "\n")
    except Exception:
        pass
    return st


def in_rth(c, now):
    n = datetime.fromtimestamp(now, PT)
    if n.weekday() >= 5:
        return False
    a, b = c["rth_pt"]
    o = datetime.strptime(a, "%H:%M").replace(year=n.year, month=n.month, day=n.day, tzinfo=PT).timestamp()
    return o + c["skip_open_min"] * 60 <= now and n.strftime("%H:%M") <= b


def check_all(eng, c, bars, news, now):
    day = datetime.fromtimestamp(now, PT).strftime("%Y%m%d")
    rows, walls = livepage_rows(c), merged_walls(c)
    q = ((T.jload(X(c["quotes"]), {}) or {}).get("symbols") or {})
    out = []
    for sym in universe(c):
        r = rows.get(sym) or {}
        last, lep = r.get("last"), iso_ep(r.get("last_pt"))
        if last is None and sym in q and q[sym].get("fresh"):
            last, lep = q[sym].get("last"), now - float(q[sym].get("age_s") or 0)
        if last is None or (lep and now - lep > c["max_quote_age_s"]):
            continue
        b = bars.get(sym, day)
        a = eng.evaluate(sym, b, float(last), lep, now, walls.get(sym), r.get("rvol"), r.get("day_rvol"),
                         news.latest, r.get("hi"), r.get("lo"))
        if a:
            out.append(a)
    return out


def loop(c_path, dry):
    c = cfg_load(c_path)
    eng, bars, news = Engine(c, dry), Bars(c), News(c)
    sd = eng.sd
    print(f"{pt_str(time.time(), '%H:%M:%S')} mover-alert start env_mode={'dry' if dry else 'live'} config_live={c.get('live')}", flush=True)
    while True:
        now = time.time()
        c = cfg_load(c_path); eng.c = c
        status = {"pt": pt_str(now, "%Y-%m-%d %I:%M:%S %p PT"), "mode": "live" if (not dry and c.get("live")) else "dry",
                  "writer": VERSION}
        if c.get("enabled") and in_rth(c, now):
            try:
                alerts = check_all(eng, c, bars, news, now)
                for a in alerts:
                    live = (not dry) and c.get("live")
                    a["dry_run"] = not live
                    a["sent_status"] = post(a, c, sd / "notify.jsonl") if live else "dry"
                    with open(sd / "alerts.jsonl", "a") as f:
                        f.write(json.dumps(a) + "\n")
                    print(f"{pt_str(now, '%H:%M:%S')} ALERT {a['summary'][:160]} -> {a['sent_status']}", flush=True)
                if eng.wall_supp:
                    with open(sd / "wall-suppressed.jsonl", "a") as f:
                        for w in eng.wall_supp:
                            f.write(json.dumps(dict(w, pt=pt_str(w["t"], "%Y-%m-%d %I:%M:%S %p PT"))) + "\n")
                    eng.wall_supp = []
                eng.save()
                status.update(state="rth", alerts_today=eng.st.get("count"), last_tick_alerts=len(alerts))
            except Exception as e:
                status.update(state="error", err=f"{type(e).__name__}: {e}"[:200])
                print(f"{pt_str(now, '%H:%M:%S')} error {status['err']}", flush=True)
            sleep = c["interval_s"]
        else:
            status.update(state="idle (outside RTH / weekend / disabled)")
            sleep = 60
        try:
            (sd / "status.json").write_text(json.dumps(status))
        except Exception:
            pass
        time.sleep(sleep)


def replay(c, sym, day_iso):
    """Walk today's 1m bars minute by minute (close = last). Uses current FA walls cache and the X archive as of each minute."""
    day = day_iso.replace("-", "")
    bars = Bars(c).get(sym, day)
    norms, news, walls = Norms(c), News(c), merged_walls(c).get(sym)
    eng = Engine(c, dry=True, persist=False)
    eng._day(bars[0]["ep"] if bars else time.time())
    out = []
    for i, b in enumerate(bars):
        now = b["ep"] + 60
        if not in_rth(c, now):
            continue
        rv1, rvd = bar_rvols(norms, sym, day_iso, bars, i)
        hi = max(x["h"] for x in bars[: i + 1]); lo = min(x["l"] for x in bars[: i + 1])
        a = eng.evaluate(sym, bars[: i + 1], b["c"], now, now, walls, rv1, rvd, news.latest, hi, lo)
        if a:
            out.append(a)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "mover-alert.json"))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--loop", action="store_true"); g.add_argument("--once", action="store_true")
    g.add_argument("--replay", metavar="SYM"); g.add_argument("--test", metavar="SYM")
    ap.add_argument("--date", default=datetime.now(PT).strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = cfg_load(a.config)
    if a.loop:
        dry = a.dry_run or os.environ.get("OID_MOVER_MODE") != "live"
        return loop(a.config, dry)
    if a.once:
        eng = Engine(c, dry=True, persist=False)
        print(json.dumps(check_all(eng, c, Bars(c), News(c), time.time()), indent=1)); return 0
    if a.replay:
        al = replay(c, a.replay.upper(), a.date)
        print(json.dumps({"symbol": a.replay.upper(), "date": a.date, "alerts": len(al),
                          "fired": [x["summary"] for x in al], "first_payload": al[0] if al else None}, indent=1))
        return 0
    if a.test:
        al = replay(c, a.test.upper(), a.date)
        if al:
            body = dict(next((x for x in al if x["direction"] == "up"), al[0]))
        else:
            now = time.time()
            body = Engine(c, True, persist=False).build(a.test.upper(), "up", ["test"], 1.0, now, 1.0, now, now,
                                                        walls_view(None, 1, now, c), None, None, {"status": "no headline found", "headlines": []}, None, None)
        body.update(test=True, dry_run=False, tag="mover-alert-TEST", trade_action="none",
                    alert_id="TEST-" + body["alert_id"], summary="TEST (replay of " + a.date + ", not live) - " + body["summary"],
                    time_pt=pt_str(time.time(), "%Y-%m-%d %I:%M:%S %p PT"))
        sd = X(c["state_dir"]); sd.mkdir(parents=True, exist_ok=True)
        st = post(body, c, sd / "notify.jsonl")
        print(json.dumps({"sent": True, "status": st, "payload": body}, indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main())
