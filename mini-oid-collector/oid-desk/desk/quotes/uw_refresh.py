#!/usr/bin/env python3
"""OID Unusual Whales box refresher (Jeffrey 2026-10-10). Research / paper only - zero broker calls.

Why: uw-market-tide / uw-net-prem / uw-flow-alerts were only written opportunistically by LLM routines
(first-hour pass, 5-min qualifier, open, afternoon), so between runs they aged past their 900s TTL.
This daemon pulls UW REST directly (auth = UW_API_KEY env, the same desk-injected secret
chart-bot/whale-flow uses) every `interval_s` (default 240s) during RTH, plus one closing pull.

  python3 quotes/uw_refresh.py            # loop (run via scripts/uw-refresh.sh start)
  python3 quotes/uw_refresh.py --once     # one cycle now, RTH or not (weekend -> last session's data)
  python3 quotes/uw_refresh.py --selftest # offline checks, no network

Writes (cache_io envelope: as_of / as_of_pt / source / writer / feed / symbols / ttl_seconds / payload / error):
  market-data/latest/uw-market-tide.json  market tide 5m series + sector tide (Technology, Comm Svcs, Cons Cyclical)
  market-data/latest/uw-net-prem.json     market tide last + per-ticker net premium (core-20 + focus) from net-prem-ticks
  market-data/latest/uw-flow-alerts.json  today's flow alerts for core-20 + focus, top N by premium + per-ticker summary
  cache/uw-refresh.json                   status / heartbeat / call counts / last errors
A failed pull never overwrites the last good file (the Data sources page then shows the real age).
Routine-written extras (uw-net-prem payload.per_strike, *.note) from today are carried forward.
UW endpoints: /api/market/market-tide, /api/market/{sector}/sector-tide, /api/stock/{T}/net-prem-ticks,
/api/option-trades/flow-alerts. 429 -> honour Retry-After / exponential backoff (60s..15min), cycle aborted.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

OID = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")
API = "https://api.unusualwhales.com/api"
LATEST = OID / "market-data" / "latest"
CFG_PATH = OID / "config" / "uw-refresh.json"
STATUS_PATH = OID / "cache" / "uw-refresh.json"
PIDF = OID / "cache" / "uw-refresh.pid"
LOG_MAX_BYTES = 2_000_000
WRITER = "uw_refresh.py (box daemon)"
TTL = 900
CLOSE_GRACE_MIN = 10  # one last pull up to 10 min after the bell

DEFAULT_CFG: dict[str, Any] = {
    "enabled": True,
    "interval_s": 240,
    "sectors": ["Technology", "Communication Services", "Consumer Cyclical"],
    "include_core20": True,
    "include_focus": True,
    "extra_symbols": [],
    "flow_alerts": {"min_premium": 250000, "etf_min_premium": 500000, "etfs": ["SPY", "QQQ"],
                    "chunk": 9, "limit": 200, "keep_top": 60},
    "request_spacing_s": 0.25,
    "daily_call_cap": 6000,
    "timeout_s": 20,
}

_stop = False


def _on_signal(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


# ---------------------------------------------------------------- helpers
def pt_stamp(dt: datetime) -> str:
    return dt.astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT")


def utc_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def envelope(feed: str, *, source: str, symbols: list[str], payload: Any, now: datetime) -> dict:
    return {"as_of": utc_z(now), "as_of_pt": pt_stamp(now), "source": source, "writer": WRITER,
            "feed": feed, "symbols": symbols, "ttl_seconds": TTL, "payload": payload, "error": None}


def load_cfg() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    user = read_json(CFG_PATH) or {}
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def session_now(now: Optional[datetime] = None) -> str:
    try:
        sys.path.insert(0, str(OID / "paper-trades"))
        from market_session import market_session  # type: ignore
        return str(market_session(now) or "closed").lower()
    except Exception:
        et = (now or datetime.now(timezone.utc)).astimezone(ET)
        m = et.hour * 60 + et.minute
        return "rth" if et.weekday() < 5 and 570 <= m < 960 else "closed"


def core_symbols() -> list[str]:
    d = read_json(OID / "config" / "stream-quote-allowlist.json") or {}
    return [str(s).strip().upper() for s in d.get("underlyings") or [] if str(s).strip()]


def focus_symbols(now_epoch: float) -> list[str]:
    """Same focus set the 5s focus watch uses (config/focus-watch.json + open paper seats)."""
    try:
        sys.path.insert(0, str(OID / "quotes"))
        from focus_watch import FocusWatch  # type: ignore
        fw = FocusWatch(OID)
        return sorted(fw.focus_list(now_epoch, fw.config(now_epoch)).keys())
    except Exception:
        d = read_json(OID / "cache" / "focus-watch.json") or {}
        return [str(s).upper() for s in d.get("focus_symbols") or []]


def universe(cfg: dict, now_epoch: float) -> tuple[list[str], list[str]]:
    focus = focus_symbols(now_epoch) if cfg.get("include_focus", True) else []
    names: list[str] = []
    for s in (core_symbols() if cfg.get("include_core20", True) else []) + focus + list(cfg.get("extra_symbols") or []):
        s = str(s).upper().strip()
        if s and s not in names:
            names.append(s)
    return names, focus


# ---------------------------------------------------------------- HTTP
class RateLimited(Exception):
    def __init__(self, retry_after: Optional[float]):
        super().__init__(f"429 rate limited (retry_after={retry_after})")
        self.retry_after = retry_after


class CapReached(Exception):
    pass


class UWClient:
    def __init__(self, cfg: dict, state: dict, opener: Optional[Callable] = None):
        self.cfg = cfg
        self.state = state
        self.opener = opener  # test hook: opener(path, params) -> parsed json
        self._last = 0.0

    def _count(self) -> None:
        today = datetime.now(PT).strftime("%Y-%m-%d")
        if self.state.get("calls_date") != today:
            self.state["calls_date"] = today
            self.state["calls_today"] = 0
        if self.state["calls_today"] >= int(self.cfg.get("daily_call_cap") or 6000):
            raise CapReached(f"daily_call_cap {self.cfg.get('daily_call_cap')} reached")
        self.state["calls_today"] += 1

    def get(self, path: str, params: Optional[dict] = None):
        self._count()
        gap = float(self.cfg.get("request_spacing_s") or 0) - (time.time() - self._last)
        if gap > 0 and self.opener is None:
            time.sleep(gap)
        self._last = time.time()
        if self.opener is not None:
            return self.opener(path, params or {})
        key = os.environ.get("UW_API_KEY")
        if not key:
            raise RuntimeError("UW_API_KEY not set")
        url = f"{API}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                                   "User-Agent": "oid-uw-refresh/1"})
        try:
            with urllib.request.urlopen(req, timeout=float(self.cfg.get("timeout_s") or 20)) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = _f(e.headers.get("Retry-After")) if e.headers else None
                raise RateLimited(ra) from None
            raise RuntimeError(f"HTTP {e.code} on {path}") from None  # never echo headers / key


def _rows(d) -> list:
    if isinstance(d, dict):
        return d.get("data") or []
    return d or []


# ---------------------------------------------------------------- builders
def build_market_tide(c: UWClient, sectors: list[str]) -> dict:
    series = [{"ts": r.get("timestamp"), "net_call_premium": _f(r.get("net_call_premium")),
               "net_put_premium": _f(r.get("net_put_premium")), "net_volume": r.get("net_volume")}
              for r in _rows(c.get("/market/market-tide", {"interval_5m": "true"}))]
    if not series:
        raise RuntimeError("market-tide returned no rows")
    ncp = [s["net_call_premium"] for s in series if s["net_call_premium"] is not None]
    last = series[-1]
    prev30 = series[-7] if len(series) >= 7 else series[0]
    out: dict[str, Any] = {
        "date": (last.get("ts") or "")[:10],
        "last": last,
        "chg_30m": {"net_call_premium": _diff(last, prev30, "net_call_premium"),
                    "net_put_premium": _diff(last, prev30, "net_put_premium")},
        "session_low_ncp": min(ncp) if ncp else None,
        "session_high_ncp": max(ncp) if ncp else None,
        "read": tide_read(last),
        "series_5m": series,
        "sectors": {},
    }
    for sec in sectors:
        try:
            rows = _rows(c.get(f"/market/{urllib.parse.quote(sec)}/sector-tide"))
        except (RateLimited, CapReached):
            raise
        except Exception as e:  # noqa: BLE001  one sector never kills the tide file
            out["sectors"][sec] = {"error": str(e)[:160]}
            continue
        if rows:
            r = rows[-1]
            out["sectors"][sec] = {"ts": r.get("timestamp"), "net_call_premium": _f(r.get("net_call_premium")),
                                   "net_put_premium": _f(r.get("net_put_premium")), "net_volume": r.get("net_volume"),
                                   "read": tide_read({"net_call_premium": _f(r.get("net_call_premium")),
                                                      "net_put_premium": _f(r.get("net_put_premium"))})}
    return out


def _diff(a: dict, b: dict, k: str) -> Optional[float]:
    if a.get(k) is None or b.get(k) is None:
        return None
    return round(a[k] - b[k], 2)


def tide_read(r: dict) -> str:
    c, p = r.get("net_call_premium"), r.get("net_put_premium")
    if c is None or p is None:
        return "n/a"
    spread = c - p
    lean = "bullish" if spread > 0 else "bearish" if spread < 0 else "flat"
    return f"{lean} lean: net call {c / 1e6:+.1f}M vs net put {p / 1e6:+.1f}M (call-put {spread / 1e6:+.1f}M)"


def summarize_ticks(rows: list[dict]) -> Optional[dict]:
    """Aggregate UW /stock/{T}/net-prem-ticks (per-minute) into day + last-15/30m net premium."""
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r.get("tape_time") or "")

    def agg(rs):
        return {
            "net_call_premium": round(sum(_f(r.get("net_call_premium")) or 0 for r in rs), 2),
            "net_put_premium": round(sum(_f(r.get("net_put_premium")) or 0 for r in rs), 2),
            "net_delta": round(sum(_f(r.get("net_delta")) or 0 for r in rs), 2),
        }

    last_t = rows[-1].get("tape_time")
    try:
        last_dt = datetime.fromisoformat(str(last_t).replace("Z", "+00:00"))
    except ValueError:
        last_dt = None

    def window(mins):
        if last_dt is None:
            return rows[-mins:]
        lo = last_dt - timedelta(minutes=mins)
        return [r for r in rows if (r.get("tape_time") and datetime.fromisoformat(r["tape_time"].replace("Z", "+00:00")) > lo)]

    day = agg(rows)
    day["call_volume"] = sum(int(r.get("call_volume") or 0) for r in rows)
    day["put_volume"] = sum(int(r.get("put_volume") or 0) for r in rows)
    out = {"date": rows[-1].get("date"), "last_tape_time": last_t, "minutes": len(rows), "day": day,
           "last_15m": agg(window(15)), "last_30m": agg(window(30))}
    cp = day["net_call_premium"] - day["net_put_premium"]
    out["read"] = ("bullish" if cp > 0 else "bearish" if cp < 0 else "flat") + f" day net (call-put) {cp / 1e6:+.2f}M"
    return out


def build_net_prem(c: UWClient, names: list[str]) -> tuple[dict, list[str]]:
    per: dict[str, Any] = {}
    errs: list[str] = []
    for t in names:
        if _stop:
            break
        try:
            s = summarize_ticks(_rows(c.get(f"/stock/{urllib.parse.quote(t)}/net-prem-ticks")))
        except (RateLimited, CapReached):
            raise
        except Exception as e:  # noqa: BLE001
            errs.append(f"{t}: {str(e)[:120]}")
            continue
        if s:
            per[t] = s
    return per, errs


ALERT_KEEP = ("id", "created_at", "ticker", "option_chain", "type", "strike", "expiry", "alert_rule", "total_premium",
              "total_ask_side_prem", "total_bid_side_prem", "total_size", "trade_count", "volume", "open_interest",
              "volume_oi_ratio", "price", "underlying_price", "has_sweep", "has_multileg", "has_singleleg",
              "all_opening_trades", "iv_start", "iv_end", "delta", "next_earnings_date", "bid", "ask")


def build_flow_alerts(c: UWClient, names: list[str], fa_cfg: dict, session_date_et: str) -> dict:
    etfs = set(fa_cfg.get("etfs") or [])
    chunk = int(fa_cfg.get("chunk") or 9)
    floor = f"{session_date_et}T13:00:00Z"  # 9:00 AM ET (covers pre-open prints, both DST regimes)
    groups = [([t for t in names if t in etfs], int(fa_cfg.get("etf_min_premium") or 500000))]
    rest = [t for t in names if t not in etfs]
    groups += [(rest[i:i + chunk], int(fa_cfg.get("min_premium") or 250000)) for i in range(0, len(rest), chunk)]
    alerts: dict[str, dict] = {}
    for g, mp in groups:
        if not g:
            continue
        lim = int(fa_cfg.get("limit") or 200)
        rows: list[dict] = []
        older = None
        for _ in range(int(fa_cfg.get("max_pages") or 4)):  # page back to the session floor when a group is busy
            p = {"ticker_symbol": ",".join(g), "min_premium": mp, "limit": lim, "newer_than": floor}
            if older:
                p["older_than"] = older
            page = _rows(c.get("/option-trades/flow-alerts", p))
            rows += page
            if len(page) < lim:
                break
            older = min(r.get("created_at") or "" for r in page) or None
            if not older:
                break
        for r in rows:
            if r.get("ticker") in g and r.get("id"):
                alerts[r["id"]] = {k: r.get(k) for k in ALERT_KEEP}
    allr = sorted(alerts.values(), key=lambda r: _f(r.get("total_premium")) or 0, reverse=True)
    by: dict[str, dict] = {}
    for r in allr:
        b = by.setdefault(r["ticker"], {"alerts": 0, "call_prem": 0.0, "put_prem": 0.0, "call_ask_prem": 0.0,
                                        "put_ask_prem": 0.0, "sweeps": 0, "top": None})
        prem = _f(r.get("total_premium")) or 0
        ask = _f(r.get("total_ask_side_prem")) or 0
        side = "call" if r.get("type") == "call" else "put"
        b["alerts"] += 1
        b[f"{side}_prem"] += prem
        b[f"{side}_ask_prem"] += ask
        b["sweeps"] += 1 if r.get("has_sweep") else 0
        if b["top"] is None:
            b["top"] = f"{r.get('option_chain')} {r.get('alert_rule')} ${prem / 1e6:.2f}M @ {r.get('created_at')}"
    for b in by.values():
        for k in ("call_prem", "put_prem", "call_ask_prem", "put_ask_prem"):
            b[k] = round(b[k], 2)
    return {"session_date": session_date_et, "count": len(allr), "by_ticker": by,
            "alerts": allr[: int(fa_cfg.get("keep_top") or 60)]}


def last_session_date_et(now: datetime) -> str:
    """ET date of the current/most recent RTH session (weekend -> Friday)."""
    try:
        sys.path.insert(0, str(OID / "paper-trades"))
        from market_session import prior_rth_close  # type: ignore
        if session_now(now) in ("rth", "ah"):
            return now.astimezone(ET).strftime("%Y-%m-%d")
        return prior_rth_close(now).strftime("%Y-%m-%d")
    except Exception:
        d = now.astimezone(ET).date()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()


# ---------------------------------------------------------------- cycle
def _carry(prev: Optional[dict], now: datetime, keys: tuple[str, ...]) -> dict:
    """Carry routine-written extras (same PT day, non-daemon writer) forward so the daemon doesn't erase them."""
    out: dict[str, Any] = {}
    if not prev or not isinstance(prev.get("payload"), dict):
        return out
    try:
        prev_day = datetime.fromisoformat(prev["as_of"].replace("Z", "+00:00")).astimezone(PT).date()
    except Exception:
        return out
    if prev_day != now.astimezone(PT).date():
        return out
    pp = prev["payload"]
    src = pp.get("routine_extras") if prev.get("writer") == WRITER else pp
    for k in keys:
        if isinstance(src, dict) and k in src and src[k]:
            out[k] = src[k]
    if out and prev.get("writer") != WRITER:
        out["from_writer"] = prev.get("writer")
        out["from_as_of_pt"] = prev.get("as_of_pt")
    elif out and isinstance(src, dict):
        out["from_writer"] = src.get("from_writer")
        out["from_as_of_pt"] = src.get("from_as_of_pt")
    return out


def run_cycle(c: UWClient, cfg: dict, *, now: Optional[datetime] = None, latest: Path = LATEST) -> dict:
    now = now or datetime.now(timezone.utc)
    names, focus = universe(cfg, now.timestamp())
    sess_date = last_session_date_et(now)
    res: dict[str, Any] = {"names": names, "focus": focus, "written": [], "errors": []}

    tide = None
    try:
        tide = build_market_tide(c, list(cfg.get("sectors") or []))
        prev = read_json(latest / "uw-market-tide.json")
        extras = _carry(prev, now, ("note",))
        if extras:
            tide["routine_extras"] = extras
        atomic_write_json(latest / "uw-market-tide.json", envelope(
            "uw-market-tide", now=now, symbols=["MARKET"] + list(tide["sectors"].keys()), payload=tide,
            source=f"Unusual Whales REST market-tide 5m + sector-tide ({', '.join(cfg.get('sectors') or [])}) {tide['date']}"))
        res["written"].append("uw-market-tide")
    except (RateLimited, CapReached):
        raise
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"market-tide: {str(e)[:160]}")

    per, errs = build_net_prem(c, names)
    res["errors"] += [f"net-prem {x}" for x in errs]
    if per:
        payload: dict[str, Any] = {"date": sess_date, "focus": focus, "per_ticker": per}
        if tide:
            payload["market_tide"] = {"at": tide["last"].get("ts"), "net_call_premium": tide["last"]["net_call_premium"],
                                      "net_put_premium": tide["last"]["net_put_premium"],
                                      "net_volume": tide["last"].get("net_volume"), "read": tide["read"]}
        prev = read_json(latest / "uw-net-prem.json")
        extras = _carry(prev, now, ("per_strike", "note"))
        if extras:
            payload["routine_extras"] = extras
            if "per_strike" in extras:
                payload["per_strike"] = extras["per_strike"]  # keep the key routines already read
        missing = [t for t in names if t not in per]
        if missing:
            payload["missing"] = missing
        atomic_write_json(latest / "uw-net-prem.json", envelope(
            "uw-net-prem", now=now, symbols=sorted(per.keys()), payload=payload,
            source=f"Unusual Whales REST net-prem-ticks (core-20 + focus, {len(per)} names) + market-tide {sess_date}"))
        res["written"].append("uw-net-prem")

    try:
        fa = build_flow_alerts(c, names, dict(cfg.get("flow_alerts") or {}), sess_date)
        fa["focus"] = focus
        atomic_write_json(latest / "uw-flow-alerts.json", envelope(
            "uw-flow-alerts", now=now, symbols=names, payload=fa,
            source=(f"Unusual Whales REST flow-alerts {sess_date} core-20 + focus, min_premium "
                    f"{cfg['flow_alerts'].get('min_premium')} (ETF {cfg['flow_alerts'].get('etf_min_premium')}), "
                    f"top {cfg['flow_alerts'].get('keep_top')} by premium")))
        res["written"].append("uw-flow-alerts")
    except (RateLimited, CapReached):
        raise
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"flow-alerts: {str(e)[:160]}")
    return res


# ---------------------------------------------------------------- daemon
def log(msg: str) -> None:
    print(f"{datetime.now(PT).strftime('%Y-%m-%d %-I:%M:%S %p PT')} {msg}", flush=True)


def _rotate_log() -> None:
    lp = OID / "cache" / "uw-refresh.log"
    try:
        if lp.stat().st_size > LOG_MAX_BYTES:
            lp.replace(lp.with_suffix(".log.1"))
    except OSError:
        pass


def write_status(st: dict, **kw) -> None:
    now = datetime.now(timezone.utc)
    st.update(kw)
    st["heartbeat_pt"] = pt_stamp(now)
    st["heartbeat_epoch"] = now.timestamp()
    st["pid"] = os.getpid()
    atomic_write_json(STATUS_PATH, st)


def do_cycle(state: dict, cfg: dict, tag: str) -> float:
    """Run one cycle; returns seconds to wait before the next one (backoff on 429)."""
    c = UWClient(cfg, state)
    t0 = time.time()
    calls0 = state.get("calls_today", 0)
    try:
        res = run_cycle(c, cfg)
        state["backoff_s"] = 0
        write_status(state, last_cycle_pt=pt_stamp(datetime.now(timezone.utc)), last_cycle_kind=tag,
                     last_written=res["written"], last_errors=res["errors"][:10], last_error=None,
                     last_cycle_s=round(time.time() - t0, 1), last_cycle_calls=state.get("calls_today", 0) - calls0,
                     names=res["names"], focus=res["focus"])
        log(f"{tag}: wrote {','.join(res['written']) or 'nothing'} names={len(res['names'])} "
            f"calls={state.get('calls_today', 0) - calls0} errs={len(res['errors'])} {time.time() - t0:.1f}s")
        return float(cfg.get("interval_s") or 240)
    except RateLimited as e:
        b = max(60.0, min(900.0, (state.get("backoff_s") or 30) * 2))
        if e.retry_after:
            b = max(b, float(e.retry_after))
        state["backoff_s"] = b
        write_status(state, last_error=f"429 rate limited; backing off {int(b)}s", rate_limited_pt=pt_stamp(datetime.now(timezone.utc)))
        log(f"{tag}: 429 from UW -> backing off {int(b)}s")
        return b
    except CapReached as e:
        write_status(state, last_error=str(e))
        log(f"{tag}: {e}; pausing until tomorrow")
        return 1800.0
    except Exception as e:  # noqa: BLE001
        write_status(state, last_error=str(e)[:200])
        log(f"{tag}: ERROR {str(e)[:200]}")
        return 120.0


def run() -> int:
    if not os.environ.get("UW_API_KEY"):
        log("UW_API_KEY not set in this environment; not starting")
        return 2
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    PIDF.write_text(str(os.getpid()))
    state = read_json(STATUS_PATH) or {}
    state.update({"started_pt": pt_stamp(datetime.now(timezone.utc)), "last_error": None, "backoff_s": 0})
    log(f"uw-refresh started pid={os.getpid()}")
    next_at = 0.0
    last_sess = None
    closing_done_for = None
    try:
        while not _stop:
            _rotate_log()
            cfg = load_cfg()
            now = datetime.now(timezone.utc)
            sess = session_now(now)
            today = now.astimezone(PT).strftime("%Y-%m-%d")
            if not cfg.get("enabled", True) or (OID / "cache" / "uw-refresh.disabled").exists():
                write_status(state, state="disabled")
            elif sess == "rth":
                if time.time() >= next_at:
                    next_at = time.time() + do_cycle(state, cfg, "rth")
                state["state"] = f"rth (every {int(cfg.get('interval_s') or 240)}s)"
                write_status(state)
            elif last_sess == "rth" or (sess == "ah" and closing_done_for != today and
                                        now.astimezone(ET).hour * 60 + now.astimezone(ET).minute < 16 * 60 + CLOSE_GRACE_MIN
                                        and state.get("last_cycle_pt", "")[:10] == today):
                if closing_done_for != today:
                    do_cycle(state, cfg, "closing")
                    closing_done_for = today
                write_status(state, state="idle (outside RTH; closing pull done)")
            else:
                write_status(state, state="idle (outside 6:30 AM-1:00 PM PT RTH)")
            last_sess = sess
            for _ in range(15):  # wake every 2s for stop, re-check schedule every ~30s
                if _stop:
                    break
                time.sleep(2)
    finally:
        try:
            if PIDF.read_text().strip() == str(os.getpid()):
                PIDF.unlink()
        except OSError:
            pass
        log("uw-refresh stopped")
    return 0


def once() -> int:
    state = read_json(STATUS_PATH) or {}
    cfg = load_cfg()
    wait = do_cycle(state, cfg, "once")
    print(json.dumps({k: state.get(k) for k in ("last_cycle_pt", "last_written", "last_errors", "last_error",
                                                 "last_cycle_calls", "calls_today", "focus")}, indent=1))
    return 0 if state.get("last_error") is None and wait != 120.0 else 1


def selftest() -> int:
    import tempfile
    tick = lambda t, c, p, d=0: {"date": "2026-10-09", "tape_time": t, "net_call_premium": str(c),  # noqa: E731
                                 "net_put_premium": str(p), "net_delta": str(d), "call_volume": 1, "put_volume": 1}

    def opener(path, params):
        if path == "/market/market-tide":
            return {"data": [{"timestamp": f"2026-10-09T15:{m:02d}:00-04:00", "net_call_premium": str(1e6 * m),
                              "net_put_premium": "-5e5", "net_volume": m} for m in range(0, 60, 5)]}
        if path.endswith("/sector-tide"):
            return {"data": [{"timestamp": "2026-10-09T20:54:00Z", "net_call_premium": "-2e8", "net_put_premium": "1e7", "net_volume": -5}]}
        if path.endswith("/net-prem-ticks"):
            if "/BAD/" in path:
                raise RuntimeError("HTTP 404")
            return {"data": [tick("2026-10-09T19:00:00Z", 100, 50), tick("2026-10-09T19:50:00Z", 200, -10),
                             tick("2026-10-09T19:59:00Z", 300, 0)]}
        if path == "/option-trades/flow-alerts":
            g = params["ticker_symbol"].split(",")
            return {"data": [{"id": f"a-{t}", "ticker": t, "type": "call", "total_premium": "1500000",
                              "total_ask_side_prem": "1000000", "option_chain": f"{t}261016C00100000",
                              "alert_rule": "RepeatedHits", "has_sweep": True, "created_at": "2026-10-09T17:00:00Z"} for t in g]}
        raise AssertionError(path)

    cfg = load_cfg()
    cfg.update({"include_core20": False, "include_focus": False, "extra_symbols": ["SPY", "NVDA", "BAD"]})
    st: dict = {}
    with tempfile.TemporaryDirectory() as td:
        latest = Path(td)
        seed = envelope("uw-net-prem", source="routine", symbols=["BE"], payload={"per_strike": {"BE": {"x": 1}}},
                        now=datetime.now(timezone.utc))
        seed["writer"] = "OID-Q5-TEST"
        atomic_write_json(latest / "uw-net-prem.json", seed)
        r = run_cycle(UWClient(cfg, st, opener=opener), cfg, latest=latest)
        assert set(r["written"]) == {"uw-market-tide", "uw-net-prem", "uw-flow-alerts"}, r
        np_ = read_json(latest / "uw-net-prem.json")
        assert np_["writer"] == WRITER and np_["ttl_seconds"] == 900 and np_["error"] is None
        assert np_["payload"]["per_ticker"]["NVDA"]["day"]["net_call_premium"] == 600
        assert np_["payload"]["per_ticker"]["NVDA"]["last_15m"]["net_call_premium"] == 500
        assert np_["payload"]["per_strike"] == {"BE": {"x": 1}}, "routine per_strike must carry"
        assert np_["payload"]["missing"] == ["BAD"]
        assert any("BAD" in e for e in r["errors"])
        mt = read_json(latest / "uw-market-tide.json")
        assert mt["payload"]["last"]["net_call_premium"] == 55e6 and "Technology" in mt["payload"]["sectors"]
        fa = read_json(latest / "uw-flow-alerts.json")
        assert fa["payload"]["count"] == 3 and fa["payload"]["by_ticker"]["SPY"]["sweeps"] == 1
        # second cycle keeps carried per_strike
        run_cycle(UWClient(cfg, st, opener=opener), cfg, latest=latest)
        assert read_json(latest / "uw-net-prem.json")["payload"]["per_strike"] == {"BE": {"x": 1}}
        # 429 propagates (daemon backs off) and does not overwrite good files
        before = (latest / "uw-market-tide.json").read_text()

        def limited(path, params):
            raise RateLimited(30)
        try:
            run_cycle(UWClient(cfg, st, opener=limited), cfg, latest=latest)
            raise AssertionError("429 should propagate")
        except RateLimited:
            pass
        assert (latest / "uw-market-tide.json").read_text() == before
        # daily cap
        cap = dict(cfg, daily_call_cap=2)
        try:
            run_cycle(UWClient(cap, {}, opener=opener), cap, latest=latest)
            raise AssertionError("cap should stop the cycle")
        except CapReached:
            pass
    print("uw_refresh selftest OK")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--once":
        sys.exit(once())
    if arg == "--selftest":
        sys.exit(selftest())
    sys.exit(run())
