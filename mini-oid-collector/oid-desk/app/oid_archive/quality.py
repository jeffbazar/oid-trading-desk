"""Data-quality exclusions (schema v1): flags, never rewrites, archived rows.

File: <archive>/quality/exclusions.json
  {"schema_version": "v1", "updated_iso": ..., "exclusions": [
     {"id": "SPCX-pre-20260612", "symbol": "SPCX", "tables": ["bars_1m","bars_5m","bars_15m","bars_1h"],
      "before": "2026-06-12", "reason": "...", "added_iso": ..., "added_by": ..., "schema_version": "v1"}]}
A row matches when symbol == symbol, its table is listed, and its ET date (partition date) is < before
(and >= after, if given). Readers filter with apply_exclusions=1 on /v1/archive/rows|bars, or read
/v1/archive/quality themselves. CLI: python -m oid_archive.quality --list | --add SYM --before D [--after D]
--tables t1,t2 --reason TEXT [--id ID]."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from .common import NS, archive_root, atomic_write_json, et_date, iso_ns
from .schemas import KEYS

ROLLUPS = ["bars_1m", "bars_5m", "bars_15m", "bars_1h"]
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def path(root: Optional[Path] = None) -> Path:
    return (root or archive_root()) / "quality" / "exclusions.json"


def load(root: Optional[Path] = None) -> dict[str, Any]:
    p = path(root)
    try:
        d = json.loads(p.read_text())
        if isinstance(d, dict) and isinstance(d.get("exclusions"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"schema_version": "v1", "updated_iso": None, "exclusions": []}


def _hit(e: dict, table: str, symbol: Optional[str], date: str) -> bool:
    if table not in (e.get("tables") or []):
        return False
    if symbol is not None and symbol != e.get("symbol"):
        return False
    if e.get("before") and not date < e["before"]:
        return False
    if e.get("after") and date < e["after"]:
        return False
    return True


def matching(table: str, date: Optional[str] = None, symbol: Optional[str] = None,
             root: Optional[Path] = None, doc: Optional[dict] = None) -> list[dict]:
    """Exclusions that touch (table, date[, symbol]). date=None -> any date."""
    ex = (doc or load(root))["exclusions"]
    out = []
    for e in ex:
        if table not in (e.get("tables") or []) or (symbol and symbol != e.get("symbol")):
            continue
        if date is None or _hit(e, table, symbol or e.get("symbol"), date):
            out.append(e)
    return out


def excluded(row: dict, table: str, exs: list[dict]) -> bool:
    if not exs:
        return False
    ts = row.get("bar_start_ns", row.get("bucket_start_ns", row.get("event_ts_ns")))
    date = row.get("date") or (et_date(ts) if ts is not None else None)
    return date is not None and any(_hit(e, table, row.get("symbol"), date) for e in exs)


def add(symbol: str, before: str, tables: list[str], reason: str, after: Optional[str] = None,
        ex_id: Optional[str] = None, added_by: str = "oid-archive", root: Optional[Path] = None) -> dict:
    symbol = symbol.upper()
    for d in (before, after):
        if d is not None and not _DATE.match(d):
            raise ValueError(f"bad date {d!r}")
    bad = [t for t in tables if t not in KEYS]
    if bad:
        raise ValueError(f"unknown tables {bad}")
    doc = load(root)
    now = iso_ns(time.time_ns())
    e = {"id": ex_id or f"{symbol}-pre-{before.replace('-', '')}", "symbol": symbol, "tables": list(tables),
         "before": before, "reason": reason, "added_iso": now, "added_by": added_by, "schema_version": "v1"}
    if after:
        e["after"] = after
    doc["exclusions"] = [x for x in doc["exclusions"] if x.get("id") != e["id"]] + [e]
    doc["schema_version"], doc["updated_iso"] = "v1", now
    atomic_write_json(path(root), doc)
    return e


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="oid_archive.quality")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--add", metavar="SYMBOL")
    ap.add_argument("--before"); ap.add_argument("--after")
    ap.add_argument("--tables", default=",".join(ROLLUPS))
    ap.add_argument("--reason"); ap.add_argument("--id"); ap.add_argument("--added-by", default="oid-archive")
    a = ap.parse_args(argv)
    if a.add:
        if not (a.before and a.reason):
            ap.error("--add needs --before and --reason")
        print(json.dumps(add(a.add, a.before, [t for t in a.tables.split(",") if t], a.reason, a.after, a.id, a.added_by), indent=1))
    else:
        print(json.dumps(load(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
