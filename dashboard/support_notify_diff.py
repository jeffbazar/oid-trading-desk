#!/usr/bin/env python3
"""Diff two support-map payloads and emit a soft notify.

``oid-support-levels-watch`` runs this after ``refresh_support_map.py``.
It must not call ``write_feed("rh-quotes")``. Crosses and distance jumps are
research color only. They never elevate and never submit an order.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard._cache import cache_io

DEFAULT_JUMP = 0.005


def _rows(payload) -> dict:
    if not isinstance(payload, dict):
        return {}
    body = payload
    if "rows" not in body and isinstance(body.get("payload"), dict):
        body = body["payload"]
    rows = body.get("rows") or []
    indexed = {}
    for row in rows:
        if isinstance(row, dict) and row.get("symbol"):
            indexed[row["symbol"]] = row
    return indexed


def diff_support(previous, current, jump: float = DEFAULT_JUMP) -> list:
    """Compare put-wall distances. Empty previous is a baseline, not 37 adds."""
    previous_rows = _rows(previous)
    current_rows = _rows(current)
    if not current_rows:
        return []
    if not previous_rows:
        return [{
            "kind": "baseline",
            "symbols": len(current_rows),
            "soft_only": True,
            "elevate": False,
            "execution": "none",
        }]
    events = []
    for symbol, row in current_rows.items():
        old = previous_rows.get(symbol)
        new_distance = row.get("distance")
        if old is None:
            events.append({
                "symbol": symbol,
                "kind": "added",
                "distance": new_distance,
                "soft_only": True,
                "elevate": False,
                "execution": "none",
            })
            continue
        old_distance = old.get("distance")
        if old_distance is None or new_distance is None:
            continue
        event = {
            "symbol": symbol,
            "put_wall": row.get("put_wall"),
            "last": row.get("last"),
            "distance": new_distance,
            "previous_distance": old_distance,
            "soft_only": True,
            "elevate": False,
            "execution": "none",
        }
        if old_distance >= 0 and new_distance < 0:
            event["kind"] = "crossed_under"
            events.append(event)
        elif old_distance < 0 and new_distance >= 0:
            event["kind"] = "crossed_over"
            events.append(event)
        elif abs(new_distance - old_distance) >= jump:
            event["kind"] = "distance_jump"
            events.append(event)
    return events


def format_notify(events) -> str:
    if not events:
        return (
            "Support map: no material put-wall distance change. "
            "Soft only. No elevate. Zero RH execution."
        )
    lines = []
    for event in events:
        kind = event.get("kind")
        if kind == "baseline":
            lines.append(
                f"Support map baseline ({event.get('symbols')} names). "
                "Soft only. No elevate. Zero RH execution."
            )
            continue
        symbol = event.get("symbol")
        if kind == "crossed_under":
            lines.append(
                f"{symbol} crossed under put wall {event.get('put_wall')} "
                f"(last {event.get('last')}, distance {event.get('distance')}). "
                "Soft only. No elevate. Zero RH execution."
            )
        elif kind == "crossed_over":
            lines.append(
                f"{symbol} reclaimed put wall {event.get('put_wall')} "
                f"(last {event.get('last')}, distance {event.get('distance')}). "
                "Soft only. No elevate. Zero RH execution."
            )
        elif kind == "distance_jump":
            lines.append(
                f"{symbol} put-wall distance {event.get('previous_distance')} → "
                f"{event.get('distance')} (last {event.get('last')}). "
                "Soft only. No elevate. Zero RH execution."
            )
        elif kind == "added":
            lines.append(
                f"{symbol} added to the support map. Soft only. No elevate. Zero RH execution."
            )
    return "\n".join(lines)


def load_payload(path):
    return cache_io().strip_secrets(json.loads(Path(path).read_text(encoding="utf-8")))


def run(previous_path, current_path, jump=DEFAULT_JUMP, write_notify=False, root=None):
    previous = load_payload(previous_path) if previous_path else {}
    current = load_payload(current_path)
    events = diff_support(previous, current, jump=jump)
    text = format_notify(events)
    written = None
    if write_notify:
        io = cache_io()
        destination = io.latest_dir(root) / "support-map-notify.txt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text + "\n", encoding="utf-8")
        written = str(destination)
    return {
        "events": events,
        "text": text,
        "written": written,
        "rh_quotes_write": False,
        "execution": "none",
    }


def _blocked(argv) -> bool:
    for arg in argv:
        text = arg.lower()
        if "rh-quotes" in text and "write" in text:
            return True
        if any(token in text for token in ("place_", "cancel_", "exercise", "--order", "--submit")):
            return True
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if _blocked(argv):
        print(
            "support_notify_diff does not write rh-quotes and does not submit orders",
            file=sys.stderr,
        )
        return 2
    parser = argparse.ArgumentParser(description="Soft support-map diff. Does not write rh-quotes.")
    parser.add_argument("--previous", default=None)
    parser.add_argument("--current", required=True)
    parser.add_argument("--jump", type=float, default=DEFAULT_JUMP)
    parser.add_argument("--write-notify", action="store_true")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    result = run(
        args.previous,
        args.current,
        jump=args.jump,
        write_notify=args.write_notify,
        root=args.root,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
