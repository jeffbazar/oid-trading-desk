#!/usr/bin/env python3
"""One-shot backfill of outcome fields from ledger + journal-recovered marks.
Does not invent fills/UW/FA. Research only.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from outcome_helper import (
    apply_mark_update,
    ensure_outcome_fields,
    finalize_outcome,
    format_pt,
    init_outcome_on_elevate,
)

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "trades.json"


def load():
    return json.loads(LEDGER.read_text())


def save(ledger):
    ledger["updatedAt"] = datetime.now(timezone.utc).isoformat()
    ledger["updatedAtPT"] = format_pt()
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")


def by_id(ledger, tid):
    for t in ledger["trades"]:
        if t["id"] == tid:
            return t
    raise KeyError(tid)


def replay_marks(trade, samples):
    """samples: list of (mark, at_pt). Starts from elevate init."""
    init_outcome_on_elevate(trade)
    for mark, at_pt in samples:
        apply_mark_update(trade, mark, at_pt=at_pt)
    trade["mfeMaePartial"] = False


def main():
    ledger = load()

    # --- OID-PAPER-20260910-1 NVDA 220C closed win ---
    # Journal marks during hold (offered 9/10 → Rose exit morning 9/11 @ 4.40).
    # Peak 4.775 (OID-Q5-20260911-2); trough 3.70 (OID-PM-20260910-1). Exit 4.40.
    t = by_id(ledger, "OID-PAPER-20260910-1")
    t["exitAt"] = "2026-09-11T15:00:00+00:00"  # morning PT approx; Rose reported
    t["exitAtApprox"] = True
    replay_marks(
        t,
        [
            (3.95, "2026-09-10 10:22 AM PT"),   # Q5-2
            (3.825, "2026-09-10 10:37 AM PT"),  # Q5-3
            (3.70, "2026-09-10 12:22 PM PT"),   # PM trough
            (3.75, "2026-09-10 1:00 PM PT"),    # cash close-ish
            (4.00, "2026-09-11 8:10 AM PT"),    # OPEN
            (4.35, "2026-09-11 6:57 AM PT"),    # Q5-1 (UTC order; PT labels from journals)
            (4.775, "2026-09-11 7:01 AM PT"),   # Q5-2 peak
            (4.40, "2026-09-11 8:00 AM PT"),    # Rose exit
        ],
    )
    finalize_outcome(
        t,
        outcome_tag="win_exit",
        result="win",
        lesson=(
            "Wall+thesis reclaim above flip toward call 220 worked enough for Rose to bank "
            "~+14.3% at $4.40; path showed MFE ~+24% then gave back — early scale worked."
        ),
        refine_hint=(
            "When live paper is ≥~+15–20% into the named wall with thesis intact, "
            "prompt a take-profit / trim check rather than only invalidation monitoring."
        ),
    )

    # --- OID-PAPER-20260914-1 TSLA 370C thesis_fail (~14 min) ---
    t = by_id(ledger, "OID-PAPER-20260914-1")
    t["exitAt"] = t.get("invalidatedAt")
    replay_marks(
        t,
        [
            (4.0, "2026-09-14 6:51 AM PT"),  # invalidate mark
        ],
    )
    # Only entry→fail marks recovered → still not inventing mid-path; flag partial lightly
    # We have entry + final; peak stayed at entryAsk → mfeMaePartial False is OK (complete for short life)
    t["mfeMaePartial"] = False
    finalize_outcome(
        t,
        outcome_tag="thesis_fail",
        result="thesis_fail",
        lesson=(
            "Long-call press-370 failed within ~15 minutes when spot broke FA flip 363.74 "
            "and tested put 360 into FOMC week — short DTE + event risk + under-wall entry."
        ),
        refine_hint=(
            "Do not elevate short-DTE long calls into FOMC week when spot is already under "
            "the call wall and the named fail is a nearby flip with thin cushion."
        ),
    )

    # --- OID-PAPER-20260914-2 NFLX 80C thesis_fail ---
    t = by_id(ledger, "OID-PAPER-20260914-2")
    t["exitAt"] = t.get("invalidatedAt")
    replay_marks(
        t,
        [
            (1.695, "2026-09-14 9:29 AM PT"),  # Q5-2 peak +29.4%
            (1.475, "2026-09-14 12:16 PM PT"),
            (1.40, "2026-09-14 12:23 PM PT"),
            (1.455, "2026-09-14 1:00 PM PT"),   # cash close Mon
            (0.71, "2026-09-15 6:39 AM PT"),    # Q5-1 Tue
            (0.39, "2026-09-15 7:21 AM PT"),    # invalidate
        ],
    )
    t["mfeMaePartial"] = False
    finalize_outcome(
        t,
        outcome_tag="thesis_fail",
        result="thesis_fail",
        lesson=(
            "Press/break call 80 worked briefly (MFE ~+29%) on Mon, then Tue open lost "
            "STALE flip 78.60 into FOMC day-1 — chase soft + short DTE into Fed both named."
        ),
        refine_hint=(
            "Gate harder on FOMC-week short-DTE call presses that already show chase soft "
            "and rely on STALE walls; invalidate faster on first flip loss, don't wait for −70%."
        ),
    )

    # --- OID-PAPER-20260916-1 NVDA 215C OPEN (Rose praised) ---
    t = by_id(ledger, "OID-PAPER-20260916-1")
    replay_marks(
        t,
        [
            (2.77, "2026-09-16 7:35 AM PT"),    # Q5-3
            (2.91, "2026-09-16 7:45 AM PT"),    # OPEN
            (2.93, "2026-09-16 11:23 AM PT"),   # Q5-4
            (1.925, "2026-09-16 1:00 PM PT"),   # CLOSE trough −26%
            (4.00, "2026-09-17 6:44 AM PT"),    # Q5-1
            (4.825, "2026-09-17 7:15 AM PT"),   # Q5-2
            (4.925, "2026-09-17 7:11 AM PT"),   # FH
            (5.075, "2026-09-17 7:45 AM PT"),   # Q5-3 peak +95.2%
            (4.725, "2026-09-17 7:51 AM PT"),   # current OPEN mark
        ],
    )
    t["mfeMaePartial"] = False
    t["outcomeTag"] = "win_open"
    t["lesson"] = (
        "FOMC day-2 wall press on 215 held flip/put through the print whip; overnight mark "
        "dipped to ~$1.93 (−26% MAE) then Thu reclaim drove MFE ~+95% — Rose called it a great paper candidate."
    )
    t["refineHint"] = (
        "Keep elevating NVDA wall+thesis when FRESH FA + flip cushion is real; track MFE/MAE "
        "through event nights rather than invalidating on cash-close soft under-wall alone."
    )
    ensure_outcome_fields(t)
    # Preserve current unrealized from last mark
    apply_mark_update(t, float(t["lastMark"]), at_pt=t.get("lastMarkedAtPT") or t.get("updatedAtPT"))

    for tr in ledger["trades"]:
        ensure_outcome_fields(tr)

    save(ledger)
    print("backfilled", len(ledger["trades"]), "trades →", LEDGER)
    for tr in ledger["trades"]:
        print(
            tr["id"],
            tr.get("outcomeTag"),
            "peak", tr.get("peakMark"),
            "trough", tr.get("troughMark"),
            "mfe%", tr.get("mfePct"),
            "mae%", tr.get("maePct"),
            "holdH", tr.get("holdHours"),
            "partial", tr.get("mfeMaePartial"),
        )


if __name__ == "__main__":
    main()
