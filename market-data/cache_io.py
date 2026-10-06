#!/usr/bin/env python3
"""Shared OID market-data cache I/O (read-before-pull / write-after-pull).

Research helpers only — no vendor calls. America/Los_Angeles for as_of_pt.
See QUERY-DEDUP.md for TTLs and owner matrix.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
MARKET_DATA_ROOT = Path(__file__).resolve().parent
LATEST_DIR = MARKET_DATA_ROOT / "latest"

# Default TTLs (seconds) — keep in sync with QUERY-DEDUP.md
DEFAULT_TTLS: dict[str, int] = {
    "fa-levels": 600,
    "fa-flow-levels": 600,
    "fa-soft": 1800,
    "uw-flow-alerts": 900,
    "uw-net-prem": 900,
    "uw-oe": 1800,
    "uw-form4": 21600,
    "rh-quotes": 120,
    "rh-rvol": 1800,
    "rh-option-marks": 300,
    "paper-open": 0,
    "market-tape": 300,
    "fidelity-three": 1800,
    "macro-spot": 300,
    "macro-morning": 21600,
    "fred-hy-oas": 86400,
    "fred-ig-oas": 86400,
}

# Elevate / PAPER_CANDIDATE must NOT use these feeds as live quote gates.
LIVE_QUOTE_GATE_FEEDS = frozenset({"rh-quotes", "rh-option-marks"})


def _feed_path(feed: str) -> Path:
    safe = feed.strip().replace("/", "-")
    return LATEST_DIR / f"{safe}.json"


def _parse_as_of(as_of: str) -> Optional[datetime]:
    if not as_of or not isinstance(as_of, str):
        return None
    s = as_of.strip()
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def format_as_of_pt(dt: Optional[datetime] = None) -> str:
    """Human PT stamp, e.g. '2026-09-17 10:10 AM PT'."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(PT)
    return local.strftime("%Y-%m-%d %I:%M %p PT").replace(" 0", " ", 1)


def age_seconds(feed: str, *, now: Optional[datetime] = None) -> Optional[float]:
    """Age of latest/{feed}.json in seconds, or None if missing/unparseable."""
    path = _feed_path(feed)
    if not path.is_file():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    as_of = _parse_as_of(rec.get("as_of") or "")
    if as_of is None:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now - as_of.astimezone(timezone.utc)).total_seconds())


def read_fresh(
    feed: str,
    ttl_seconds: Optional[int] = None,
    *,
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Return record dict if present, not expired, and error is null/empty; else None.

    ttl_seconds: override; default from record's ttl_seconds, else DEFAULT_TTLS[feed], else 600.
    """
    path = _feed_path(feed)
    if not path.is_file():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(rec, dict):
        return None
    err = rec.get("error")
    if err not in (None, "", False):
        return None
    as_of = _parse_as_of(rec.get("as_of") or "")
    if as_of is None:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ttl = ttl_seconds
    if ttl is None:
        ttl = rec.get("ttl_seconds")
    if ttl is None:
        ttl = DEFAULT_TTLS.get(feed, 600)
    try:
        ttl = int(ttl)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTLS.get(feed, 600)
    if ttl < 0:
        return None
    # paper-open / ttl 0: fresh only if written "on change" — treat age==0 window as
    # always requiring explicit ttl_seconds>0 from caller, or accept if age < 1s.
    age = (now - as_of.astimezone(timezone.utc)).total_seconds()
    if age < 0:
        age = 0.0
    if ttl == 0:
        # No automatic freshness window; caller must pass ttl_seconds to treat as fresh.
        if ttl_seconds is None:
            return None
        ttl = int(ttl_seconds)
    if age > ttl:
        return None
    return rec


def write_feed(
    feed: str,
    *,
    source: str,
    writer: str,
    symbols: list[str] | tuple[str, ...] | None,
    payload: Any,
    ttl_seconds: Optional[int] = None,
    error: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> dict[str, Any]:
    """Write latest/{feed}.json and return the record."""
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    as_of_utc = as_of.astimezone(timezone.utc)
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTLS.get(feed, 600)
    rec: dict[str, Any] = {
        "as_of": as_of_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of_pt": format_as_of_pt(as_of_utc),
        "source": source,
        "writer": writer,
        "feed": feed,
        "symbols": list(symbols) if symbols else [],
        "ttl_seconds": int(ttl),
        "payload": payload if payload is not None else {},
        "error": error,
    }
    path = _feed_path(feed)
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec


def _cli_get(feed: str) -> int:
    rec = read_fresh(feed)
    if rec is None:
        # Distinguish miss vs stale for operators
        path = _feed_path(feed)
        age = age_seconds(feed)
        if not path.is_file():
            print(json.dumps({"feed": feed, "status": "missing", "fresh": False}))
            return 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            err = raw.get("error")
        except (OSError, json.JSONDecodeError):
            err = "unreadable"
        status = "error" if err not in (None, "", False) else "stale"
        print(
            json.dumps(
                {
                    "feed": feed,
                    "status": status,
                    "fresh": False,
                    "age_seconds": age,
                    "error": err,
                }
            )
        )
        return 1
    out = {"feed": feed, "status": "fresh", "fresh": True, "age_seconds": age_seconds(feed)}
    out.update({k: rec[k] for k in ("as_of", "as_of_pt", "source", "writer", "ttl_seconds", "symbols") if k in rec})
    out["payload"] = rec.get("payload")
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _cli_age(feed: str) -> int:
    age = age_seconds(feed)
    path = _feed_path(feed)
    ttl = DEFAULT_TTLS.get(feed)
    rec_ttl = None
    if path.is_file():
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            rec_ttl = rec.get("ttl_seconds")
            ttl = rec_ttl if rec_ttl is not None else ttl
        except (OSError, json.JSONDecodeError):
            pass
    fresh = False
    if age is not None and ttl is not None and int(ttl) > 0:
        fresh = age <= int(ttl) and read_fresh(feed) is not None
    print(
        json.dumps(
            {
                "feed": feed,
                "exists": path.is_file(),
                "age_seconds": age,
                "ttl_seconds": ttl,
                "fresh": fresh,
            }
        )
    )
    return 0 if path.is_file() else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OID market-data cache helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    get_p = sub.add_parser("get", help="Print fresh record JSON or status if miss/stale")
    get_p.add_argument("feed")
    age_p = sub.add_parser("age", help="Print age / TTL / fresh flag")
    age_p.add_argument("feed")
    args = parser.parse_args(argv)
    if args.cmd == "get":
        return _cli_get(args.feed)
    if args.cmd == "age":
        return _cli_age(args.feed)
    parser.error(f"unknown cmd {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())


# --- RH quotes piggyback (Duplicates #2) --------------------------------------
# support-map + market-tape read shared rh-quotes first (TTL ~120s).
# Rose (refresh_marks.py / live_refresh.py) remains sole writer of rh-quotes.
# Hal / readers never write this feed.


def extract_rh_quote_map(payload: Any) -> dict[str, dict[str, Any]]:
    """Normalize rh-quotes payload → SYMBOL → quote fields.

    Accepts:
      - cache payload: {"quotes": {SYM: {...}}, "count": N, ...}
      - bare {SYM: {...}} map
      - raw RH get_equity_quotes shapes (best-effort; prefer refresh_marks.normalize)
    """
    if not payload:
        return {}
    if isinstance(payload, dict):
        inner = payload.get("quotes")
        if isinstance(inner, dict) and inner:
            sample = next(iter(inner.values()), None)
            if isinstance(sample, dict):
                payload = inner
        # else fall through — may already be SYM→quote
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return out
    skip = {
        "results", "quotes", "data", "instruments", "closes",
        "closes_error", "error", "meta", "guide", "as_of_pt",
        "source", "delayed", "quote_label", "session", "count",
    }
    for sym, q in payload.items():
        if sym in skip or not isinstance(q, dict):
            continue
        s = str(sym).strip().upper()
        if not s or len(s) > 12:
            continue
        # Must look like a quote row
        if not any(
            k in q
            for k in (
                "last", "last_trade_price", "previous_close", "prev",
                "prev_close", "adjusted_previous_close", "bid", "ask",
                "last_non_reg", "last_non_reg_trade_price",
            )
        ):
            continue

        def _f(x: Any) -> Optional[float]:
            if x is None or x == "":
                return None
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        last = _f(q.get("last_trade_price")) or _f(q.get("last")) or _f(q.get("price"))
        last_non_reg = (
            _f(q.get("last_non_reg_trade_price"))
            or _f(q.get("last_non_reg"))
            or _f(q.get("lastNonReg"))
        )
        prev = (
            _f(q.get("adjusted_previous_close"))
            or _f(q.get("previous_close"))
            or _f(q.get("prev_close"))
            or _f(q.get("prev"))
        )
        out[s] = {
            "last": last,
            "last_non_reg": last_non_reg,
            "prev_close": prev,
            "previous_close": prev,
            "bid": _f(q.get("bid_price")) or _f(q.get("bid")),
            "ask": _f(q.get("ask_price")) or _f(q.get("ask")),
            "last_trade_time": q.get("venue_last_trade_time") or q.get("last_trade_time") or q.get("updated_at"),
            "last_non_reg_time": q.get("venue_last_non_reg_trade_time") or q.get("last_non_reg_time"),
            "venue_last_trade_time": q.get("venue_last_trade_time") or q.get("last_trade_time"),
            "venue_last_non_reg_trade_time": q.get("venue_last_non_reg_trade_time") or q.get("last_non_reg_time"),
            "state": q.get("state"),
            "delayed": q.get("delayed"),
            "quote_label": q.get("quote_label"),
        }
    return out


def piggyback_rh_quotes(
    symbols: list[str] | tuple[str, ...] | None = None,
    *,
    ttl_seconds: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Read fresh shared rh-quotes and return covered marks for ``symbols``.

    Returns dict with:
      fresh, record, quotes, covered, missing, age_seconds, as_of_pt, writer, ttl_seconds

    - If cache miss/stale/error → fresh=False, missing=all requested (or []).
    - Covered symbols are reused; missing are names not present in the fresh map
      (Rose may pull only those — Hal must not write rh-quotes).
    - Elevate / PAPER_CANDIDATE still requires live RH ≤120s (never this helper alone).
    """
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTLS.get("rh-quotes", 120)
    wanted = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]
    rec = read_fresh("rh-quotes", ttl_seconds=ttl, now=now)
    age = age_seconds("rh-quotes", now=now)
    if rec is None:
        return {
            "fresh": False,
            "record": None,
            "quotes": {},
            "covered": [],
            "missing": list(wanted),
            "age_seconds": age,
            "as_of_pt": None,
            "writer": None,
            "ttl_seconds": ttl,
            "reused": False,
        }
    qmap = extract_rh_quote_map(rec.get("payload"))
    if not wanted:
        covered = sorted(qmap.keys())
        missing: list[str] = []
        quotes = dict(qmap)
    else:
        covered = [s for s in wanted if s in qmap]
        missing = [s for s in wanted if s not in qmap]
        quotes = {s: qmap[s] for s in covered}
    return {
        "fresh": True,
        "record": rec,
        "quotes": quotes,
        "covered": covered,
        "missing": missing,
        "age_seconds": age,
        "as_of_pt": rec.get("as_of_pt"),
        "writer": rec.get("writer"),
        "ttl_seconds": rec.get("ttl_seconds") if rec.get("ttl_seconds") is not None else ttl,
        "reused": bool(covered),
    }
