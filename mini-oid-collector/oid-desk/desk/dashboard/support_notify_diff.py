#!/usr/bin/env python3
"""OID support-levels notify diff — companion to refresh_support_map.py.

Run AFTER `refresh_support_map.py` (non-dry-run). Reads the freshly written
paper-trades/universe-support-watch.json + market-data/latest/support-map.json,
compares PRIMARY names vs tmp/support-levels-last.json, and decides notify.

Notify semantics (unchanged from the pre-2026-10-05 per-run rebuild scripts):
  - Only PRIMARY names; only hints GOOD_LOW / THRU_PUT.
  - Reasons: new_entry / reenter (was not near last run), hard_roll (put wall
    changed while near), hint_change (GOOD_LOW <-> THRU_PUT) — at most once per
    symbol+hint per RTH half-day (AM < 12:30 PM PT <= PM) unless leave+reenter.
  - Extended names are listed as soft color only, never notify alone.
  - Soft only — never elevates; never PAPER_CANDIDATE from support alone.

Writes (unless --dry-run):
  tmp/support-levels-last.json, tmp/support-levels-notify-this-run.json,
  tmp/support-levels-desk-ping.txt (cleared when notify=false),
  journal/runs + journals/runs OID-SUPPORT-YYYYMMDD-HHMM.md (notify only),
  NVDA-SUPPORT-WATCH.md "## Last support-levels run" line.

NEVER writes rh-quotes or any market-data feed. Zero RH calls / orders.
"""
from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OID = ROOT.parent
PT = ZoneInfo("America/Los_Angeles")
PRIMARY = [
    "SPY", "QQQ", "NVDA", "TSLA", "PLTR", "GOOGL", "NFLX",
    "META", "AMZN", "AMD", "CBRS", "INTC", "TSM",
]
NEAR = ("GOOD_LOW", "THRU_PUT")
LAST = OID / "tmp" / "support-levels-last.json"
BACKUP_LAST = Path(
    "/workspace/tmp/oid-cutover-backup-20261005/options-intelligence-desk-FULL/tmp/support-levels-last.json"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="OID support-levels notify diff (no feed writes)")
    ap.add_argument("--dry-run", action="store_true", help="Compute notify; write nothing")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    now_pt = now.astimezone(PT)
    as_of_pt = now_pt.strftime("%Y-%m-%d %-I:%M %p PT")
    hm = now_pt.hour * 60 + now_pt.minute
    half = f"{now_pt:%Y-%m-%d}-{'AM' if hm < 12 * 60 + 30 else 'PM'}"

    watch = json.loads((OID / "paper-trades" / "universe-support-watch.json").read_text())
    smap = json.loads((OID / "market-data" / "latest" / "support-map.json").read_text())
    sp = smap.get("payload") or {}
    rows = {r["symbol"]: r for r in watch.get("symbols") or []}
    near = list(watch.get("nearSupportNow") or [])
    session_label = watch.get("sessionLabel") or sp.get("sessionLabel") or "?"

    if not LAST.exists() and BACKUP_LAST.exists() and not args.dry_run:
        LAST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_LAST, LAST)  # one-time seed after 2026-10-05 cutover
    src = LAST if LAST.exists() else (BACKUP_LAST if BACKUP_LAST.exists() else None)
    prev = json.loads(src.read_text()) if src else {}
    prev_put = prev.get("putBySymbol") or {}
    prev_status = prev.get("statusBySymbol") or {}
    prev_notified = deepcopy(prev.get("notified") or {})

    status_by, put_by, hard_rolls, items, left_band = {}, {}, [], [], []
    for sym in PRIMARY:
        row = rows.get(sym) or {}
        new_h = row.get("statusHint") or "WALLS_DATA_INSUFFICIENT"
        put = row.get("faPutWall")
        status_by[sym] = new_h
        if put is not None:
            put_by[sym] = put
        old_put = prev_put.get(sym)
        hard = None
        if old_put is not None and put is not None and float(old_put) != float(put) and row.get("last") is not None:
            hard = {"from": old_put, "to": put}
            hard_rolls.append({"symbol": sym, "put_old": old_put, "put_new": put})
        old_h = prev_status.get(sym)
        near_now = new_h in NEAR
        was_near = old_h in NEAR + ("AT_PUT",)
        if was_near and not near_now:
            left_band.append(sym)
        reason = None
        if near_now:
            nrec = prev_notified.get(sym) or {}
            already = nrec.get("half_key") == half and nrec.get("hint") == new_h
            if not was_near:
                reason = "reenter" if already else "new_entry"
            elif hard:
                if not already or nrec.get("put") != put:
                    reason = "hard_roll"
            elif old_h != new_h and not already:
                reason = "hint_change"
        if reason:
            items.append({
                "symbol": sym, "hint": new_h, "reason": reason, "last": row.get("last"),
                "put": put, "call": row.get("faCallWall"), "distPct": row.get("distanceToPutWallPct"),
                "dayPct": row.get("dayPct"), "note": row.get("softNote"), "flip": row.get("faFlip"),
            })

    ext_near = [s for s in near if s not in PRIMARY]
    notify = bool(items)
    new_notified = deepcopy(prev_notified)
    for it in items:
        new_notified[it["symbol"]] = {
            "hint": it["hint"], "half_key": half, "at_pt": as_of_pt,
            "reason": it["reason"], "put": it["put"], "last": it["last"],
        }

    ping = None
    if notify:
        lines = [
            f"OID soft support ping · {as_of_pt} · {session_label}",
            "Soft take-look only — never elevate on support alone. Elevate stays with Q5/opening.",
            "",
        ]
        for it in items:
            d = it["distPct"]
            sign = "+" if d is not None and d >= 0 else ""
            lines.append(
                f"• {it['symbol']} {it['hint']} · spot {it['last']} · put {it['put']} "
                f"({sign}{d}% vs put) · call {it['call']} · day {it['dayPct']}% · {it['note']} [{it['reason']}]"
            )
        lines.append("")
        if left_band:
            lines.append(f"Left band: {', '.join(left_band)}")
        if ext_near:
            lines.append(f"Extended near (no PRIMARY notify): {', '.join(ext_near)}")
        lines += ["", "Research/paper only — zero RH execution."]
        ping = "\n".join(lines)

    doc = {
        "notify": notify, "items": items, "left_band": left_band, "hard_rolls": hard_rolls,
        "nearSupportNow": near, "extendedNear": ext_near, "statusBySymbol": status_by,
        "as_of_pt": as_of_pt, "half_key": half, "session": session_label,
        "fa": {"freshness": sp.get("faFreshness"), "as_of_pt": sp.get("faAsOfPT"),
               "writer": sp.get("faWriter"), "age_sec": sp.get("faAgeSec")},
        "rh": {"source": sp.get("quoteSource"), "as_of_pt": sp.get("rhAsOfPT"),
               "writer": sp.get("rhWriter"), "age_sec": sp.get("rhAgeSec"), "label": sp.get("rhLabel")},
        "ping": ping, "dry_run": bool(args.dry_run), "wrote_rh_quotes": False,
        "prev_state_source": str(src) if src else None,
    }
    if args.dry_run:
        print(json.dumps(doc, indent=2))
        return 0

    tmp = OID / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps({
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "as_of_pt": as_of_pt, "half_key": half,
        "nearSupportNow": near, "statusBySymbol": status_by, "putBySymbol": put_by,
        "notified": new_notified, "writer": "oid-support-levels-watch (support_notify_diff.py)",
    }, indent=2) + "\n")
    (tmp / "support-levels-notify-this-run.json").write_text(json.dumps(doc, indent=2) + "\n")
    (tmp / "support-levels-desk-ping.txt").write_text((ping + "\n") if ping else "")

    if notify:
        body = "\n".join([
            f"# OID support levels · {as_of_pt}", "",
            f"Session: {session_label}. Soft color only — never elevate on support alone.", "",
            "## Notify", "", "```", ping, "```", "## Hard rolls", "",
            "```json", json.dumps(hard_rolls, indent=2), "```", "",
        ])
        name = f"OID-SUPPORT-{now_pt:%Y%m%d-%H%M}.md"
        for d in (OID / "journal" / "runs", OID / "journals" / "runs"):
            d.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(body)

    md_path = OID / "NVDA-SUPPORT-WATCH.md"
    lines = md_path.read_text().rstrip().splitlines()
    fa_age, rh_age = sp.get("faAgeSec"), sp.get("rhAgeSec")
    bullet = (
        f"- {as_of_pt} — {session_label} soft map rebuild via refresh_support_map.py; "
        f"FA walls {sp.get('faFreshness')} (writer {sp.get('faWriter')}, age ~{round(fa_age) if fa_age is not None else '?'}s); "
        f"RH quotes {sp.get('quoteSource')} (writer {sp.get('rhWriter')}, age ~{round(rh_age) if rh_age is not None else '?'}s; piggyback, no rh-quotes write). "
        f"nearSupportNow: {', '.join(near) if near else '(none)'}. notify={'true' if notify else 'false'}"
        + (f" left_band={','.join(left_band)}" if left_band else "") + ". Soft color only."
    )
    out, done = [], False
    for i, ln in enumerate(lines):
        if ln.startswith("## Last support-levels run"):
            out += [ln, bullet]
            j = i + 1
            while j < len(lines) and (lines[j].startswith("- ") or not lines[j].strip()):
                j += 1
            out += lines[j:]
            done = True
            break
        out.append(ln)
    if not done:
        out += ["", "## Last support-levels run", bullet]
    md_path.write_text("\n".join(out) + "\n")

    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
