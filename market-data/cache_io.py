#!/usr/bin/env python3
"""Shared latest-cache helper for the OID desk.

Research / paper only. One owner writes ``market-data/latest/{feed}.json``.
Everyone else reads. ``rh-quotes`` has a single writer: ``refresh_marks.py``
(owner ``rose``, TTL 120s). ``piggyback_rh_quotes`` only reads that file.

This module does not call Robinhood and does not place, cancel, or exercise orders.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RH_QUOTES_FEED = "rh-quotes"
RH_QUOTES_TTL = 120
RH_QUOTES_WRITER = "refresh_marks.py"
RH_QUOTES_OWNER = "rose"

PT = ZoneInfo("America/Los_Angeles")
_FEED_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_PRICE_KEYS = (
    "last_trade_price",
    "last",
    "last_price",
    "mark_price",
    "mark",
    "price",
)
_SECRET_KEYS = frozenset({
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "account_number",
    "cookie",
    "client_secret",
})
_NEST_KEYS = ("quotes", "results", "data", "equity_quotes", "equityQuotes", "payload")


def desk_root(root=None) -> Path:
    if root is not None:
        return Path(root).resolve()
    env = os.environ.get("OID_DESK_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def latest_dir(root=None) -> Path:
    return desk_root(root) / "market-data" / "latest"


def _validate_feed(feed: str) -> str:
    name = str(feed or "").strip()
    if not _FEED_RE.fullmatch(name):
        raise ValueError(f"invalid feed name: {feed!r}")
    return name


def feed_path(feed: str, root=None) -> Path:
    return latest_dir(root) / f"{_validate_feed(feed)}.json"


def normalize_symbol(value) -> str | None:
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def _secret_key(key) -> bool:
    return str(key).lower().replace("-", "_") in _SECRET_KEYS


def strip_secrets(value):
    """Drop credential-shaped keys before anything is written or returned."""
    if isinstance(value, dict):
        return {
            key: strip_secrets(item)
            for key, item in value.items()
            if not _secret_key(key)
        }
    if isinstance(value, list):
        return [strip_secrets(item) for item in value]
    return value


def to_float(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if text in {"", "—", "-", "null", "None"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _aware(now=None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso_z(moment: datetime) -> str:
    return _aware(moment).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_pt(moment: datetime) -> str:
    local = _aware(moment).astimezone(PT)
    hour = str(int(local.strftime("%I")))
    return local.strftime(f"%Y-%m-%d {hour}:%M %p PT")


def parse_as_of(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _error_set(record) -> bool:
    if not isinstance(record, dict):
        return False
    error = record.get("error")
    return error is not None and error != ""


def is_fresh(record, ttl=None, now=None) -> bool:
    """True when ``as_of`` is within TTL and ``error`` is not set."""
    if not isinstance(record, dict) or _error_set(record):
        return False
    as_of = parse_as_of(record.get("as_of"))
    if as_of is None:
        return False
    limit = record.get("ttl_seconds") if ttl is None else ttl
    limit_n = to_float(limit)
    if limit_n is None or limit_n < 0:
        return False
    age = (_aware(now) - as_of).total_seconds()
    if age < -5:
        return False
    if age < 0:
        age = 0
    return age <= limit_n


def read_record(feed: str, root=None):
    path = feed_path(feed, root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return strip_secrets(data)


def read_fresh(feed: str, ttl=None, root=None, now=None):
    """Return the record when it is inside TTL. Otherwise return None."""
    record = read_record(feed, root=root)
    if record is None:
        return None
    use_ttl = record.get("ttl_seconds") if ttl is None else ttl
    if not is_fresh(record, ttl=use_ttl, now=now):
        return None
    return record


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_feed(
    feed,
    payload,
    *,
    writer,
    symbols=None,
    ttl_seconds=None,
    source="",
    error=None,
    owner=None,
    root=None,
    now=None,
):
    """Write one latest envelope. ``rh-quotes`` rejects every writer except Rose."""
    name = _validate_feed(feed)
    if name == RH_QUOTES_FEED and (writer != RH_QUOTES_WRITER or owner != RH_QUOTES_OWNER):
        raise PermissionError(
            "rh-quotes sole writer is refresh_marks.py (owner rose); "
            f"refusing writer={writer!r} owner={owner!r}"
        )
    body = strip_secrets(payload if payload is not None else {})
    moment = _aware(now)
    if symbols is None:
        quotes = body.get("quotes") if isinstance(body, dict) else None
        symbols = sorted(quotes) if isinstance(quotes, dict) else []
    record = {
        "as_of": _iso_z(moment),
        "as_of_pt": format_pt(moment),
        "source": source or "",
        "writer": writer,
        "feed": name,
        "symbols": list(symbols),
        "ttl_seconds": int(ttl_seconds if ttl_seconds is not None else 0),
        "payload": body,
        "error": error,
    }
    if owner is not None:
        record["owner"] = owner
    _atomic_write(feed_path(name, root), json.dumps(record, indent=2) + "\n")
    return record


def _looks_like_quote(raw) -> bool:
    return isinstance(raw, dict) and any(key in raw for key in _PRICE_KEYS)


def normalize_quote(symbol: str, raw) -> dict:
    source = strip_secrets(raw if isinstance(raw, dict) else {})
    last = None
    for key in _PRICE_KEYS:
        last = to_float(source.get(key))
        if last is not None:
            break
    previous = to_float(source.get("adjusted_previous_close"))
    if previous is None:
        previous = to_float(source.get("previous_close"))
    quote = dict(source)
    quote["symbol"] = symbol
    if last is not None:
        quote["last"] = last
    if last is not None and previous not in (None, 0):
        quote["day_pct"] = (last - previous) / previous * 100.0
    return quote


def _map_from_list(items) -> dict:
    found = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = normalize_symbol(item.get("symbol") or item.get("ticker") or "")
        if symbol is None:
            continue
        found[symbol] = normalize_quote(symbol, item)
    return found


def extract_rh_quote_map(record, _depth: int = 0) -> dict:
    """Unwrap an rh-quotes envelope, a Robinhood results list, or a symbol map.

    Accepted shapes include ``payload.quotes``, ``{results: [...]}``,
    ``{quotes: {SYM: quote}}``, and one extra ``payload`` / ``data`` wrap.
    """
    if _depth > 5 or record is None:
        return {}
    record = strip_secrets(record)
    if isinstance(record, list):
        return _map_from_list(record)
    if not isinstance(record, dict):
        return {}
    for key in _NEST_KEYS:
        if key not in record:
            continue
        found = extract_rh_quote_map(record.get(key), _depth + 1)
        if found:
            return found
    symbol = normalize_symbol(record.get("symbol") or record.get("ticker") or "")
    if symbol and _looks_like_quote(record):
        return {symbol: normalize_quote(symbol, record)}
    mapped = {}
    for key, value in record.items():
        sym = normalize_symbol(key if isinstance(key, str) else "")
        if sym is None or not isinstance(value, dict):
            return {}
        mapped[sym] = normalize_quote(sym, value)
    return mapped


def _piggyback_shell(symbols, *, fresh, reason, record):
    return {
        "fresh": fresh,
        "reason": reason,
        "record": record,
        "quotes": {},
        "covered": [],
        "missing": list(symbols),
        "rh_quotes_write": False,
    }


def piggyback_rh_quotes(symbols, ttl=RH_QUOTES_TTL, root=None, now=None) -> dict:
    """Reuse a fresh ``rh-quotes`` file. Never writes that file.

    Covered symbols are returned from the cache. Missing, stale, or error
    results leave those symbols in ``missing`` so Rose can refresh once and
    the caller can rerun. This function does not call ``get_equity_quotes``.
    """
    wanted = []
    seen = set()
    for symbol in symbols:
        normalized = normalize_symbol(symbol if isinstance(symbol, str) else "")
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        wanted.append(normalized)
    record = read_record(RH_QUOTES_FEED, root=root)
    if record is None:
        return _piggyback_shell(wanted, fresh=False, reason="miss", record=None)
    if _error_set(record):
        return _piggyback_shell(wanted, fresh=False, reason="error", record=record)
    limit = RH_QUOTES_TTL if ttl is None else ttl
    if not is_fresh(record, ttl=limit, now=now):
        return _piggyback_shell(wanted, fresh=False, reason="stale", record=record)
    quote_map = extract_rh_quote_map(record)
    quotes = {}
    covered = []
    missing = []
    for symbol in wanted:
        if symbol in quote_map:
            quotes[symbol] = quote_map[symbol]
            covered.append(symbol)
        else:
            missing.append(symbol)
    return {
        "fresh": True,
        "reason": "fresh",
        "record": record,
        "quotes": quotes,
        "covered": covered,
        "missing": missing,
        "rh_quotes_write": False,
    }


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read a latest-cache feed. Does not call a vendor or write rh-quotes."
    )
    parser.add_argument("command", choices=["get"])
    parser.add_argument("feed")
    parser.add_argument("--ttl", type=float, default=None)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    record = read_record(args.feed, root=args.root)
    if record is None:
        _print_json({"fresh": False, "reason": "miss", "feed": args.feed})
        return 0
    if _error_set(record):
        _print_json({"fresh": False, "reason": "error", "feed": args.feed})
        return 0
    limit = record.get("ttl_seconds") if args.ttl is None else args.ttl
    fresh = is_fresh(record, ttl=limit)
    reason = "fresh" if fresh else "stale"
    body = {"fresh": fresh, "reason": reason, "feed": args.feed}
    if fresh:
        body["writer"] = record.get("writer")
        body["symbols"] = record.get("symbols")
        body["ttl_seconds"] = record.get("ttl_seconds")
    _print_json(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
