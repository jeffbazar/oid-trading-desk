#!/usr/bin/env python3
"""OID private live page (Mac mini, 2026-10-18). Stdlib only, python3.9+.

A separate, read-only service: polls the collector's /v1/live-volume once a second (plus held-option marks every 5 s
and the desk's live trades every 30 s), merges 1-min volume history from the collector's bar files, reads local UW
net-prem / flow-alerts JSON (~45 s) for soft put/call lean badges (zero UW API calls), and pushes the
result to one HTML page over Server-Sent Events.

  bind      127.0.0.1:8791 only (exposed to the tailnet with `tailscale serve`, HTTPS, tailnet-only; never Funnel)
  token     read in-process from ~/oid-quote/secrets/OID_QUOTE_TOKEN; never sent to the browser, never logged
  writes    nothing except its own log; never touches the collector, the trigger engine or Robinhood

Routes: /  (page)   /stream  (SSE)   /state.json  (current state)   /healthz
"""
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.request
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
#   data/fa-walls-pulse.json (copy of the box walls pulse tmp/fa-walls-last.json, when present).
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
                "t": t, "src": src, "fa_spot": rnd(v.get("underlying_price"), 2)}
    except (TypeError, ValueError):
        return None


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
        stale = (age > WALLS_STALE_S) if rth else bool(session_date and wdate < str(session_date))
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


class Engine:
    def __init__(self):
        self.h = Hist()
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
                       "partial_s": cur.get("elapsed_s") if cur else None}
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
        try:  # WALLS
            self.walls.refresh(now)
            WALL_STATE["rth"] = rth
            for r in rows:
                r["walls"] = self.walls.for_row(r["sym"], r.get("last"), rth, now, r.get("date"))
        except Exception as e:
            log(f"walls error: {type(e).__name__}")
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
        self.tick += 1
        return {"as_of_pt": pt_str(now), "as_of": round(now, 2), "collector_as_of": raw.get("as_of_pt"), "session": raw.get("session"),
                "market_open": rth, "half_day": raw.get("half_day"), "et_date": et_date,
                "stream": {"feed": stream.get("feed"), "connected": stream.get("connected"), "age": stream.get("last_data_age_s")},
                "norms": {k: (raw.get("norms") or {}).get(k) for k in ("for_date", "symbols", "current")},
                "rows": rows, "optflow": of_meta, "options": opts, "trades": trades, "strip": strip[:5], "flow_lean": flow_lean,
                "uw": {"as_of_pt": self.uw.as_of_pt, "n": len(self.uw.by_sym), "tide": self.uw.tide,
                       "cite": "Unusual Whales (soft color only · core-20+focus · no elevate)"},
                "ladder": LADDER.latest(10),
                "walls": {k: self.walls.status.get(k) for k in ("last_pass_pt", "err", "reqs_today")},
                "vol_surge": {"mode": st.get("mode"), "gate": st.get("last_gate"), "updated_pt": st.get("updated_pt"),
                              "events": [{k: e.get(k) for k in ("symbol", "engine_pt", "level", "level_price", "dir", "last", "rvol_1m", "vol_60s", "seat_id", "dry_run")} for e in evs[:20]]}}


LIGHT_KEYS = ("sym", "mode", "last", "last_pt", "chg", "vol_1m", "rvol", "pace", "day_vol", "day_norm", "day_rvol", "hi", "lo",
              "partial", "partial_norm", "partial_s", "label", "day_label", "hot", "vs_recent",
              "cp", "lean15", "net15_m", "ask_lean", "uw", "af15", "af60", "af_age", "af_stale", "af_n", "lean5", "net5_m", "win5_min", "lean5_age_s",
              "kind", "label", "src", "src_as_of_pt", "age_s", "stale", "closed", "fut", "contract_label", "proxy", "note", "unit", "walls")


def poll_loop():
    eng = Engine()
    last_err_log = 0
    while True:
        t0 = time.time()
        try:
            full = eng.build()
            light = dict(full, rows=[{k: r.get(k) for k in LIGHT_KEYS} for r in full["rows"]], light=True)
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
                        "err": S["err"], "clients": S["clients"], "uptime_s": round(time.time() - S["started"])}
            return self._send(200, json.dumps(body), "application/json")
        if path == "/state.json":
            with LOCK:
                f = S["full"]
            return self._send(200 if f else 503, json.dumps(f or {"error": S["err"] or "starting"}), "application/json")
        if path == "/stream":
            return self._stream()
        if path == "/sectors.json":
            try:
                return self._send(200, SECTORS_FILE.read_bytes(), "application/json")
            except OSError:
                return self._send(404, json.dumps({"error": "no sectors.json"}), "application/json")
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
    srv = ThreadingHTTPServer((HOST, PORT), H)
    srv.daemon_threads = True
    log(f"live page on http://{HOST}:{PORT}/ (loopback only)")
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
