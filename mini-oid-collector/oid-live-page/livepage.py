#!/usr/bin/env python3
"""OID private live page (Mac mini, 2026-10-18). Stdlib only, python3.9+.

A separate, read-only service: polls the collector's /v1/live-volume once a second (plus held-option marks every 5 s
and the desk's live trades every 30 s), merges 1-min volume history from the collector's bar files, reads local UW
net-prem / flow-alerts JSON (~45 s) for soft put/call lean badges (zero UW API calls), and pushes the
result to one HTML page over Server-Sent Events.

  bind      127.0.0.1:8791 only (exposed to the tailnet with `tailscale serve`, HTTPS, tailnet-only; never Funnel)
  token     read in-process from ~/oid-quote/secrets/OID_QUOTE_TOKEN; never sent to the browser, never logged
  writes    nothing except its own log; never touches the collector, the trigger engine or Robinhood

Routes: /  (page)   /stream  (SSE)   /state.json  (current state)   /healthz   /wide-sectors.json
CHART (2026-10-20): /chart.json?sym=&iv=15s|1m|5m|15m|1h|1d&range=1D|1W|1M|3M|YTD|1Y&ext=0|1&since=<epoch s>  (read-only
bars + score + C/P + wall history for the click-to-open chart; built by the chart_backend.py child process, oid-desk venv
duckdb, nice 10, cached), /vendor/lightweight-charts.standalone.production.js (TradingView Lightweight Charts 5.0.9,
Apache-2.0, served locally, no CDN). Wall history recorder: appends each new FlashAlpha wall level the page sees to
~/oid-data/walls-history/walls-YYYYMMDD.jsonl (the only file this service writes besides its log).

WIDE / Sector watch (2026-10-20): a separate, collapsible section below the core tiles for the 144 sector names in
wide-sectors.json. Data = collector /v1/live-volume?tier=wide (SIP trades + 1-min bars only, no quotes), read every
5 s. Columns: price, % change, 1-min rvol, surge flag (>=3x) and mover flag (>=3% vs prior close), FlashAlpha walls only
when data/fa-walls-wide.json has them (fetched by com.oid.desk.fa-walls for surging wide names, capped). Wide names
are never added to `rows`, so fa-walls rotation, mover-alert and every other core consumer stay core-only; wide
alerts are page-only and batched per sector (no chat alerts).
LIGHT score (2026-10-20): each wide row also carries "ls" = the light direction score from ~/oid-data/score/latest-wide.json
(com.oid.desk.score-wide; trend+volume+market only, raw, unsmoothed, 5 s). Display only.
"""
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.request
import gzip
import select
import subprocess
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET, PT = ZoneInfo("America/New_York"), ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    ET = PT = timezone.utc

HOME = Path.home()
HOST = os.environ.get("OID_LIVEPAGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("OID_LIVEPAGE_PORT", "8791"))
COLLECTOR = os.environ.get("OID_LIVEPAGE_COLLECTOR", "http://127.0.0.1:8787")
TOKEN_FILE = Path(os.environ.get("OID_LIVEPAGE_TOKEN_FILE", str(HOME / "oid-quote/secrets/OID_QUOTE_TOKEN")))
STORE = Path(os.environ.get("OID_LIVEPAGE_STORE", str(HOME / "oid-desk/desk/cache/bars/store")))
NORMS = STORE.parent / "live-norms-1m.json"
TRADES = Path(os.environ.get("OID_LIVEPAGE_TRADES", str(HOME / "oid-desk/desk/paper-trades/trades.json")))
DESK = Path(os.environ.get("OID_LIVEPAGE_DESK", str(HOME / "oid-desk/desk")))
UW_NET = Path(os.environ.get("OID_LIVEPAGE_UW_NET", str(DESK / "market-data/latest/uw-net-prem.json")))
UW_FLOW = Path(os.environ.get("OID_LIVEPAGE_UW_FLOW", str(DESK / "market-data/latest/uw-flow-alerts.json")))
UW_TIDE = Path(os.environ.get("OID_LIVEPAGE_UW_TIDE", str(DESK / "market-data/latest/uw-market-tide.json")))
UW_REFRESH_S = float(os.environ.get("OID_LIVEPAGE_UW_REFRESH_S", "45"))
UW_LEAN_DEADBAND = 50_000.0  # $ net premium below this → FLAT (soft only)
UW_LEAN5_DEADBAND = 25_000.0  # 5m window is 1/3 of 15m → half the band (soft only)
UW5_MIN_S, UW5_MAX_S, UW5_TARGET_S = 180, 600, 300  # snapshot gap accepted for the 5m delta
UW5_STALE_S = 600  # newest UW snapshot older than this → 5m chip shows "—"
GUIDE_TYPES = {".md": "text/markdown; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
               ".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
               ".json": "application/json"}
HERE = Path(__file__).resolve().parent
UW5_HIST_FILE = HERE / "data/uw-net-hist.json"
SECTORS_FILE = HERE / "sectors.json"
WIDE_SECTORS_FILE = HERE / "wide-sectors.json"   # WIDE: sector watch groups (separate from sectors.json on purpose)
WIDE_WALLS_FILE = HERE / "data/fa-walls-wide.json"  # WIDE: FA walls for surging wide names (com.oid.desk.fa-walls)
WIDE_STORE = Path(os.environ.get("OID_LIVEPAGE_WIDE_STORE", str(HOME / "oid-quote/cache/bars-wide/store")))
WIDE_EVERY_S = 5.0        # collector read cadence for the wide tier
WIDE_SURGE_RVOL = 3.0     # 1-min rvol >= this -> surge flag
WIDE_MOVE_PCT = 3.0       # |% change vs prior close| >= this -> mover flag
WIDE_BATCH_S = 15 * 60    # sector alert batch window
WIDE_WALLS_MAX_AGE_S = 8 * 3600
WIDE_LIGHT_FILE = Path(os.environ.get("OID_LIVEPAGE_WIDE_SCORE", str(HOME / "oid-data/score/latest-wide.json")))  # LIGHT score (com.oid.desk.score-wide)
WIDE_OPTFLOW_FILE = Path(os.environ.get("OID_LIVEPAGE_WIDE_OPTFLOW", str(HOME / "oid-optflow/data/optflow-wide.json")))  # WIDECP: trades-only tick-test C/P
WIDE_FULL_FILE = Path(os.environ.get("OID_LIVEPAGE_WIDE_FULL", str(HOME / "oid-data/score/latest-widefull.json")))  # WIDECP: full score, 2nd wide profile
WIDE_CP_BAND = 1.10          # WIDECP flow lean: 1m (else 15s) C/P > 1.10 CALL, < 1/1.10 PUT, else FLAT (same band as the score context)
WIDE_LIGHT_STALE_S = 30      # light feed older than this -> chip greyed
WIDE_LIGHT_MAX_AGE_S = 900   # older than this -> chip hidden

# ---- DIRECTION (2026-10-20): real-time volume + C/P direction on every core row. Additive only: no existing number
# is hidden, replaced or smoothed. Computed every 1 s server-side (the page redraws every <=5 s).
DIR_CFG = {
    # volume: last 15 s rate vs the prior 60 s rate (15-75 s ago), from the collector's per-second SIP print buckets
    "vol_up_x": 1.3,          # ratio >= this -> ▲ gaining
    "vol_dn_x": 0.7,          # ratio <= this -> ▼ losing ("–" in between)
    "vol_min_shares": 500,    # 15 s + prior 60 s volume below this -> thin, shown "·" (no arrow)
    # C/P: optflow 15 s and 1 m call-buy ÷ put-buy premium now vs the reading ~60 s ago
    "cp_lookback_s": 60,      # compare with the sample closest to 60 s ago ...
    "cp_lookback_tol_s": 15,  # ... accepted if 45-75 s old
    "cp_flat_abs": 0.10,      # |Δ C/P| below this -> "–"
    "cp_strong_x": 2.0,       # STRONG if C/P at least doubles or halves ...
    "cp_strong_abs": 0.5,     # ... or moves more than 0.5 in absolute ratio
    "cp_min_prints": {"15s": 8, "1m": 20},          # floor on BOTH readings: prints in the window
    "cp_min_prem_k": {"15s": 15.0, "1m": 40.0},     # floor on BOTH readings: call-buy + put-buy premium ($K)
    "cp_cap": 20.0,           # ∞ / huge ratios capped here for the comparison
}
OPTFLOW_FILE = Path(os.environ.get("OID_LIVEPAGE_OPTFLOW", str(Path.home() / "oid-optflow/data/optflow.json")))  # OPTFLOW: Alpaca OPRA aggressor flow
OPTFLOW_STALE_S = 30.0  # no trade for this long (RTH) -> chip greyed

GUIDE_DIR = HERE / "guide"
LADDER_TOKEN_FILE = Path(os.environ.get("OID_LADDER_TOKEN_FILE", str(HERE / "secrets/LADDER_PUSH_TOKEN")))
LADDER_FILE = HERE / "data/ladder.jsonl"
LADDER_MAX_BYTES = 64 * 1024
LADDER_KEEP = 300
LADDER_RATE = 120  # accepted POSTs per hour
SPARK_N = 30
MAX_CLIENTS = 12
FULL_EVERY = 10  # ticks between full payloads (sparklines); light ticks carry only changing fields

LOCK = threading.Lock()
COND = threading.Condition(LOCK)
S = {"seq": 0, "full": None, "light": None, "err": None, "clients": 0, "started": time.time()}


def log(msg):
    sys.stdout.write(f"{datetime.now(PT):%Y-%m-%d %I:%M:%S %p PT} {msg}\n")
    sys.stdout.flush()


def pt_str(t):
    return datetime.fromtimestamp(t, PT).strftime("%Y-%m-%d %I:%M:%S %p PT")


def _token():
    try:
        return TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def get_json(path, params=None, timeout=3.0):
    url = COLLECTOR + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _token(), "Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def et_slot(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(ET)
    except ValueError:
        return None, None
    m = t.hour * 60 + t.minute - 570
    return t.strftime("%Y-%m-%d"), (m if 0 <= m < 390 else -1)


def occ_from_contract(c):
    """'META 2026-10-23 705 put' -> META261023P00705000 (single-leg only)."""
    try:
        p = str(c).split()
        if len(p) != 4:
            return None
        d = datetime.strptime(p[1], "%Y-%m-%d")
        k = int(round(float(p[2]) * 1000))
        return f"{p[0].upper()}{d:%y%m%d}{'P' if p[3].lower().startswith('p') else 'C'}{k:08d}"
    except Exception:
        return None


# ------------------------------------------------------------------ ladder dry-run snapshots (pushed by the box)
SYM_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
OUTCOMES = {None, "WIN_wall", "LOSS_stop", "FLAT", "AMBIG_same_bar"}


def _num(v, lo=-1e9, hi=1e12):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not (lo <= v <= hi):
        raise ValueError("bad number")
    return float(v)


def _str(v, n=80):
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("bad string")
    return v[:n]


def validate_ladder(obj):
    """Whitelist-copy of one ladder snapshot; raises ValueError on anything unexpected."""
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    sym = obj.get("symbol")
    if not isinstance(sym, str) or not SYM_RE.match(sym):
        raise ValueError("bad symbol")
    rid = _str(obj.get("id"), 40)
    if not rid or not re.match(r"^[A-Za-z0-9.\-]+$", rid):
        raise ValueError("bad id")
    d = obj.get("dir")
    if d not in ("up", "down", None):
        raise ValueError("bad dir")
    book = obj.get("book") or {}
    if not isinstance(book, dict):
        raise ValueError("bad book")
    lv = obj.get("levels") or {}
    if not isinstance(lv, dict):
        raise ValueError("bad levels")
    levels = {}
    for side in ("asks", "bids"):
        rows = lv.get(side) or []
        if not isinstance(rows, list) or len(rows) > 25:
            raise ValueError("bad levels side")
        levels[side] = [[_num(r[0], 0, 1e7), _num(r[1], 0, 1e10)] for r in rows if isinstance(r, list) and len(r) == 2]
    w = book.get("wall_ahead") or None
    if w is not None and not isinstance(w, dict):
        raise ValueError("bad wall")
    wall = None if not w else {"price": _num(w.get("price"), 0, 1e7), "qty": _num(w.get("qty"), 0, 1e10),
                                "dist_usd": _num(w.get("dist_usd"), 0, 1e7), "level": _num(w.get("level"), 0, 100),
                                "x_median": _num(w.get("x_median"), 0, 1e6)}
    o = obj.get("outcome") or None
    if o is not None and not isinstance(o, dict):
        raise ValueError("bad outcome")
    res = o.get("result") if o else None
    if res not in OUTCOMES:
        raise ValueError("bad result")
    out = {"id": rid, "symbol": sym, "logged_epoch": _num(obj.get("logged_epoch"), 1.5e9, 4e9), "time_pt": _str(obj.get("time_pt"), 40),
           "dir": d, "rvol_1m": _num(obj.get("rvol_1m"), 0, 1e4), "test": bool(obj.get("test")), "trigger": _str(obj.get("trigger"), 20),
           "note": _str(obj.get("note"), 120), "levels": levels,
           "book": {"empty": bool(book.get("empty")), "n_asks": _num(book.get("n_asks"), 0, 1e4), "n_bids": _num(book.get("n_bids"), 0, 1e4),
                    "ask0": _num(book.get("ask0"), 0, 1e7), "bid0": _num(book.get("bid0"), 0, 1e7), "mid": _num(book.get("mid"), 0, 1e7),
                    "spread": _num(book.get("spread"), -1e3, 1e7), "tick": _num(book.get("tick"), 0, 1e4),
                    "thin_ratio5": _num(book.get("thin_ratio5"), 0, 1e6), "thin": bool(book.get("thin")), "wall_ahead": wall},
           "outcome": None if not o else {"status": _str(o.get("status"), 20), "result": res, "mfe5": _num(o.get("mfe5")), "mfe15": _num(o.get("mfe15")),
                                          "mae15": _num(o.get("mae15")), "wall_hit_min": _num(o.get("wall_hit_min"), 0, 1e4),
                                          "stop_hit_min": _num(o.get("stop_hit_min"), 0, 1e4), "reason": _str(o.get("reason"), 80)}}
    if out["logged_epoch"] is None:
        raise ValueError("missing logged_epoch")
    return out


class Ladder:
    def __init__(self):
        self.rows = {}  # id -> row
        self.lock = threading.Lock()
        self.hits = []
        try:
            for ln in LADDER_FILE.read_text().splitlines():
                try:
                    r = json.loads(ln)
                    self.rows[r["id"]] = r
                except Exception:
                    continue
        except OSError:
            pass

    def token_ok(self, hdr):
        try:
            tok = LADDER_TOKEN_FILE.read_text().strip()
        except OSError:
            return False
        if len(tok) < 32 or not hdr or not hdr.startswith("Bearer "):
            return False
        return hmac.compare_digest(hdr[7:].strip().encode(), tok.encode())

    def rate_ok(self):
        now = time.time()
        self.hits = [h for h in self.hits if now - h < 3600]
        if len(self.hits) >= LADDER_RATE:
            return False
        self.hits.append(now)
        return True

    def upsert(self, rows):
        with self.lock:
            for r in rows:
                self.rows[r["id"]] = r
            keep = sorted(self.rows.values(), key=lambda r: r["logged_epoch"])[-LADDER_KEEP:]
            self.rows = {r["id"]: r for r in keep}
            LADDER_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = LADDER_FILE.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in keep))
            os.chmod(tmp, 0o600)
            tmp.replace(LADDER_FILE)

    def latest(self, n=10):
        with self.lock:
            rows = sorted(self.rows.values(), key=lambda r: -r["logged_epoch"])
        seen, out = set(), []
        for r in rows:
            if r["symbol"] in seen:
                continue
            seen.add(r["symbol"])
            out.append(r)
            if len(out) >= n:
                break
        return out


LADDER = Ladder()



# ------------------------------------------------------------------ UW put/call lean (local JSON only; zero API calls)
def _lean_side(net, dead=UW_LEAN_DEADBAND):
    """Soft CALL/PUT/FLAT from net call−put premium dollars."""
    if net is None:
        return None
    try:
        n = float(net)
    except (TypeError, ValueError):
        return None
    if abs(n) < dead:
        return "FLAT"
    return "CALL" if n > 0 else "PUT"


def _fmt_m(v):
    if v is None:
        return None
    try:
        return round(float(v) / 1e6, 2)
    except (TypeError, ValueError):
        return None


class UwLean:
    """Read-only lean from mini desk UW files (uw-refresh ~240s). Livepage polls files ~45s."""

    def __init__(self):
        self.by_sym = {}
        self.tide = None
        self.as_of_pt = None
        self.mtime = (0, 0, 0)
        self.loaded_at = 0
        self.hist = self._load_hist()  # [(as_of_epoch, date, {sym: day_net$})] newest last, for the 5m delta
        self.l5 = {}  # sym -> {net5_m, lean5, win5_min}
        self.l5_t = None  # epoch of newest snapshot used

    def _load_hist(self):
        try:
            h = json.loads(UW5_HIST_FILE.read_text())
            return [(float(t), str(d), {k: float(v) for k, v in m.items()}) for t, d, m in h][-12:]
        except Exception:
            return []

    def _save_hist(self):
        try:
            UW5_HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = UW5_HIST_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.hist[-12:]))
            tmp.replace(UW5_HIST_FILE)
        except Exception:
            pass

    def _update_5m(self, t, date, day_nets):
        """5m net = change in UW day net (call−put premium) between the newest snapshot and one ~5 min older."""
        if t is None or not day_nets:
            return
        if not self.hist or t > self.hist[-1][0] + 1:
            self.hist.append((t, date, day_nets))
            self.hist = self.hist[-12:]
            self._save_hist()
        lt, ld, lm = self.hist[-1]
        best = None
        for pt_, pd_, pm_ in self.hist[:-1]:
            gap = lt - pt_
            if pd_ == ld and UW5_MIN_S <= gap <= UW5_MAX_S and (best is None or abs(gap - UW5_TARGET_S) < abs(best[0] - UW5_TARGET_S)):
                best = (gap, pm_)
        l5 = {}
        if best:
            gap, pm_ = best
            for sym, v in lm.items():
                if sym in pm_:
                    n5 = v - pm_[sym]
                    l5[sym] = {"net5_m": _fmt_m(n5), "lean5": _lean_side(n5, UW_LEAN5_DEADBAND), "win5_min": round(gap / 60, 1)}
        self.l5, self.l5_t = l5, lt

    def lean5(self, sym, now):
        u = self.l5.get(sym)
        age = None if self.l5_t is None else round(now - self.l5_t)
        if not u or age is None or age > UW5_STALE_S:
            return {"lean5": None, "net5_m": None, "win5_min": None, "lean5_age_s": age}
        return dict(u, lean5_age_s=age)

    def refresh(self, now):
        if now - self.loaded_at < UW_REFRESH_S and self.by_sym:
            return
        try:
            nm = UW_NET.stat().st_mtime
        except OSError:
            nm = 0
        try:
            fm = UW_FLOW.stat().st_mtime
        except OSError:
            fm = 0
        try:
            tm = UW_TIDE.stat().st_mtime
        except OSError:
            tm = 0
        if (nm, fm, tm) == self.mtime and self.by_sym and now - self.loaded_at < UW_REFRESH_S * 2:
            self.loaded_at = now
            return
        by = {}
        as_of = None
        net_t, net_date, day_nets = None, None, {}
        # net-prem: day C/P volume + 15m net call−put
        try:
            d = json.loads(UW_NET.read_text())
            as_of = d.get("as_of_pt")
            try:
                net_t = datetime.strptime(str(d.get("as_of")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                net_t = None
            net_date = str((d.get("payload") or {}).get("date") or "")
            pt = (d.get("payload") or {}).get("per_ticker") or {}
            for sym, row in pt.items():
                if not isinstance(row, dict):
                    continue
                day = row.get("day") or {}
                l15 = row.get("last_15m") or {}
                cv, pv = day.get("call_volume"), day.get("put_volume")
                cp = None
                try:
                    if cv is not None and pv and float(pv) > 0:
                        cp = round(float(cv) / float(pv), 2)
                except (TypeError, ValueError):
                    cp = None
                ncp = l15.get("net_call_premium")
                npp = l15.get("net_put_premium")
                net15 = None
                try:
                    if ncp is not None or npp is not None:
                        net15 = float(ncp or 0) - float(npp or 0)
                except (TypeError, ValueError):
                    net15 = None
                try:
                    if day and (day.get("net_call_premium") is not None or day.get("net_put_premium") is not None):
                        day_nets[sym] = float(day.get("net_call_premium") or 0) - float(day.get("net_put_premium") or 0)
                except (TypeError, ValueError):
                    pass
                by[sym] = {
                    "cp": cp,
                    "cv": int(cv) if isinstance(cv, (int, float)) else None,
                    "pv": int(pv) if isinstance(pv, (int, float)) else None,
                    "net15_m": _fmt_m(net15),
                    "lean15": _lean_side(net15),
                    "day_net_m": _fmt_m(
                        (float(day.get("net_call_premium") or 0) - float(day.get("net_put_premium") or 0))
                        if day else None
                    ),
                    "ask_lean": None,
                    "ask_call_m": None,
                    "ask_put_m": None,
                }
        except Exception:
            pass
        # flow-alerts ask-side lean (same core-20 + focus set)
        try:
            d = json.loads(UW_FLOW.read_text())
            as_of = as_of or d.get("as_of_pt")
            bt = (d.get("payload") or {}).get("by_ticker") or {}
            for sym, row in bt.items():
                if not isinstance(row, dict):
                    continue
                ca = row.get("call_ask_prem")
                pa = row.get("put_ask_prem")
                try:
                    ca_f = float(ca) if ca is not None else None
                    pa_f = float(pa) if pa is not None else None
                except (TypeError, ValueError):
                    ca_f = pa_f = None
                ask_lean = None
                if ca_f is not None or pa_f is not None:
                    ask_lean = _lean_side((ca_f or 0) - (pa_f or 0))
                slot = by.setdefault(sym, {"cp": None, "cv": None, "pv": None, "net15_m": None,
                                           "lean15": None, "day_net_m": None, "ask_lean": None,
                                           "ask_call_m": None, "ask_put_m": None})
                slot["ask_lean"] = ask_lean
                slot["ask_call_m"] = _fmt_m(ca_f)
                slot["ask_put_m"] = _fmt_m(pa_f)
        except Exception:
            pass
        tide = None
        try:
            d = json.loads(UW_TIDE.read_text())
            as_of = as_of or d.get("as_of_pt")
            last = (d.get("payload") or {}).get("last") or {}
            ncp, npp = last.get("net_call_premium"), last.get("net_put_premium")
            net = None
            try:
                if ncp is not None or npp is not None:
                    net = float(ncp or 0) - float(npp or 0)
            except (TypeError, ValueError):
                net = None
            tide = {"net_m": _fmt_m(net), "lean": _lean_side(net), "as_of_pt": d.get("as_of_pt"),
                    "read": ((d.get("payload") or {}).get("read"))}
        except Exception:
            pass
        try:
            self._update_5m(net_t, net_date, day_nets)
        except Exception:
            pass
        self.by_sym = by
        self.tide = tide
        self.as_of_pt = as_of
        self.mtime = (nm, fm, tm)
        self.loaded_at = now
        if by:
            log(f"uw lean loaded: {len(by)} symbols · as_of {as_of or '—'}")

    def for_sym(self, sym):
        return self.by_sym.get(sym) or {}


# ------------------------------------------------------------------ extra (non-SIP) tiles: VIX, oil, IWM (local desk files only)
EXT_VIX = DESK / "market-data/latest/vix-live.json"
EXT_RHQ = DESK / "market-data/latest/rh-quotes.json"
EXT_MACRO = DESK / "market-data/latest/macro-spot.json"
EXT_STALE_S = 600  # live sources older than this are flagged STALE
EXT_FUT = DESK / "market-data/latest/futures-quotes.json"  # oid_desk.futures_live (FlashAlpha CL=F / BZ=F), 10/19


def _ts(v):
    """Parse ISO (Z/offset), 'YYYY-MM-DD HH:MM[:SS] AM PT' or 'YYYY-MM-DD' to epoch; None if unknown."""
    if not v:
        return None
    v = str(v)
    for f in ("%Y-%m-%d %I:%M:%S %p PT", "%Y-%m-%d %I:%M %p PT"):
        try:
            return datetime.strptime(v, f).replace(tzinfo=PT).timestamp()
        except ValueError:
            pass
    try:
        v = re.sub(r"(\.\d{6})\d+", r"\1", v)  # ns → µs (python3.9 fromisoformat)
        v = re.sub(r"\.(\d{1,5})(?=[+-]|Z|$)", lambda m: "." + m.group(1).ljust(6, "0"), v)
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=PT)
        return d.timestamp()
    except ValueError:
        return None


class ExtTiles:
    """Read-only extra tiles. Never invents values: missing → None, old → stale=True with its real as-of."""

    def __init__(self):
        self.rows, self.loaded_at = [], 0

    @staticmethod
    def _load(p):
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def _row(self, sym, label, last, prev, chg_pct, src, as_of_t, proxy=None, note=None, now=None, unit=None, closed=None, stale_s=None):
        if chg_pct is None and last is not None and prev:
            try:
                chg_pct = round((float(last) / float(prev) - 1) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                chg_pct = None
        age = None if as_of_t is None else max(0, round(now - as_of_t))
        return {"sym": sym, "kind": "ext", "mode": "ext", "label": label, "last": last, "chg": chg_pct, "src": src,
                "src_as_of_pt": pt_str(as_of_t) if as_of_t else None, "age_s": age,
                "stale": bool(last is None or age is None or (not closed and age > (stale_s or EXT_STALE_S))), "closed": closed, "proxy": proxy, "note": note, "unit": unit,
                "rvol": None, "day_rvol": None, "vol_1m": None, "pace": None, "day_vol": None, "day_norm": None,
                "hi": None, "lo": None, "last_pt": pt_str(as_of_t) if as_of_t else None, "spark": [], "hot": False,
                "vs_recent": False, "uw": False}

    def get(self, now, have):
        if now - self.loaded_at < 10 and self.rows:
            return self.rows
        out = []
        v = self._load(EXT_VIX) or {}
        pv = v.get("payload") or {}
        out.append(self._row("VIX", "VIX index", pv.get("value"), None, None, "FlashAlpha real-time index",
                             _ts(pv.get("last_update") or v.get("as_of")), now=now, unit="pts"))
        q = ((self._load(EXT_RHQ) or {}).get("payload") or {}).get("quotes") or {}
        ms = ((self._load(EXT_MACRO) or {}).get("payload") or {}).get("by_id") or {}

        def rhq(sym, label, proxy=None, note=None):
            r = q.get(sym) or {}
            return self._row(sym, label, r.get("last"), r.get("previous_close") or r.get("prev_close"), None,
                             "Alpaca SIP snapshot (~60 s, via mini marks job)", _ts(r.get("venue_last_trade_time")), proxy=proxy, note=note, now=now)
        if "IWM" not in have:
            out.append(rhq("IWM", "Russell 2000 ETF"))
        # Real CME front-month futures (FlashAlpha CL=F / BZ=F via oid_desk.futures_live); USO/BNO proxy tiles removed 10/19
        fq = self._load(EXT_FUT) or {}
        fp = fq.get("payload") or {}
        cme = _cme_state(now)
        for fsym, tsym, nm in (("CL", "WTI", "WTI"), ("BZ", "BRENT", "Brent")):
            r = (fp.get("quotes") or {}).get(fsym) or {}
            lab = "%s %s front%s" % (nm, fsym, (" · " + r["contract_label"]) if r.get("contract_label") else "")
            fnote = (r.get("contract") or "") + (" · DELAYED" if r.get("delayed") else "") + ((" · " + r["note"]) if r.get("note") else "")
            if cme != "open":
                fnote += " · CME " + ("daily break 2–3 PM PT" if cme == "break" else "closed for the weekend")
            if not r.get("previous_close"):
                fnote += " · no prev settle yet"
            row = self._row(tsym, lab, r.get("last"), r.get("previous_close"), None, r.get("src") or "FlashAlpha CME futures (~2 min)",
                            _ts(r.get("venue_last_trade_time")), note=fnote.strip(" ·") or None, now=now, unit="$/bbl",
                            closed=(None if cme == "open" else cme), stale_s=(600 if fp.get("fast_window") else 2400))
            row["fut"] = True
            row["contract_label"] = r.get("contract_label")
            out.append(row)
        self.rows, self.loaded_at = out, now
        return out



# ------------------------------------------------------------------ WALLS: FlashAlpha wall/flip edge marks (2026-10-19)
# Levels: local FlashAlpha caches only (zero FlashAlpha calls from this page) - newest per symbol wins across
#   fa-levels.json (merged), fa-focus-levels.json (5-min focus refresh), fa-flow-levels.json (open pull) and
#   data/fa-walls-pulse.json (written on the mini by com.oid.desk.fa-walls: FA /v1/flow/levels, 10 min core / 40 min rotated;
#   per-record stale_after_s overrides WALLS_STALE_S).
# Weight: Alpaca options data (free, read-only GETs, same account the mini marks job already uses):
#   open interest per contract (paper-api /v2/options/contracts, read-only) + today's volume (data API OPRA snapshots)
#   at the wall strike, expiries <= WALLS_MAX_DTE days.  Keys read in-process from the mini secrets dir; never logged.
WALL_FILES = [("fa-walls-pulse", Path(os.environ.get("OID_LIVEPAGE_WALLS_PULSE", str(HERE / "data/fa-walls-pulse.json")))),
              ("fa-focus-levels", DESK / "market-data/latest/fa-focus-levels.json"),
              ("fa-levels", DESK / "market-data/latest/fa-levels.json"),
              ("fa-flow-levels", DESK / "market-data/latest/fa-flow-levels.json")]
WALLS_STALE_S = 20 * 60          # RTH: walls older than this -> STALE
WALLS_MAX_AGE_S = 4 * 86400      # older than this -> not drawn at all (never show last week's walls)
WALLS_MAX_DTE = int(os.environ.get("OID_LIVEPAGE_WALLS_DTE", "45"))
WALLS_VOL_EVERY_S = 300          # RTH volume refresh cadence
WALLS_REQ_GAP_S = 0.35           # spacing between Alpaca GETs (~170/min worst case, well under limits)
SECRETS_DIR = Path(os.environ.get("OID_LIVEPAGE_SECRETS_DIR", str(HOME / "oid-quote/secrets")))
WALLS_WEIGHT_FILE = HERE / "data/wall-weights.json"
ALPACA_DATA = "https://data.alpaca.markets"
ALPACA_TRADE = "https://paper-api.alpaca.markets"   # read-only GET /v2/options/contracts (open_interest)


def _wall_rec(src, sym, v, file_as_of=None):
    """Normalise one level record from any of the four cache shapes -> dict or None."""
    if not isinstance(v, dict):
        return None
    lv = v.get("levels") if isinstance(v.get("levels"), dict) else v
    cw = lv.get("call_wall", lv.get("live_call_wall"))
    pw = lv.get("put_wall", lv.get("live_put_wall"))
    gf = lv.get("gamma_flip", lv.get("live_gamma_flip"))
    t = _ts(v.get("as_of")) or _ts(v.get("fetched_pt")) or _ts(v.get("as_of_pt")) or _ts(file_as_of)
    if t is None or (cw is None and pw is None and gf is None):
        return None
    try:
        return {"cw": None if cw is None else float(cw), "pw": None if pw is None else float(pw),
                "gf": None if gf is None else float(gf), "gf_status": lv.get("gamma_flip_status") or v.get("gamma_flip_status"),
                "t": t, "src": src, "fa_spot": rnd(v.get("underlying_price"), 2),
                "stale_s": v.get("stale_after_s") if isinstance(v.get("stale_after_s"), (int, float)) else None}
    except (TypeError, ValueError):
        return None


SCORE_FILE = Path(os.environ.get("OID_LIVEPAGE_SCORE", str(HOME / "oid-data/score/latest.json")))  # SCORE: direction score badge feed


class ScoreFeed:
    """SCORE: read ~/oid-data/score/latest.json (written by com.oid.desk.score, ~60 s in RTH). Research only."""

    def __init__(self):
        self.m, self.d = None, {}

    def get(self):
        try:
            m = SCORE_FILE.stat().st_mtime
        except OSError:
            return {}
        if m != self.m:
            try:
                self.d = json.loads(SCORE_FILE.read_text())
            except Exception:
                self.d = {}
            self.m = m
        return self.d


SCORE = ScoreFeed()


MOM_DIR = Path(os.environ.get("OID_LIVEPAGE_MOMENTUM", str(HOME / "oid-desk/state/momentum")))  # MOMENTUM: shadow detector feed
MOM_QUIET_S = 600  # a flag older than 10 min shows as quiet (grey)
MOM_PAIR_S = 120   # decelerate -> resume on the same name within 2 min collapses into one "pause -> resume" flag


class MomentumFeed:
    """MOMENTUM: read ~/oid-desk/state/momentum/current.json + today's events-YYYYMMDD.jsonl (com.oid.desk.momentum,
    shadow, 15 s). Read-only, mtime cached. Research/log only."""

    def __init__(self):
        self.cm, self.cur = None, {}
        self.ek, self.recent = None, []

    @staticmethod
    def _ep(tp):
        try:
            return datetime.strptime(tp, "%Y-%m-%d %I:%M:%S %p PT").replace(tzinfo=PT).timestamp()
        except Exception:
            return None

    def current(self):
        p = MOM_DIR / "current.json"
        try:
            m = p.stat().st_mtime
        except OSError:
            return {}
        if m != self.cm:
            try:
                self.cur = json.loads(p.read_text())
            except Exception:
                self.cur = {}
            self.cm = m
        return self.cur

    def events(self, now):
        p = MOM_DIR / f"events-{datetime.fromtimestamp(now, PT):%Y%m%d}.jsonl"
        try:
            k = (p.name, p.stat().st_size)
        except OSError:
            self.ek, self.recent = None, []
            return self.recent
        if k == self.ek:
            return self.recent
        ev = []
        try:
            lines = p.read_text(errors="replace").splitlines()  # re-read only when the file grows (~every 15 s)
            for ln in lines:
                try:
                    e = json.loads(ln)
                except Exception:
                    continue
                t = self._ep(e.get("time_pt"))
                if t is None:
                    continue
                ev.append({"t": t, "sym": e.get("symbol"), "kind": e.get("kind"), "stage": e.get("stage"),
                           "basis": e.get("basis"), "px": e.get("price"), "z": e.get("z"), "rv": e.get("rvol_1m")})
        except Exception:
            ev = []
        ev.sort(key=lambda x: x["t"])
        # drop a provisional (intrabar) flag once the same name/kind confirms on the bar close within 90 s
        conf = [x for x in ev if x["basis"] == "bar_close"]
        out = []
        for x in ev:
            if x["basis"] == "intrabar" and any(y["sym"] == x["sym"] and y["kind"] == x["kind"] and 0 <= y["t"] - x["t"] <= 90 for y in conf):
                continue
            out.append(x)
        # collapse decelerate -> resume pairs on the same name within MOM_PAIR_S
        res, open_dec = [], {}
        for x in out:
            if x["kind"] == "decelerate" and x["sym"] != "MARKET":
                open_dec[x["sym"]] = len(res)
                res.append(dict(x))
                continue
            if x["kind"] == "resume" and x["sym"] in open_dec:
                i = open_dec.pop(x["sym"])
                d = res[i]
                if d and x["t"] - d["t"] <= MOM_PAIR_S:
                    res[i] = None
                    res.append(dict(x, kind="resume", paused_s=round(x["t"] - d["t"])))
                    continue
            if x["kind"] in ("accelerate", "resume"):
                open_dec.pop(x["sym"], None)
            res.append(dict(x))
        res = [x for x in res if x]
        res.sort(key=lambda x: -x["t"])
        for x in res:
            x["time_pt"] = datetime.fromtimestamp(x["t"], PT).strftime("%-I:%M:%S %p")
        self.ek, self.recent = k, res[:20]
        return self.recent


def _lvl(px, step):
    import math
    nxt = math.floor(px / step + 1e-9) * step + step
    return round(nxt, 2), round((nxt - px) * 100, 1)


MOMENTUM = MomentumFeed()


MOMLOG_ROOT = Path(os.environ.get("OID_LIVEPAGE_MOMLOG", str(HOME / "oid-data/archive")))  # MOMSTATE


class MomStateLog:
    """MOMSTATE (2026-10-20): one archive row each time the Momentum state a ticker SHOWS on the page changes
    (accelerate / resume / decelerate / quiet, incl. the 10-min quiet rule), plus the first state of each ET day.
    Written to ~/oid-data/archive/momentum_state/date=YYYY-MM-DD/part-oid-livepage-N.jsonl (ET date), same layout and
    columns style as the other archive tables, so com.oid.archive.main/post compact it to Parquet and
    com.oid.archive.weekly deletes JSONL after 90 days once Parquet holds every row. Read back by chart_backend.py."""
    WRITER = "oid-livepage"

    def __init__(self, root=MOMLOG_ROOT):
        self.dir0 = root / "momentum_state"
        self.day, self.path, self.last, self.errors, self.rows = None, None, {}, 0, 0

    def _open_day(self, day):
        d = self.dir0 / f"date={day}"
        d.mkdir(parents=True, exist_ok=True)
        last, seqs = {}, []
        for f in sorted(d.glob("part-*.jsonl")):
            if f.name.startswith(f"part-{self.WRITER}-"):
                try:
                    seqs.append(int(f.stem.rsplit("-", 1)[1]))
                except ValueError:
                    pass
            try:  # restore the last logged state per name so a restart does not re-log unchanged names
                for ln in f.read_text(errors="replace").splitlines():
                    try:
                        x = json.loads(ln)
                        last[x["symbol"]] = x.get("state")
                    except Exception:
                        continue
            except OSError:
                pass
        self.day, self.last = day, last
        self.path = d / f"part-{self.WRITER}-{(max(seqs) + 1) if seqs else 1}.jsonl"

    def note(self, rows, by, md, now):
        try:
            day = datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")
            if day != self.day:
                self._open_day(day)
            out = []
            ns = int(now * 1e9)
            iso = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            tpt = datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d %-I:%M:%S %p PT")
            for r in rows:
                m = r.get("mom")
                if not m:
                    continue
                sym, stt = r["sym"], m.get("st")
                prev = self.last.get(sym, "__none__")
                if prev == stt:
                    continue
                x = by.get(sym) or {}
                out.append({"change_id": f"{sym}-{ns}", "symbol": sym, "state": stt,
                            "prev_state": None if prev == "__none__" else prev, "raw_state": m.get("raw"),
                            "since_ep": m.get("t"), "since_pt": m.get("since_pt"), "held": m.get("held"),
                            "prov": m.get("prov"), "first": prev == "__none__", "t_pt": tpt,
                            "detector_as_of_pt": md.get("as_of_pt"), "src": md.get("writer") or "momentum",
                            "schema_version": "v1", "event_ts_ns": ns, "event_ts_iso": iso, "ingest_ts_ns": ns,
                            "ingest_ts_iso": iso, "writer": self.WRITER})
                self.last[sym] = stt
            if out:
                with open(self.path, "a") as fh:
                    fh.write("".join(json.dumps(o, separators=(",", ":")) + "\n" for o in out))
                self.rows += len(out)
        except Exception as e:
            self.errors += 1
            log(f"momstate log error: {type(e).__name__}")


MOMLOG = MomStateLog()


SCORE_CFG = Path(os.environ.get("OID_SCORE_CONFIG", str(HOME / "oid-data/config/score-config.json")))  # SCORENAMES


class ScoreVersions:
    """SCORENAMES (2026-10-20): the score settings versions that are active now, read from the score config
    (mtime cached), so table headers / chart lanes can name each score with its profile and settings version."""

    def __init__(self):
        self.m, self.v = None, {}

    def get(self):
        try:
            m = SCORE_CFG.stat().st_mtime
        except OSError:
            return self.v
        if m != self.m:
            try:
                c = json.loads(SCORE_CFG.read_text())
                pr = c.get("profiles") or {}
                self.v = {"core": c.get("config_version"), "light": (pr.get("light") or {}).get("config_version"),
                          "full": (pr.get("wide_full") or {}).get("config_version"), "src": str(SCORE_CFG).replace(str(HOME), "~")}
            except Exception:
                pass
            self.m = m
        return self.v


SCOREV = ScoreVersions()


class Walls:
    def __init__(self):
        self.by, self.loaded_at, self.lock = {}, 0, threading.Lock()
        self.w = self._load_w()    # {"oi": {key: [oi, oi_date, strike, day]}, "vol": {key: [vol, strike, t]}, ...}
        self.status = {"last_pass_pt": None, "err": None, "reqs_today": 0, "day": None}

    # ---- level caches
    def refresh(self, now):
        if now - self.loaded_at < 30 and self.by:
            return
        best = {}
        for src, p in WALL_FILES:
            try:
                d = json.loads(p.read_text())
            except Exception:
                continue
            fa = d.get("as_of_pt") or d.get("as_of")
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
                if not isinstance(sym, str) or not SYM_RE.match(sym):
                    continue
                r = _wall_rec(src, sym, v, fa)
                if r and (sym not in best or r["t"] > best[sym]["t"]):
                    best[sym] = r
        self.by, self.loaded_at = best, now

    # ---- weights (background thread)
    def _load_w(self):
        try:
            d = json.loads(WALLS_WEIGHT_FILE.read_text())
            return {"oi": d.get("oi") or {}, "vol": d.get("vol") or {}, "vol_t": d.get("vol_t") or {}, "flip_k": d.get("flip_k") or {}}
        except Exception:
            return {"oi": {}, "vol": {}, "vol_t": {}, "flip_k": {}}

    def _save_w(self):
        try:
            WALLS_WEIGHT_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = WALLS_WEIGHT_FILE.with_suffix(".tmp")
            with self.lock:
                tmp.write_text(json.dumps(self.w, separators=(",", ":")))
            tmp.replace(WALLS_WEIGHT_FILE)
        except Exception:
            pass

    @staticmethod
    def _hdr():
        try:
            k = (SECRETS_DIR / "APCA_API_KEY_ID").read_text().strip()
            s = (SECRETS_DIR / "APCA_API_SECRET_KEY").read_text().strip()
        except OSError:
            return None
        return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s, "Accept": "application/json"} if k and s else None

    def _get(self, url, hdr):
        from urllib.parse import urlencode  # noqa: F401  (urls are built by the caller)
        req = urllib.request.Request(url, headers=hdr)
        time.sleep(WALLS_REQ_GAP_S)
        self.status["reqs_today"] += 1
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8"))

    def _strike_rows(self, sym, typ, lo, hi, hdr, want_oi):
        """-> {strike: {"oi": int|None, "oi_date": str, "vol": int}} for contracts <= WALLS_MAX_DTE days out."""
        from urllib.parse import urlencode
        exp = (datetime.now(ET).date() + timedelta(days=WALLS_MAX_DTE)).isoformat()
        out = {}
        if want_oi:
            q = {"underlying_symbols": sym, "strike_price_gte": f"{lo:g}", "strike_price_lte": f"{hi:g}",
                 "expiration_date_lte": exp, "limit": 1000, "status": "active"}
            if typ:
                q["type"] = typ
            tok = None
            for _ in range(4):
                if tok:
                    q["page_token"] = tok
                d = self._get(ALPACA_TRADE + "/v2/options/contracts?" + urlencode(q), hdr)
                for c in d.get("option_contracts") or []:
                    try:
                        k = float(c.get("strike_price"))
                    except (TypeError, ValueError):
                        continue
                    o = out.setdefault(k, {"oi": 0, "oi_date": None, "vol": 0})
                    try:
                        o["oi"] += int(float(c.get("open_interest") or 0))
                    except (TypeError, ValueError):
                        pass
                    o["oi_date"] = max(o["oi_date"] or "", str(c.get("open_interest_date") or "")) or None
                tok = d.get("next_page_token")
                if not tok:
                    break
        q = {"feed": "opra", "strike_price_gte": f"{lo:g}", "strike_price_lte": f"{hi:g}", "expiration_date_lte": exp, "limit": 1000}
        if typ:
            q["type"] = typ
        tok = None
        for _ in range(4):
            if tok:
                q["page_token"] = tok
            d = self._get(ALPACA_DATA + f"/v1beta1/options/snapshots/{sym}?" + urlencode(q), hdr)
            for occ, s in (d.get("snapshots") or {}).items():
                try:
                    k = int(occ[-8:]) / 1000.0
                except ValueError:
                    continue
                db = s.get("dailyBar") or {}
                # dailyBar is today's bar once the contract trades today; ignore a bar from an older session
                if str(db.get("t", ""))[:10] != datetime.now(ET).strftime("%Y-%m-%d"):
                    continue
                out.setdefault(k, {"oi": None, "oi_date": None, "vol": 0})
                out[k]["vol"] = (out[k].get("vol") or 0) + int(db.get("v") or 0)
            tok = d.get("next_page_token")
            if not tok:
                break
        return out

    def weights_pass(self, rth):
        hdr = self._hdr()
        if not hdr:
            self.status["err"] = "alpaca keys missing"
            return
        day = datetime.now(ET).strftime("%Y-%m-%d")
        if self.status["day"] != day:
            self.status.update(day=day, reqs_today=0)
        with self.lock:
            by = dict(self.by)
        errs = 0
        for sym, r in sorted(by.items()):
            if time.time() - r["t"] > WALLS_MAX_AGE_S:
                continue
            for lv, typ in (("cw", "call"), ("pw", "put"), ("gf", None)):
                px = r.get(lv)
                if px is None:
                    continue
                key = f"{sym}|{lv}|{px:g}"
                need_oi = (self.w["oi"].get(key) or [None, None, None, None])[3] != day
                try:
                    if lv == "gf":
                        band = max(0.5, px * 0.012)
                        rows = self._strike_rows(sym, None, px - band, px + band, hdr, need_oi)
                        if not rows:
                            continue
                        k = min(rows, key=lambda s: (abs(s - px), -s))
                        row = rows[k]
                        self.w["flip_k"][key] = k
                    else:
                        rows = self._strike_rows(sym, typ, px, px, hdr, need_oi)
                        k, row = px, rows.get(px) or {"oi": None, "oi_date": None, "vol": 0}
                except Exception as e:  # never log URLs/keys
                    errs += 1
                    self.status["err"] = f"{type(e).__name__} on {sym}"
                    continue
                with self.lock:
                    if need_oi and row.get("oi") is not None:
                        self.w["oi"][key] = [row["oi"], row.get("oi_date"), k, day]
                    self.w["vol"][key] = [row.get("vol") or 0, k, day]
                    self.w["vol_t"][key] = time.time()
        live_keys = {f"{s_}|{lv_}|{r_[lv_]:g}" for s_, r_ in by.items() for lv_ in ("cw", "pw", "gf") if r_.get(lv_) is not None}
        with self.lock:  # prune weights for levels that no longer exist
            for part in ("oi", "vol", "vol_t", "flip_k"):
                self.w[part] = {k_: v_ for k_, v_ in self.w[part].items() if k_ in live_keys}
        if not errs:
            self.status["err"] = None
        self.status["last_pass_pt"] = pt_str(time.time())
        self._save_w()
        log(f"walls weights pass: {len(by)} symbols · {self.status['reqs_today']} Alpaca GETs today · errors {errs}")

    def loop(self, eng_state):
        last = 0
        while True:
            try:
                rth = bool(eng_state.get("rth"))
                due = (WALLS_VOL_EVERY_S if rth else 3600)
                if self.by and time.time() - last >= due:
                    last = time.time()
                    self.weights_pass(rth)
            except Exception as e:
                self.status["err"] = type(e).__name__
            time.sleep(5)

    # ---- per-row payload
    def for_row(self, sym, spot, rth, now, session_date):
        r = self.by.get(sym)
        if not r or now - r["t"] > WALLS_MAX_AGE_S:
            return None
        age = max(0, round(now - r["t"]))
        wdate = datetime.fromtimestamp(r["t"], ET).strftime("%Y-%m-%d")
        stale = (age > (r.get("stale_s") or WALLS_STALE_S)) if rth else bool(session_date and wdate < str(session_date))
        day = datetime.now(ET).strftime("%Y-%m-%d")
        lv = {}
        with self.lock:
            for k in ("cw", "pw", "gf"):
                px = r.get(k)
                if px is None:
                    continue
                key = f"{sym}|{k}|{px:g}"
                oi = self.w["oi"].get(key)
                vo = self.w["vol"].get(key)
                vt = self.w["vol_t"].get(key)
                o = oi[0] if oi else None
                v = vo[0] if vo and vo[2] == day else (0 if vo else None)
                wt = None if o is None and v is None else (o or 0) + (v or 0)
                lv[k] = {"px": round(px, 2), "dist": rnd((px / spot - 1) * 100) if spot else None,
                         "oi": o, "oi_date": oi[1] if oi else None, "vol": v, "w": wt,
                         "k": px if k != "gf" else self.w["flip_k"].get(key),
                         "w_pt": datetime.fromtimestamp(vt, PT).strftime("%-I:%M %p PT") if vt else None}
        mx = max([x["w"] for x in lv.values() if x.get("w")] or [0])
        for x in lv.values():
            x["rel"] = round(x["w"] / mx, 3) if mx and x.get("w") else None
        return {"lv": lv, "gf_ok": r.get("gf_status") == "available", "gf_status": r.get("gf_status"),
                "as_of_pt": datetime.fromtimestamp(r["t"], PT).strftime("%a %-m/%-d %-I:%M %p PT"), "age_s": age,
                "stale": stale, "src": r["src"], "dte": WALLS_MAX_DTE}


def _cme_state(t):
    """open | break | weekend for CME Globex energy (Sun 15:00 -> Fri 14:00 PT, daily halt 14:00-15:00 PT)."""
    n = datetime.fromtimestamp(t, PT)
    wd, hm = n.weekday(), (n.hour, n.minute)
    if wd == 5 or (wd == 4 and hm >= (14, 0)) or (wd == 6 and hm < (15, 0)):
        return "weekend"
    return "break" if (14, 0) <= hm < (15, 0) else "open"

class Hist:
    """Last-session + today's 1-min bars and norms, from the collector's files (read-only)."""

    def __init__(self):
        self.norms, self.norms_m = {}, 0
        self.last = {}   # sym -> {date, close, prev_close, bars:[(t, v, slot)]}
        self.today = {}  # sym -> [(t, v, slot)]
        self.today_m = {}

    def refresh(self, symbols, force=False):
        try:
            m = NORMS.stat().st_mtime
        except OSError:
            m = 0
        if force or m != self.norms_m:
            try:
                self.norms = json.loads(NORMS.read_text()).get("norms") or {}
            except Exception:
                self.norms = {}
            for sym in symbols:
                self._load_last(sym)
            self.norms_m = m
            log(f"history loaded: {len(self.last)} symbols, norms {len(self.norms)}")

    def _load_last(self, sym):
        try:
            d = json.loads((STORE / f"{sym}-1m.json").read_text())
        except Exception:
            return
        bars = d.get("bars") or []
        if not bars:
            return
        ld = bars[-1]["d"]
        dates = sorted({b["d"] for b in bars})
        prev = dates[-2] if len(dates) > 1 else None
        pc = next((b.get("c") for b in reversed(bars) if b["d"] == prev), None) if prev else None
        lb = [b for b in bars if b["d"] == ld]
        self.last[sym] = {"date": ld, "close": lb[-1].get("c"), "prev_close": pc,
                          "bars": [(b["t"], float(b.get("v") or 0), b.get("slot", -1)) for b in lb[-SPARK_N:]]}

    def refresh_today(self, symbols):
        day = datetime.now(ET).strftime("%Y%m%d")
        live = STORE / "live"
        for sym in symbols:
            p = live / f"{sym}-1m-{day}.jsonl"
            try:
                m = p.stat().st_mtime
            except OSError:
                self.today.pop(sym, None)
                continue
            if self.today_m.get(sym) == (day, m):
                continue
            rows = {}
            try:
                for ln in p.read_text().splitlines()[-400:]:
                    try:
                        b = json.loads(ln)
                        rows[b["t"]] = (b["t"], float(b.get("v") or 0), b.get("slot", -1))  # updatedBars: last wins
                    except Exception:
                        continue
            except OSError:
                continue
            self.today[sym] = [rows[k] for k in sorted(rows)][-SPARK_N:]
            self.today_m[sym] = (day, m)

    def norm(self, sym, slot):
        row = self.norms.get(sym)
        if row is None or slot is None or slot < 0 or slot >= len(row):
            return None
        return row[slot]


def label(r):
    if r is None:
        return None
    return "SURGE" if r >= 3 else "HEAVY" if r >= 1.5 else "INLINE" if r >= 0.7 else "LIGHT"


def rnd(v, n=2):
    try:
        return None if v is None else round(float(v), n)
    except (TypeError, ValueError):
        return None


WALLS = None  # set in main
WALL_STATE = {"rth": False}


NEWS_FILE = Path(os.environ.get("OID_LIVEPAGE_NEWS", str(HOME / "oid-desk/state/news/latest.json")))  # NEWS: com.oid.desk.news


class NewsFeed:
    """NEWS: read ~/oid-desk/state/news/latest.json (Alpaca/Benzinga headlines + X archive top posts, sentiment -2..+2).
    Read-only, mtime cached. Research only."""

    def __init__(self):
        self.m, self.d = None, {}

    def get(self):
        try:
            m = NEWS_FILE.stat().st_mtime
        except OSError:
            return {}
        if m != self.m:
            try:
                self.d = json.loads(NEWS_FILE.read_text())
            except Exception:
                return self.d
            self.m = m
        return self.d


NEWS = NewsFeed()


class WideWatch:
    """WIDE: sector-watch rows from the collector's wide tier (read-only). Compact payload, refreshed every 5 s."""

    def __init__(self):
        self.t = 0.0
        self.seq = 0
        self.payload = None
        self.sec_m, self.groups, self.info = None, [], {}
        self.prev_m, self.prev = {}, {}     # sym -> store mtime, {date: last close}
        self.tail, self.lbars, self.lb_date = {}, {}, None  # SECTORHEAT: store tail {date: [(t, v, slot)]}, live closed bars (today)
        self.wn_m, self.wn, self.sp_t, self.sp = None, {}, 0.0, None  # SECTORHEAT: wide same-minute norms, /wide-spark.json cache
        self.walls_m, self.walls = None, {}
        self.light_m, self.light = None, {}  # LIGHT: latest-wide.json (raw, unsmoothed light direction score, 5 s)
        self.full_m, self.full = None, {}    # WIDECP: latest-widefull.json (full score, wide_full profile)
        self.cpdir = None                    # WIDECP: own CpDir (C/P now vs ~60 s ago), created lazily
        self.of_meta = None
        self.flags = {}                     # sym -> (surge, mover) last tick (RTH crossings -> events)
        self.events = []                    # [{sym, sector, kind, t, time_pt, rvol, chg}]
        self.err = None

    def _sectors(self):
        try:
            m = WIDE_SECTORS_FILE.stat().st_mtime
        except OSError:
            self.groups, self.info = [], {}
            return
        if m != self.sec_m:
            try:
                d = json.loads(WIDE_SECTORS_FILE.read_text())
                self.groups = [g for g in (d.get("groups") or []) if isinstance(g, dict) and isinstance(g.get("tickers"), list)]
                self.info = d.get("info") or {}
            except Exception:
                pass
            self.sec_m = m

    def _prev_close(self, sym, before):
        """Close of the latest full session strictly before `before` (ET date), from the wide REST store."""
        p = WIDE_STORE / f"{sym}-1m.json"
        try:
            m = p.stat().st_mtime
        except OSError:
            return None
        if self.prev_m.get(sym) != m:
            try:
                bars = json.loads(p.read_text()).get("bars") or []
                closes = {}
                for b in bars:
                    if b.get("c") is not None:
                        closes[b["d"]] = b["c"]
                self.prev[sym] = closes
                ds = sorted({b.get("d") for b in bars if b.get("d")})[-2:]  # SECTORHEAT: last 30 bars of the 2 newest sessions
                self.tail[sym] = {dd: [(b["t"], float(b.get("v") or 0), b.get("slot", -1)) for b in bars if b.get("d") == dd][-SPARK_N:] for dd in ds}
            except Exception:
                self.prev[sym] = {}
            self.prev_m[sym] = m
        c = self.prev.get(sym) or {}
        ds = sorted(d for d in c if before is None or d < before)
        return c[ds[-1]] if ds else None

    def _walls(self, now):
        try:
            m = WIDE_WALLS_FILE.stat().st_mtime
        except OSError:
            self.walls = {}
            return
        if m != self.walls_m:
            try:
                d = json.loads(WIDE_WALLS_FILE.read_text())
                self.walls = {k: v for k, v in d.items() if isinstance(v, dict) and SYM_RE.match(k)}
            except Exception:
                pass
            self.walls_m = m

    def _light(self):
        try:
            m = WIDE_LIGHT_FILE.stat().st_mtime
        except OSError:
            self.light = {}
            return
        if m != self.light_m:
            try:
                self.light = json.loads(WIDE_LIGHT_FILE.read_text())
            except Exception:
                pass
            self.light_m = m

    def _full(self):
        try:
            m = WIDE_FULL_FILE.stat().st_mtime
        except OSError:
            self.full = {}
            return
        if m != self.full_m:
            try:
                self.full = json.loads(WIDE_FULL_FILE.read_text())
            except Exception:
                pass
            self.full_m = m

    def _full_row(self, sym, now):
        """WIDECP: full direction score (wide_full profile) {s, raw, h, st, cov, mi: missing inputs} or None. Research only."""
        F = self.full or {}
        x = (F.get("by_sym") or {}).get(sym)
        age = now - (F.get("as_of") or 0)
        if not x or age > WIDE_LIGHT_MAX_AGE_S:
            return None
        return {"s": x.get("s"), "raw": x.get("raw"), "h": round(now - x["since_t"]) if x.get("since_t") else None,
                "st": age > WIDE_LIGHT_STALE_S, "cov": x.get("cov"), "mi": x.get("missing")}

    def _optflow(self, now):
        """WIDECP: ~/oid-optflow/data/optflow-wide.json (every 1 s; trades-only, tick-test classification)."""
        try:
            d = json.loads(WIDE_OPTFLOW_FILE.read_text())
        except Exception:
            self.of_meta = None
            return {}
        age = now - float(d.get("computed_epoch") or 0)
        self.of_meta = {"computed_at": d.get("computed_at"), "age_s": round(age, 2), "subs": d.get("subs"), "cls": "tick",
                        "ws": (d.get("ws") or {}).get("state")}
        return (d.get("underlyings") or {}) if age < 10 else {}

    @staticmethod
    def _af(a, rth, now):
        """WIDECP: same chip fields as the core rows (af15/af60/af_age/af_stale/af_n) from one optflow-wide entry."""
        if not a:
            return {"af15": None, "af60": None, "af_age": None, "af_stale": True, "af_n": None}

        def _c(w):
            w = a.get(w) or {}
            out = {"cp": w.get("cp_buy"), "net_k": round((w.get("net") or 0) / 1000, 1), "cov": w.get("coverage"),
                   "n": w.get("n"), "thin": bool(w.get("thin", True)), "cb_k": round((w.get("cb") or 0) / 1000, 1),
                   "pb_k": round((w.get("pb") or 0) / 1000, 1), "cls": "tick"}
            return out
        r = {"af15": _c("15s"), "af60": _c("60s")}
        mo = a.get("mom") or {}
        for k, w in (("af15", "15s"), ("af60", "60s")):
            m = mo.get(w)
            if m:
                r[k].update({"md": m.get("d"), "ms": m.get("s"), "mh": m.get("h"), "mrr": bool(m.get("rr"))})
        lr = a.get("last_recv")
        try:
            r["af_age"] = round(now - datetime.fromisoformat(lr).timestamp(), 1) if lr else None
        except Exception:
            r["af_age"] = None
        r["af_stale"] = bool(rth and (r["af_age"] is None or r["af_age"] > OPTFLOW_STALE_S))
        r["af_n"] = a.get("contracts")
        return r

    @staticmethod
    def _lean(af):
        """WIDECP flow lean from the aggressor C/P: 1m window first, else 15 s; thin windows give no lean."""
        for k in ("af60", "af15"):
            w = af.get(k) or {}
            cp = w.get("cp")
            if cp is not None and not w.get("thin", True):
                return "CALL" if cp > WIDE_CP_BAND else "PUT" if cp < 1.0 / WIDE_CP_BAND else "FLAT"
        return None

    def _light_row(self, sym, now):
        """LIGHT: {s: score -3..+3, raw, h: seconds the score has held, st: feed stale} or None. Research only."""
        L = self.light or {}
        x = (L.get("by_sym") or {}).get(sym)
        age = now - (L.get("as_of") or 0)
        if not x or age > WIDE_LIGHT_MAX_AGE_S:
            return None
        return {"s": x.get("s"), "raw": x.get("raw"), "h": round(now - x["since_t"]) if x.get("since_t") else None,
                "st": age > WIDE_LIGHT_STALE_S}

    def _wall_row(self, sym, last, now, et_date):
        r = _wall_rec("fa-walls-wide", sym, self.walls.get(sym))
        if not r or now - r["t"] > WIDE_WALLS_MAX_AGE_S:
            return None
        wdate = datetime.fromtimestamp(r["t"], ET).strftime("%Y-%m-%d")
        out = {"t": datetime.fromtimestamp(r["t"], PT).strftime("%-I:%M %p PT"), "st": bool(et_date and wdate < str(et_date)) or now - r["t"] > 3600,
               "ts": round(r["t"], 1), "gs": r.get("gf_status")}   # WIDECP: epoch + flip status for the wide_full score
        for k in ("cw", "pw", "gf"):
            px = r.get(k)
            if px is not None:
                out[k] = round(px, 2)
                out[k[0] + "d"] = rnd((px / last - 1) * 100, 1) if last else None
        return out

    def _wnorm(self, sym, slot):
        """SECTORHEAT: same-minute 1-min volume norm for a sector name (collector's wide live-norms-1m.json)."""
        f = WIDE_STORE.parent / "live-norms-1m.json"
        try:
            m = f.stat().st_mtime
        except OSError:
            return None
        if m != self.wn_m:
            try:
                self.wn = json.loads(f.read_text()).get("norms") or {}
            except Exception:
                self.wn = {}
            self.wn_m = m
        row = self.wn.get(sym)
        if row is None or slot is None or slot < 0 or slot >= len(row):
            return None
        return row[slot]

    def _heat_extra(self, sym, v, ls, et_date):
        """SECTORHEAT: Heatmap tile footer + current-minute bar, from the same collector read (no new pulls)."""
        if self.lb_date != et_date:
            self.lbars, self.lb_date = {}, et_date
        if not v:
            return {"v1": None, "pc": None, "dv": ls.get("volume"), "dn": ls.get("norm_day"), "hi": rnd(ls.get("high"), 4), "lo": rnd(ls.get("low"), 4),
                    "lt": f"{ls.get('date')} close" if ls.get("date") else None, "pb": None, "pn": None, "ps": None}
        lc, cur = v.get("last_closed_bar"), v.get("cur_bar")
        if lc and lc.get("t"):
            b = self.lbars.setdefault(sym, {})
            b[lc["t"]] = (lc["t"], float(lc.get("v") or 0), et_slot(lc["t"])[1])
            if len(b) > SPARK_N + 10:
                for k in sorted(b)[:len(b) - SPARK_N]:
                    b.pop(k, None)
        pn = self._wnorm(sym, et_slot(cur["t"])[1]) if (cur and cur.get("t")) else None
        return {"v1": v.get("vol_60s"), "pc": rnd(v.get("pace_rvol_10s")), "dv": v.get("day_vol_rth"), "dn": v.get("day_norm_to_now"), "lt": v.get("last_trade_pt"),
                "hi": rnd(v.get("day_high"), 4), "lo": rnd(v.get("day_low"), 4),
                "pb": round(cur.get("v") or 0) if cur else None, "pn": rnd(pn) if pn else None, "ps": cur.get("elapsed_s") if cur else None}

    def spark_payload(self, now):
        """SECTORHEAT: /wide-spark.json = last 30 one-min volumes + same-minute norm per sector name (Heatmap sparkline)."""
        if self.sp is not None and now - self.sp_t < 10:
            return self.sp
        out = {}
        for g in (self.payload or {}).get("groups") or []:
            for r in g.get("rows") or []:
                sym, d = r["s"], r.get("d")
                self._prev_close(sym, None)  # loads the REST store tail (cached by mtime)
                bars = {b[0]: b for b in (self.tail.get(sym) or {}).get(d, [])}
                if r.get("m") == "L" and d == self.lb_date:
                    bars.update(self.lbars.get(sym) or {})
                sp = []
                for k in sorted(bars)[-SPARK_N:]:
                    n = self._wnorm(sym, bars[k][2])
                    sp.append([round(bars[k][1]), round(n) if n else None])
                out[sym] = sp
        self.sp, self.sp_t = {"as_of_pt": pt_str(now), "n": len(out), "spark": out}, now
        return self.sp

    def refresh(self, now):
        if self.payload is not None and now - self.t < WIDE_EVERY_S:
            return False
        self.t = now
        self._sectors()
        if not self.groups:
            self.payload = None
            return False
        try:
            raw = get_json("/v1/live-volume", {"tier": "wide"}, timeout=4.0)
            self.err = raw.get("error")
        except Exception as e:
            self.err = f"collector read failed ({type(e).__name__})"
            raw = {}
        self._walls(now)
        try:
            self._light()
        except Exception:
            self.light = {}
        try:
            self._full()
        except Exception:
            self.full = {}
        live, last_s = raw.get("symbols") or {}, raw.get("last_session") or {}
        rth = raw.get("session") == "RTH"
        try:
            of = self._optflow(now)
        except Exception:
            of = {}
        if self.cpdir is None:
            self.cpdir = CpDir()
        if not rth:
            self.cpdir.h.clear()
        et_date = raw.get("et_date")
        groups, n_live, cross = [], 0, []
        for g in self.groups:
            rows = []
            for sym in g["tickers"]:
                v, ls = live.get(sym), last_s.get(sym) or {}
                use_live = bool(v) and (rth or v.get("day_date") == et_date or not ls)
                if use_live and not rth and ls and v.get("last") is None:
                    use_live = False
                if use_live:
                    n_live += 1
                    last = v.get("last")
                    prev = v.get("prev_close") or self._prev_close(sym, v.get("day_date") or et_date)
                    rv, drv, mode, d = rnd(v.get("rvol_1m")), rnd(v.get("day_rvol")), "L", v.get("day_date")
                else:
                    last = ls.get("close")
                    prev = self._prev_close(sym, ls.get("date")) if ls.get("date") else None
                    rv, drv, mode, d = None, rnd(ls.get("day_rvol")), "S", ls.get("date")
                chg = rnd((last / prev - 1) * 100) if last and prev else None
                sg = bool(rth and rv is not None and rv >= WIDE_SURGE_RVOL)
                mv = bool(chg is not None and abs(chg) >= WIDE_MOVE_PCT)
                i = self.info.get(sym) or {}
                row = {"s": sym, "p": rnd(last, 4), "c": chg, "r": rv, "dr": drv, "sg": sg, "mv": mv, "m": mode, "d": d,
                       "i": i.get("industry"), "w": self._wall_row(sym, last, now, et_date), "ls": self._light_row(sym, now)}
                try:  # SECTORHEAT: tile footer fields (1m vol, 10s pace, day vol, hi/lo) + current-minute bar
                    row.update(self._heat_extra(sym, v if use_live else None, ls, et_date))
                except Exception:
                    pass
                try:  # WIDECP: aggressor C/P chips, C/P direction, flow lean, volume direction, full score
                    af = self._af(of.get(sym), rth, now)
                    row.update(af)
                    row["fl"] = self._lean(af)
                    row["cpdir"] = self.cpdir.update({"sym": sym, **af}, now) if (rth and (af.get("af15") or af.get("af60"))) else None
                    row["vdir"] = vol_dir(v) if (rth and use_live and v) else None
                    row["fs"] = self._full_row(sym, now)
                except Exception as e:
                    row["fs"] = None
                    self.err = self.err or f"wide C/P error ({type(e).__name__})"
                rows.append(row)
                p_sg, p_mv = self.flags.get(sym, (False, False))
                if rth and ((sg and not p_sg) or (mv and not p_mv)):
                    cross.append({"sym": sym, "sector": g.get("name"), "gid": g.get("id"), "kind": "surge" if sg and not p_sg else "move",
                                  "t": now, "time_pt": datetime.fromtimestamp(now, PT).strftime("%-I:%M %p PT"), "rvol": rv, "chg": chg})
                self.flags[sym] = (sg, mv)
            rows.sort(key=lambda r: r["s"])
            groups.append({"id": g.get("id"), "name": g.get("name"), "rows": rows,
                           "n_sg": sum(1 for r in rows if r["sg"]), "n_mv": sum(1 for r in rows if r["mv"])})
        if cross:
            self.events = (self.events + cross)[-200:]
        self.events = [e for e in self.events if now - e["t"] <= WIDE_BATCH_S]
        batches = {}
        for e in self.events:  # one entry per sector (newest first), names deduped
            b = batches.setdefault(e["gid"], {"sector": e["sector"], "gid": e["gid"], "t": 0, "syms": {}})
            b["t"] = max(b["t"], e["t"])
            b["syms"][e["sym"]] = {"sym": e["sym"], "kind": e["kind"], "rvol": e["rvol"], "chg": e["chg"], "time_pt": e["time_pt"]}
        alerts = sorted(({**b, "syms": list(b["syms"].values()), "time_pt": datetime.fromtimestamp(b["t"], PT).strftime("%-I:%M %p PT")}
                         for b in batches.values()), key=lambda b: -b["t"])
        st = raw.get("stream") or {}
        self.seq += 1
        self.payload = {"seq": self.seq, "as_of_pt": pt_str(now), "session": raw.get("session"), "et_date": et_date,
                        "n": sum(len(g["rows"]) for g in groups), "live_n": n_live, "err": self.err,
                        "stream": {"feed": st.get("feed"), "connected": st.get("connected")},
                        "norms": {k: (raw.get("norms") or {}).get(k) for k in ("for_date", "symbols", "current")},
                        "surge_rvol": WIDE_SURGE_RVOL, "move_pct": WIDE_MOVE_PCT, "batch_min": WIDE_BATCH_S // 60,
                        "walls_n": sum(1 for g in groups for r in g["rows"] if r["w"]),
                        "light": {"cfg": (self.light or {}).get("config_version"), "as_of_pt": (self.light or {}).get("as_of_pt"),
                                  "n": sum(1 for g in groups for r in g["rows"] if r.get("ls"))},
                        "full": {"cfg": (self.full or {}).get("config_version"), "as_of_pt": (self.full or {}).get("as_of_pt"),
                                 "n": sum(1 for g in groups for r in g["rows"] if r.get("fs"))},
                        "optflow": self.of_meta, "cp_n": sum(1 for g in groups for r in g["rows"] if r.get("af15") or r.get("af60")),
                        "groups": groups, "alerts": alerts,
                        "surging": [r["s"] for g in groups for r in g["rows"] if r["sg"] or (rth and r["mv"])]}
        return True


WIDE = WideWatch()


def vol_dir(v):
    """DIRECTION: {"a": up|dn|flat|thin, "x": ratio, "v15", "p60"} from the collector's vol_15s / vol_prev60_15."""
    if not v or v.get("vol_15s") is None or v.get("vol_prev60_15") is None:
        return None
    v15, p60 = float(v["vol_15s"]), float(v["vol_prev60_15"])
    out = {"v15": round(v15), "p60": round(p60), "x": None}
    if v15 + p60 < DIR_CFG["vol_min_shares"]:
        out["a"] = "thin"
        return out
    if p60 <= 0:
        out["a"] = "up"
        return out
    x = (v15 / 15.0) / (p60 / 60.0)
    out["x"] = round(x, 2)
    out["a"] = "up" if x >= DIR_CFG["vol_up_x"] else "dn" if x <= DIR_CFG["vol_dn_x"] else "flat"
    return out


class CpDir:
    """DIRECTION: per-symbol 1 s history of the optflow 15 s / 1 m C/P readings (~100 s kept) -> now vs ~60 s ago."""

    def __init__(self):
        self.h = {}  # sym -> [(t, {"15s": (cp, n, prem_k, thin), "1m": (...)})]

    @staticmethod
    def _rd(w):
        if not w:
            return None
        cp = w.get("cp")
        return (None if cp is None else min(float(cp), DIR_CFG["cp_cap"]), w.get("n") or 0,
                round((w.get("cb_k") or 0) + (w.get("pb_k") or 0), 1), bool(w.get("thin", True)))

    @staticmethod
    def _ok(rd, win):
        return bool(rd and rd[0] is not None and not rd[3] and rd[1] >= DIR_CFG["cp_min_prints"][win]
                    and rd[2] >= DIR_CFG["cp_min_prem_k"][win])

    def update(self, r, now):
        if not (r.get("af15") or r.get("af60")):
            return None
        cur = {"15s": self._rd(r.get("af15")), "1m": self._rd(r.get("af60"))}
        hist = self.h.setdefault(r["sym"], [])
        hist.append((now, cur))
        while hist and now - hist[0][0] > DIR_CFG["cp_lookback_s"] + DIR_CFG["cp_lookback_tol_s"] + 25:
            hist.pop(0)
        lb, tol = DIR_CFG["cp_lookback_s"], DIR_CFG["cp_lookback_tol_s"]
        old = [x for x in hist if abs((now - x[0]) - lb) <= tol]
        past = min(old, key=lambda x: abs((now - x[0]) - lb)) if old else None
        out = {}
        for win in ("15s", "1m"):
            c = cur[win]
            p = past[1][win] if past else None
            d = {"to": rnd(c[0]) if c else None, "from": rnd(p[0]) if p else None, "ago_s": round(now - past[0]) if past else None,
                 "n": c[1] if c else None, "prem_k": c[2] if c else None, "strong": False}
            if not past:
                d["a"] = "wait"   # less than ~45 s of history (page just restarted)
            elif not (self._ok(c, win) and self._ok(p, win)):
                d["a"] = "thin"   # below the print / premium floor now or 60 s ago
            else:
                dv = c[0] - p[0]
                d["d"] = round(dv, 2)
                d["a"] = "up" if dv >= DIR_CFG["cp_flat_abs"] else "dn" if dv <= -DIR_CFG["cp_flat_abs"] else "flat"
                rx = (c[0] / p[0]) if p[0] > 0 else (99.0 if c[0] > 0 else 1.0)
                d["strong"] = bool(abs(dv) > DIR_CFG["cp_strong_abs"] or rx >= DIR_CFG["cp_strong_x"] or rx <= 1.0 / DIR_CFG["cp_strong_x"])
            out[win] = d
        return out

    def prune(self, live_syms):
        for k in [k for k in self.h if k not in live_syms]:
            self.h.pop(k, None)


class Engine:
    def __init__(self):
        self.h = Hist()
        self.cpdir = CpDir()  # DIRECTION
        self.marks, self.marks_t = {}, 0
        self.trades, self.trades_t = [], 0
        self.today_t = 0
        self.crosses = []      # rvol>=3 crossings seen by this page: {sym, t, rvol}
        self.hot_since = {}    # sym -> epoch it last went >= 3x
        self.prev_rv = {}
        self.tick = 0
        self.uw = UwLean()
        self.ext = ExtTiles()
        self.walls = WALLS  # WALLS

    def load_trades(self, now):
        if now - self.trades_t < 30:
            return
        self.trades_t = now
        try:
            d = json.loads(TRADES.read_text())
        except Exception:
            return
        out = []
        for t in d.get("trades", []):
            if "LIVE" not in str(t.get("id", "")) and "8444" not in str(t.get("account", "")):
                continue
            occ = t.get("occSymbol") or t.get("occ") or occ_from_contract(t.get("contract"))
            ex = t.get("exits")
            out.append({"id": t.get("id"), "agent": t.get("agent"), "status": t.get("status"), "contract": t.get("contract"),
                        "occ": occ, "qty": t.get("qty"), "entry": t.get("entryPrice"), "entry_pt": t.get("entryTimePT"),
                        "ledger_mark": t.get("mark"), "ledger_mark_pt": t.get("lastQuotedAtPT"),
                        "stop": ex.get("stop") if isinstance(ex, dict) else t.get("stop"),
                        "target": ex.get("target") if isinstance(ex, dict) else t.get("target"),
                        "exit_px": t.get("exitPrice"), "exit_pt": t.get("exitTimePT"), "underlying": t.get("underlying") or t.get("symbol")})
        out.sort(key=lambda r: (r["status"] != "open", str(r.get("entry_pt"))), reverse=False)
        self.trades = out[:12]

    def load_marks(self, now, occs):
        if now - self.marks_t < 5 or not occs:
            return
        self.marks_t = now
        try:
            d = get_json("/v1/options", {"contracts": ",".join(sorted(occs))})
        except Exception:
            return
        for occ, q in (d.get("options") or {}).items():
            b, a = q.get("bid"), q.get("ask")
            mid = round((b + a) / 2, 2) if b and a else q.get("last")
            obs = q.get("quote_observed_at") or q.get("trade_observed_at")
            try:
                lab = datetime.strptime(str(obs)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).astimezone(PT).strftime("%a %-m/%-d %-I:%M %p PT")
            except Exception:
                lab = None
            self.marks[occ] = {"mark": mid, "at": lab, "status": q.get("feed_status")}

    def optflow(self, now):
        """OPTFLOW: read ~/oid-optflow/data/optflow.json (written every 1 s by com.oid.desk.optflow)."""
        try:
            d = json.loads(OPTFLOW_FILE.read_text())
        except Exception:
            return {}, None
        age = now - float(d.get("computed_epoch") or 0)
        meta = {"computed_at": d.get("computed_at"), "age_s": round(age, 2), "ws": (d.get("ws") or {}).get("state"),
                "subs": d.get("subs"), "lag": d.get("exch_to_recv_lag_5m"), "source": d.get("source")}
        return (d.get("underlyings") or {}) if age < 10 else {}, meta

    def build(self):
        now = time.time()
        self.uw.refresh(now)
        raw = get_json("/v1/live-volume", {"events": "20"})
        live = raw.get("symbols") or {}
        last_s = raw.get("last_session") or {}
        syms = sorted(set(live) | set(last_s))
        if not self.h.last or self.tick == 0:
            self.h.refresh(syms, force=True)
        elif self.tick % 30 == 0:
            self.h.refresh(syms)
        if now - self.today_t >= 5:
            self.h.refresh_today(syms)
            self.today_t = now
        rth = raw.get("session") == "RTH"
        et_date = raw.get("et_date")
        rows = []
        for sym in syms:
            v, ls, hl = live.get(sym), last_s.get(sym) or {}, self.h.last.get(sym) or {}
            use_live = bool(v) and (rth or v.get("day_date") == et_date or not ls)
            if use_live and not rth and ls and v.get("last") is None:  # collector restarted after the close: fall back to last session
                use_live = False
            if use_live:
                last = v.get("last")
                prev = v.get("prev_close") or (hl.get("close") if hl.get("date") and hl["date"] < (v.get("day_date") or et_date) else None)
                bars = list(self.h.today.get(sym) or [])
                lc = v.get("last_closed_bar")
                if lc and (not bars or lc["t"] > bars[-1][0]):
                    bars.append((lc["t"], float(lc.get("v") or 0), et_slot(lc["t"])[1]))
                if not bars and not rth:
                    bars = list(hl.get("bars") or [])
                cur = v.get("cur_bar")
                row = {"sym": sym, "mode": "live", "last": rnd(last, 4), "last_pt": v.get("last_trade_pt"),
                       "chg": rnd((last / prev - 1) * 100) if last and prev else None,
                       "vol_1m": v.get("vol_60s"), "rvol": rnd(v.get("rvol_1m")), "pace": rnd(v.get("pace_rvol_10s")),
                       "day_vol": v.get("day_vol_rth"), "day_norm": v.get("day_norm_to_now"), "day_rvol": rnd(v.get("day_rvol")),
                       "hi": rnd(v.get("day_high"), 4), "lo": rnd(v.get("day_low"), 4), "date": v.get("day_date"),
                       "partial": round(cur["v"]) if cur else None,
                       "partial_norm": self.h.norm(sym, et_slot(cur["t"])[1]) if cur else None,
                       "partial_s": cur.get("elapsed_s") if cur else None,
                       "vdir": vol_dir(v) if rth else None}  # DIRECTION: volume, RTH only
            else:
                bars = list(hl.get("bars") or [])
                close, pc = ls.get("close") or hl.get("close"), hl.get("prev_close")
                row = {"sym": sym, "mode": "last_session", "last": rnd(close, 4), "last_pt": f"{ls.get('date') or hl.get('date')} close",
                       "chg": rnd((close / pc - 1) * 100) if close and pc else None, "vol_1m": None, "rvol": None, "pace": None,
                       "day_vol": ls.get("volume"), "day_norm": ls.get("norm_day"), "day_rvol": rnd(ls.get("day_rvol")),
                       "hi": rnd(ls.get("high"), 4), "lo": rnd(ls.get("low"), 4), "date": ls.get("date") or hl.get("date"),
                       "partial": None, "partial_norm": None, "partial_s": None}
            row["spark"] = [[round(b[1]), (round(self.h.norm(sym, b[2])) if self.h.norm(sym, b[2]) else None), b[0][11:16]] for b in bars[-SPARK_N:]]
            rv = row["rvol"]
            row["label"] = label(rv)
            row["day_label"] = label(row["day_rvol"])
            if rv is not None and rv >= 3 and (self.prev_rv.get(sym) or 0) < 3:
                self.hot_since[sym] = now
                self.crosses.append({"symbol": sym, "t": now, "time_pt": datetime.fromtimestamp(now, PT).strftime("%-I:%M:%S %p PT"),
                                     "rvol": rv, "chg": row["chg"], "kind": "rvol"})
                self.crosses = self.crosses[-50:]
            self.prev_rv[sym] = rv
            rows.append(row)
        # vol_surge events (from the trigger engine via the collector) -> hot flag for 5 min
        vs = raw.get("vol_surge") or {}
        evs = vs.get("events") or []
        recent_vs = set()
        for e in evs:
            try:
                et = datetime.strptime(str(e.get("engine_pt")).replace(" PT", ""), "%Y-%m-%d %I:%M:%S %p").replace(tzinfo=PT).timestamp()
            except Exception:
                continue
            e["t"] = et
            if now - et <= 300:
                recent_vs.add(e.get("symbol"))
        of_rows, of_meta = self.optflow(now)  # OPTFLOW
        for r in rows:
            r["hot"] = bool((r["rvol"] is not None and r["rvol"] >= 3) or r["sym"] in recent_vs)
            r["vs_recent"] = r["sym"] in recent_vs
            u = self.uw.for_sym(r["sym"])
            r["cp"] = u.get("cp")
            r["lean15"] = u.get("lean15")
            r["net15_m"] = u.get("net15_m")
            r["ask_lean"] = u.get("ask_lean")
            r.update(self.uw.lean5(r["sym"], now) if u else {"lean5": None, "net5_m": None, "win5_min": None, "lean5_age_s": None})
            r["uw"] = bool(u)  # True when this symbol is in core-20/focus UW set
            a = of_rows.get(r["sym"])  # OPTFLOW
            if a:
                def _c(w):
                    w = a.get(w) or {}
                    return {"cp": w.get("cp_buy"), "net_k": round((w.get("net") or 0) / 1000, 1), "cov": w.get("coverage"),
                            "n": w.get("n"), "thin": bool(w.get("thin", True)), "cb_k": round((w.get("cb") or 0) / 1000, 1),
                            "pb_k": round((w.get("pb") or 0) / 1000, 1)}
                r["af15"], r["af60"] = _c("15s"), _c("60s")
                _mo = a.get("mom") or {}  # OPTMOM: momentum from optflow 15 s slots
                for _k, _w in (("af15", "15s"), ("af60", "60s")):
                    _m = _mo.get(_w)
                    if _m:
                        r[_k].update({"md": _m.get("d"), "ms": _m.get("s"), "mh": _m.get("h"), "mrr": bool(_m.get("rr"))})
                lr = a.get("last_recv")
                try:
                    r["af_age"] = round(now - datetime.fromisoformat(lr).timestamp(), 1) if lr else None
                except Exception:
                    r["af_age"] = None
                r["af_stale"] = bool(rth and (r["af_age"] is None or r["af_age"] > OPTFLOW_STALE_S))
                r["af_n"] = a.get("contracts")
            else:
                r["af15"] = r["af60"] = r["af_age"] = r["af_n"] = None
                r["af_stale"] = True
        try:  # DIRECTION: C/P now vs ~60 s ago (RTH only; history cleared off-hours)
            if rth:
                for r in rows:
                    r["cpdir"] = self.cpdir.update(r, now) if r.get("af15") or r.get("af60") else None
            else:
                self.cpdir.h.clear()
            self.cpdir.prune({r["sym"] for r in rows})
        except Exception as e:
            log(f"cpdir error: {type(e).__name__}")
        try:  # WALLS
            self.walls.refresh(now)
            WALL_STATE["rth"] = rth
            for r in rows:
                r["walls"] = self.walls.for_row(r["sym"], r.get("last"), rth, now, r.get("date"))
        except Exception as e:
            log(f"walls error: {type(e).__name__}")
        try:  # SCORE
            sd = SCORE.get()
            by = sd.get("by_sym") or {}
            for r in rows:
                x = by.get(r["sym"])
                r["score"] = dict(x, age_s=round(now - x["t"]), kind=sd.get("kind"), feed_pt=sd.get("as_of_pt")) if x else None
        except Exception as e:
            log(f"score error: {type(e).__name__}")
        try:  # NEWS badge: headline in last 30 min + rolling 60-min net sentiment
            nd = NEWS.get()
            nby = nd.get("by_sym") or {}
            for r in rows:
                x = nby.get(r["sym"])
                if not x:
                    r["news"] = None
                    continue
                lt = x.get("last_t")
                age = round(now - lt) if lt else None
                r["news"] = {"n30": (x.get("n30") or 0) if (age is not None and age <= 1800) else 0, "n60": x.get("n60"),
                             "net60": x.get("net60"), "x60": x.get("x60"), "age_s": age, "t": x.get("last_time_pt"),
                             "h": x.get("last_headline"), "src": x.get("last_source"), "s": x.get("last_sent")}
        except Exception as e:
            log(f"news error: {type(e).__name__}")
        mom_top = None
        try:  # MOMENTUM
            md = MOMENTUM.current()
            by = md.get("by_sym") or {}
            for r in rows:
                x = by.get(r["sym"])
                if not x:
                    r["mom"] = None
                    continue
                px = r.get("last") or x.get("price")
                age = (now - x["since_ep"]) if x.get("since_ep") else None
                stt = x.get("state") or "quiet"
                if age is not None and age > MOM_QUIET_S:
                    stt = "quiet"
                m = {"st": stt, "raw": x.get("state"), "t": x.get("since_ep"), "since_pt": x.get("since_pt"), "held": x.get("held")}
                if px:
                    m["l25"], m["d25"] = _lvl(float(px), 0.25)
                    m["l1"], m["d1"] = _lvl(float(px), 1.0)
                pv = x.get("provisional")
                if pv and now - (pv.get("ep") or 0) <= 60:
                    m["prov"] = pv.get("kind")
                r["mom"] = m
            MOMLOG.note(rows, by, md, now)  # MOMSTATE: archive on change
            mom_top = {"market": md.get("market"), "as_of_pt": md.get("as_of_pt"),
                       "age_s": round(now - md["as_of"]) if md.get("as_of") else None,
                       "recent": MOMENTUM.events(now), "quiet_s": MOM_QUIET_S, "pair_s": MOM_PAIR_S}
        except Exception as e:
            log(f"momentum error: {type(e).__name__}")
        try:
            have = {r["sym"] for r in rows}
            rows += [dict(x) for x in self.ext.get(now, have) if x["sym"] not in have]
        except Exception as e:
            log(f"ext tiles error: {e}")
        strip = [{"symbol": e.get("symbol"), "t": e.get("t") or 0, "time_pt": (str(e.get("engine_pt") or "")[11:]), "rvol": e.get("rvol_1m"),
                  "kind": "vol_surge", "level": e.get("level"), "dir": e.get("dir"), "test": bool(e.get("dry_run", True))} for e in evs]
        strip += self.crosses
        strip.sort(key=lambda x: -(x.get("t") or 0))
        # Flow lean strip: hot/surge symbols that have UW lean (soft color only)
        flow_lean = []
        seen_fl = set()
        for r in sorted(rows, key=lambda x: (-(1 if x.get("hot") else 0), -(x.get("rvol") or 0), x["sym"])):
            if not r.get("uw") or r["sym"] in seen_fl:
                continue
            if not (r.get("hot") or (r.get("rvol") is not None and r["rvol"] >= 1.5)):
                continue
            seen_fl.add(r["sym"])
            flow_lean.append({"symbol": r["sym"], "cp": r.get("cp"), "lean15": r.get("lean15"),
                              "net15_m": r.get("net15_m"), "ask_lean": r.get("ask_lean"),
                              "lean5": r.get("lean5"), "net5_m": r.get("net5_m"),
                              "hot": bool(r.get("hot")), "rvol": r.get("rvol")})
            if len(flow_lean) >= 8:
                break
        # options + live trades
        opts = [{"contract": k, "vol_60s": o.get("vol_60s"), "vol_5m": o.get("vol_5m"), "day_vol": o.get("day_vol"),
                 "day_trades": o.get("day_trades"), "last_trade_pt": o.get("last_trade_pt"), "date": o.get("day_date")}
                for k, o in (raw.get("options") or {}).items()]
        opts.sort(key=lambda r: -(r.get("day_vol") or 0))
        self.load_trades(now)
        occs = {t["occ"] for t in self.trades if t.get("occ") and t.get("status") == "open"}
        self.load_marks(now, occs)
        trades = []
        for t in self.trades:
            m = self.marks.get(t.get("occ") or "") or {}
            mark = m.get("mark") if t["status"] == "open" else t.get("exit_px")
            mark_at = m.get("at") if m.get("mark") is not None else None
            if t["status"] == "open" and mark is None:
                mark, mark_at = t.get("ledger_mark"), t.get("ledger_mark_pt")
            pnl = pct = None
            try:
                pnl = round((float(mark) - float(t["entry"])) * float(t["qty"]) * 100, 2)
                pct = round((float(mark) / float(t["entry"]) - 1) * 100, 1)
            except Exception:
                pass
            trades.append({**{k: t.get(k) for k in ("id", "agent", "status", "contract", "qty", "entry", "entry_pt", "stop", "target", "underlying")},
                           "mark": mark, "mark_at": mark_at, "mark_src": "mini OPRA mid" if m.get("mark") is not None else "ledger",
                           "pnl": pnl, "pct": pct})
        stream = raw.get("stream") or {}
        st = vs.get("status") or {}
        self.wide_fresh = False
        try:  # WIDE: sector watch (own collector read every 5 s; never merged into rows)
            self.wide_fresh = WIDE.refresh(now)
        except Exception as e:
            log(f"wide error: {type(e).__name__}")
        self.tick += 1
        return {"as_of_pt": pt_str(now), "as_of": round(now, 2), "collector_as_of": raw.get("as_of_pt"), "session": raw.get("session"),
                "market_open": rth, "half_day": raw.get("half_day"), "et_date": et_date,
                "stream": {"feed": stream.get("feed"), "connected": stream.get("connected"), "age": stream.get("last_data_age_s")},
                "norms": {k: (raw.get("norms") or {}).get(k) for k in ("for_date", "symbols", "current")},
                "rows": rows, "optflow": of_meta, "options": opts, "trades": trades, "strip": strip[:5], "flow_lean": flow_lean,
                "uw": {"as_of_pt": self.uw.as_of_pt, "n": len(self.uw.by_sym), "tide": self.uw.tide,
                       "cite": "Unusual Whales (soft color only · core-20+focus · no elevate)"},
                "ladder": LADDER.latest(10), "momentum": mom_top,
                "walls": {k: self.walls.status.get(k) for k in ("last_pass_pt", "err", "reqs_today")},
                "wide": WIDE.payload,
                "dir_cfg": DIR_CFG,
                "score_versions": SCOREV.get(),  # SCORENAMES
                "vol_surge": {"mode": st.get("mode"), "gate": st.get("last_gate"), "updated_pt": st.get("updated_pt"),
                              "events": [{k: e.get(k) for k in ("symbol", "engine_pt", "level", "level_price", "dir", "last", "rvol_1m", "vol_60s", "seat_id", "dry_run")} for e in evs[:20]]}}


LIGHT_KEYS = ("sym", "mode", "last", "last_pt", "chg", "vol_1m", "rvol", "pace", "day_vol", "day_norm", "day_rvol", "hi", "lo",
              "partial", "partial_norm", "partial_s", "label", "day_label", "hot", "vs_recent",
              "cp", "lean15", "net15_m", "ask_lean", "uw", "af15", "af60", "af_age", "af_stale", "af_n", "lean5", "net5_m", "win5_min", "lean5_age_s",
              "kind", "label", "src", "src_as_of_pt", "age_s", "stale", "closed", "fut", "contract_label", "proxy", "note", "unit", "walls", "score", "mom", "news", "vdir", "cpdir")


def poll_loop():
    eng = Engine()
    last_err_log = 0
    while True:
        t0 = time.time()
        try:
            full = eng.build()
            light = dict(full, rows=[{k: r.get(k) for k in LIGHT_KEYS} for r in full["rows"]], light=True)
            if not getattr(eng, "wide_fresh", False):
                light.pop("wide", None)  # WIDE: sent only when it changed (every 5 s); the page keeps the last copy
            with COND:
                S["seq"] += 1
                S["full"], S["light"], S["err"] = full, light, None
                S["last_full_seq"] = S["seq"] if (S["seq"] % FULL_EVERY == 1 or S.get("last_spark_key") != _spark_key(full)) else S.get("last_full_seq", 0)
                S["last_spark_key"] = _spark_key(full)
                COND.notify_all()
        except Exception as e:  # never log URLs/tokens
            with COND:
                S["err"] = f"{datetime.now(PT):%I:%M:%S %p PT} collector read failed ({type(e).__name__})"
                COND.notify_all()
            if time.time() - last_err_log > 60:
                log(S["err"])
                last_err_log = time.time()
        time.sleep(max(0.05, 1.0 - (time.time() - t0)))


def _spark_key(full):
    return tuple((r["sym"], len(r["spark"]), r["spark"][-1][2] if r["spark"] else None) for r in full["rows"])


# ---------------------------------------------------------------- CHART (2026-10-20)
CHART_PY = Path(os.environ.get("OID_CHART_PY", str(HOME / "oid-desk/venv/bin/python3")))   # needs duckdb
CHART_BACKEND = HERE / "chart_backend.py"
CHART_LOG = HERE / "logs/chart-backend.log"
CHART_TIMEOUT_S = 25.0
CHART_IVS = ("15s", "1m", "5m", "15m", "1h", "1d")
CHART_RANGES = ("1D", "1W", "1M", "3M", "YTD", "1Y")
VENDOR_DIR = HERE / "vendor"
VENDOR_FILES = {"lightweight-charts.standalone.production.js": "application/javascript; charset=utf-8",
                "LICENSE-lightweight-charts.txt": "text/plain; charset=utf-8"}
WALL_HIST_DIR = Path(os.environ.get("OID_LIVEPAGE_WALL_HIST", str(HOME / "oid-data/walls-history")))
WALL_HIST_EVERY_S = 30


class ChartBackend:
    """One long-lived child (chart_backend.py, duckdb) answering one JSON line per request. Serialised by a lock."""

    def __init__(self):
        self.p, self.lock, self.seq, self.err = None, threading.Lock(), 0, None
        self.n, self.ms_sum, self.started = 0, 0.0, None

    def _spawn(self):
        CHART_LOG.parent.mkdir(parents=True, exist_ok=True)
        logf = open(CHART_LOG, "a")
        self.p = subprocess.Popen([str(CHART_PY), str(CHART_BACKEND)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=logf, cwd=str(HERE), preexec_fn=lambda: os.nice(10), close_fds=True)
        logf.close()
        self.started = time.time()
        log(f"chart backend started pid {self.p.pid}")

    def _kill(self):
        try:
            if self.p:
                self.p.kill()
                self.p.wait(timeout=2)
        except Exception:
            pass
        self.p = None

    def ask(self, req, _retry=True):
        rep = self._ask(req)
        if not rep.get("ok") and _retry and rep.get("_dead"):
            return self._ask(req)   # the child had exited (idle exit / crash): one retry on a fresh child
        return rep

    def _ask(self, req):
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self._spawn()
            self.seq += 1
            req = dict(req, id=self.seq)
            t0 = time.time()
            try:
                self.p.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
                self.p.stdin.flush()
                fd = self.p.stdout
                r, _, _ = select.select([fd], [], [], CHART_TIMEOUT_S)
                if not r:
                    raise TimeoutError("chart backend timeout")
                line = fd.readline()
                if not line:
                    raise RuntimeError("chart backend exited")
                rep = json.loads(line)
                if rep.get("id") != self.seq:
                    raise RuntimeError("chart backend out of sync")
            except Exception as e:
                dead = self.p is not None and self.p.poll() is not None
                self.err = str(e)[:120]
                log(f"chart backend error: {self.err}; restarting")
                self._kill()
                return {"ok": False, "error": self.err, "_dead": dead or isinstance(e, (BrokenPipeError, RuntimeError))}
            self.n += 1
            self.ms_sum += (time.time() - t0) * 1000
            return rep


CHART = ChartBackend()



# ---- PATTERN BADGES (2026-10-21 3 PM, display only): hit rates + expiry for the heatmap pattern badges ----
# Rates: latest ~/oid-data/patterns/scorecard-*.json by_mode.live[pattern|iv|dir] when live n >= 20 (graded with the
# RRFIX grader: wrong-side targets rejected, med R:R, breakeven, 1:1 rate); else base-rates.json "backtest" (labelled BT).
# Expiry: detection ts0 + horizon (30 bars on 1m, 24 on 5m, 26 on 30m, gap = rest of session), counted in regular-hours
# minutes so the clock stops overnight. Never touches the detector, a score or a trade.
PAT_DIR = HOME / "oid-data/patterns"
PAT_MIN_LIVE_N = 20
PAT_IV_MIN = {"1m": 1, "5m": 5, "30m": 30}
PAT_HZ_BARS = {"1m": 30, "5m": 24, "30m": 26}
try:
    import importlib.util as _ilu  # read-only: horizon constants only; loaded by path so sys.path is untouched
    _spec = _ilu.spec_from_file_location("_oid_patterns_ro", str(HOME / "oid-score/patterns.py"))
    _PTMOD = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_PTMOD)
    PAT_HZ_BARS = {k: v["hz"] for k, v in _PTMOD.CFG.items()}
except Exception:
    pass
_PAT_RC = {"key": None, "doc": None}


def _pat_rates():
    try:
        cards = sorted(PAT_DIR.glob("scorecard-20*.json"))
        sc = cards[-1] if cards else None
        br = PAT_DIR / "base-rates.json"
        key = (str(sc), sc.stat().st_mtime if sc else 0, br.stat().st_mtime if br.exists() else 0)
        if _PAT_RC["key"] == key:
            return _PAT_RC["doc"]
        card = json.loads(sc.read_text()) if sc else {}
        bt = (json.loads(br.read_text()).get("backtest") or {}) if br.exists() else {}
        doc = {"live": ((card.get("by_mode") or {}).get("live") or {}), "bt": bt, "card": sc.name if sc else None,
               "graded_pt": card.get("graded_pt"), "days": card.get("days_graded")}
        _PAT_RC.update(key=key, doc=doc)
        return doc
    except Exception as e:
        log(f"pattern rates: {type(e).__name__}: {e}")
        return {"live": {}, "bt": {}, "card": None}


def _rth_min(t0, t1):
    """Regular-hours minutes (6:30 AM-1:00 PM PT, Mon-Fri; holidays not removed) between epoch t0 and t1."""
    if t1 <= t0:
        return 0.0
    d = datetime.fromtimestamp(t0, PT).date()
    end = datetime.fromtimestamp(t1, PT).date()
    tot = 0.0
    while d <= end:
        if d.weekday() < 5:
            o = datetime(d.year, d.month, d.day, 6, 30, tzinfo=PT).timestamp()
            c = datetime(d.year, d.month, d.day, 13, 0, tzinfo=PT).timestamp()
            tot += max(0.0, min(t1, c) - max(t0, o)) / 60
        d += timedelta(days=1)
    return tot


def _pat_enrich(a, R, now):
    if not a.get("dir") or a.get("state") not in ("confirmed", "triggered"):
        return None
    iv, d = a.get("iv"), a["dir"]
    trig, tgt = a.get("trig"), a.get("tgt")
    if trig is not None and tgt is not None and (tgt - trig) * d <= 0:
        return None  # target on the wrong side of the trigger: never badge it (RRFIX)
    k = f"{a['pattern']}|{iv}|{d:+d}"
    lv, bt = R["live"].get(k) or {}, R["bt"].get(k) or {}
    if (lv.get("n") or 0) >= PAT_MIN_LIVE_N:
        src, rate, n = "live", lv.get("rate"), lv.get("n")
        rr, be, r1, n1 = lv.get("med_rr"), lv.get("breakeven"), lv.get("rate_1r"), lv.get("n_1r")
    elif bt.get("n"):
        src, rate, n = "backtest", bt.get("rate"), bt.get("n")
        rr, be, r1, n1 = bt.get("med_rr"), bt.get("breakeven"), bt.get("rate_1r"), bt.get("n_1r")
    else:
        return None
    if rate is None:
        return None
    hz_bars = 77 if a["pattern"] in ("gap_up", "gap_down") else PAT_HZ_BARS.get(iv, 30)
    hz_min = hz_bars * PAT_IV_MIN.get(iv, 1)
    ts0 = a.get("ts0") or 0
    left = round(hz_min - _rth_min(ts0, now), 1)
    if left <= 0:
        return None
    return {"id": a.get("id"), "p": a["pattern"], "iv": iv, "dir": d, "state": a.get("state"), "trig": trig, "tgt": tgt,
            "inv": a.get("inv"), "rate": rate, "n": n, "src": src, "n_live": lv.get("n"), "rate_live": lv.get("rate"),
            "rr": rr, "be": be, "r1": r1, "n1": n1, "left_min": left, "hz_min": hz_min, "ts0": ts0,
            "t0_pt": datetime.fromtimestamp(ts0, PT).strftime("%-I:%M %p") if ts0 else None}



# PATTERN TALLY (10/21 3:15 PM, display only): today's live shadow detections per ticker and pattern with their outcomes so
# far. Reads the detector archive incrementally (new lines only). Outcome = the nightly grader label when one exists
# (target_hit / invalidated / expired), else the detector's own last state (completed = hit, failed = miss, expired,
# anything else = open). Triggered detections only; a trigger whose target sits on the wrong side of entry is not counted
# (same rule as the grader's RRFIX).
PAT_ARCH = HOME / "oid-data/archive"
_PT_TALLY = {"date": None, "files": {}, "dets": {}, "labels_key": None, "labels": {}, "t": 0, "out": None}


def _pat_tally():
    T = _PT_TALLY
    now = time.time()
    if T["out"] is not None and now - T["t"] < 20:
        return T["out"]
    try:
        days = sorted(p.name[5:] for p in (PAT_ARCH / "patterns").glob("date=*") if any(p.glob("part-patterns-live-*.jsonl")))
        if not days:
            return None
        D = days[-1]
        if T["date"] != D:
            T.update(date=D, files={}, dets={}, labels_key=None, labels={})
        for f in sorted((PAT_ARCH / "patterns" / f"date={D}").glob("part-patterns-live-*.jsonl")):
            off = T["files"].get(f.name, 0)
            sz = f.stat().st_size
            if sz <= off:
                continue
            with open(f, "rb") as fh:
                fh.seek(off)
                chunk = fh.read(sz - off)
            cut = chunk.rfind(b"\n") + 1  # only whole lines
            T["files"][f.name] = off + cut
            for ln in chunk[:cut].splitlines():
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if not r.get("direction") or r.get("mode") != "live":
                    continue
                dd = T["dets"].get(r["det_id"])
                if r["state"] == "triggered" and dd is None:
                    kl = r.get("key_levels") or {}
                    tg, px = kl.get("target"), r.get("px")
                    bad = tg is None or px is None or (tg - px) * r["direction"] <= 0
                    dd = T["dets"][r["det_id"]] = {"sym": r["ticker"], "p": r["pattern"], "iv": r["interval"],
                                                   "dir": r["direction"], "bad": bad, "st": "triggered"}
                elif dd is not None:
                    dd["st"] = r["state"]
        lf = PAT_ARCH / "pattern_labels" / f"date={D}" / "part-pattern-grader-1.jsonl"
        lk = (lf.stat().st_mtime, lf.stat().st_size) if lf.exists() else None
        if lk != T["labels_key"]:
            T["labels_key"], T["labels"] = lk, {}
            if lf.exists():
                for ln in lf.read_text().splitlines():
                    try:
                        x = json.loads(ln)
                    except Exception:
                        continue
                    if x.get("mode") == "live":
                        T["labels"][x["det_id"]] = x.get("outcome")
        MAP = {"target_hit": "hit", "invalidated": "miss", "expired": "exp", "completed": "hit", "failed": "miss"}
        by = {}
        for did, dd in T["dets"].items():
            lab = T["labels"].get(did)
            if dd["bad"] or lab == "rejected_wrong_side":
                continue
            o = MAP.get(lab) or MAP.get(dd["st"]) or "open"
            k = f"{dd['p']}|{dd['iv']}|{dd['dir']:+d}"
            a = by.setdefault(dd["sym"], {}).setdefault(k, {"k": k, "p": dd["p"], "iv": dd["iv"], "dir": dd["dir"], "n": 0,
                                                            "hit": 0, "miss": 0, "exp": 0, "open": 0})
            a["n"] += 1
            a[o] += 1
        out = {"date": D, "labelled": lk is not None,
               "by_sym": {s_: sorted(v.values(), key=lambda a: (-a["n"], a["k"])) for s_, v in by.items()}}
        T.update(out=out, t=now)
        return out
    except Exception as e:
        log(f"pattern tally: {type(e).__name__}: {e}")
        return T["out"]

def chart_cur_walls(sym):
    """Latest wall level the page itself shows for this symbol (core: best of the 4 FA caches; Sector watch: fa-walls-wide)."""
    r = None
    try:
        if WALLS is not None:
            r = WALLS.by.get(sym)
        if r is None:
            r = _wall_rec("fa-walls-wide", sym, (WIDE.walls or {}).get(sym))
    except Exception:
        r = None
    if not r:
        return None
    return {"t": r.get("t"), "cw": r.get("cw"), "pw": r.get("pw"), "gf": r.get("gf"), "src": r.get("src")}


class WallHistory:
    """Append-only log of every new wall level the page sees (FlashAlpha levels only change every 10-40 min).
    ~/oid-data/walls-history/walls-YYYYMMDD.jsonl (ET date of the record time). Read back by chart_backend.py."""

    def __init__(self):
        self.last = {}
        try:
            for p in sorted(WALL_HIST_DIR.glob("walls-*.jsonl"))[-5:]:
                for line in p.read_text().splitlines():
                    try:
                        d = json.loads(line)
                        self.last[d["sym"]] = (d.get("as_of"), d.get("cw"), d.get("pw"), d.get("gf"))
                    except Exception:
                        pass
        except Exception:
            pass

    def tick(self, now):
        recs = []
        try:
            if WALLS is not None:
                WALLS.refresh(now)
                for sym, r in list(WALLS.by.items()):
                    recs.append(("core", sym, r))
            for sym, v in list((WIDE.walls or {}).items()):
                r = _wall_rec("fa-walls-wide", sym, v)
                if r:
                    recs.append(("wide", sym, r))
        except Exception as e:
            log(f"wall history read: {e}")
            return
        out = []
        for tier, sym, r in recs:
            key = (round(r["t"], 1), r.get("cw"), r.get("pw"), r.get("gf"))
            if self.last.get(sym) == key:
                continue
            self.last[sym] = key
            out.append({"sym": sym, "tier": tier, "as_of": key[0], "as_of_pt": pt_str(r["t"]), "cw": r.get("cw"), "pw": r.get("pw"),
                        "gf": r.get("gf"), "gf_status": r.get("gf_status"), "src": r.get("src"), "rec_t": round(now, 1)})
        if not out:
            return
        try:
            WALL_HIST_DIR.mkdir(parents=True, exist_ok=True)
            p = WALL_HIST_DIR / f"walls-{datetime.fromtimestamp(now, ET).strftime('%Y%m%d')}.jsonl"
            with open(p, "a") as fh:
                for d in out:
                    fh.write(json.dumps(d, separators=(",", ":")) + "\n")
        except Exception as e:
            log(f"wall history write: {e}")

    def loop(self):
        time.sleep(5)
        while True:
            self.tick(time.time())
            time.sleep(WALL_HIST_EVERY_S)


def chart_query(qs):
    from urllib.parse import parse_qs
    q = {k: v[0] for k, v in parse_qs(qs or "").items() if v}
    sym = (q.get("sym") or "").upper()
    iv, rng = q.get("iv") or "1m", q.get("range") or "1D"
    if not SYM_RE.match(sym) or iv not in CHART_IVS or rng not in CHART_RANGES:
        return 400, {"error": "bad sym / iv / range"}
    req = {"sym": sym, "iv": iv, "range": rng, "ext": 0 if q.get("ext") == "0" else 1, "cur_walls": chart_cur_walls(sym)}
    if q.get("since"):
        try:
            req["since"] = float(q["since"])
        except ValueError:
            return 400, {"error": "bad since"}
    rep = CHART.ask(req)
    if not rep.get("ok"):
        return 502 if "timeout" not in str(rep.get("error")) else 504, {"error": rep.get("error")}
    return 200, rep["data"]



# CREDITTAB (2026-10-21): Credit & Betas tab. Read-only view of ~/oid-data/research/spread-corr (com.oid.desk.spread-corr).
CREDIT_DIR = Path.home() / "oid-data/research/spread-corr"
CREDIT_SERIES = ["date", "regime", "hyg_ief", "hyg_ief_chg20_pct", "hy_oas", "neocloud__META__beta20", "memory__META__beta20",
                 "neocloud__QQQ__beta20", "memory__QQQ__beta20", "neocloud__META__xbeta20"]
_CREDIT_CACHE = {"key": None, "body": None}


def credit_payload():
    """latest.json + the chart columns of spread_corr_daily.csv (raw values, no smoothing); cached on file mtimes."""
    import csv as _csv
    from datetime import date as _date
    lj, cv = CREDIT_DIR / "latest.json", CREDIT_DIR / "spread_corr_daily.csv"
    key = (lj.stat().st_mtime, cv.stat().st_mtime)
    if _CREDIT_CACHE["key"] == key:
        return _CREDIT_CACHE["body"]
    latest = json.loads(lj.read_text())
    ser = {c: [] for c in CREDIT_SERIES}
    with open(cv, newline="") as f:
        for row in _csv.DictReader(f):
            for c in CREDIT_SERIES:
                v = row.get(c, "")
                if c in ("date", "regime"):
                    ser[c].append(v or None)
                else:
                    try:
                        ser[c].append(float(v))
                    except ValueError:
                        ser[c].append(None)
    sp = latest.get("spreads") or {}
    stale = None
    try:
        stale = (_date.fromisoformat(latest["date"]) - _date.fromisoformat(sp["hy_oas_obs_date"])).days
    except Exception:
        pass
    body = json.dumps({"latest": latest, "series": ser, "fred_stale_days": stale}, separators=(",", ":"))
    _CREDIT_CACHE.update(key=key, body=body)
    return body

class H(BaseHTTPRequestHandler):
    server_version = "oid-livepage/1.0"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(b)

    def _send_json_gz(self, code, obj):
        b = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        gz = "gzip" in (self.headers.get("Accept-Encoding") or "") and len(b) > 2048
        if gz:
            b = gzip.compress(b, 5)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/ingest/ladder":
            return self._send(404, "not found", "text/plain")
        if not LADDER.token_ok(self.headers.get("Authorization")):
            return self._send(401, json.dumps({"error": "unauthorized"}), "application/json")
        if self.headers.get("Transfer-Encoding"):
            return self._send(411, json.dumps({"error": "length required"}), "application/json")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n <= 0 or n > LADDER_MAX_BYTES:
            return self._send(413, json.dumps({"error": "size", "max": LADDER_MAX_BYTES}), "application/json")
        if "json" not in (self.headers.get("Content-Type") or ""):
            return self._send(415, json.dumps({"error": "content-type"}), "application/json")
        with LADDER.lock:
            ok = LADDER.rate_ok()
        if not ok:
            return self._send(429, json.dumps({"error": "rate"}), "application/json")
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            items = body.get("snapshots") if isinstance(body, dict) else None
            if not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise ValueError("snapshots must be a list of 1..20")
            rows = [validate_ladder(x) for x in items]
        except Exception as e:
            return self._send(400, json.dumps({"error": "invalid", "detail": str(e)[:80]}), "application/json")
        LADDER.upsert(rows)
        log(f"ladder push accepted: {len(rows)} snapshot(s) {','.join(r['symbol'] for r in rows)}")
        return self._send(200, json.dumps({"ok": True, "accepted": len(rows)}), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/healthz":
            with LOCK:
                f = S["full"]
                body = {"ok": f is not None and S["err"] is None, "as_of_pt": f and f["as_of_pt"], "rows": f and len(f["rows"]),
                        "err": S["err"], "clients": S["clients"], "uptime_s": round(time.time() - S["started"]),
                        "chart": {"requests": CHART.n, "avg_ms": round(CHART.ms_sum / CHART.n, 1) if CHART.n else None, "err": CHART.err}}
            return self._send(200, json.dumps(body), "application/json")
        if path == "/state.json":
            with LOCK:
                f = S["full"]
            return self._send(200 if f else 503, json.dumps(f or {"error": S["err"] or "starting"}), "application/json")
        if path == "/stream":
            return self._stream()
        if path == "/news.json":  # NEWS panel feed (separate from the 1 s stream)
            d = NEWS.get()
            if not d:
                return self._send(503, json.dumps({"error": "news feed not running (com.oid.desk.news)"}), "application/json")
            body = {k: d.get(k) for k in ("as_of_pt", "as_of", "source", "sentiment", "status", "today", "today_followed",
                                           "items", "market", "x_top", "followed")}
            return self._send(200, json.dumps(body), "application/json")
        if path in ("/chart.js", "/chart.css"):  # CHART: page-side chart code (static, read-only)
            try:
                return self._send(200, (HERE / path[1:]).read_bytes(), "application/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
            except OSError:
                return self._send(404, "not found", "text/plain")
        if path == "/chart.json":  # CHART: read-only bars + score + C/P + wall history
            code, body = chart_query(self.path.split("?", 1)[1] if "?" in self.path else "")
            return self._send_json_gz(code, body)
        if path.startswith("/vendor/"):  # CHART: locally vendored chart library (no CDN)
            name = path[len("/vendor/"):]
            if name not in VENDOR_FILES:
                return self._send(404, "not found", "text/plain")
            try:
                return self._send(200, (VENDOR_DIR / name).read_bytes(), VENDOR_FILES[name])
            except OSError:
                return self._send(404, "not found", "text/plain")
        if path == "/walls.json":  # read-only copy of data/fa-walls-pulse.json (com.oid.desk.fa-walls) for the box fa-levels merge
            try:
                return self._send(200, WALL_FILES[0][1].read_bytes(), "application/json")
            except OSError:
                return self._send(404, json.dumps({"error": "no fa-walls-pulse.json"}), "application/json")
        if path == "/wide-spark.json":  # SECTORHEAT: Heatmap sparklines for the sector names
            try:
                return self._send_json_gz(200, WIDE.spark_payload(time.time()))
            except Exception as e:
                return self._send(500, json.dumps({"error": type(e).__name__}), "application/json")
        if path == "/wide-sectors.json":  # WIDE: sector watch groups
            try:
                return self._send(200, WIDE_SECTORS_FILE.read_bytes(), "application/json")
            except OSError:
                return self._send(404, json.dumps({"error": "no wide-sectors.json"}), "application/json")
        if path == "/sectors.json":
            try:
                return self._send(200, SECTORS_FILE.read_bytes(), "application/json")
            except OSError:
                return self._send(404, json.dumps({"error": "no sectors.json"}), "application/json")
        if path == "/leadlag.json":  # LEADLAG (10/21): shadow leader -> follower predictions per ticker
            try:
                return self._send(200, (Path.home() / "oid-data/patterns/leadlag-live.json").read_bytes(), "application/json")
            except OSError:
                return self._send(404, json.dumps({"error": "no leadlag-live.json yet (com.oid.desk.leadlag)"}), "application/json")
        if path == "/patterns.json":  # PATTERNS (10/21): shadow pattern detector, top active pattern per ticker
            try:
                d = json.loads((Path.home() / "oid-data/patterns/live.json").read_text())
                body = {k: d.get(k) for k in ("as_of", "as_of_pt", "mode", "detector_version", "note")}
                body["by_sym"] = {s: {"top": v.get("top"), "n_active": v.get("n_active")} for s, v in (d.get("by_sym") or {}).items()}
                # PATTERN BADGES (10/21 3 PM): every unexpired directional detection with its rate source, R:R and expiry
                R, now = _pat_rates(), time.time()
                for s_, v in (d.get("by_sym") or {}).items():
                    act = [x for x in (_pat_enrich(a, R, now) for a in (v.get("active") or [])) if x]
                    if act:
                        body["by_sym"][s_]["act"] = sorted(act, key=lambda x: (-x["rate"], -(x["n"] or 0)))
                body["rates"] = {"card": R.get("card"), "graded_pt": R.get("graded_pt"), "days": R.get("days"),
                                 "min_live_n": PAT_MIN_LIVE_N}
                body["age_s"] = round(now - (d.get("as_of") or 0))
                TL = _pat_tally()  # PATTERN TALLY (10/21 3:15 PM)
                if TL:
                    body["tally_date"], body["tally_labelled"] = TL["date"], TL["labelled"]
                    for s_, tl in TL["by_sym"].items():
                        body["by_sym"].setdefault(s_, {"top": None, "n_active": 0})["tally"] = tl
                return self._send(200, json.dumps(body), "application/json")
            except Exception:
                return self._send(404, json.dumps({"error": "no patterns live.json yet (com.oid.desk.patterns)"}), "application/json")
        if path == "/credit":  # CREDITTAB: Credit & Betas tab
            try:
                return self._send(200, (HERE / "credit.html").read_bytes(), "text/html; charset=utf-8")
            except OSError:
                return self._send(404, "no credit.html", "text/plain")
        if path == "/credit/":
            self.send_response(302)
            self.send_header("Location", "/credit")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/credit.json":  # CREDITTAB: spread-corr latest + chart series
            try:
                return self._send(200, credit_payload(), "application/json")
            except Exception as e:
                return self._send(404, json.dumps({"error": f"no spread-corr data yet (com.oid.desk.spread-corr): {type(e).__name__}"}), "application/json")
        if path == "/name-credit.json":  # NAMECREDIT 10/21: company credit (DTCC CDS, X CDS prints, FINRA bond yields) for /credit
            try:
                return self._send(200, (Path.home() / "oid-data/research/name-credit/latest.json").read_bytes(), "application/json")
            except OSError:
                return self._send(404, json.dumps({"error": "no name-credit data yet (com.oid.desk.name-credit)"}), "application/json")
        if path in ("/research", "/research/"):  # RESEARCHTAB
            self.send_response(302)
            self.send_header("Location", "/guide/research/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/guide":
            self.send_response(301)
            self.send_header("Location", "/guide/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path.startswith("/guide/"):
            return self._guide(path[len("/guide/"):])
        return self._send(404, "not found", "text/plain")

    def _guide(self, rel):
        """Static field guide (read-only): /guide/ viewer, /guide/docs/*.md + img, /guide/vendor/*.js."""
        from urllib.parse import unquote
        rel = unquote(rel) or "index.html"
        if rel.endswith("/"):  # RESEARCHTAB: guide/research/ -> guide/research/index.html
            rel += "index.html"
        if "\x00" in rel or rel.startswith("/") or ".." in rel.split("/"):
            return self._send(400, "bad path", "text/plain")
        root = GUIDE_DIR.resolve()
        f = (root / rel).resolve()
        ctype = GUIDE_TYPES.get(f.suffix.lower())
        if ctype is None or root not in f.parents or not f.is_file():
            return self._send(404, "not found", "text/plain")
        return self._send(200, f.read_bytes(), ctype)

    def _stream(self):
        with LOCK:
            if S["clients"] >= MAX_CLIENTS:
                return self._send(503, "too many viewers", "text/plain")
            S["clients"] += 1
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            seen, first = -1, True
            while True:
                with COND:
                    COND.wait_for(lambda: S["seq"] != seen, timeout=15)
                    seq, err = S["seq"], S["err"]
                    payload = S["full"] if (first or S.get("last_full_seq") == seq or seq - seen > 1) else S["light"]
                    if payload is not None:
                        payload = dict(payload, err=err)
                if seq == seen:
                    self.wfile.write(b": ping\n\n")
                else:
                    seen = seq
                    if payload is not None:
                        self.wfile.write(b"data: " + json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n\n")
                        first = False
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            with LOCK:
                S["clients"] -= 1


def main():
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        log("refusing to bind a non-loopback address")
        return 2
    global WALLS
    WALLS = Walls()
    WALLS.refresh(time.time())
    threading.Thread(target=WALLS.loop, args=(WALL_STATE,), daemon=True).start()  # WALLS weights (Alpaca, read-only)
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=WallHistory().loop, daemon=True).start()  # CHART: wall history recorder
    srv = ThreadingHTTPServer((HOST, PORT), H)
    srv.daemon_threads = True
    log(f"live page on http://{HOST}:{PORT}/ (loopback only)")
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
