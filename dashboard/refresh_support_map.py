#!/usr/bin/env python3
"""Put-wall distance for the support watch, reading Rose ``rh-quotes`` first.

Primary book: NVDA and the standing index / megacap wall names.
Extended book: the rest of the Tech∪chip union (37 names together).
``--equity-quotes-file`` fills cache misses only. ``--walls-file`` supplies
put walls already on disk (no FlashAlpha call). ``--dry-run`` and
``--check-piggyback`` do not write.

This builder never writes ``rh-quotes``. Research / paper only. Soft color.
Zero brokerage execution. A distance is not an elevate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard._cache import cache_io

# Standing structure names. NVDA is the support-watch primary.
PRIMARY_SUPPORT = (
    "NVDA",
    "SPY",
    "QQQ",
    "TSLA",
    "AMD",
    "MU",
    "AVGO",
    "META",
    "GOOG",
    "SMH",
)
# Tech∪chip union minus PRIMARY_SUPPORT. 10 + 27 = 37.
EXTENDED_SUPPORT = (
    "ADI",
    "AMZN",
    "ARM",
    "ASML",
    "BE",
    "COHR",
    "CRDO",
    "EWY",
    "GLW",
    "INTC",
    "INTU",
    "IREN",
    "KEYS",
    "KLAC",
    "LITE",
    "LRCX",
    "MH",
    "MRVL",
    "NBIS",
    "NFLX",
    "ORCL",
    "SKHY",
    "SNDK",
    "SPCX",
    "STX",
    "TSM",
    "WDC",
)
SUPPORT_SYMBOLS = PRIMARY_SUPPORT + EXTENDED_SUPPORT
FEED = "support-map"
TTL_SECONDS = 300
WRITER = "refresh_support_map.py"


def _io():
    return cache_io()


def load_quotes_file(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _io().extract_rh_quote_map(raw)


def load_walls(path) -> dict:
    if not path:
        return {}
    raw = _io().strip_secrets(json.loads(Path(path).read_text(encoding="utf-8")))
    if isinstance(raw, dict) and isinstance(raw.get("payload"), dict):
        payload = raw["payload"]
        raw = payload.get("walls", payload)
    if isinstance(raw, dict) and isinstance(raw.get("walls"), dict):
        raw = raw["walls"]
    walls = {}
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = []
        for key, value in raw.items():
            symbol = _io().normalize_symbol(key if isinstance(key, str) else "")
            if symbol and isinstance(value, dict):
                item = dict(value)
                item.setdefault("symbol", symbol)
                rows.append(item)
    else:
        rows = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = _io().normalize_symbol(item.get("symbol") or "")
        if symbol:
            walls[symbol] = item
    return walls


def put_wall_of(wall):
    if not isinstance(wall, dict):
        return None
    for key in ("put_wall", "put", "pw"):
        price = _io().to_float(wall.get(key))
        if price is not None:
            return price
    return None


def distance_to_put_wall(last, put_wall):
    if last is None or put_wall in (None, 0):
        return None
    return (last - put_wall) / put_wall


def resolve_quotes(equity_quotes_file=None, root=None, now=None):
    io = _io()
    piggy = io.piggyback_rh_quotes(SUPPORT_SYMBOLS, ttl=io.RH_QUOTES_TTL, root=root, now=now)
    quotes = dict(piggy["quotes"])
    missing = list(piggy["missing"])
    filled = []
    if equity_quotes_file and missing:
        file_map = load_quotes_file(equity_quotes_file)
        still_missing = []
        for symbol in missing:
            if symbol in file_map:
                quotes[symbol] = file_map[symbol]
                filled.append(symbol)
            else:
                still_missing.append(symbol)
        missing = still_missing
    return {
        "quotes": quotes,
        "missing": missing,
        "filled_from_file": filled,
        "piggyback": {
            "fresh": piggy["fresh"],
            "reason": piggy["reason"],
            "covered": list(piggy["covered"]),
            "missing": list(piggy["missing"]),
            "rh_quotes_write": False,
        },
    }


def build_payload(resolved, walls=None) -> dict:
    walls = walls or {}
    quotes = resolved["quotes"]
    covered = set(resolved["piggyback"]["covered"])
    filled = set(resolved["filled_from_file"])
    primary = set(PRIMARY_SUPPORT)
    rows = []
    for symbol in SUPPORT_SYMBOLS:
        quote = quotes.get(symbol)
        if symbol in covered:
            origin = "rh-quotes"
        elif symbol in filled:
            origin = "equity-quotes-file"
        else:
            origin = "missing"
        last = None if quote is None else quote.get("last")
        put_wall = put_wall_of(walls.get(symbol))
        rows.append({
            "symbol": symbol,
            "book": "primary" if symbol in primary else "extended",
            "last": last,
            "put_wall": put_wall,
            "distance": distance_to_put_wall(last, put_wall),
            "quote_from": origin,
            "soft_only": True,
            "elevate": False,
        })
    return {
        "rows": rows,
        "primary": list(PRIMARY_SUPPORT),
        "extended": list(EXTENDED_SUPPORT),
        "missing": list(resolved["missing"]),
        "filled_from_file": list(resolved["filled_from_file"]),
        "piggyback": resolved["piggyback"],
        "soft_only": True,
        "never_elevates": True,
        "rh_quotes_write": False,
        "execution": "none",
    }


def smoke(root=None, now=None) -> dict:
    piggy = resolve_quotes(root=root, now=now)["piggyback"]
    return {
        "ok": True,
        "feed": FEED,
        "fresh": piggy["fresh"],
        "reason": piggy["reason"],
        "covered": piggy["covered"],
        "missing": piggy["missing"],
        "rh_quotes_write": False,
        "execution": "none",
    }


def run(
    root=None,
    now=None,
    equity_quotes_file=None,
    walls_file=None,
    write=True,
    dry_run=False,
    check_piggyback=False,
):
    if check_piggyback:
        return smoke(root=root, now=now)
    resolved = resolve_quotes(equity_quotes_file=equity_quotes_file, root=root, now=now)
    payload = build_payload(resolved, load_walls(walls_file))
    if dry_run or not write:
        payload["written"] = False
        return payload
    _io().write_feed(
        FEED,
        payload,
        writer=WRITER,
        symbols=list(SUPPORT_SYMBOLS),
        ttl_seconds=TTL_SECONDS,
        source="rh-quotes piggyback",
        owner="rose",
        root=root,
        now=now,
    )
    payload["written"] = True
    return payload


def _blocked(argv) -> bool:
    for arg in argv:
        text = arg.lower()
        if any(token in text for token in ("place_", "cancel_", "exercise", "--order", "--submit")):
            return True
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if _blocked(argv):
        print("research/paper only; refresh_support_map does not submit brokerage orders", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Cache-first support map. Never writes rh-quotes.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--equity-quotes-file", default=None)
    parser.add_argument("--walls-file", default=None)
    parser.add_argument("--check-piggyback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run(
        root=args.root,
        equity_quotes_file=args.equity_quotes_file,
        walls_file=args.walls_file,
        write=not (args.dry_run or args.check_piggyback),
        dry_run=args.dry_run,
        check_piggyback=args.check_piggyback,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
