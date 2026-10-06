#!/usr/bin/env python3
"""Single publisher loop's cache-first tape step.

Order is fixed: read ``rh-quotes`` and build ``market-tape`` before any other
work. This package does not call Robinhood, does not write ``rh-quotes``, and
does not publish. Production publish stays ``dashboard/publish.sh`` on the box
to https://bold-tulip-nejq.here.now/ (swift-dune is review-only).

Research / paper only. Zero brokerage execution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import refresh_market_tape, refresh_support_map

PUBLISH_SLUG = "bold-tulip-nejq"
REVIEW_SLUG = "swift-dune-cs3e"


def run_cache_first(
    root=None,
    now=None,
    equity_quotes_file=None,
    with_support=False,
    walls_file=None,
    write=True,
    publish=False,
):
    if publish:
        raise RuntimeError(
            "this package does not publish and does not call here.now; "
            f"production publish is dashboard/publish.sh on the box to {PUBLISH_SLUG}"
        )
    steps = ["market-tape-piggyback"]
    tape = refresh_market_tape.run(
        root=root,
        now=now,
        equity_quotes_file=equity_quotes_file,
        write=write,
    )
    support = None
    if with_support:
        steps.append("support-map-piggyback")
        support = refresh_support_map.run(
            root=root,
            now=now,
            equity_quotes_file=equity_quotes_file,
            walls_file=walls_file,
            write=write,
        )
    return {
        "steps": steps,
        "tape": tape,
        "support": support,
        "quote_pulls": [],
        "rh_quotes_written": False,
        "published": False,
        "publish_slug": PUBLISH_SLUG,
        "execution": "none",
    }


def _blocked(argv) -> bool:
    for arg in argv:
        text = arg.lower()
        if any(token in text for token in ("place_", "cancel_", "exercise", "--order", "--submit")):
            return True
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if _blocked(argv):
        print("research/paper only; live_refresh does not submit brokerage orders", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Tape cache-first refresh. Does not write rh-quotes.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--equity-quotes-file", default=None)
    parser.add_argument("--walls-file", default=None)
    parser.add_argument("--with-support", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-piggyback", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if args.check_piggyback:
        result = refresh_market_tape.smoke(root=args.root)
        result["steps"] = ["market-tape-piggyback"]
        print(json.dumps(result, indent=2))
        return 0
    try:
        result = run_cache_first(
            root=args.root,
            equity_quotes_file=args.equity_quotes_file,
            with_support=args.with_support,
            walls_file=args.walls_file,
            write=not args.dry_run,
            publish=args.publish,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
