#!/usr/bin/env python3
"""Whale Flow collector (CB-WHALE-V1, Jeffrey 2026-10-09). Research/paper only: never orders, never elevates.

Source: Unusual Whales REST /api/option-trades/flow-alerts (OPRA-derived sweeps / blocks / repeated hits),
auth = UW_API_KEY env var (desk-injected secret). Universe = Chart Bot 37 names (levels/latest/levels.json).

  python3 whale_flow.py --once        # one poll (backfills today's session if the log is empty) + summary
  python3 whale_flow.py --loop        # poll every 60s during RTH (6:30 AM-1:00 PM PT weekdays), republish <= every 5 min
  python3 whale_flow.py --summarize   # rebuild latest summary from today's log only

Outputs: chart-bot/whale-flow/<YYYY-MM-DD>/trades.jsonl (deduped by UW alert id), .../summary.json,
         chart-bot/whale-flow/latest/summary.json (read by scripts/package_prod_dist.py -> Evidence > Whale flow),
         chart-bot/whale-flow/status.json (last poll / errors / last publish).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HERE = Path(__file__).resolve().parent
DESK = HERE.parents[1]
API = "https://api.unusualwhales.com/api/option-trades/flow-alerts"
MIN_PREMIUM = int(os.environ.get("WHALE_MIN_PREMIUM", "100000"))
POLL_S = 60
PUBLISH_EVERY_S = 300
RTH = (dt.time(6, 30), dt.time(13, 0))
CONFIG_VERSION = "CB-WHALE-V1"


def now_pt() -> dt.datetime:
    return dt.datetime.now(PT)


def fmt_pt(t: dt.datetime) -> str:
    return t.astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT")


def universe() -> list[str]:
    L = json.loads((DESK / "chart-bot/levels/latest/levels.json").read_text())
    return [n["symbol"] for n in L["names"]]


def fetch(params: dict, base: str = API) -> list[dict]:
    key = os.environ.get("UW_API_KEY")
    if not key:
        raise RuntimeError("UW_API_KEY not set")
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
        return (d.get("data") or []) if isinstance(d, dict) else (d or [])


ETF_MIN_PREMIUM = int(os.environ.get("WHALE_ETF_MIN_PREMIUM", "500000"))
ETFS = ("SPY", "QQQ")
CHUNK = 9  # UW silently drops symbols past ~20 in ticker_symbol; keep groups small


def groups(tickers: list[str]) -> list[tuple[list[str], int]]:
    etf = [t for t in tickers if t in ETFS]
    rest = [t for t in tickers if t not in ETFS]
    g = [(etf, ETF_MIN_PREMIUM)] if etf else []
    return g + [(rest[i:i + CHUNK], MIN_PREMIUM) for i in range(0, len(rest), CHUNK)]


def pull(tickers: list[str], newer_than: str | None, floor_utc: str) -> list[dict]:
    out = []
    for g, mp in groups(tickers):
        out += pull_group(g, mp, newer_than, floor_utc)
    return out


def pull_group(tickers: list[str], min_prem: int, newer_than: str | None, floor_utc: str) -> list[dict]:
    """Page backwards from now until newer_than (or the session floor). Max 15 pages per group per poll."""
    out, older = [], None
    stop = newer_than or floor_utc
    for _ in range(15):
        p = {"limit": 200, "ticker_symbol": ",".join(tickers), "min_premium": min_prem, "newer_than": stop}
        if older:
            p["older_than"] = older
        rows = fetch(p)
        out += rows
        if len(rows) < 200:
            break
        older = min(r["created_at"] for r in rows)
    return out


# ---------- raw prints (UW /api/stock/{T}/flow-recent) ----------
# Flow alerts miss many big single/multi-leg block prints (e.g. AMZN 9:38 AM PT 10/9 260/275 call spread,
# $41.5M, no alert). So we also poll raw prints >= $1M ($5M SPY/QQQ): busiest names every minute, the
# rest round-robin. flow-recent returns only the latest 50 prints >= min_premium (no paging), so a
# busy name must be polled before 50 newer big prints pile up.
PRINT_MIN = int(os.environ.get("WHALE_PRINT_MIN_PREMIUM", "1000000"))
PRINT_ETF_MIN = int(os.environ.get("WHALE_PRINT_ETF_MIN_PREMIUM", "5000000"))
BIG_MIN, BIG_ETF_MIN = 1_000_000, 5_000_000
HOT = ("TSLA", "NVDA", "MU", "AMZN", "SPY", "QQQ")
ROTATE_PER_MIN = 8
_rot = {"i": 0}


def print_targets(tickers: list[str], all_names: bool = False) -> list[str]:
    if all_names:
        return tickers
    hot = [t for t in tickers if t in HOT]
    rest = [t for t in tickers if t not in HOT]
    i = _rot["i"] % max(1, len(rest))
    pick = (rest[i:] + rest[:i])[:ROTATE_PER_MIN]
    _rot["i"] = i + ROTATE_PER_MIN
    return hot + pick


def pull_prints(tickers: list[str]) -> list[dict]:
    out = []
    for t in tickers:
        mp = PRINT_ETF_MIN if t in ETFS else PRINT_MIN
        try:
            out += fetch({"min_premium": mp}, f"https://api.unusualwhales.com/api/stock/{t}/flow-recent")
        except Exception:  # noqa: BLE001  one bad symbol never stops the poll
            continue
    return out


COND = {"ml": "multi-leg print", "tl": "stock-tied print"}


def normalize_print(a: dict, lv: dict) -> dict:
    ex = dt.datetime.fromisoformat(a["executed_at"].replace("Z", "+00:00"))
    tags = a.get("tags") or []
    side = "ask" if "ask_side" in tags else "bid" if "bid_side" in tags else "mid/mixed"
    cond = (a.get("upstream_condition_detail") or "").lower()
    multileg = cond[:2] in ("ml", "tl")
    kind = COND.get(cond[:2]) or ("sweep print" if cond == "isoc" else "late print" if cond == "late" else "block print")
    typ = a.get("option_type")
    lean = "neutral" if multileg or side == "mid/mixed" else ("bullish" if (typ == "call") == (side == "ask") else "bearish")
    size, oi = a.get("size") or 0, a.get("open_interest") or 0
    exp = a.get("expiry")
    try:
        dte = (dt.date.fromisoformat(exp) - ex.astimezone(PT).date()).days
    except Exception:  # noqa: BLE001
        dte = None
    rec = {
        "id": "p:" + str(a.get("id")), "src": "print", "created_at": ex.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "time_pt": ex.astimezone(PT).strftime("%-I:%M:%S %p"), "ticker": a.get("underlying_symbol"), "type": typ,
        "strike": f(a.get("strike")), "expiry": exp, "dte": dte, "chain": a.get("option_chain_id"), "side": side,
        "ask_share": None, "kind": kind, "cond": cond, "multileg": multileg, "size": size, "price": f(a.get("price")),
        "premium": round(f(a.get("premium")) or 0), "ask_prem": None, "bid_prem": None, "volume": a.get("volume"), "oi": oi,
        "vol_oi": round((a.get("volume") or 0) / oi, 2) if oi else None, "opening": bool(oi and size > oi),
        "spot": f(a.get("underlying_price")), "iv": round(f(a.get("implied_volatility")) or 0, 4),
        "delta": round(f(a.get("delta")) or 0, 3), "rule": "print", "trade_count": 1, "lean": lean,
        "exchange": a.get("exchange"),
    }
    relabel(rec)
    rec["tags"] = tags_for(rec, lv)
    return rec


def pair_combos(recs: list[dict]) -> None:
    """Multi-leg prints at the same instant + size on one ticker = one combo; describe the other legs."""
    grp = {}
    for r in recs:
        if r.get("multileg"):
            grp.setdefault((r["ticker"], r["created_at"][:19], r["size"]), []).append(r)
    for legs in grp.values():
        if len(legs) < 2:
            continue
        for r in legs:
            others = [o for o in legs if o is not r]
            r["combo"] = "; ".join(f"{'bought' if o['side']=='ask' else 'sold' if o['side']=='bid' else 'traded'} "
                                   f"{o['size']:,} {o['expiry']} {_g(o['strike'])}{o['type'][0].upper()} ${o['premium']/1e6:.2f}M"
                                   for o in others)


def is_big(r: dict) -> bool:
    return r["premium"] >= (BIG_ETF_MIN if r["ticker"] in ETFS else BIG_MIN)


def nearest_level(r: dict, lv: dict) -> str:
    L, s = dict(lv.get(r["ticker"]) or {}), r.get("spot")
    if not s:
        return ""
    W = walls_at(r["ticker"])
    if W:
        L["cw"], L["pw"], L["flip"] = W["cw"], W["pw"], W["flip"]
    cands = []
    for k, nm in (("cw", "call wall"), ("pw", "put wall"), ("flip", "gamma flip"), ("bull", "4h bull trigger"),
                  ("bear", "4h bear trigger"), ("breakout", "daily breakout")):
        if L.get(k) is not None:
            cands.append((nm, L[k]))
    cands += [("daily resistance", x) for x in L.get("res") or []] + [("daily support", x) for x in L.get("sup") or []]
    if not cands:
        return ""
    nm, px = min(cands, key=lambda c: abs(c[1] - s))
    d = (s - px) / s * 100
    leg = {"call wall": "cw", "put wall": "pw", "gamma flip": "flip"}.get(nm)
    stamp = (" " + wall_stamp(W[leg + "_ts"])) if leg and W and W.get(leg + "_ts") else ""
    return f"spot {_g(s)} is {abs(d):.1f}% {'above' if d >= 0 else 'below'} {nm} {_g(px)}{stamp}"


def ping_line(r: dict, lv: dict) -> str:
    relabel(r)
    verb = {"ask": "bought", "bid": "sold"}.get(r["side"], "traded (mid)")
    c = f"{r['size']:,} {r['ticker']} {r['expiry']} {_g(r['strike'])} {r['type']}s"
    px = f" @ {_g(r['price'])}" if r.get("price") else ""
    pre = "[NOT DIRECTIONAL - likely closing] " if r["lean"] in CLOSING_LEANS else ""
    bits = [f"{pre}{r['time_pt']} PT {r['ticker']}: {verb} {c}{px} = ${r['premium']/1e6:.2f}M ({r['kind']}, lean: {r['lean']})"]
    bits.append(f"{r['badge']} (size {r['size']:,} vs OI {r.get('oi') or 0:,})")
    if r.get("combo"):
        bits.append("other leg(s): " + r["combo"])
    nl = nearest_level(r, lv)
    if nl:
        bits.append(nl)
    return " · ".join(bits)


def append_big(d: dt.date, recs: list[dict], backfill: bool = False) -> int:
    p = day_dir(d) / "big_trades.jsonl"
    have = set()
    n = 0
    if p.is_file():
        for line in p.read_text().splitlines():
            try:
                have.add(json.loads(line)["id"]); n += 1
            except (ValueError, KeyError):
                pass
    add = 0
    # one queue line per combo: keep only the largest-premium leg (its "combo" text names the other legs)
    best = {}
    for r in recs:
        if r.get("combo"):
            k = (r["ticker"], r["created_at"][:19], r["size"])
            if k not in best or r["premium"] > best[k]["premium"]:
                best[k] = r
    with open(p, "a") as fh:
        for r in sorted(recs, key=lambda r: r["created_at"]):
            if r["id"] in have or not is_big(r):
                continue
            if r.get("combo") and best.get((r["ticker"], r["created_at"][:19], r["size"])) is not r:
                continue
            n += 1
            add += 1
            fh.write(json.dumps(dict(r, seq=n, queued_pt=fmt_pt(now_pt()), backfill=backfill), ensure_ascii=False) + "\n")
    return add


def pending_pings(mark: bool, directional_only: bool = False) -> int:
    d = now_pt().date()
    cur_p = HERE / "ping_cursor.json"
    cur = json.loads(cur_p.read_text()) if cur_p.is_file() else {}
    last = cur.get("last_seq", 0) if cur.get("date") == d.isoformat() else 0
    p = day_dir(d) / "big_trades.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() else []
    new = [r for r in rows if r.get("seq", 0) > last]
    lv = load_levels()
    ingest_walls()
    shown = 0
    for r in new:
        relabel(r)
        if directional_only and r["lean"] not in ("bullish", "bearish"):
            continue
        print(ping_line(r, lv))
        shown += 1
    if new and not shown:
        print(f"({len(new)} new big trades, none directional)")
    if not new:
        print(f"(no new big trades since cursor seq {last} on {d.isoformat()})")
    if mark and new:
        cur_p.write_text(json.dumps({"date": d.isoformat(), "last_seq": max(r["seq"] for r in new),
                                     "marked_pt": fmt_pt(now_pt())}, indent=1))
    return 0


# ---------- lean (v2, Jeffrey/Hal 2026-10-09) ----------
# Directional only for ask-side buys or OPENING bid-side sales. A bid-side sale with size <= OI and no UW
# opening flag is most likely closing / profit-taking / an overwrite -> neutral. Mid/mixed + multi-leg -> neutral.
CLOSING_LEANS = ("closing / overwrite", "closing")


def relabel(r: dict) -> dict:
    size, oi = r.get("size") or 0, r.get("oi") or 0
    if "uw_opening" not in r and r.get("src", "alert") == "alert":  # pre-v2 records: recover UW flag
        r["uw_opening"] = bool(r.get("opening")) and not (oi and size > oi)
    opening = bool(r.get("uw_opening")) or bool(oi and size > oi) or (not oi and size > 0)
    r["opening"] = opening
    side, typ = r.get("side"), r.get("type")
    if r.get("multileg") or side == "mid/mixed":
        r["lean"], r["badge"] = "neutral", ("opening" if opening else "size ≤ OI")
    elif side == "ask":
        r["lean"] = "bullish" if typ == "call" else "bearish"
        r["badge"] = "opening" if opening else "size ≤ OI"
    elif opening:
        r["lean"] = "bearish" if typ == "call" else "bullish"
        r["badge"] = "opening"
    else:
        r["lean"] = "closing / overwrite" if typ == "call" else "closing"
        r["badge"] = "likely closing"
    return r


# ---------- levels / tagging ----------
def load_levels() -> dict:
    lv = {}
    try:
        L = json.loads((DESK / "chart-bot/levels/latest/levels.json").read_text())
        for n in L["names"]:
            sr = n.get("sr") or {}
            lv.setdefault(n["symbol"], {}).update({
                "res": [x["price"] for x in sr.get("resistance", [])[:2]],
                "sup": [x["price"] for x in sr.get("support", [])[:2]],
                "breakout": n.get("breakout_trigger"), "inval": n.get("invalidation"),
                "buy": (n.get("fib") or {}).get("buy_zone"), "pull": n.get("pullback_zone"),
            })
    except Exception:  # noqa: BLE001
        pass
    try:
        S = json.loads((DESK / "chart-bot/setups_4h/latest/setups.json").read_text())
        for n in S["names"]:
            op = n.get("options") or {}
            lv.setdefault(n["symbol"], {}).update({
                "bull": n.get("bull_trigger"), "bear": n.get("bear_trigger"),
            })
    except Exception:  # noqa: BLE001
        pass
    return lv


# ---------- FlashAlpha walls (time-stamped) ----------
# Cache-first: market-data/latest/fa-levels.json + fa-focus-levels.json (written by quotes/fa_focus_refresh.py,
# Rose/Hal routines). Every distinct snapshot seen is kept in <date>/walls.jsonl so each trade is tagged with
# the walls known at its time. Live top-up via the desk's own client (quotes/fa_focus_refresh.flow_levels)
# only for names with a big trade in the last 15 min whose freshest wall is > 10 min old; capped.
import re  # noqa: E402

WALL_MAX_AGE_S = 600
FA_LIVE_PER_CYCLE, FA_LIVE_PER_DAY, FA_MIN_REMAINING = 6, 120, 700
_walls = {"hist": {}, "loaded_for": None, "last_try": {}, "live_today": 0, "live_date": None}


def _epoch(x) -> float | None:
    if not x:
        return None
    x = str(x)
    try:
        return dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", x)
    if m:
        return dt.datetime.fromisoformat(f"{m[1]}T{m[2]}+00:00").timestamp()
    m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{1,2}):(\d{2})(?:-\d{1,2}:\d{2})? (AM|PM)", x)
    if m:
        h = int(m[2]) % 12 + (12 if m[4] == "PM" else 0)
        return dt.datetime.combine(dt.date.fromisoformat(m[1]), dt.time(h, int(m[3])), PT).timestamp()
    return None


def _num(v):
    v = f(v)
    return v if v else None


def _add_wall(sym, ts, cw, pw, flip, src, persist=True):
    if ts is None or (cw is None and pw is None):
        return
    h = _walls["hist"].setdefault(sym, [])
    if any(abs(w["ts"] - ts) < 1 and w["cw"] == cw and w["pw"] == pw for w in h):
        return
    w = {"sym": sym, "ts": ts, "cw": cw, "pw": pw, "flip": flip, "src": src}
    h.append(w)
    h.sort(key=lambda w: w["ts"])
    if persist:
        with open(day_dir(now_pt().date()) / "walls.jsonl", "a") as fh:
            fh.write(json.dumps(dict(w, as_of_pt=dt.datetime.fromtimestamp(ts, PT).strftime("%Y-%m-%d %-I:%M:%S %p PT"))) + "\n")


def ingest_walls() -> None:
    d = now_pt().date()
    if _walls["loaded_for"] != d:
        _walls["hist"], _walls["loaded_for"] = {}, d
        wp = day_dir(d) / "walls.jsonl"
        if wp.is_file():
            for line in wp.read_text().splitlines():
                try:
                    w = json.loads(line)
                    _add_wall(w["sym"], w["ts"], w["cw"], w["pw"], w["flip"], w["src"], persist=False)
                except (ValueError, KeyError):
                    pass
        try:  # today's FA wall rolls logged by quotes/focus_watch.py (partial: only the rolled leg)
            for line in (DESK / "cache/focus-watch-events.jsonl").read_text().splitlines():
                e = json.loads(line)
                if e.get("event") != "wall_roll" or e.get("session_date") != d.isoformat():
                    continue
                m = re.search(r"rolled [\d.]+ -> ([\d.]+) \(fa as_of ([^ )]+)", e.get("note") or "")
                if not m:
                    continue
                leg = {"call_wall": "cw", "put_wall": "pw"}.get(e.get("level_kind"))
                if leg:
                    v = float(m[1])
                    _add_wall(e["symbol"], _epoch(m[2]) or e.get("epoch"), v if leg == "cw" else None,
                              v if leg == "pw" else None, None, "focus-watch wall_roll log", persist=False)
        except Exception:  # noqa: BLE001
            pass
        try:  # oldest baseline: setups_4h cached options (Oct 8 snapshot or this morning)
            S = json.loads((DESK / "chart-bot/setups_4h/latest/setups.json").read_text())
            for n in S["names"]:
                op = n.get("options") or {}
                _add_wall(n["symbol"], _epoch(op.get("as_of")), _num(op.get("call_wall")), _num(op.get("put_wall")),
                          _num(op.get("gamma_flip")), "setups_4h cache", persist=False)
        except Exception:  # noqa: BLE001
            pass
    md = DESK / "market-data" / "latest"
    for fn, getter in (("fa-levels.json", lambda d: (d.get("payload") or {}).get("levels") or {}),
                       ("fa-focus-levels.json", lambda d: d.get("levels") or {})):
        try:
            for sym, v in getter(json.loads((md / fn).read_text())).items():
                _add_wall(sym, _epoch(v.get("as_of")), _num(v.get("call_wall")), _num(v.get("put_wall")),
                          _num(v.get("gamma_flip")), f"desk cache {fn}")
        except Exception:  # noqa: BLE001
            pass


def walls_at(sym: str, ts: float | None = None) -> dict | None:
    """Per-leg: each of call wall / put wall / flip = latest reading at or before ts (else earliest known),
    with its own timestamp, so a stale leg is never presented as fresh."""
    h = _walls["hist"].get(sym) or []
    if not h:
        return None
    out = {"ts": 0}
    for leg in ("cw", "pw", "flip"):
        hl = [w for w in h if w.get(leg) is not None]
        if not hl:
            out[leg], out[leg + "_ts"], out[leg + "_src"] = None, None, None
            continue
        prior = hl if ts is None else [w for w in hl if w["ts"] <= ts + 60]
        w = prior[-1] if prior else hl[0]
        out[leg], out[leg + "_ts"], out[leg + "_src"] = w[leg], w["ts"], w["src"]
        if leg in ("cw", "pw"):
            out["ts"] = max(out["ts"], w["ts"])
    out["src"] = out.get("cw_src") or out.get("pw_src")
    return out


def wall_stamp(w, ref_ts: float | None = None) -> str:
    t = dt.datetime.fromtimestamp(w if isinstance(w, (int, float)) else w["ts"], PT)
    ref = dt.datetime.fromtimestamp(ref_ts, PT) if ref_ts else now_pt()
    return "@" + (t.strftime("%-I:%M") if t.date() == ref.date() else t.strftime("%b %-d %-I:%M"))


def refresh_walls_live(recs_recent: list[dict]) -> int:
    """Top up FlashAlpha walls for names with a big trade in the last 15 min and no wall <= 10 min old."""
    t = time.time()
    d = now_pt().date()
    if _walls["live_date"] != d:
        _walls["live_date"], _walls["live_today"] = d, 0
    try:
        st = json.loads((DESK / "cache/fa-focus-refresh-state.json").read_text())
        remaining = ((st.get("last_account") or {}).get("remaining"))
    except Exception:  # noqa: BLE001
        remaining = None
    if remaining is not None and remaining < FA_MIN_REMAINING:
        return 0
    want = []
    for r in sorted(recs_recent, key=lambda r: -r["premium"]):
        sym = r["ticker"]
        if sym in want or not is_big(r) or t - _epoch(r["created_at"]) > 900:
            continue
        w = walls_at(sym)
        if w and t - w["ts"] <= WALL_MAX_AGE_S:
            continue
        if t - _walls["last_try"].get(sym, 0) < WALL_MAX_AGE_S:
            continue
        want.append(sym)
    n = 0
    if not want:
        return 0
    try:
        sys.path.insert(0, str(DESK / "quotes"))
        import fa_focus_refresh as fa  # desk client; reads its own key file, never printed
    except Exception:  # noqa: BLE001
        return 0
    for sym in want[:FA_LIVE_PER_CYCLE]:
        if _walls["live_today"] >= FA_LIVE_PER_DAY:
            break
        _walls["last_try"][sym] = t
        try:
            r = fa.flow_levels(sym)
            _walls["live_today"] += 1
            n += 1
            _add_wall(sym, _epoch(r.get("as_of")) or t, _num(r.get("live_call_wall")), _num(r.get("live_put_wall")),
                      _num(r.get("live_gamma_flip")), "FlashAlpha flow/levels (whale collector)")
        except Exception:  # noqa: BLE001
            continue
    return n


def _g(v):
    return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, (int, float)) else str(v)


def tags_for(rec: dict, lv: dict) -> list[str]:
    L = lv.get(rec["ticker"]) or {}
    s, k = rec.get("spot"), rec.get("strike")
    if not s:
        return []
    t = []
    ts = _epoch(rec.get("created_at"))
    W = walls_at(rec["ticker"], ts)
    L = dict(L)
    L["cw"], L["pw"], L["flip"] = (W["cw"], W["pw"], W["flip"]) if W else (None, None, None)
    stp = lambda leg: (" " + wall_stamp(W[leg + "_ts"], ts)) if W and W.get(leg + "_ts") else ""  # noqa: E731
    near = lambda a, b, pct: a is not None and b is not None and abs(a - b) / s <= pct  # noqa: E731
    if L.get("cw") is not None and near(k, L["cw"], 0.004):
        t.append(f"strike at call wall {_g(L['cw'])}{stp('cw')}")
    if L.get("pw") is not None and near(k, L["pw"], 0.004):
        t.append(f"strike at put wall {_g(L['pw'])}{stp('pw')}")
    if L.get("bull") is not None and s > L["bull"]:
        t.append(f"spot above 4h bull trigger {_g(L['bull'])}")
    elif L.get("bear") is not None and s < L["bear"]:
        t.append(f"spot below 4h bear trigger {_g(L['bear'])}")
    elif L.get("bull") is not None and near(s, L["bull"], 0.006):
        t.append(f"spot just under 4h bull trigger {_g(L['bull'])}")
    if L.get("cw") is not None and near(s, L["cw"], 0.01) and not any("call wall" in x for x in t):
        t.append(f"spot near call wall {_g(L['cw'])}{stp('cw')}")
    if L.get("pw") is not None and near(s, L["pw"], 0.01) and not any("put wall" in x for x in t):
        t.append(f"spot near put wall {_g(L['pw'])}{stp('pw')}")
    if L.get("flip") is not None and near(s, L["flip"], 0.003):
        t.append(f"spot at gamma flip {_g(L['flip'])}{stp('flip')}")
    if L.get("breakout") is not None and s > L["breakout"]:
        t.append(f"above daily breakout {_g(L['breakout'])}")
    for r in L.get("res") or []:
        if near(s, r, 0.008):
            t.append(f"spot at daily resistance {_g(r)}"); break
    for r in L.get("sup") or []:
        if near(s, r, 0.008):
            t.append(f"spot at daily support {_g(r)}"); break
    for nm, z in (("pullback zone", L.get("pull")), ("buy zone", L.get("buy"))):
        if z and z.get("lo") is not None and z["lo"] <= s <= z["hi"]:
            t.append(f"spot in {nm} {_g(z['lo'])}-{_g(z['hi'])}"); break
    return t[:3]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def normalize(a: dict, lv: dict) -> dict:
    prem = f(a.get("total_premium")) or 0.0
    askp, bidp = f(a.get("total_ask_side_prem")) or 0.0, f(a.get("total_bid_side_prem")) or 0.0
    share = askp / prem if prem else 0
    bshare = bidp / prem if prem else 0
    side = "ask" if share >= 0.6 else "bid" if bshare >= 0.6 else "mid/mixed"
    typ = a.get("type")
    multileg = bool(a.get("has_multileg"))
    if multileg or side == "mid/mixed":
        lean = "neutral"
    elif (typ == "call") == (side == "ask"):
        lean = "bullish"
    else:
        lean = "bearish"
    tc = a.get("trade_count") or 0
    kind = "sweep" if a.get("has_sweep") else "floor" if a.get("has_floor") else "block" if tc <= 1 else "repeated prints"
    if multileg:
        kind += " (multi-leg)"
    created = dt.datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
    size, oi = a.get("total_size") or 0, a.get("open_interest") or 0
    exp = a.get("expiry")
    try:
        dte = (dt.date.fromisoformat(exp) - created.astimezone(PT).date()).days
    except Exception:  # noqa: BLE001
        dte = None
    rec = {
        "id": a.get("id"), "created_at": a["created_at"], "time_pt": created.astimezone(PT).strftime("%-I:%M:%S %p"),
        "ticker": a.get("ticker"), "type": typ, "strike": f(a.get("strike")), "expiry": exp, "dte": dte,
        "chain": a.get("option_chain"), "side": side, "ask_share": round(share, 2), "kind": kind,
        "size": size, "price": f(a.get("price")), "premium": round(prem), "ask_prem": round(askp), "bid_prem": round(bidp),
        "volume": a.get("volume"), "oi": oi, "vol_oi": round(f(a.get("volume_oi_ratio")) or 0, 2),
        "opening": bool(a.get("all_opening_trades")) or (oi and size > oi), "uw_opening": bool(a.get("all_opening_trades")),
        "spot": f(a.get("underlying_price")), "iv": round(f(a.get("iv")) or 0, 4), "delta": round(f(a.get("delta")) or 0, 3),
        "rule": a.get("alert_rule"), "trade_count": tc, "lean": lean, "src": "alert", "multileg": multileg,
    }
    relabel(rec)
    rec["tags"] = tags_for(rec, lv)
    return rec


# ---------- log / summary ----------
def day_dir(d: dt.date) -> Path:
    p = HERE / d.isoformat()
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_log(d: dt.date) -> list[dict]:
    p = day_dir(d) / "trades.jsonl"
    if not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def summarize(d: dt.date, last_poll: dt.datetime | None = None) -> dict:
    ingest_walls()
    recs = read_log(d)
    by = {}
    for r in recs:
        relabel(r)
        b = by.setdefault(r["ticker"], {"ticker": r["ticker"], "n": 0, "call_prem": 0, "put_prem": 0,
                                         "bull_prem": 0, "bear_prem": 0, "neutral_prem": 0, "closing_prem": 0,
                                         "spot": None, "_t": ""})
        b["n"] += 1
        b["first"] = min(b.get("first") or r["created_at"], r["created_at"])
        b["last"] = max(b.get("last") or r["created_at"], r["created_at"])
        b["call_prem" if r["type"] == "call" else "put_prem"] += r["premium"]
        b[{"bullish": "bull_prem", "bearish": "bear_prem"}.get(r["lean"],
          "closing_prem" if r["lean"] in CLOSING_LEANS else "neutral_prem")] += r["premium"]
        if r["created_at"] > b["_t"]:
            b["_t"], b["spot"] = r["created_at"], r["spot"]
    tick = []
    for b in by.values():
        b.pop("_t")
        b["first_pt"] = dt.datetime.fromisoformat(b["first"].replace("Z", "+00:00")).astimezone(PT).strftime("%-I:%M:%S %p")
        b["last_pt"] = dt.datetime.fromisoformat(b["last"].replace("Z", "+00:00")).astimezone(PT).strftime("%-I:%M:%S %p")
        net = b["bull_prem"] - b["bear_prem"]
        dirn = b["bull_prem"] + b["bear_prem"]
        b["net_dir_prem"] = net
        b["lean"] = ("bullish" if net > 0 else "bearish") if dirn and abs(net) / dirn >= 0.2 else "mixed"
        tick.append(b)
    tick.sort(key=lambda b: -(b["call_prem"] + b["put_prem"]))
    top = sorted(recs, key=lambda r: -r["premium"])[:40]
    newest = sorted(recs, key=lambda r: r["created_at"], reverse=True)[:40]
    tape = sorted(recs, key=lambda r: r["created_at"], reverse=True)[:200]
    tot = sum(r["premium"] for r in recs)
    bull = sum(r["premium"] for r in recs if r["lean"] == "bullish")
    bear = sum(r["premium"] for r in recs if r["lean"] == "bearish")
    last_trade = max((r["created_at"] for r in recs), default=None)
    s = {
        "config_version": CONFIG_VERSION, "session_date": d.isoformat(),
        "as_of_pt": fmt_pt(last_poll or now_pt()),
        "last_trade_pt": fmt_pt(dt.datetime.fromisoformat(last_trade.replace("Z", "+00:00"))) if last_trade else None,
        "count": len(recs), "total_prem": tot, "bull_prem": bull, "bear_prem": bear, "min_premium": MIN_PREMIUM, "etf_min_premium": ETF_MIN_PREMIUM,
        "tickers": tick, "top": top, "newest": newest, "tape": tape,
        "as_of_iso": (last_poll or now_pt()).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "big_min": BIG_MIN, "big_etf_min": BIG_ETF_MIN, "print_min": PRINT_MIN, "print_etf_min": PRINT_ETF_MIN,
        "big_count": sum(1 for r in recs if is_big(r)),
        "closing_prem": sum(r["premium"] for r in recs if r["lean"] in CLOSING_LEANS),
        "walls": {sym: {"cw": w["cw"], "pw": w["pw"], "flip": w["flip"], "src": w["src"],
                        "as_of_pt": dt.datetime.fromtimestamp(w["ts"], PT).strftime("%b %-d %-I:%M %p PT")}
                  for sym, w in ((k, walls_at(k)) for k in sorted(_walls["hist"])) if w},
        "source": "Unusual Whales REST flow-alerts (OPRA-derived sweeps/blocks/repeated hits), UW_API_KEY; Chart Bot 37-name universe",
        "method_note": (f"Alerts with premium >= ${MIN_PREMIUM:,} (SPY/QQQ >= ${ETF_MIN_PREMIUM:,}) on the 37 Chart names, polled every ~60s during 6:30 AM-1:00 PM PT; "
                        "deduped by UW alert id. Also raw block/multi-leg prints >= $1M ($5M SPY/QQQ) from UW flow-recent (prints already inside an alert are skipped; multi-leg legs are paired as combos). Side: ask/bid when >=60% of premium printed there, else mid/mixed. Lean (v2): ask-side buys = bullish (calls) / bearish (puts); "
                        "bid-side sales count as directional ONLY when opening (UW all-opening flag or size > prior OI); a non-opening bid-side sale is "
                        "'closing / overwrite' (calls) or 'closing' (puts), shown grey and excluded from net lean; mid/mixed and multi-leg = neutral. "
                        "Tags compare spot/strike to Chart Bot 4h triggers, daily S/R and FlashAlpha walls/flip as known at the trade time, stamped @time "
                        "(desk caches fa-levels / fa-focus-levels first; collector tops up names with a fresh big trade at most every 10 min). "
                        "Soft research only; never orders, never elevates."),
        "mandate": "research/paper only - never orders, never elevates",
    }
    for p in (day_dir(d) / "summary.json", HERE / "latest" / "summary.json"):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(s, ensure_ascii=False, indent=1))
    return s


def write_status(**kw):
    p = HERE / "status.json"
    st = json.loads(p.read_text()) if p.is_file() else {}
    st.update(kw)
    st["pid"] = os.getpid()
    p.write_text(json.dumps(st, indent=1))


def poll_once(lv: dict | None = None, all_prints: bool = False) -> tuple[int, dt.datetime]:
    t = now_pt()
    d = t.date()
    existing = read_log(d)
    seen = {r["id"] for r in existing}
    newest = max((r["created_at"] for r in existing if r.get("src", "alert") == "alert"), default=None)
    floor = dt.datetime.combine(d, dt.time(0, 0), PT).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    newer = None
    if newest:  # 3-min overlap so late-indexed alerts are not missed; dedupe by id
        nt = dt.datetime.fromisoformat(newest.replace("Z", "+00:00")) - dt.timedelta(minutes=3)
        newer = nt.strftime("%Y-%m-%dT%H:%M:%SZ")
    names = universe()
    lv = lv if lv is not None else load_levels()
    ingest_walls()
    new = []
    for a in sorted(pull(names, newer, floor), key=lambda a: a["created_at"]):
        if a.get("id") in seen:
            continue
        if dt.datetime.fromisoformat(a["created_at"].replace("Z", "+00:00")).astimezone(PT).date() != d:
            continue
        seen.add(a["id"])
        new.append(normalize(a, lv))
    for a in pull_prints(print_targets(names, all_prints)):
        pid = "p:" + str(a.get("id"))
        if pid in seen or a.get("flow_alert_id") or a.get("canceled"):
            continue  # prints already inside a UW alert are counted via the alert
        if dt.datetime.fromisoformat(a["executed_at"].replace("Z", "+00:00")).astimezone(PT).date() != d:
            continue
        seen.add(pid)
        new.append(normalize_print(a, lv))
    pair_combos(new)
    new.sort(key=lambda r: r["created_at"])
    try:
        recent = [r for r in existing[-400:] if r.get("premium")] + new
        if refresh_walls_live(recent):
            for r in new:
                r["tags"] = tags_for(r, lv)
    except Exception:  # noqa: BLE001  walls never stop the poll
        pass
    if new:
        with open(day_dir(d) / "trades.jsonl", "a") as fh:
            for r in new:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        append_big(d, new, backfill=all_prints)
    return len(new), t


def retro(d: dt.date) -> dict:
    """Re-apply lean v2 + time-aware wall tags to today's trades.jsonl and big_trades.jsonl in place."""
    lv = load_levels()
    ingest_walls()
    out = {}
    for fn in ("trades.jsonl", "big_trades.jsonl"):
        p = day_dir(d) / fn
        if not p.is_file():
            continue
        rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        ch = 0
        for r in rows:
            old = (r.get("lean"), tuple(r.get("tags") or []))
            relabel(r)
            r["tags"] = tags_for(r, lv)
            ch += old != (r["lean"], tuple(r["tags"]))
        tmp = p.with_name("." + fn + ".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        tmp.replace(p)
        out[fn] = {"rows": len(rows), "changed": ch}
    return out


def publish() -> int:
    env = dict(os.environ, OID_PUBLISH_LOCK_WAIT_S="90")
    try:
        r = subprocess.run(["bash", str(DESK / "dashboard/publish.sh")], cwd=DESK, env=env,
                           capture_output=True, text=True, timeout=600)
        return r.returncode
    except subprocess.TimeoutExpired:
        return 124


def loop():
    last_pub, pending, lv, lv_at = 0.0, False, load_levels(), time.time()
    write_status(started_pt=fmt_pt(now_pt()), state="running")
    while True:
        t = now_pt()
        in_rth = t.weekday() < 5 and RTH[0] <= t.time() <= RTH[1]
        # one final catch-up poll window to 1:05 PM PT so late-indexed closing prints land
        tail = t.weekday() < 5 and RTH[1] < t.time() <= dt.time(13, 5)
        if in_rth or tail:
            if time.time() - lv_at > 1800:
                lv, lv_at = load_levels(), time.time()
            try:
                n, tp = poll_once(lv)
                s = summarize(tp.date(), tp)
                pending = pending or n > 0
                write_status(state="polling", last_poll_pt=fmt_pt(tp), last_new=n, count_today=s["count"], last_error=None)
            except Exception as e:  # noqa: BLE001
                write_status(state="poll_error", last_error=f"{fmt_pt(now_pt())}: {type(e).__name__}: {e}"[:300])
            if pending and time.time() - last_pub >= PUBLISH_EVERY_S:
                rc = publish()
                last_pub = time.time()
                if rc == 0:
                    pending = False
                write_status(last_publish_pt=fmt_pt(now_pt()), last_publish_rc=rc)
        else:
            write_status(state="idle (outside 6:30 AM-1:05 PM PT weekdays)", heartbeat_pt=fmt_pt(t))
        time.sleep(max(5, POLL_S - (time.time() % POLL_S)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["pending-pings"], help="pending-pings: print new unpinged big trades")
    ap.add_argument("--mark", action="store_true", help="with pending-pings: advance ping_cursor.json past printed trades")
    ap.add_argument("--directional-only", action="store_true", help="with pending-pings: hide closing/neutral trades (cursor still advances with --mark)")
    ap.add_argument("--retro", action="store_true", help="re-apply lean v2 + wall tags to today's logs")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--all-prints", action="store_true", help="with --once: poll raw prints for all 37 names")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--summarize", action="store_true")
    a = ap.parse_args()
    if a.cmd == "pending-pings":
        return pending_pings(a.mark, a.directional_only)
    if a.retro:
        print(json.dumps(retro(now_pt().date())))
        s = summarize(now_pt().date())
        print(json.dumps({"count": s["count"], "closing_prem": s["closing_prem"]}))
        return 0
    if a.loop:
        loop()
    elif a.once:
        n, t = poll_once(all_prints=a.all_prints)
        s = summarize(t.date(), t)
        write_status(last_poll_pt=fmt_pt(t), last_new=n, count_today=s["count"])
        print(json.dumps({"new": n, "count": s["count"], "big": s["big_count"], "as_of": s["as_of_pt"]}))
    else:
        s = summarize(now_pt().date())
        print(json.dumps({"count": s["count"], "as_of": s["as_of_pt"]}))


if __name__ == "__main__":
    sys.exit(main())
