#!/usr/bin/env python3
"""OID Live Book refresh orchestrator (research / paper only).

Typical agent flow (executor has Robinhood MCP):
  1) python3 live_refresh.py --emit-ids
  2) MCP get_option_quotes → save JSON
  3) python3 live_refresh.py --emit-symbols   # open seats + market-tape + Shay watch symbols
  4) MCP get_equity_quotes → save JSON
  5) python3 live_refresh.py --quotes-file opt.json --equity-quotes-file eq.json --publish

Equity-only (weekend / CLOSED):
  python3 live_refresh.py --equity-quotes-file eq.json --publish

Steps: apply marks/equity → market-tape/Fidelity-3 → close_triggers → scorecard → rebuild → optional publish.
Never places RH orders.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def _abs(path: Path | None) -> Path | None:
    """Resolve quote file paths against repo root (cwd is dashboard/)."""
    if path is None:
        return None
    path = Path(path)
    if path.is_absolute():
        return path
    # Prefer repo-root relative (tmp/...), then cwd, then dashboard/
    for base in (REPO, Path.cwd(), ROOT):
        cand = (base / path).resolve()
        if cand.exists():
            return cand
    return (REPO / path).resolve()


PT = ROOT.parent / "paper-trades"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, cwd=str(ROOT), check=check)


def _merged_symbols() -> int:
    """Print unique open-seat + Shay watch + market-tape symbols for get_equity_quotes."""
    import json
    refresh = ROOT / "refresh_marks.py"
    tape = ROOT / "refresh_market_tape.py"
    r1 = subprocess.run(
        [sys.executable, str(refresh), "--list-symbols"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if r1.returncode != 0:
        print(r1.stderr, file=sys.stderr)
        return r1.returncode or 1
    r2 = subprocess.run(
        [sys.executable, str(tape), "--emit-symbols"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    seat = []
    try:
        seat_payload = json.loads(r1.stdout)
        if isinstance(seat_payload, dict):
            seat = seat_payload.get("symbols") or seat_payload.get("underlying") or []
        elif isinstance(seat_payload, list):
            seat = seat_payload
    except Exception:
        seat = []
    tape_syms = ["SPY", "QQQ", "DIA", "RSP", "VTV", "VUG"]
    if r2.returncode == 0:
        try:
            tp = json.loads(r2.stdout)
            tape_syms = tp.get("symbols") or tape_syms
        except Exception:
            pass
    seen = []
    for s in list(seat) + list(tape_syms):
        s = str(s).strip().upper()
        if s and s not in seen:
            seen.append(s)
    print(json.dumps({"symbols": seen, "seat": seat, "tape": tape_syms}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="OID live ticker: marks → tape → scorecard → rebuild → optional publish")
    ap.add_argument("--emit-ids", action="store_true", help="Print open instrument_ids JSON")
    ap.add_argument("--emit-symbols", action="store_true", help="Print open + market-tape symbols JSON")
    ap.add_argument("--quotes-file", type=Path, help="RH option quotes JSON to apply")
    ap.add_argument("--quotes-stdin", action="store_true")
    ap.add_argument("--equity-quotes-file", type=Path, help="RH equity quotes JSON (get_equity_quotes)")
    ap.add_argument("--equity-quotes-stdin", action="store_true")
    ap.add_argument("--skip-scorecard", action="store_true")
    ap.add_argument("--skip-rebuild", action="store_true")
    ap.add_argument("--index-quotes-file", type=Path, help="RH get_index_quotes JSON (VIX) for macro strip")
    ap.add_argument("--index-historicals-file", type=Path, help="RH get_index_historicals JSON (VIX)")
    ap.add_argument("--skip-tape", action="store_true", help="Skip market-tape / Fidelity-3 refresh")
    ap.add_argument("--publish", action="store_true", help="Run dashboard/publish.sh after rebuild")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    refresh = ROOT / "refresh_marks.py"
    tape_script = ROOT / "refresh_market_tape.py"

    if args.emit_ids:
        return subprocess.call([sys.executable, str(refresh), "--list-ids"])
    if args.emit_symbols:
        return _merged_symbols()

    has_opt = bool(args.quotes_file or args.quotes_stdin)
    has_eq = bool(args.equity_quotes_file or args.equity_quotes_stdin)
    if not has_opt and not has_eq:
        print(
            "Usage:\n"
            "  python3 live_refresh.py --emit-ids\n"
            "  python3 live_refresh.py --emit-symbols\n"
            "  python3 live_refresh.py --quotes-file opt.json --equity-quotes-file eq.json --publish\n",
            file=sys.stderr,
        )
        return 2

    if args.quotes_stdin and args.equity_quotes_stdin:
        print("ERROR: use files when applying both option and equity quotes", file=sys.stderr)
        return 2

    cmd = [sys.executable, str(refresh)]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.quotes_stdin:
        cmd.append("--quotes-stdin")
    elif args.quotes_file:
        cmd.extend(["--quotes-file", str(_abs(args.quotes_file))])
    if args.equity_quotes_stdin:
        cmd.append("--equity-quotes-stdin")
    elif args.equity_quotes_file:
        cmd.extend(["--equity-quotes-file", str(_abs(args.equity_quotes_file))])

    if args.quotes_stdin or args.equity_quotes_stdin:
        r = subprocess.run(cmd, cwd=str(ROOT), input=sys.stdin.read(), text=True)
    else:
        r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        return r.returncode
    if args.dry_run:
        return 0

    # Market-overview strip (indices + Fidelity-3).
    # Duplicates #2: refresh_market_tape piggybacks fresh rh-quotes; equity file fills misses.
    if not args.skip_tape and tape_script.is_file():
        tape_cmd = [
            sys.executable,
            str(tape_script),
            "--writer",
            "live_refresh.py",
        ]
        if has_eq and args.equity_quotes_file:
            tape_cmd.extend(["--equity-quotes-file", str(_abs(args.equity_quotes_file))])
        # else: tape script uses --from-rh-quotes-cache (default) for covered symbols
        if getattr(args, "index_quotes_file", None):
            tape_cmd.extend(["--index-quotes-file", str(_abs(args.index_quotes_file))])
        if getattr(args, "index_historicals_file", None):
            tape_cmd.extend(["--index-historicals-file", str(_abs(args.index_historicals_file))])
        run(tape_cmd, check=False)

    run([sys.executable, str(PT / "close_triggers.py")])
    if not args.skip_scorecard:
        run([sys.executable, str(PT / "refresh_scorecard.py")])
    if not args.skip_rebuild:
        run([sys.executable, str(ROOT / "rebuild.py")])
    if args.publish:
        run(["bash", str(ROOT / "publish.sh")])
    print("live_refresh done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
