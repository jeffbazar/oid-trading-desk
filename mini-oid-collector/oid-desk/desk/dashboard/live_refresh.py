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

Mac mini (2026-10-07): refresh_marks.py + refresh_market_tape.py overlay fresher core-20 marks from
cache/mini-quotes.json (5s poller, scripts/mini-poller.sh) on top of the RH payload when fresh
(<=15s RTH, <=120s PRE/AH). RH stays the base (prev_close) and the fallback. --no-mini disables.
Option marks (2026-10-10): the mini also streams Alpaca OPRA for every desk contract
(quotes/option_marks.py; the 5 s poller writes cache/mini-option-quotes.json). refresh_marks uses mini OPRA
first when live (<=60 s RTH) and RH get_option_quotes as fallback; with no --quotes-file this
orchestrator passes --options-from-mini so option marks still refresh from OPRA alone.
--no-mini-options restores RH-only option marks.
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

# Quote input files must be freshly pulled this cycle. 2026-10-07 12:59 PM PT incident:
# `…/tmp/oid-live-equity.json` was expanded to /workspace/tmp/ (a 9/21 leftover from the
# 10/05 box seed) instead of the repo tmp/, and its prices were stamped as fresh.
MAX_QUOTE_FILE_AGE_SEC = 20 * 60


def _check_input_file(label: str, path: Path | None, *, allow_old: bool) -> str | None:
    """Return an error string if a quote input file is missing or too old to be this cycle's pull."""
    if path is None:
        return None
    import time
    if not path.is_file():
        return f"{label}: file not found: {path}"
    try:
        path.resolve().relative_to(REPO.resolve())
    except ValueError:
        print(f"WARNING {label}: {path} is outside the repo ({REPO}); expected repo tmp/", file=sys.stderr)
    age = time.time() - path.stat().st_mtime
    if age > MAX_QUOTE_FILE_AGE_SEC and not allow_old:
        return (
            f"{label}: {path} is {age/60:.0f} min old (> {MAX_QUOTE_FILE_AGE_SEC//60} min). "
            "Refusing to stamp an old payload as fresh; re-pull quotes or pass --allow-old-file."
        )
    return None


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


def _print_mini_status(disabled: bool) -> None:
    """One-line mini cache status (no network, no secrets)."""
    if disabled:
        print("mini: overlay disabled (--no-mini)", flush=True)
        return
    try:
        sys.path.insert(0, str(REPO / "quotes"))
        from mini_client import read_cache
        c = read_cache()
        print(
            f"mini: cache_fresh={c.get('fresh_file')} file_age={c.get('file_age_s')}s "
            f"fresh_mini_symbols={len(c.get('quotes') or {})} err={c.get('error')}",
            flush=True,
        )
    except Exception as e:  # informational only
        print(f"mini: status unavailable ({type(e).__name__})", flush=True)


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
    ap.add_argument("--no-mini", action="store_true",
                    help="Disable Mac-mini 5s equity mark overlay (RH payload only)")
    ap.add_argument("--no-mini-options", action="store_true",
                    help="Option marks from the RH payload only (skip mini OPRA)")
    ap.add_argument("--options-from-mini", action="store_true",
                    help="Mark options from mini OPRA only (implied when no --quotes-file is given)")
    ap.add_argument("--allow-old-file", action="store_true",
                    help="Allow quote files older than 20 min (backfill/debug only)")
    args = ap.parse_args()

    refresh = ROOT / "refresh_marks.py"
    tape_script = ROOT / "refresh_market_tape.py"

    if args.emit_ids:
        return subprocess.call([sys.executable, str(refresh), "--list-ids"])
    if args.emit_symbols:
        return _merged_symbols()

    has_opt = bool(args.quotes_file or args.quotes_stdin)
    has_eq = bool(args.equity_quotes_file or args.equity_quotes_stdin)
    mini_opt_only = (not has_opt) and not args.no_mini_options
    if not has_opt and not has_eq and not args.options_from_mini:
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

    # 2026-10-09 (Hal 8:47 stale check): a stale --equity-quotes-file used to abort the WHOLE run
    # (exit 3), so routines fell back to marks-only refresh_marks and market-tape / macro-spot /
    # fidelity-three / shay-* never restamped. Now: stale option file still aborts; a stale equity
    # file is DROPPED (never stamped as fresh) and the run continues; tape then tries the rh-quotes
    # cache and any tape failure is reported loudly instead of swallowed.
    for label, fp in (("--quotes-file", args.quotes_file), ("--equity-quotes-file", args.equity_quotes_file)):
        err = _check_input_file(label, _abs(fp) if fp else None, allow_old=args.allow_old_file)
        if err:
            if label == "--equity-quotes-file" and has_opt:
                print(f"WARNING {err} -> dropping equity file; market-tape/macro/fidelity/shay feeds "
                      "will NOT restamp unless rh-quotes cache is fresh. Re-pull get_equity_quotes "
                      "for --emit-symbols.", file=sys.stderr, flush=True)
                args.equity_quotes_file = None
                has_eq = False
                continue
            print(f"ERROR {err}", file=sys.stderr)
            return 3

    _print_mini_status(args.no_mini)
    cmd = [sys.executable, str(refresh)]
    if args.no_mini:
        cmd.append("--no-mini")
    if args.no_mini_options:
        cmd.append("--no-mini-options")
    elif mini_opt_only:
        cmd.append("--options-from-mini")
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

    tape_failed = None
    if not has_eq:
        print("WARNING NO_EQUITY_QUOTES: shay-semi-watch / shay-ma-levels will not restamp this run.",
              file=sys.stderr, flush=True)
    # Market-overview strip (indices + Fidelity-3).
    # Duplicates #2: refresh_market_tape piggybacks fresh rh-quotes; equity file fills misses.
    if not args.skip_tape and tape_script.is_file():
        tape_cmd = [
            sys.executable,
            str(tape_script),
            "--writer",
            "live_refresh.py",
        ]
        if args.no_mini:
            tape_cmd.append("--no-mini")
        if has_eq and args.equity_quotes_file:
            tape_cmd.extend(["--equity-quotes-file", str(_abs(args.equity_quotes_file))])
        # else: tape script uses --from-rh-quotes-cache (default) for covered symbols
        if getattr(args, "index_quotes_file", None):
            tape_cmd.extend(["--index-quotes-file", str(_abs(args.index_quotes_file))])
        if getattr(args, "index_historicals_file", None):
            tape_cmd.extend(["--index-historicals-file", str(_abs(args.index_historicals_file))])
        tr = run(tape_cmd, check=False)
        if tr.returncode != 0:
            tape_failed = tr.returncode
            print(f"WARNING TAPE_STEP_FAILED rc={tr.returncode}: market-tape / macro-spot / fidelity-three "
                  "NOT refreshed (need fresh equity quotes file or rh-quotes cache <=120s).",
                  file=sys.stderr, flush=True)
    elif args.skip_tape:
        tape_failed = "skipped"

    run([sys.executable, str(PT / "close_triggers.py")])
    if not args.skip_scorecard:
        run([sys.executable, str(PT / "refresh_scorecard.py")])
    if not args.skip_rebuild:
        run([sys.executable, str(ROOT / "rebuild.py")])
    # Data Sources tab / front-page alarm (Jeffrey 2026-10-10): recompute feed status each refresh
    # (publish.sh -> package_prod_dist.py recomputes again at package time). Never fatal.
    if (ROOT / "source_status.py").is_file():
        run([sys.executable, str(ROOT / "source_status.py")], check=False)
    if args.publish:
        run(["bash", str(ROOT / "publish.sh")])
    print("live_refresh done" + (f" (TAPE NOT REFRESHED: {tape_failed})" if tape_failed else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
