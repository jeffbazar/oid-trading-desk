#!/usr/bin/env python3
"""Mac mini quote-collector client (research / paper only — zero execution).

Primary 5-second equity quote source for the core-20 allowlist is the OID quote
collector on the Mac mini (``oid-mini`` on the tailnet). Robinhood (shared
``market-data/latest/rh-quotes.json``, Rose sole writer) stays the fallback.

Box reaches the mini through the userspace tailscaled outbound HTTP proxy
(localhost:1056); no extra Python deps (stdlib urllib only).

SECRETS: the Bearer token is read from ``OID_QUOTE_TOKEN_FILE`` (default
/home/box/tailscale/secrets/OID_QUOTE_TOKEN). It is never printed, logged,
returned, or written to any cache. Errors are scrubbed of headers.

Equities only. Live OPRA/option quotes never go to the public blotter.
Elevate / PAPER_CANDIDATE gates still require live RH <=120s quotes — this
module is a mark/tape source, not an elevate gate.

Public API
----------
fetch_mini(symbols)            -> raw fetch + normalize from the mini (no fallback)
get_quotes(symbols, ...)       -> mini-first, RH fallback per symbol (live fetch)
read_cache(symbols, ...)       -> fresh mini rows from cache/mini-quotes.json (no network)
overlay_rh_quotes(rh, ...)     -> overlay fresh mini fields onto RH-normalized rows
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "market-data"))
sys.path.insert(0, str(OID / "paper-trades"))

PT = ZoneInfo("America/Los_Angeles")

MINI_BASE_URL = os.environ.get("OID_MINI_URL", "http://100.106.118.33:8787")
# tailscaled --outbound-http-proxy-listen=localhost:1056 (userspace networking)
MINI_PROXY = os.environ.get("OID_MINI_PROXY", "http://localhost:1056")
TOKEN_FILE = Path(os.environ.get("OID_QUOTE_TOKEN_FILE", "/home/box/tailscale/secrets/OID_QUOTE_TOKEN"))
ALLOWLIST_PATH = OID / "config" / "stream-quote-allowlist.json"
CACHE_PATH = Path(os.environ.get("OID_MINI_CACHE", str(OID / "cache" / "mini-quotes.json")))

DEFAULT_TIMEOUT_S = 2.0
# Freshness windows by current_session(): quote/trade must be newer than this.
# "overnight" = Alpaca overnight feed window (8 PM-4 AM ET, Sun night -> Fri morning, trading nights only);
# the mini switches its single stock socket from SIP to v1beta1/overnight for it (collector v0.2.0).
MAX_AGE_S = {"rth": 15.0, "pre": 120.0, "ah": 120.0, "overnight": 120.0, "closed": 0.0}
# Cache file itself must have been written within this window to be trusted.
CACHE_MAX_FILE_AGE_S = 15.0

FALLBACK_SOURCE = "rh-quotes"
MINI_SOURCE = "mini"


# ---------------------------------------------------------------- helpers
def _f(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def _parse_ts(ts: Any) -> Optional[float]:
    """RFC-3339 (any fraction length, Z or offset) -> epoch seconds."""
    if not ts or not isinstance(ts, str):
        return None
    raw = ts.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    if "." in raw:
        head, _, tail = raw.partition(".")
        frac, rest = "", ""
        for i, ch in enumerate(tail):
            if ch.isdigit():
                frac += ch
            else:
                rest = tail[i:]
                break
        raw = f"{head}.{frac[:6].ljust(6, '0')}{rest}" if frac else f"{head}{rest}"
    try:
        d = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _pt_stamp(epoch: Optional[float] = None) -> str:
    d = datetime.fromtimestamp(time.time() if epoch is None else epoch, PT)
    return d.strftime("%Y-%m-%d %-I:%M:%S %p PT")


def overnight_active(when: Optional[datetime] = None) -> bool:
    """True inside the overnight window that precedes a trading day (ET wall clock).

    Evening half (>=20:00 ET) counts when the next calendar day is a trading day (Sun-Thu nights);
    morning half (<04:00 ET) counts when today is a trading day (Mon-Fri). NYSE holidays skipped.
    """
    from datetime import timedelta

    try:
        from market_session import NYSE_HOLIDAYS, now_et
    except Exception:  # pragma: no cover
        return False
    et = now_et(when)
    mins = et.hour * 60 + et.minute

    def trading(d) -> bool:
        return d.weekday() < 5 and d not in NYSE_HOLIDAYS

    if mins >= 20 * 60:
        return trading(et.date() + timedelta(days=1))
    if mins < 4 * 60:
        return trading(et.date())
    return False


def current_session(when: Optional[datetime] = None) -> str:
    """rth | pre | ah | overnight | closed. market_session() never returns overnight; this adds it."""
    try:
        from market_session import market_session

        sess = market_session(when)
    except Exception:  # pragma: no cover
        return "rth"
    if sess == "closed" and overnight_active(when):
        return "overnight"
    return sess


def max_age_for(session: Optional[str] = None) -> float:
    return MAX_AGE_S.get(session or current_session(), 15.0)


def core_symbols() -> list[str]:
    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        return [str(s).strip().upper() for s in data.get("underlyings") or [] if str(s).strip()]
    except (OSError, json.JSONDecodeError):
        return []


def _read_token() -> Optional[str]:
    try:
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return tok or None


class MiniError(Exception):
    """Scrubbed error (never carries the token)."""


# ---------------------------------------------------------------- transport
def _http_get_json(path: str, *, timeout: float, auth: bool, params: Optional[dict] = None,
                   opener: Optional[Callable[..., Any]] = None) -> tuple[int, Any, float]:
    """GET MINI_BASE_URL+path via the tailscale HTTP proxy. Returns (status, json, latency_ms)."""
    url = MINI_BASE_URL.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": "oid-mini-client/1.0"}
    if auth:
        tok = _read_token()
        if not tok:
            raise MiniError(f"token file missing/empty: {TOKEN_FILE}")
        headers["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(url, headers=headers, method="GET")
    if opener is None:
        handlers = [urllib.request.ProxyHandler({"http": MINI_PROXY} if MINI_PROXY else {})]
        opener = urllib.request.build_opener(*handlers).open
    t0 = time.monotonic()
    try:
        resp = opener(req, timeout=timeout)
        status = getattr(resp, "status", None) or resp.getcode()
        body = resp.read()
    except urllib.error.HTTPError as e:  # non-2xx
        lat = (time.monotonic() - t0) * 1000.0
        raise MiniError(f"HTTP {e.code} from mini {path} ({lat:.0f} ms)") from None
    except Exception as e:  # timeout / proxy down / tailnet down
        lat = (time.monotonic() - t0) * 1000.0
        raise MiniError(f"mini unreachable {path}: {type(e).__name__} ({lat:.0f} ms)") from None
    lat = (time.monotonic() - t0) * 1000.0
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise MiniError(f"bad JSON from mini {path}") from None
    return int(status), data, lat


def health(*, timeout: float = DEFAULT_TIMEOUT_S, opener=None) -> dict[str, Any]:
    status, data, lat = _http_get_json("/v1/health", timeout=timeout, auth=False, opener=opener)
    return {"http_status": status, "latency_ms": round(lat, 1), "health": data}


# ---------------------------------------------------------------- normalize
def normalize_row(sym: str, row: dict[str, Any], *, mini_as_of: Optional[float]) -> dict[str, Any]:
    """Collector cache view -> desk quote row. Ages are vs the mini's own clock at response time."""
    ref = mini_as_of if mini_as_of is not None else time.time()
    q_ts = _parse_ts(row.get("quote_observed_at"))
    t_ts = _parse_ts(row.get("trade_observed_at"))
    bid, ask, last = _f(row.get("bid")), _f(row.get("ask")), _f(row.get("last"))
    mid = round((bid + ask) / 2.0, 4) if bid and ask and ask >= bid else None
    quote_age = round(max(0.0, ref - q_ts), 3) if q_ts else None
    trade_age = round(max(0.0, ref - t_ts), 3) if t_ts else None
    ages = [a for a in (quote_age, trade_age) if a is not None]
    return {
        "symbol": sym,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": last,
        "bid_size": row.get("bid_size"),
        "ask_size": row.get("ask_size"),
        "last_size": row.get("last_size"),
        "quote_time": row.get("quote_observed_at"),
        "trade_time": row.get("trade_observed_at"),
        "quote_age_s": quote_age,
        "trade_age_s": trade_age,
        "age_s": min(ages) if ages else None,
        "feed": row.get("feed"),
        # sip | overnight (which collector socket wrote the newest field), plus per-channel tags
        "stream_feed": row.get("stream_feed") or ("overnight" if row.get("feed") == "alpaca-overnight" else
                                                  ("sip" if row.get("feed") == "alpaca-sip" else None)),
        "quote_feed": row.get("quote_feed"),
        "trade_feed": row.get("trade_feed"),
        "feed_status": row.get("feed_status"),
        "delayed": bool(row.get("delayed")),
        "collector_session": row.get("session"),
        "source": MINI_SOURCE,
    }


def classify(row: dict[str, Any], max_age_s: float) -> bool:
    """True when the mini row is usable as a fresh mark."""
    if not row or row.get("source") != MINI_SOURCE:
        return False
    if row.get("feed_status") != "ok" or row.get("delayed"):
        return False
    if max_age_s <= 0:
        return False
    age = row.get("age_s")
    if age is None or age > max_age_s:
        return False
    return row.get("last") is not None or row.get("mid") is not None


def fetch_mini(symbols: Optional[Iterable[str]] = None, *, timeout: float = DEFAULT_TIMEOUT_S,
               session: Optional[str] = None, opener=None) -> dict[str, Any]:
    """Fetch /v1/quotes from the mini. Never raises; returns {ok, quotes, fresh, stale, missing, ...}."""
    syms = [s.strip().upper() for s in (symbols or core_symbols()) if s and s.strip()]
    sess = session or current_session()
    max_age = max_age_for(sess)
    out: dict[str, Any] = {
        "ok": False, "http_status": None, "latency_ms": None, "error": None,
        "collector_status": None, "stocks_feed": None, "session": sess, "max_age_s": max_age,
        "quotes": {}, "fresh": [], "stale": [], "missing": list(syms), "fetched_at": time.time(),
    }
    try:
        status, data, lat = _http_get_json(
            "/v1/quotes", timeout=timeout, auth=True,
            params={"symbols": ",".join(syms)} if syms else None, opener=opener,
        )
    except MiniError as e:
        out["error"] = str(e)
        return out
    out["http_status"], out["latency_ms"] = status, round(lat, 1)
    if not isinstance(data, dict):
        out["error"] = "unexpected payload"
        return out
    out["ok"] = status == 200
    out["collector_status"] = data.get("status")
    feed = data.get("feed") or {}
    out["stocks_feed"] = {k: feed.get(k) for k in ("feed", "state", "connected", "fallback_active",
                                                   "subscribed_count", "last_data_age_s") if k in feed}
    mini_as_of = _parse_ts(data.get("as_of"))
    rows = data.get("quotes") or {}
    quotes: dict[str, dict] = {}
    for sym, row in rows.items():
        if isinstance(row, dict):
            quotes[str(sym).upper()] = normalize_row(str(sym).upper(), row, mini_as_of=mini_as_of)
    out["quotes"] = quotes
    out["fresh"] = [s for s in syms if s in quotes and classify(quotes[s], max_age)]
    out["stale"] = [s for s in syms if s in quotes and s not in out["fresh"]]
    out["missing"] = [s for s in syms if s not in quotes]
    return out


# ---------------------------------------------------------------- RH fallback
def rh_fallback(symbols: Iterable[str]) -> dict[str, Any]:
    """Shared RH quotes (Rose-written rh-quotes.json, TTL 120s) with trade-date stale guard."""
    syms = [s.upper() for s in symbols]
    if not syms:
        return {"fresh": False, "quotes": {}, "age_seconds": None, "as_of_pt": None}
    try:
        from cache_io import piggyback_rh_quotes
        from quote_freshness import EQUITY_TIME_KEYS, check_quotes
    except Exception as e:  # pragma: no cover
        return {"fresh": False, "quotes": {}, "error": f"import: {e}"}
    pb = piggyback_rh_quotes(syms)
    quotes = pb.get("quotes") or {}
    if quotes:
        quotes = check_quotes(quotes, EQUITY_TIME_KEYS)["fresh"]
    return {"fresh": bool(pb.get("fresh")), "quotes": quotes, "age_seconds": pb.get("age_seconds"),
            "as_of_pt": pb.get("as_of_pt")}


def _rh_row(sym: str, q: dict[str, Any], age: Optional[float]) -> dict[str, Any]:
    bid, ask = _f(q.get("bid")), _f(q.get("ask"))
    return {
        "symbol": sym,
        "bid": bid,
        "ask": ask,
        "mid": round((bid + ask) / 2.0, 4) if bid and ask and ask >= bid else None,
        "last": _f(q.get("last")),
        "last_non_reg": _f(q.get("last_non_reg")),
        "prev_close": _f(q.get("prev_close") or q.get("previous_close")),
        "trade_time": q.get("venue_last_trade_time") or q.get("last_trade_time"),
        "age_s": round(age, 1) if age is not None else None,
        "source": FALLBACK_SOURCE,
    }


def merge_with_fallback(symbols: list[str], mini: dict[str, Any], rh: Optional[dict[str, Any]] = None,
                        *, rh_loader: Callable[[list[str]], dict[str, Any]] = rh_fallback) -> dict[str, Any]:
    """Per symbol: fresh mini row, else fresh RH row, else source=None."""
    need = [s for s in symbols if s not in mini.get("fresh", [])]
    rh = rh if rh is not None else (rh_loader(need) if need else {"quotes": {}})
    rh_q = rh.get("quotes") or {}
    rh_age = rh.get("age_seconds")
    out: dict[str, dict] = {}
    for s in symbols:
        if s in mini.get("fresh", []):
            row = dict(mini["quotes"][s])
            row["fresh"] = True
        elif s in rh_q:
            row = _rh_row(s, rh_q[s], rh_age)
            row["fresh"] = True
            row["mini_reason"] = "stale" if s in mini.get("stale", []) else ("missing" if mini.get("ok") else "unreachable")
        else:
            row = {"symbol": s, "source": None, "fresh": False, "age_s": None,
                   "mini_reason": "stale" if s in mini.get("stale", []) else ("missing" if mini.get("ok") else "unreachable")}
        out[s] = row
    return {
        "quotes": out,
        "from_mini": [s for s in symbols if out[s].get("source") == MINI_SOURCE],
        "from_rh": [s for s in symbols if out[s].get("source") == FALLBACK_SOURCE],
        "unresolved": [s for s in symbols if out[s].get("source") is None],
        "rh_age_seconds": rh_age,
        "rh_as_of_pt": rh.get("as_of_pt"),
    }


def get_quotes(symbols: Optional[Iterable[str]] = None, *, timeout: float = DEFAULT_TIMEOUT_S,
               rh: Optional[dict[str, Any]] = None, session: Optional[str] = None, opener=None) -> dict[str, Any]:
    """Mini-first quotes with clean per-symbol RH fallback. Never raises.

    ``rh``: optional pre-loaded {"quotes": {SYM: rh_normalized}, "age_seconds": N}; default
    reads shared rh-quotes.json (no RH API call from here).
    """
    syms = [s.strip().upper() for s in (symbols or core_symbols()) if s and s.strip()]
    mini = fetch_mini(syms, timeout=timeout, session=session, opener=opener)
    merged = merge_with_fallback(syms, mini, rh)
    merged["mini"] = {k: mini[k] for k in ("ok", "http_status", "latency_ms", "error", "collector_status",
                                           "stocks_feed", "session", "max_age_s")}
    return merged


# ---------------------------------------------------------------- cache reader
def read_cache(symbols: Optional[Iterable[str]] = None, *, max_file_age_s: float = CACHE_MAX_FILE_AGE_S,
               max_age_s: Optional[float] = None, path: Optional[Path] = None,
               now: Optional[float] = None, include_fallback: bool = False) -> dict[str, Any]:
    """Read cache/mini-quotes.json written by mini_poller. No network.

    Returns {fresh_file, file_age_s, quotes: {SYM: row}} with only rows that are still fresh
    *now* (age re-computed = age_at_write + seconds since write). By default only
    source=="mini" rows; include_fallback=True also returns the poller's RH rows.
    """
    p = path or CACHE_PATH
    t = time.time() if now is None else now
    res: dict[str, Any] = {"fresh_file": False, "file_age_s": None, "quotes": {}, "path": str(p)}
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        res["error"] = "missing_or_unreadable"
        return res
    written = rec.get("written_epoch") or _parse_ts(rec.get("as_of"))
    if not written:
        res["error"] = "no_timestamp"
        return res
    file_age = max(0.0, t - float(written))
    res["file_age_s"] = round(file_age, 2)
    res["mini"] = rec.get("mini")
    if file_age > max_file_age_s:
        res["error"] = "cache_file_stale"
        return res
    res["fresh_file"] = True
    limit = max_age_s if max_age_s is not None else max_age_for()
    want = {s.upper() for s in symbols} if symbols else None
    for sym, row in (rec.get("quotes") or {}).items():
        if want is not None and sym not in want:
            continue
        if not isinstance(row, dict) or not row.get("fresh"):
            continue
        src = row.get("source")
        if src == MINI_SOURCE:
            age = row.get("age_s")
            if age is None or age + file_age > limit or limit <= 0:
                continue
        elif not (include_fallback and src == FALLBACK_SOURCE):
            continue
        r = dict(row)
        if r.get("age_s") is not None:
            r["age_s"] = round(float(r["age_s"]) + file_age, 2)
        res["quotes"][sym] = r
    return res


# ---------------------------------------------------------------- RH overlay
def overlay_rh_quotes(rh_quotes: dict[str, dict], *, session: Optional[str] = None,
                      mini_rows: Optional[dict[str, dict]] = None, max_age_s: Optional[float] = None) -> dict[str, Any]:
    """Overlay fresh mini fields onto RH-normalized equity rows (refresh_marks.normalize_equity_quotes shape).

    Only rows already present (and already through the RH trade-date stale guard) are touched,
    so prev_close always comes from RH. Per field:
      - bid/ask from mini when its quote age <= max_age
      - last (RTH) or last_non_reg (PRE/AH) from mini when its trade age <= max_age
      - CLOSED: no overlay (RH close is authoritative)
    Mutates rh_quotes in place; returns a summary.
    """
    sess = session or current_session()
    limit = max_age_s if max_age_s is not None else max_age_for(sess)
    summary: dict[str, Any] = {"session": sess, "max_age_s": limit, "overlaid": [], "skipped": None}
    if sess not in ("rth", "pre", "ah") or limit <= 0:
        summary["skipped"] = f"session={sess}"
        return summary
    if mini_rows is None:
        c = read_cache(list(rh_quotes.keys()), max_age_s=limit)
        summary["cache_file_age_s"] = c.get("file_age_s")
        if not c.get("fresh_file"):
            summary["skipped"] = c.get("error") or "cache_not_fresh"
            return summary
        mini_rows = c["quotes"]
    for sym, q in rh_quotes.items():
        m = mini_rows.get(sym)
        if not m or m.get("source") != MINI_SOURCE:
            continue
        touched = False
        qa = m.get("quote_age_s")
        if qa is not None and qa <= limit and m.get("bid") and m.get("ask"):
            q["bid"], q["ask"] = m["bid"], m["ask"]
            touched = True
        ta = m.get("trade_age_s")
        if ta is not None and ta <= limit and m.get("last") is not None:
            if sess == "rth":
                q["last"] = m["last"]
                q["last_trade_time"] = m.get("trade_time") or q.get("last_trade_time")
            else:
                q["last_non_reg"] = m["last"]
                q["last_non_reg_time"] = m.get("trade_time") or q.get("last_non_reg_time")
            touched = True
        if touched:
            q["mark_source"] = MINI_SOURCE
            q["mini_age_s"] = m.get("age_s")
            summary["overlaid"].append(sym)
    return summary


# ---------------------------------------------------------------- CLI
def _main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="OID mini quote client (no token output)")
    ap.add_argument("cmd", choices=["health", "quotes", "cache"])
    ap.add_argument("--symbols", default="", help="comma list (default core-20)")
    args = ap.parse_args(argv)
    syms = [s for s in args.symbols.split(",") if s.strip()] or None
    if args.cmd == "health":
        try:
            h = health()
        except MiniError as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1
        hh = h["health"]
        print(json.dumps({"ok": True, "http_status": h["http_status"], "latency_ms": h["latency_ms"],
                          "status": hh.get("status"), "stocks": (hh.get("stocks") or {}).get("state"),
                          "options": (hh.get("options") or {}).get("state")}))
        return 0
    if args.cmd == "quotes":
        print(json.dumps(get_quotes(syms), indent=2, default=str))
        return 0
    print(json.dumps(read_cache(syms, include_fallback=True), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
