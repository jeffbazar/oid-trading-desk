#!/usr/bin/env python3
"""Consumer for cache/focus-watch-events.jsonl (5s focus watch). Research / paper only.

Prints JSON for a routine to act on (same contract as dashboard/notify_new_seats.py):
  {"notify": bool, "count": N, "events": [...], "readings": {...}, "watch": {...}}
notify=true when any unseen event is >= --min-severity (default medium). A routine that sees
notify=true should WakeParent / post a brief (symbol, event, level, spot, seat).

  python3 quotes/focus_watch_digest.py --consumer q5            # advance q5's cursor
  python3 quotes/focus_watch_digest.py --consumer q5 --peek     # don't advance
  python3 quotes/focus_watch_digest.py --since-min 15 --peek    # last 15 min regardless of cursor
Cursors (byte offsets per consumer) live in cache/focus-watch-cursors.json. Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

OID = Path(__file__).resolve().parents[1]
EVENTS = OID / "cache" / "focus-watch-events.jsonl"
OUT = OID / "cache" / "focus-watch.json"
CURSORS = OID / "cache" / "focus-watch-cursors.json"
RANK = {"low": 0, "medium": 1, "high": 2}


def digest(consumer: str | None = "default", *, peek: bool = False, min_severity: str = "medium",
           since_min: float | None = None, max_events: int = 25) -> dict:
    try:
        cursors = json.loads(CURSORS.read_text())
    except (OSError, json.JSONDecodeError):
        cursors = {}
    size = EVENTS.stat().st_size if EVENTS.exists() else 0
    start = 0 if since_min is not None else int(cursors.get(consumer or "default", {}).get("offset", 0))
    if start > size:  # rotated / truncated
        start = 0
    events = []
    if size:
        with EVENTS.open("rb") as fh:
            fh.seek(start)
            data = fh.read()
        end = start + data.rfind(b"\n") + 1 if b"\n" in data else start
        for line in data[: end - start].splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        end = 0
    if since_min is not None:
        cutoff = time.time() - since_min * 60
        events = [e for e in events if (e.get("epoch") or 0) >= cutoff]
    floor = RANK.get(min_severity, 1)
    hot = [e for e in events if RANK.get(e.get("severity"), 0) >= floor]
    try:
        w = json.loads(OUT.read_text())
    except (OSError, json.JSONDecodeError):
        w = {}
    readings = {}
    for s, r in (w.get("readings") or {}).items():
        readings[s] = {"spot": r.get("spot"), "flags": r.get("flags"), "seats": r.get("seats"),
                       "levels": {l["name"]: {"price": l["price"], "dist_pct": l.get("dist_pct"), "side": l.get("side")}
                                  for l in r.get("levels") or []},
                       "last_5m_close": ((r.get("bar5") or {}).get("last_close") or {}).get("c")}
    out = {
        "consumer": consumer, "notify": bool(hot), "count": len(hot), "all_count": len(events),
        "min_severity": min_severity,
        "events": [{k: e.get(k) for k in ("ts_pt", "symbol", "event", "severity", "level", "level_price", "spot",
                                         "dist_pct", "seats", "note")} for e in hot[-max_events:]],
        "watch": {"as_of_pt": w.get("as_of_pt"), "state": w.get("state"),
                  "age_s": round(time.time() - float(w.get("written_epoch") or 0), 1) if w else None,
                  "focus_symbols": w.get("focus_symbols")},
        "readings": readings,
        "mandate": "research/paper only - alerts, never orders",
    }
    if not peek and since_min is None:
        cursors[consumer or "default"] = {"offset": end, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        tmp = CURSORS.with_suffix(".tmp")
        tmp.write_text(json.dumps(cursors, indent=1))
        tmp.replace(CURSORS)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consumer", default="default")
    ap.add_argument("--peek", action="store_true")
    ap.add_argument("--min-severity", default="medium", choices=list(RANK))
    ap.add_argument("--since-min", type=float)
    a = ap.parse_args()
    print(json.dumps(digest(a.consumer, peek=a.peek, min_severity=a.min_severity, since_min=a.since_min), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
