"""Live WTI / Brent front-month futures for the private live page (Jeffrey approved 2026-10-19 12:06 PM PT).

launchd interval job, 60 s. Each run makes AT MOST ONE FlashAlpha call, alternating CL=F and BZ=F
(GET https://lab.flashalpha.com/stockquote/CL%3DF, Growth plan, CME Globex feed), so each symbol refreshes ~every 2 min:
  fast window  Mon-Fri 06:30-13:00 PT (RTH) -> one call / min (~390/day)
  other CME hours                      -> each symbol every 30 min (~4 calls/h)
  CME daily break (Mon-Thu 14:00-15:00 PT) and weekend (Fri 14:00 -> Sun 15:00 PT) -> no calls, quotes kept, state=closed
Quota guard: FlashAlpha X-RateLimit-Remaining (fallback /v1/account) is recorded after each call; below GUARD_MIN
(default 300) the job pauses until the quota resets (00:00 UTC = 5 PM PT) so vix-live / fa-focus never starve.
Previous settle + contract name: one Yahoo chart read per symbol per CME trading day (fallback source only).
If FlashAlpha is unavailable/paused and its quote is >10 min old, Yahoo's price is used and tagged DELAYED.
Writes market-data/latest/futures-quotes.json (marks-style envelope, payload.quotes.CL / .BZ).
Kill switch: oidctl disable futures-live. FLASHALPHA_API_KEY comes from run-job.sh env and is never logged.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from . import util

JOB = "futures-live"
PT = ZoneInfo("America/Los_Angeles")
FA = "https://lab.flashalpha.com"
SYMS = {"CL": {"fa": "CL=F", "yh": "CL=F", "name": "WTI"}, "BZ": {"fa": "BZ=F", "yh": "BZ=F", "name": "Brent"}}
GUARD_MIN = int(os.environ.get("OID_FUT_GUARD_MIN", "300"))
FAST_GAP_S = 110        # per-symbol gap in the fast window (60 s runs alternate CL/BZ)
SLOW_GAP_S = 1800       # per-symbol gap outside it
FAST_START, FAST_END = (6, 30), (13, 0)
SRC_FA = "FlashAlpha CME futures (~2 min)"
SRC_YH = "Yahoo (~10 min DELAYED)"
MONTHS = "FGHJKMNQUVXZ"
MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ------------------------------------------------------------------ CME calendar (weekdays; exchange holidays not modelled)
def cme_state(now: datetime) -> str:
    """open | break | weekend (Globex energy: Sun 15:00 -> Fri 14:00 PT, daily halt 14:00-15:00 PT)."""
    wd, hm = now.weekday(), (now.hour, now.minute)
    if wd == 5 or (wd == 4 and hm >= (14, 0)) or (wd == 6 and hm < (15, 0)):
        return "weekend"
    if (14, 0) <= hm < (15, 0):
        return "break"
    return "open"


def _bday_back(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _prev_or_same_bday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _bdays_between(a: date, b: date) -> int:
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def last_trade(root: str, y: int, m: int) -> date:
    if root == "CL":  # 3 business days before the 25th (or the bday before it) of the month before delivery
        py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
        return _bday_back(_prev_or_same_bday(date(py, pm, 25)), 3)
    # BZ (Brent Last Day Financial): last business day of the second month before the contract month
    py, pm = (y, m - 2) if m > 2 else (y - 1, m + 10)
    nxt = date(py + (pm // 12), pm % 12 + 1, 1)
    return _prev_or_same_bday(nxt - timedelta(days=1))


def front_contract(root: str, today: date) -> tuple[int, int]:
    """First contract with >1 business day left before last trade (both FlashAlpha and Yahoo roll then)."""
    y, m = today.year, today.month
    for _ in range(18):
        if _bdays_between(today, last_trade(root, y, m)) > 1:
            return y, m
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return today.year, today.month


def code(root: str, y: int, m: int) -> str:
    return f"{root}{MONTHS[m - 1]}{y % 100:02d}"


def label(y: int, m: int) -> str:
    return f"{MON3[m - 1]} '{y % 100:02d}"


def parse_yahoo_month(name: str) -> Optional[tuple[int, int]]:
    mm = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{2})\b", name or "")
    return (2000 + int(mm.group(2)), MON3.index(mm.group(1)) + 1) if mm else None


# ------------------------------------------------------------------ sources
def fa_quote(sym: str, key: str) -> tuple[dict, Optional[int]]:
    url = f"{FA}/stockquote/{urllib.parse.quote(SYMS[sym]['fa'], safe='')}"
    req = urllib.request.Request(url, headers={"X-Api-Key": key, "User-Agent": "oid-mini-futures/1"})
    with OPENER.open(req, timeout=10) as r:
        d = json.load(r)
        rem = r.headers.get("X-RateLimit-Remaining")
    try:
        rem = int(float(rem)) if rem is not None else None
    except ValueError:
        rem = None
    return d, rem


def fa_account(key: str) -> Optional[int]:
    req = urllib.request.Request(f"{FA}/v1/account", headers={"X-Api-Key": key, "User-Agent": "oid-mini-futures/1"})
    with OPENER.open(req, timeout=10) as r:
        d = json.load(r)
    try:
        return int(float(d.get("remaining")))
    except (TypeError, ValueError):
        return None


def yahoo(sym: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(SYMS[sym]['yh'], safe='')}?interval=1m&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with OPENER.open(req, timeout=10) as r:
        m = json.load(r)["chart"]["result"][0]["meta"]
    return {"prev_close": m.get("chartPreviousClose") or m.get("previousClose"), "short_name": m.get("shortName"),
            "price": m.get("regularMarketPrice"), "price_t": m.get("regularMarketTime"), "exchange": m.get("exchangeName")}


# ------------------------------------------------------------------ main
def _iso_ts(s: Optional[str]) -> Optional[float]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def main(argv: Optional[list[str]] = None) -> int:
    t = time.time()
    now = datetime.fromtimestamp(t, PT)
    sp = util.root() / "state" / "futures-live.json"
    st = util.read_json(sp) or {}
    st.setdefault("last_fetch", {}); st.setdefault("fa", {}); st.setdefault("yahoo", {})
    qday = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # FlashAlpha quota day (resets 00:00 UTC)
    if st.get("calls_day") != qday:
        st["calls_day"], st["calls_today"], st["quota_remaining"], st["paused"] = qday, 0, None, False
    state = cme_state(now)
    tday = (now + timedelta(hours=8, minutes=30)).date().isoformat()  # CME trading day key (rolls 15:30 PT)
    key = os.environ.get("FLASHALPHA_API_KEY") or util.read_secret("FLASHALPHA_API_KEY")
    did = None

    # Yahoo: once per symbol per trading day (prev settle + contract name); retry at most every 15 min
    if state == "open":
        for s in SYMS:
            y = st["yahoo"].get(s) or {}
            if y.get("tday") != tday and t - float(y.get("tried", 0)) > 900:
                try:
                    st["yahoo"][s] = dict(yahoo(s), tday=tday, tried=t, read_pt=util.now_pt_str(t))
                    util.log(JOB, f"yahoo {s}: prev {st['yahoo'][s].get('prev_close')} name {st['yahoo'][s].get('short_name')!r}")
                except Exception as e:  # noqa: BLE001
                    y["tried"] = t; st["yahoo"][s] = y
                    util.log(JOB, f"yahoo {s} failed: {type(e).__name__}")

    # FlashAlpha: at most one call this run
    fast = now.weekday() < 5 and FAST_START <= (now.hour, now.minute) < FAST_END
    gap = FAST_GAP_S if fast else SLOW_GAP_S
    rem = st.get("quota_remaining")
    guard = rem is not None and rem < GUARD_MIN
    if guard and not st.get("paused"):
        util.log(JOB, f"GUARD: FlashAlpha remaining {rem} < {GUARD_MIN}; pausing until quota reset (5 PM PT)")
    st["paused"] = bool(guard)
    if state == "open" and not guard and key:
        due = [s for s in SYMS if t - float(st["last_fetch"].get(s, 0)) >= gap]
        if due:
            s = min(due, key=lambda x: float(st["last_fetch"].get(x, 0)))
            st["last_fetch"][s] = t
            try:
                d, r = fa_quote(s, key)
                st["calls_today"] = int(st.get("calls_today") or 0) + 1
                if r is None:
                    try:
                        r = fa_account(key)
                    except Exception:  # noqa: BLE001
                        r = None
                st["quota_remaining"], st["quota_at_pt"] = r, util.now_pt_str(t)
                last = d.get("lastPrice") or d.get("mid")
                if last:
                    rd = lambda v: round(float(v), 4) if isinstance(v, (int, float)) else v  # noqa: E731
                    last = rd(last)
                    st["fa"][s] = {"last": last, "bid": rd(d.get("bid")), "ask": rd(d.get("ask")), "mid": rd(d.get("mid")),
                                   "last_update": d.get("lastUpdate"), "futures_feed_as_of": (d.get("data_as_of") or {}).get("futures_feed"),
                                   "fetched": t}
                did = s
                util.log(JOB, f"{SYMS[s]['fa']} {last} rem={r} calls_today={st['calls_today']} ({'fast' if fast else 'slow'})")
            except Exception as e:  # noqa: BLE001
                util.log(JOB, f"{SYMS[s]['fa']} fetch failed: {type(e).__name__}")

    # build payload
    today = now.date()
    quotes = {}
    for s in SYMS:
        y, m = front_contract(s, today)
        cal = (y, m)
        yh = st["yahoo"].get(s) or {}
        ym = parse_yahoo_month(yh.get("short_name") or "")
        note = None
        if ym and ym != cal:
            note = f"Yahoo shows {label(*ym)}, calendar {label(*cal)}; using Yahoo"
            y, m = ym
        f = st["fa"].get(s) or {}
        fa_t = _iso_ts(f.get("last_update"))
        src, delayed, last, bid, ask, qt = SRC_FA, False, f.get("last"), f.get("bid"), f.get("ask"), fa_t
        fa_old = fa_t is None or t - fa_t > 600
        if fa_old and state == "open" and yh.get("price"):
            # fallback: refresh Yahoo price at most every 5 min while FlashAlpha is unavailable/paused
            if t - float(yh.get("price_read", yh.get("tried", 0))) > 300:
                try:
                    yy = yahoo(s); yh.update(price=yy["price"], price_t=yy["price_t"], price_read=t); st["yahoo"][s] = yh
                except Exception:  # noqa: BLE001
                    pass
            if yh.get("price_t") and (fa_t is None or yh["price_t"] > fa_t):
                src, delayed, last, bid, ask, qt = SRC_YH, True, yh.get("price"), None, None, float(yh["price_t"])
        pc = yh.get("prev_close")
        if last and yh.get("price") and not delayed and abs(float(last) / float(yh["price"]) - 1) > 0.02:
            note = (note + "; " if note else "") + "FlashAlpha vs Yahoo >2% apart: check contract"
        quotes[s] = {"symbol": s, "name": SYMS[s]["name"], "last": last, "bid": bid, "ask": ask, "previous_close": pc,
                     "prev_close_src": "Yahoo chartPreviousClose (prior settle)" if pc else None,
                     "venue_last_trade_time": datetime.fromtimestamp(qt, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if qt else None,
                     "contract": code(s, y, m), "contract_label": label(y, m), "src": src, "delayed": delayed,
                     "fetched_pt": util.now_pt_str(f["fetched"]) if f.get("fetched") else None, "note": note}
    payload = {"quotes": quotes, "cme_state": state, "fast_window": fast, "per_symbol_gap_s": gap,
               "quota": {"remaining": st.get("quota_remaining"), "at_pt": st.get("quota_at_pt"), "guard_min": GUARD_MIN,
                         "paused": st.get("paused"), "calls_today_utc": st.get("calls_today"), "day_utc": qday}}
    util.atomic_write_json(sp, st)
    util.write_feed("futures-quotes", source=SRC_FA + " · Yahoo prev settle/contract (fallback)", writer="mini:oid_desk.futures_live",
                    symbols=list(SYMS), payload=payload, ttl_seconds=600)
    print(json.dumps({"called": did, "state": state, "fast": fast, "rem": st.get("quota_remaining"),
                      "CL": quotes["CL"]["last"], "BZ": quotes["BZ"]["last"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
