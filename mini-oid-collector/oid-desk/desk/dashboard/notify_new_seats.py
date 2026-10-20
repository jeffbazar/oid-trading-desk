#!/usr/bin/env python3
"""Diff open paper seats vs notify-open-baseline.json. Exit 0 always; print JSON for WakeParent.
Research/paper only — never places orders.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
PT = ZoneInfo("America/Los_Angeles")
OID = Path(__file__).resolve().parent.parent
BASE = OID / "paper-trades" / "notify-open-baseline.json"
TRADES = OID / "paper-trades" / "trades.json"

def main() -> int:
    trades = json.loads(TRADES.read_text())
    items = trades.get("trades") if isinstance(trades, dict) else trades
    open_rows = []
    for t in items or []:
        if not isinstance(t, dict):
            continue
        st = str(t.get("status") or "").lower()
        if st not in ("open", "watching", "paper", "live"):
            continue
        open_rows.append({
            "id": t.get("id"),
            "symbol": t.get("symbol"),
            "contract": t.get("contract"),
            "agent": t.get("agent") or t.get("desk") or "unknown",
            "entryAsk": t.get("entryAsk") or t.get("entryMark"),
            "rationale": (t.get("rationale") or t.get("thesis") or "")[:180],
            "status": st,
        })
    prev = {}
    if BASE.is_file():
        prev = json.loads(BASE.read_text())
    prev_ids = set(prev.get("ids") or [])
    cur_ids = {r["id"] for r in open_rows if r.get("id")}
    new_rows = [r for r in open_rows if r.get("id") and r["id"] not in prev_ids]
    out = {
        "as_of_pt": datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT"),
        "new_count": len(new_rows),
        "new": new_rows,
        "open_count": len(open_rows),
        "notify": len(new_rows) > 0,
        "blotter": "https://swift-dune-cs3e.here.now/",
    }
    print(json.dumps(out, indent=2))
    if new_rows:
        BASE.write_text(json.dumps({
            "as_of_pt": out["as_of_pt"],
            "open": open_rows,
            "ids": sorted(cur_ids),
            "note": "Updated after new-seat notify",
        }, indent=2) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
