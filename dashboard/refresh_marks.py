#!/usr/bin/env python3
"""Sole writer of ``market-data/latest/rh-quotes.json``.

Unwrap a local equity-quotes file (envelope, ``{quotes: ...}``, ``{results: [...]}``,
or a bare list) and write the Rose envelope: writer ``refresh_marks.py``,
owner ``rose``, TTL 120s.

This packaged entry point does not call Robinhood. On the box, Rose pulls
``get_equity_quotes`` for symbols that were missing from a fresh file, writes
that response to a local file, and passes it here. Elevate / invalidate quotes
are a separate live read and are never served from this cache.

Research / paper only. Zero brokerage execution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard._cache import cache_io

WRITER = "refresh_marks.py"
OWNER = "rose"
TTL_SECONDS = 120


def _io():
    return cache_io()


def unwrap_equity_quotes(raw) -> dict:
    """Return a symbol → quote map from the shapes Rose's quote file may use."""
    return _io().extract_rh_quote_map(raw)


def write_rh_quotes(quotes, *, source, root=None, now=None, error=None):
    payload = {"quotes": quotes}
    return _io().write_feed(
        "rh-quotes",
        payload,
        writer=WRITER,
        owner=OWNER,
        symbols=sorted(quotes),
        ttl_seconds=TTL_SECONDS,
        source=source or "equity-quotes-file",
        error=error,
        root=root,
        now=now,
    )


def write_from_file(path, root=None, now=None, dry_run=False):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    source = "equity-quotes-file"
    if isinstance(raw, dict) and isinstance(raw.get("source"), str) and raw.get("source").strip():
        source = raw["source"].strip()
    quotes = unwrap_equity_quotes(raw)
    if dry_run:
        return {
            "dry_run": True,
            "writer": WRITER,
            "owner": OWNER,
            "ttl_seconds": TTL_SECONDS,
            "symbols": sorted(quotes),
            "quotes": quotes,
            "rh_quotes_write": False,
            "execution": "none",
        }
    if not quotes:
        record = write_rh_quotes(
            {},
            source=source,
            root=root,
            now=now,
            error="empty equity quotes file",
        )
    else:
        record = write_rh_quotes(quotes, source=source, root=root, now=now)
    record["execution"] = "none"
    return record


def _blocked(argv) -> bool:
    for arg in argv:
        text = arg.lower()
        if any(token in text for token in ("place_", "cancel_", "exercise", "--order", "--submit")):
            return True
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if _blocked(argv):
        print("research/paper only; refresh_marks does not submit brokerage orders", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Rose rh-quotes writer. Unwrap a local quotes file.")
    parser.add_argument("--equity-quotes-file", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = write_from_file(args.equity_quotes_file, root=args.root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
