#!/usr/bin/env python3
"""Build the market-tape strip from a fresh Rose ``rh-quotes`` cache.

Default symbols: SPY, QQQ, DIA on the strip, plus RSP, VTV, VUG helpers.
``--equity-quotes-file`` fills cache misses only. ``--check-piggyback`` is a
smoke read. This builder never writes ``rh-quotes`` and never calls Robinhood.

Research / paper only. Soft color. Zero brokerage execution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard._cache import cache_io

TAPE_STRIP = ("SPY", "QQQ", "DIA")
TAPE_HELPERS = ("RSP", "VTV", "VUG")
TAPE_SYMBOLS = TAPE_STRIP + TAPE_HELPERS
FEED = "market-tape"
TTL_SECONDS = 300
WRITER = "refresh_market_tape.py"


def _io():
    return cache_io()


def load_quotes_file(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _io().extract_rh_quote_map(raw)


def resolve_quotes(symbols=TAPE_SYMBOLS, equity_quotes_file=None, root=None, now=None):
    """Cache first. A local quotes file is consulted only for symbols still missing."""
    io = _io()
    piggy = io.piggyback_rh_quotes(symbols, ttl=io.RH_QUOTES_TTL, root=root, now=now)
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


def _row(symbol, quote, origin):
    if quote is None or origin == "missing":
        return {"symbol": symbol, "last": None, "day_pct": None, "from": "missing"}
    return {
        "symbol": symbol,
        "last": quote.get("last"),
        "day_pct": quote.get("day_pct"),
        "from": origin,
    }


def build_payload(resolved) -> dict:
    quotes = resolved["quotes"]
    covered = set(resolved["piggyback"]["covered"])
    filled = set(resolved["filled_from_file"])

    def origin(symbol):
        if symbol in covered:
            return "rh-quotes"
        if symbol in filled:
            return "equity-quotes-file"
        return "missing"

    return {
        "strip": [_row(symbol, quotes.get(symbol), origin(symbol)) for symbol in TAPE_STRIP],
        "helpers": [_row(symbol, quotes.get(symbol), origin(symbol)) for symbol in TAPE_HELPERS],
        "missing": list(resolved["missing"]),
        "filled_from_file": list(resolved["filled_from_file"]),
        "piggyback": resolved["piggyback"],
        "soft_only": True,
        "never_elevates": True,
        "rh_quotes_write": False,
        "execution": "none",
    }


def smoke(root=None, now=None) -> dict:
    resolved = resolve_quotes(root=root, now=now)
    piggy = resolved["piggyback"]
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


def run(root=None, now=None, equity_quotes_file=None, write=True, dry_run=False, check_piggyback=False):
    if check_piggyback:
        return smoke(root=root, now=now)
    resolved = resolve_quotes(
        equity_quotes_file=equity_quotes_file,
        root=root,
        now=now,
    )
    payload = build_payload(resolved)
    if dry_run or not write:
        payload["written"] = False
        return payload
    _io().write_feed(
        FEED,
        payload,
        writer=WRITER,
        symbols=list(TAPE_SYMBOLS),
        ttl_seconds=TTL_SECONDS,
        source="rh-quotes piggyback",
        owner="shared",
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
        print("research/paper only; refresh_market_tape does not submit brokerage orders", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Cache-first market tape. Never writes rh-quotes.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--equity-quotes-file", default=None)
    parser.add_argument("--check-piggyback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run(
        root=args.root,
        equity_quotes_file=args.equity_quotes_file,
        write=not (args.dry_run or args.check_piggyback),
        dry_run=args.dry_run,
        check_piggyback=args.check_piggyback,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
