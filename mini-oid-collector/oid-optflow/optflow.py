#!/usr/bin/env python3
"""oid-optflow: real-time options aggressor flow (Alpaca OPRA websocket) for the private live page.

Separate process + separate websocket from oid-quote-collector (:8787). Never places orders.

  - Picks a contract set per underlying (near-dated, near-ATM, ranked by today's volume) from Alpaca
    REST option snapshots, within a total budget (default 900 contracts; Alpaca option-quote cap is 1000).
  - Streams OPRA quotes + trades for that set, classifies each trade (Lee-Ready):
        p >= ask -> BUY (ask);  p <= bid -> SELL (bid)
        inside spread: above mid -> BUY (mid+), below mid -> SELL (mid-), at mid -> tick test, else neutral
    Multi-leg / stock-option tied / cancel / late prints are excluded from the ratios (counted as 'excluded').
  - Rolling 15s and 60s windows per underlying: call-buy vs put-buy premium ratio, net aggressor premium
    ((call buy - call sell) - (put buy - put sell)), contracts, and a 'strict' (ask/bid-only) variant.
  - Serves  http://127.0.0.1:8792/v1/optflow  (+ /v1/health, /v1/recent?sym=)  and writes
    ~/oid-optflow/data/optflow.json atomically every second.

WIDE tier (v0.4.0, 2026-10-20): the 144 Sector watch names (~/oid-quote/wide-allowlist.json, minus core, minus
WDC/STX/SNDK) ride the SAME websocket as TRADES ONLY (Alpaca caps option QUOTE subscriptions at 1,000 per connection,
the core uses 900 of them, and the account allows only 2 OPRA connections, both in use; trade subscriptions have no
cap - probed 2026-10-20). With no NBBO for those contracts, a wide print is classified by the TICK TEST only
(price above the contract's previous print = buy, below = sell, equal = previous side, first print = neutral).
Everything else (15 s / 60 s windows, C/P, net, momentum slots) is the same code. Wide output goes to separate files so
core consumers are untouched:  data/optflow-wide.json (every 1 s) and data/cp-history-wide/YYYY-MM-DD.jsonl (15 s).
Every wide window carries cls="tick". Kill switch: OID_OPTFLOW_WIDE=0.
"""
from __future__ import annotations
import asyncio, gzip, json, logging, math, os, queue, re, signal, ssl, statistics, sys, threading, time
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import urllib.request, urllib.parse

import aiohttp, msgpack
from aiohttp import web

HOME = Path.home()
ROOT = Path(os.environ.get("OID_OPTFLOW_ROOT", str(HOME / "oid-optflow")))
SECRETS = Path(os.environ.get("OID_OPTFLOW_SECRETS", str(HOME / "oid-quote/secrets")))
ALLOWLIST = Path(os.environ.get("OID_OPTFLOW_ALLOWLIST", str(HOME / "oid-quote/app/stream-quote-allowlist.json")))
OUT = ROOT / "data/optflow.json"
SUBS_OUT = ROOT / "data/optflow-subs.json"
PORT = int(os.environ.get("OID_OPTFLOW_PORT", "8792"))
BUDGET = int(os.environ.get("OID_OPTFLOW_BUDGET", "900"))
MAX_DTE = int(os.environ.get("OID_OPTFLOW_MAX_DTE", "21"))
RESELECT_S = float(os.environ.get("OID_OPTFLOW_RESELECT_S", "900"))
WS_URL = os.environ.get("OID_OPTFLOW_WS", "wss://stream.data.alpaca.markets/v1beta1/opra")
DATA = "https://data.alpaca.markets"
PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")
WINDOWS = (15, 60)
QUOTE_MAX_AGE = float(os.environ.get("OID_OPTFLOW_QUOTE_MAX_AGE", "2.0"))
THIN_PRINTS = int(os.environ.get("OID_OPTFLOW_THIN_PRINTS", "5"))
INDEX_ETF = {"SPY", "QQQ", "DIA", "RSP", "TQQQ", "VTV", "VUG", "EWY", "SMH", "SOXX"}
GOOD_COND = set("IJSabcde")           # single-leg prints we classify
MULTI_COND = set("fghijlmtu")         # multi-leg
STOCKOPT_COND = set("knopqrs")        # tied to stock
CANCEL_LATE = set("ABCDEFGH")         # cancels / late / out-of-sequence
OCC = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
# --- OPTMOM: C/P momentum (spec docs/live-page/22-cp-momentum-spec.md)
MOMENTUM = os.environ.get("OID_OPTFLOW_MOMENTUM", "1") != "0"      # kill switch
HIST_LOG = os.environ.get("OID_OPTFLOW_HIST_LOG", "1") != "0"
HIST_N = int(os.environ.get("OID_OPTFLOW_HIST_N", "6"))
HIST_KEEP_D = int(os.environ.get("OID_OPTFLOW_HIST_KEEP_D", "365"))
HIST_DIR = ROOT / "data/cp-history"
SAMPLE_S = 15
MOM_SLOTS = 4                       # slope over the last 4 slots (45 s span)
MOM_MIN_VALID = 3
STALE_S = 30.0
RERANK_MIN_OVERLAP = 0.70
L_CAP = math.log(10)
DB = {"15s": (float(os.environ.get("OID_OPTFLOW_DB15_IN", "0.35")), float(os.environ.get("OID_OPTFLOW_DB15_OUT", "0.20"))),
      "60s": (float(os.environ.get("OID_OPTFLOW_DB60_IN", "0.20")), float(os.environ.get("OID_OPTFLOW_DB60_OUT", "0.10")))}
WKEYS = {"15s": "15", "60s": "60"}
# --- WIDE tier (trades only, tick-test classification)
WIDE_ON = os.environ.get("OID_OPTFLOW_WIDE", "1") != "0"
WIDE_ALLOWLIST = Path(os.environ.get("OID_OPTFLOW_WIDE_ALLOWLIST", str(HOME / "oid-quote/wide-allowlist.json")))
WIDE_BUDGET = int(os.environ.get("OID_OPTFLOW_WIDE_BUDGET", "3000"))   # trade-only subscriptions (no Alpaca cap)
WIDE_CAP, WIDE_FLOOR = 40, 4
WIDE_EXCLUDE = {"WDC", "STX", "SNDK"}
WIDE_OUT = ROOT / "data/optflow-wide.json"
WIDE_SUBS_OUT = ROOT / "data/optflow-wide-subs.json"
HIST_DIR_WIDE = ROOT / "data/cp-history-wide"
VERSION = "0.4.0"


def _logratio(cb, pb):
    """OPTMOM: smoothed, clamped ln(call-buy / put-buy premium)."""
    k = max(2000.0, 0.05 * (cb + pb))
    return max(-L_CAP, min(L_CAP, math.log((cb + k) / (pb + k))))


def _rth(ts):
    d = datetime.fromtimestamp(ts, ET)
    if d.weekday() >= 5:
        return False
    m = d.hour * 60 + d.minute
    return 570 <= m < 960


def _open_epoch(ts):
    d = datetime.fromtimestamp(ts, ET)
    return d.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()


def _ols_slope(pts):
    n = len(pts); mx = sum(t for t, _ in pts) / n; my = sum(v for _, v in pts) / n
    den = sum((t - mx) ** 2 for t, _ in pts)
    return 0.0 if den <= 0 else sum((t - mx) * (v - my) for t, v in pts) / den

log = logging.getLogger("optflow")


def _key(name):
    return (SECRETS / name).read_text().strip()


def _headers():
    return {"APCA-API-KEY-ID": _key("APCA_API_KEY_ID"), "APCA-API-SECRET-KEY": _key("APCA_API_SECRET_KEY")}


def _get(path, params):
    url = DATA + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=_headers()), timeout=20) as r:
        return json.load(r)


def _iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, PT).isoformat(timespec="milliseconds")


def _ts(v):
    """msgpack Timestamp / RFC-3339 / number -> epoch seconds float."""
    if v is None:
        return None
    if hasattr(v, "to_unix_nano"):
        return v.to_unix_nano() / 1e9
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, datetime):
        return v.timestamp()
    s = str(v)
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(\.\d+)?(Z|[+-]\d\d:\d\d)$", s)
    if not m:
        return None
    base = datetime.fromisoformat(m.group(1) + ("+00:00" if m.group(3) == "Z" else m.group(3)))
    return base.timestamp() + (float("0" + m.group(2)) if m.group(2) else 0.0)


def underlyings():
    try:
        d = json.loads(ALLOWLIST.read_text())
        return [s for s in d.get("underlyings", []) if s]
    except Exception as e:  # pragma: no cover
        log.warning("allowlist read failed: %s", e)
        return ["SPY", "QQQ", "NVDA"]


def wide_underlyings():
    """WIDE: Sector watch names, minus anything in the core allowlist, minus WDC/STX/SNDK."""
    try:
        d = json.loads(WIDE_ALLOWLIST.read_text())
        syms = [(x if isinstance(x, str) else (x or {}).get("symbol")) for x in d.get("symbols", [])]
    except Exception as e:  # pragma: no cover
        log.warning("wide allowlist read failed: %s", e)
        return []
    core = set(underlyings())
    return sorted({s for s in syms if s and s not in core and s not in WIDE_EXCLUDE})


# ----------------------------------------------------------------------------- selection
def select_contracts(budget=BUDGET, syms=None, floor=4, cap=110):
    syms = underlyings() if syms is None else syms
    today = datetime.now(ET).date()
    spots = {}
    for i in range(0, len(syms), 50):
        chunk = syms[i:i + 50]
        try:
            d = _get("/v2/stocks/snapshots", {"symbols": ",".join(chunk), "feed": "sip"})
            for s, v in d.items():
                p = ((v or {}).get("latestTrade") or {}).get("p") or ((v or {}).get("dailyBar") or {}).get("c")
                if p:
                    spots[s] = float(p)
        except Exception as e:
            log.warning("spot snapshot failed: %s", e)
    per = {}
    for s in syms:
        spot = spots.get(s)
        if not spot:
            continue
        band = 0.05 if s in INDEX_ETF else 0.12
        params = {"feed": "opra", "limit": 1000,
                  "expiration_date_gte": today.isoformat(),
                  "expiration_date_lte": (today + timedelta(days=MAX_DTE)).isoformat(),
                  "strike_price_gte": f"{spot * (1 - band):.2f}", "strike_price_lte": f"{spot * (1 + band):.2f}"}
        rows, tok, pages = [], None, 0
        try:
            while True:
                if tok:
                    params["page_token"] = tok
                d = _get(f"/v1beta1/options/snapshots/{s}", params)
                for c, v in (d.get("snapshots") or {}).items():
                    db = v.get("dailyBar") or {}
                    vol = 0
                    if db.get("t", "")[:10] == today.isoformat():
                        vol = db.get("v") or 0
                    prev = (v.get("prevDailyBar") or {}).get("v") or 0
                    m = OCC.match(c)
                    if not m:
                        continue
                    k = int(m.group(4)) / 1000.0
                    vw = db.get("vw") or (v.get("latestTrade") or {}).get("p") or 0
                    rows.append({"c": c, "vol": vol, "prev": prev, "prem": vol * vw * 100,
                                 "dist": abs(k - spot) / spot, "exp": m.group(2), "cp": m.group(3)})
                tok = d.get("next_page_token"); pages += 1
                if not tok or pages >= 12:
                    break
        except Exception as e:
            log.warning("chain snapshot %s failed: %s", s, e)
        if rows:
            per[s] = rows
    # allocate budget proportional to sqrt(window premium) with floor/cap
    w = {s: max(sum(r["prem"] for r in rows), sum(r["prev"] for r in rows) * 50.0, 1.0) ** 0.5 for s, rows in per.items()}
    W = sum(w.values()) or 1.0
    alloc = {s: max(floor, min(cap, int(round(budget * w[s] / W)))) for s in per}
    while sum(alloc.values()) > budget:
        big = max(alloc, key=lambda s: alloc[s]); alloc[big] -= 1
    spare = budget - sum(alloc.values())
    for s in sorted(per, key=lambda s: -w[s]):
        if spare <= 0:
            break
        add = min(spare, cap - alloc[s], max(0, len(per[s]) - alloc[s]))
        alloc[s] += add; spare -= add
    chosen, coverage = [], {}
    for s, rows in per.items():
        rows.sort(key=lambda r: (-(r["prem"] or 0), -(r["vol"] or 0), -(r["prev"] or 0), r["dist"]))
        pick = rows[:alloc[s]]
        chosen += [r["c"] for r in pick]
        tv = sum(r["vol"] for r in rows) or 0
        tp = sum(r["prem"] for r in rows) or 0
        coverage[s] = {"n": len(pick), "chain_n": len(rows), "spot": spots.get(s),
                       "vol_cov": round(sum(r["vol"] for r in pick) / tv, 3) if tv else None,
                       "prem_cov": round(sum(r["prem"] for r in pick) / tp, 3) if tp else None,
                       "expiries": sorted({r["exp"] for r in pick})[:4]}
    return chosen[:budget], coverage


# ----------------------------------------------------------------------------- state
class Win:
    __slots__ = ("cb", "cs", "pb", "ps", "cbn", "csn", "pbn", "psn", "scb", "spb", "neu", "n", "unq")

    def __init__(self):
        self.cb = self.cs = self.pb = self.ps = 0.0
        self.cbn = self.csn = self.pbn = self.psn = 0
        self.scb = self.spb = 0.0
        self.neu = 0.0
        self.unq = 0.0
        self.n = 0


class State:
    def __init__(self):
        self.quotes: dict[str, tuple] = {}
        self.last_px: dict[str, float] = {}
        self.last_side: dict[str, int] = {}
        self.events: dict[str, deque] = defaultdict(deque)   # und -> (recv, cp, side, prem, size, how)
        self.day: dict[str, Win] = defaultdict(Win)
        self.day_date = None
        self.last_trade: dict[str, tuple] = {}               # und -> (exch_ts, recv_ts)
        self.lat = deque(maxlen=20000)                       # (recv, recv-exch)
        self.recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self.counts = defaultdict(int)
        self.subs: list[str] = []
        self.coverage = {}
        self.selected_at = None
        self.ws_state = "init"
        self.ws_connected_at = None
        self.ws_last_msg = None
        self.ws_errors = deque(maxlen=20)
        self.started = time.time()
        self.snapshot = {}
        # OPTMOM state
        self.hist: dict[str, dict] = defaultdict(lambda: {w: deque(maxlen=HIST_N) for w in WKEYS})  # und -> {win: deque[slot]}
        self.last_boundary = None
        self.last_d: dict[str, dict] = defaultdict(dict)
        self.mom: dict[str, dict] = {}
        self.rerank_at: dict[str, float] = {}
        self.histq: queue.Queue = queue.Queue(maxsize=200)
        self.subs_ready_at = None  # OPTMOM2: first non-empty subscription ack on this connection
        self.day_date_seen = False  # OPTMOM3
        self.wide: set[str] = set()          # WIDE: underlyings classified by tick test (trades only)
        self.wide_subs: list[str] = []
        self.wide_coverage = {}
        self.wide_selected_at = None
        self.wide_snapshot = {}

    # --- classification
    def classify(self, sym, p, exch):
        """Quote rule vs prior NBBO. Returns (side, how). how='unq' = no usable quote (unclassified)."""
        q = self.quotes.get(sym)
        how, side = None, 0
        if not q:
            return 0, "unq_noquote"
        bp, ap, qt = q
        if bp <= 0 or ap <= 0 or ap <= bp:
            return 0, "unq_crossed"
        if exch and qt and exch - qt > QUOTE_MAX_AGE:
            return 0, "unq_stale"
        if (ap - bp) > 0.5 * ((ap + bp) / 2):
            return 0, "unq_wide"
        if True:
            if p >= ap:
                side, how = 1, "ask"
            elif p <= bp:
                side, how = -1, "bid"
            else:
                mid = (bp + ap) / 2
                if p > mid + 1e-9:
                    side, how = 1, "mid+"
                elif p < mid - 1e-9:
                    side, how = -1, "mid-"
        if side == 0:
            lp = self.last_px.get(sym)
            if lp is not None and p > lp:
                side, how = 1, "tick"
            elif lp is not None and p < lp:
                side, how = -1, "tick"
            elif lp is not None and self.last_side.get(sym):
                side, how = self.last_side[sym], "tick0"
            else:
                how = "neutral"
        return side, how

    def classify_tick(self, sym, p):
        """WIDE: tick test only (no NBBO subscribed for wide contracts)."""
        lp = self.last_px.get(sym)
        if lp is not None and p > lp:
            return 1, "tick"
        if lp is not None and p < lp:
            return -1, "tick"
        if lp is not None and self.last_side.get(sym):
            return self.last_side[sym], "tick0"
        return 0, "neutral"

    def on_trade(self, m, recv):
        sym = m.get("S"); p = m.get("p"); sz = m.get("s") or 0
        if not sym or p is None:
            return
        mm = OCC.match(sym)
        if not mm:
            return
        und, cp = mm.group(1), mm.group(3)
        exch = _ts(m.get("t"))
        cond = m.get("c") or ""
        wide = und in self.wide
        self.counts["wide_trades" if wide else "trades"] += 1
        if exch:
            self.lat.append((recv, recv - exch))
            self.last_trade[und] = (exch, recv)
        prem = float(p) * sz * 100.0
        pre = "wide_" if wide else ""
        if any(ch in CANCEL_LATE for ch in cond):
            self.counts[pre + "excl_cancel_late"] += 1; return
        if any(ch in MULTI_COND or ch in STOCKOPT_COND for ch in cond):
            self.counts[pre + "excl_complex"] += 1
            self.events[und].append((recv, cp, 0, prem, sz, "complex"))
            return
        side, how = self.classify_tick(sym, float(p)) if wide else self.classify(sym, float(p), exch)
        self.last_px[sym] = float(p)
        if side:
            self.last_side[sym] = side
        self.counts[pre + "cls_" + how] += 1
        self.events[und].append((recv, cp, side, prem, sz, how))
        self.recent[und].append({"S": sym, "t": _iso(exch), "recv": _iso(recv), "lag_ms": round((recv - exch) * 1000, 1) if exch else None,
                                 "p": p, "s": sz, "c": cond, "side": side, "how": how,
                                 "bid": (self.quotes.get(sym) or (None, None))[0], "ask": (self.quotes.get(sym) or (None, None))[1]})
        d = self.day[und]
        self._add(d, cp, side, prem, sz, how)

    @staticmethod
    def _add(w, cp, side, prem, sz, how):
        w.n += 1
        if side == 0:
            if how.startswith("unq"):
                w.unq += prem
            else:
                w.neu += prem
            return
        strict = how in ("ask", "bid")
        if cp == "C":
            if side > 0:
                w.cb += prem; w.cbn += sz
                if strict: w.scb += prem
            else:
                w.cs += prem; w.csn += sz
        else:
            if side > 0:
                w.pb += prem; w.pbn += sz
                if strict: w.spb += prem
            else:
                w.ps += prem; w.psn += sz

    def compute(self):
        now = time.time()
        dd = datetime.now(ET).date()
        if self.day_date != dd:
            self.day.clear(); self.day_date = dd
            if self.day_date_seen:  # OPTMOM3: real rollover only, keep warm-start on boot
                self.hist.clear(); self.last_d.clear(); self.mom.clear(); self.last_boundary = None  # OPTMOM
            self.day_date_seen = True
        horizon = now - max(WINDOWS)
        out = {}
        for und, ev in self.events.items():
            while ev and ev[0][0] < horizon:
                ev.popleft()
            res = {}
            for wsec in WINDOWS:
                w = Win(); cx = 0.0
                cut = now - wsec
                for (r, cp, side, prem, sz, how) in reversed(ev):
                    if r < cut:
                        break
                    if how == "complex":
                        cx += prem; continue
                    self._add(w, cp, side, prem, sz, how)
                res[f"{wsec}s"] = _summ(w, cx)
            res["day"] = _summ(self.day[und], None)
            lt = self.last_trade.get(und)
            res["last_trade_t"] = _iso(lt[0]) if lt else None
            res["last_recv"] = _iso(lt[1]) if lt else None
            res["contracts"] = ((self.wide_coverage if und in self.wide else self.coverage).get(und) or {}).get("n")
            if und in self.wide:
                res["tier"], res["cls"] = "wide", "tick"
                for k in ("15s", "60s", "day"):
                    res[k]["cls"] = "tick"
            out[und] = res
        if MOMENTUM:  # OPTMOM
            try:
                self.sample(now, out)
            except Exception as e:  # never break the chips
                log.warning("momentum sample failed: %s", e)
            for und, res in out.items():
                if und in self.mom:
                    res["mom"] = self.mom[und]
        lags = [l for (r, l) in self.lat if r >= now - 300]
        lagstat = None
        if lags:
            ls = sorted(lags)
            lagstat = {"n": len(ls), "p50_ms": round(ls[len(ls) // 2] * 1000, 1),
                       "p95_ms": round(ls[min(len(ls) - 1, int(len(ls) * 0.95))] * 1000, 1),
                       "max_ms": round(ls[-1] * 1000, 1)}
        if WIDE_ON:  # WIDE: separate file / snapshot; the core snapshot keeps only core names
            wout = {u: out.pop(u) for u in list(out) if u in self.wide}
            self.wide_snapshot = {
                "service": "oid-optflow", "version": VERSION, "tier": "wide", "source": "alpaca-opra-ws (trades only)",
                "computed_at": _iso(now), "computed_epoch": round(now, 3),
                "ws": {"state": self.ws_state, "connected_at": _iso(self.ws_connected_at),
                       "last_msg_age_s": round(now - self.ws_last_msg, 2) if self.ws_last_msg else None},
                "subs": len(self.wide_subs), "selected_at": _iso(self.wide_selected_at),
                "counts": {k: v for k, v in self.counts.items() if k.startswith("wide_")},
                "method": "TICK TEST ONLY (no OPRA quotes for wide contracts: Alpaca 1,000-quote cap per connection is used by the core): "
                          "print above the contract's previous print = buy, below = sell, equal = previous side, first print of the day = neutral; "
                          "multi-leg + stock-tied (complex), cancel/late excluded. Same 15 s / 60 s windows, C/P, net and momentum as the core.",
                "momentum": ({"enabled": True, "hist_n": HIST_N, "sample_s": SAMPLE_S, "deadband": DB} if MOMENTUM else {"enabled": False}),
                "thin_prints": THIN_PRINTS, "underlyings": wout,
            }
        self.snapshot = {
            "service": "oid-optflow", "version": VERSION, "source": "alpaca-opra-ws",
            "computed_at": _iso(now), "computed_epoch": round(now, 3),
            "ws": {"state": self.ws_state, "connected_at": _iso(self.ws_connected_at),
                   "last_msg_age_s": round(now - self.ws_last_msg, 2) if self.ws_last_msg else None},
            "subs": len(self.subs), "selected_at": _iso(self.selected_at),
            "exch_to_recv_lag_5m": lagstat,
            "counts": dict(self.counts),
            "method": "quote rule vs prior OPRA NBBO: >=ask buy, <=bid sell, inside spread nearest side, exact mid tick test; unclassified if no quote / crossed-locked / quote >2s older than trade / spread >50% of mid; multi-leg + stock-tied (complex), cancel/late excluded" + ("; momentum (mom): 15 s slots of L=ln((cb+k)/(pb+k)), k=max(2000,5% of cb+pb), clamped +-ln10; OLS slope of last 4 slots per min; >=3 valid incl latest; deadband w/ hysteresis" if MOMENTUM else ""),
            "momentum": ({"enabled": True, "hist_n": HIST_N, "sample_s": SAMPLE_S, "deadband": DB} if MOMENTUM else {"enabled": False}),
            "quote_max_age_s": QUOTE_MAX_AGE, "thin_prints": THIN_PRINTS,
            "underlyings": out,
        }
        return self.snapshot

    # ------------------------------------------------------------- OPTMOM
    def _why(self, und, w, wsec, b, sm):
        if not _rth(b):
            return "closed"
        if b - wsec < _open_epoch(b):
            return "warmup"
        if (self.ws_state != "subscribed_ready" or not self.ws_connected_at or not self.subs_ready_at
                or (b - wsec) < max(self.ws_connected_at, self.subs_ready_at)):  # OPTMOM2
            return "ws"
        lt = self.last_trade.get(und)
        if not lt or b - lt[1] > STALE_S:
            return "stale"
        if not sm or sm.get("thin", True):
            return "thin"
        if (sm.get("cb") or 0) + (sm.get("pb") or 0) <= 0:
            return "nobuy"
        return None

    def sample(self, now, out):
        b = math.floor(now / SAMPLE_S) * SAMPLE_S
        if self.last_boundary is not None and b <= self.last_boundary:
            return
        if self.last_boundary is not None and b - self.last_boundary > SAMPLE_S:
            miss = int((b - self.last_boundary) // SAMPLE_S) - 1
            for k in range(max(0, miss - HIST_N), miss):
                tb = self.last_boundary + (k + 1) * SAMPLE_S
                for und in list(self.hist):
                    for w in WKEYS:
                        self.hist[und][w].append({"t": tb, "cp": None, "L": None, "cb": 0, "pb": 0, "n": 0, "why": "missed"})
        self.last_boundary = b
        line = {}
        for und in set(out) | set(self.hist):
            res = out.get(und) or {}
            lu = {}
            for w in WKEYS:
                sm = res.get(w) or {}
                why = self._why(und, w, int(w[:-1]), b, sm)
                cb, pb = sm.get("cb") or 0, sm.get("pb") or 0
                L = None if why else round(_logratio(cb, pb), 4)
                cp = None if why else sm.get("cp_buy")
                self.hist[und][w].append({"t": b, "cp": cp, "L": L, "cb": cb, "pb": pb, "n": sm.get("n") or 0, "why": why})
                lu[WKEYS[w]] = [cp, L, cb, pb, sm.get("n") or 0, why]
            line[und] = lu
            self.mom[und] = {w: self.momentum(und, w) for w in WKEYS}
        if HIST_LOG and _rth(b):
            wl = {u: line.pop(u) for u in list(line) if u in self.wide}   # WIDE: own file
            try:
                self.histq.put_nowait({"t": b, "pt": datetime.fromtimestamp(b, PT).strftime("%H:%M:%S"),
                                       "sel": _iso(self.selected_at), "u": line})
                if wl:
                    self.histq.put_nowait({"t": b, "pt": datetime.fromtimestamp(b, PT).strftime("%H:%M:%S"),
                                           "sel": _iso(self.wide_selected_at), "tier": "wide", "cls": "tick", "u": wl})
            except queue.Full:
                pass

    def momentum(self, und, w):
        wsec = int(w[:-1])
        sl = list(self.hist[und][w])
        h = [x["cp"] for x in sl]
        rr = self.rerank_at.get(und)
        last = sl[-MOM_SLOTS:]
        ok = lambda x: x["L"] is not None and not (rr and x["t"] - wsec < rr)
        valid = [x for x in last if ok(x)]
        d = s = None
        if last and ok(last[-1]) and len(valid) >= MOM_MIN_VALID:
            s = _ols_slope([(x["t"], x["L"]) for x in valid]) * 60.0
            din, dout = DB[w]
            prev = self.last_d[und].get(w)
            sg = 1 if s > 0 else -1
            if prev in (1, -1) and s * prev >= dout:
                d = prev
            elif abs(s) >= din:
                d = sg
            else:
                d = 0
            s = round(s, 2)
        self.last_d[und][w] = d
        return {"d": d, "s": s, "nv": len(valid), "h": h, "rr": bool(rr and last and any(x["t"] - wsec < rr for x in last))}


def _r(a, b):
    if b > 0:
        return round(a / b, 2)
    return None if a <= 0 else 99.0


def _summ(w, cx):
    d = {"cb": round(w.cb), "cs": round(w.cs), "pb": round(w.pb), "ps": round(w.ps),
         "cbn": w.cbn, "csn": w.csn, "pbn": w.pbn, "psn": w.psn,
         "cp_buy": _r(w.cb, w.pb),
         "cp_buy_strict": _r(w.scb, w.spb),
         "net": round((w.cb - w.cs) - (w.pb - w.ps)),
         "neutral": round(w.neu), "unclassified": round(w.unq), "n": w.n}
    tot = w.cb + w.cs + w.pb + w.ps + w.neu + w.unq + (cx or 0)
    d["coverage"] = round((w.cb + w.cs + w.pb + w.ps) / tot, 3) if tot > 0 else None
    d["thin"] = w.n < THIN_PRINTS
    if cx is not None:
        d["complex"] = round(cx)
    return d


ST = State()


# ----------------------------------------------------------------------------- websocket
class Stream:
    def __init__(self, st: State):
        self.st = st
        self.ws = None
        self.want: set[str] = set()        # core: quotes + trades
        self.want_wide: set[str] = set()   # WIDE: trades only
        self.have_q: set[str] = set()
        self.have_t: set[str] = set()
        self.lock = asyncio.Lock()

    async def send(self, obj):
        await self.ws.send_bytes(msgpack.packb(obj, use_bin_type=True))

    async def sync_subs(self):
        if not self.ws or self.st.ws_state != "subscribed_ready":
            return
        async with self.lock:
            want_t = self.want | (self.want_wide if WIDE_ON else set())
            rem_q = sorted(self.have_q - self.want); rem_t = sorted(self.have_t - want_t)
            add_core = sorted(self.want - (self.have_q & self.have_t))
            add_t = sorted(want_t - self.have_t - set(add_core))
            for i in range(0, len(rem_q), 200):
                await self.send({"action": "unsubscribe", "quotes": rem_q[i:i + 200]})
            for i in range(0, len(rem_t), 200):
                await self.send({"action": "unsubscribe", "trades": rem_t[i:i + 200]})
            for i in range(0, len(add_core), 200):
                ch = add_core[i:i + 200]
                await self.send({"action": "subscribe", "quotes": ch, "trades": ch})
            for i in range(0, len(add_t), 200):   # WIDE: trades only, never quotes
                await self.send({"action": "subscribe", "trades": add_t[i:i + 200]})
            if add_core or add_t or rem_q or rem_t:
                log.info("subscribe core +%d, trades-only +%d, -%dq -%dt (want core=%d wide=%d)",
                         len(add_core), len(add_t), len(rem_q), len(rem_t), len(self.want), len(self.want_wide))

    async def run(self):
        backoff = 2
        ssl_ctx = ssl.create_default_context()
        try:
            import certifi
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        while True:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(WS_URL, headers={"Content-Type": "application/msgpack"},
                                               heartbeat=20, ssl=ssl_ctx, max_msg_size=0) as ws:
                        self.ws = ws; self.have_q = set(); self.have_t = set(); self.st.ws_state = "connected"; self.st.subs_ready_at = None  # OPTMOM2
                        async for msg in ws:
                            if msg.type != aiohttp.WSMsgType.BINARY:
                                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    break
                                continue
                            recv = time.time()
                            self.st.ws_last_msg = recv
                            for m in msgpack.unpackb(msg.data, raw=False):
                                T = m.get("T")
                                if T == "q":
                                    bp, ap = m.get("bp"), m.get("ap")
                                    if bp is not None and ap is not None:
                                        self.st.quotes[m.get("S")] = (bp, ap, _ts(m.get("t")) or recv)
                                    self.st.counts["quotes"] += 1
                                elif T == "t":
                                    self.st.on_trade(m, recv)
                                elif T == "success" and m.get("msg") == "connected":
                                    await self.send({"action": "auth", "key": _key("APCA_API_KEY_ID"), "secret": _key("APCA_API_SECRET_KEY")})
                                elif T == "success" and m.get("msg") == "authenticated":
                                    self.st.ws_state = "subscribed_ready"; self.st.ws_connected_at = recv; backoff = 2
                                    log.info("authenticated on %s", WS_URL)
                                    await self.sync_subs()
                                elif T == "subscription":
                                    _had = bool(self.have_q)
                                    self.have_q = set(m.get("quotes") or []); self.have_t = set(m.get("trades") or [])
                                    if self.have_q and not _had:
                                        self.st.subs_ready_at = recv  # OPTMOM2
                                    log.info("subscription now quotes=%d trades=%d", len(m.get("quotes") or []), len(m.get("trades") or []))
                                elif T == "error":
                                    log.warning("stream error: %s", m)
                                    self.st.ws_errors.append({"at": _iso(recv), **{k: m.get(k) for k in ("code", "msg")}})
                                    if m.get("code") in (406, 402, 409):
                                        backoff = 60
                                    if m.get("code") == 405:  # symbol limit: shrink WIDE first (trades-only), core only if no wide left
                                        if self.want_wide:
                                            self.want_wide = set(sorted(self.want_wide)[: int(len(self.want_wide) * 0.8)])
                                        else:
                                            self.want = set(sorted(self.want)[: int(len(self.want) * 0.8)])
            except Exception as e:
                log.warning("ws error: %s", e)
                self.st.ws_errors.append({"at": _iso(time.time()), "msg": str(e)[:200]})
            self.st.ws_state = "disconnected"; self.ws = None
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 120)


STREAM = Stream(ST)


async def selector():
    loop = asyncio.get_running_loop()
    while True:
        try:
            chosen, cov = await loop.run_in_executor(None, select_contracts)
            if chosen:
                if ST.subs:  # OPTMOM: flag names whose contract set changed a lot
                    def _by(lst):
                        g = defaultdict(set)
                        for c in lst:
                            m = OCC.match(c)
                            if m: g[m.group(1)].add(c)
                        return g
                    old, new = _by(ST.subs), _by(chosen)
                    t_rr = time.time()
                    for u, oc in old.items():
                        if oc and len(oc & new.get(u, set())) / len(oc) < RERANK_MIN_OVERLAP:
                            ST.rerank_at[u] = t_rr
                ST.subs = chosen; ST.coverage = cov; ST.selected_at = time.time()
                STREAM.want = set(chosen)
                SUBS_OUT.write_text(json.dumps({"selected_at": _iso(ST.selected_at), "budget": BUDGET, "max_dte": MAX_DTE,
                                                "n": len(chosen), "coverage": cov, "contracts": chosen}, indent=1))
                log.info("selected %d contracts across %d underlyings", len(chosen), len(cov))
                await STREAM.sync_subs()
        except Exception as e:
            log.exception("selector failed: %s", e)
        await asyncio.sleep(RESELECT_S)


async def selector_wide():
    """WIDE: trades-only contract set for the Sector watch names (own loop so core selection is never delayed)."""
    if not WIDE_ON:
        return
    loop = asyncio.get_running_loop()
    await asyncio.sleep(45)
    while True:
        try:
            syms = await loop.run_in_executor(None, wide_underlyings)
            ST.wide = set(syms)
            chosen, cov = await loop.run_in_executor(None, lambda: select_contracts(WIDE_BUDGET, syms, WIDE_FLOOR, WIDE_CAP))
            if chosen:
                ST.wide_subs = chosen; ST.wide_coverage = cov; ST.wide_selected_at = time.time()
                STREAM.want_wide = set(chosen) - STREAM.want
                WIDE_SUBS_OUT.write_text(json.dumps({"selected_at": _iso(ST.wide_selected_at), "budget": WIDE_BUDGET, "max_dte": MAX_DTE,
                                                     "channels": ["trades"], "cls": "tick", "n": len(chosen), "underlyings": len(syms),
                                                     "coverage": cov, "contracts": chosen}, indent=1))
                log.info("WIDE selected %d trade-only contracts across %d underlyings", len(chosen), len(cov))
                await STREAM.sync_subs()
        except Exception as e:
            log.exception("wide selector failed: %s", e)
        await asyncio.sleep(RESELECT_S)


async def writer():
    while True:
        t0 = time.time()
        try:
            snap = ST.compute()
            tmp = OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(snap, separators=(",", ":")))
            os.replace(tmp, OUT)
            if WIDE_ON and ST.wide_snapshot:
                tmp = WIDE_OUT.with_suffix(".tmp")
                tmp.write_text(json.dumps(ST.wide_snapshot, separators=(",", ":")))
                os.replace(tmp, WIDE_OUT)
        except Exception as e:
            log.exception("writer: %s", e)
        await asyncio.sleep(max(0.05, 1.0 - (time.time() - t0)))


def _hist_rotate(hdir=None):
    """OPTMOM: gzip non-today JSONL, delete gz older than HIST_KEEP_D days."""
    if hdir is None:
        for h in ((HIST_DIR, HIST_DIR_WIDE) if WIDE_ON else (HIST_DIR,)):
            _hist_rotate(h)
        return
    HIST_DIR_ = hdir
    HIST_DIR_.mkdir(parents=True, exist_ok=True)
    today = datetime.now(ET).date()
    for f in HIST_DIR_.glob("*.jsonl"):
        try:
            if date.fromisoformat(f.stem) < today:
                with open(f, "rb") as src, gzip.open(str(f) + ".gz", "wb") as dst:
                    dst.write(src.read())
                f.unlink()
        except Exception as e:
            log.warning("hist rotate %s: %s", f.name, e)
    for f in HIST_DIR_.glob("*.jsonl.gz"):
        try:
            if (today - date.fromisoformat(f.name[:10])).days > HIST_KEEP_D:
                f.unlink()
        except Exception:
            pass


def _hist_thread():
    cur = None
    while True:
        rec = ST.histq.get()
        try:
            day = datetime.fromtimestamp(rec["t"], ET).date().isoformat()
            wide = rec.get("tier") == "wide"
            f = (HIST_DIR_WIDE if wide else HIST_DIR) / f"{day}.jsonl"
            if cur != day:
                _hist_rotate(); cur = day
            new = not f.exists()
            with open(f, "a") as fh:
                if new:
                    hdr = {"hdr": 1, "version": VERSION, "tuple": ["cp", "L", "cb", "pb", "n", "why"],
                           "deadband": DB, "hist_n": HIST_N, "sample_s": SAMPLE_S}
                    if wide:
                        hdr.update({"tier": "wide", "cls": "tick", "note": "trades-only, tick-test classification"})
                    fh.write(json.dumps(hdr) + "\n")
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        except Exception as e:
            log.warning("hist log write: %s", e)


def _hist_warm(hdir=None):
    """OPTMOM: refill deques from the tail of today's JSONL after a restart."""
    if hdir is None:
        return sum(_hist_warm(h) for h in ((HIST_DIR, HIST_DIR_WIDE) if WIDE_ON else (HIST_DIR,)))
    f = hdir / f"{datetime.now(ET).date().isoformat()}.jsonl"
    if not f.exists():
        return 0
    try:
        with open(f, "rb") as fh:
            fh.seek(0, 2); sz = fh.tell(); fh.seek(max(0, sz - 60000))
            lines = fh.read().decode("utf-8", "ignore").splitlines()[1:]
        recs = [json.loads(l) for l in lines[-HIST_N:] if l.startswith('{"t"')]
    except Exception as e:
        log.warning("hist warm: %s", e); return 0
    cut = time.time() - HIST_N * SAMPLE_S
    n = 0
    for rec in recs:
        if rec["t"] < cut:
            continue
        for und, lu in rec["u"].items():
            for w, k in WKEYS.items():
                v = lu.get(k)
                if v:
                    ST.hist[und][w].append({"t": rec["t"], "cp": v[0], "L": v[1], "cb": v[2], "pb": v[3], "n": v[4], "why": v[5]})
        ST.last_boundary = rec["t"]; n += 1
    return n


async def h_history(req):
    u = req.query.get("sym", "NVDA").upper()
    h = ST.hist.get(u) or {}
    return web.json_response({"sym": u, "mom": ST.mom.get(u), "slots": {w: list(h.get(w, [])) for w in WKEYS}})


async def h_flow(req):
    return web.json_response(ST.snapshot or ST.compute())


async def h_health(req):
    s = ST.snapshot or {}
    w = ST.wide_snapshot or {}
    return web.json_response({k: s.get(k) for k in ("service", "version", "computed_at", "ws", "subs", "selected_at", "exch_to_recv_lag_5m", "counts")}
                             | {"errors": list(ST.ws_errors), "coverage": ST.coverage,
                                "wide": {"enabled": WIDE_ON, "subs": len(ST.wide_subs), "subscribed_trades": len(STREAM.have_t - STREAM.have_q),
                                         "underlyings": len(ST.wide), "selected_at": _iso(ST.wide_selected_at), "counts": w.get("counts"),
                                         "coverage": ST.wide_coverage}})


async def h_recent(req):
    u = req.query.get("sym", "NVDA").upper()
    return web.json_response(list(ST.recent.get(u, [])))


async def main():
    ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
    app = web.Application()
    app.router.add_get("/v1/optflow", h_flow)
    app.router.add_get("/v1/health", h_health)
    app.router.add_get("/v1/recent", h_recent)
    app.router.add_get("/v1/history", h_history)  # OPTMOM
    if WIDE_ON:
        ST.wide = set(wide_underlyings())   # known before the warm start so wide slots never land in the core file
    if MOMENTUM:
        try:
            _hist_rotate()
            log.info("momentum on; warm-started %d slots from JSONL", _hist_warm())
        except Exception as e:
            log.warning("hist init: %s", e)
        if HIST_LOG:
            threading.Thread(target=_hist_thread, daemon=True, name="cp-hist").start()
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()
    log.info("oid-optflow %s listening on 127.0.0.1:%d budget=%d max_dte=%d wide=%s wide_budget=%d", VERSION, PORT, BUDGET, MAX_DTE, WIDE_ON, WIDE_BUDGET)
    await asyncio.gather(STREAM.run(), selector(), selector_wide(), writer())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    asyncio.run(main())
