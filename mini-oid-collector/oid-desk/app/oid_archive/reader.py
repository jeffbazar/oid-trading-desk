"""Read-side helpers: one partition (Parquet passes unioned, de-duplicated; JSONL when not compacted) and bars."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Optional

from .common import ET, NS, archive_root, iter_jsonl, jsonl_parts, partition_dir
from .rollup import rollup
from .schemas import KEYS, columns

# when the same key is in several passes, prefer the reconciled live data over the backfill
PASS_RANK = {"main": 0, "post": 1, "backfill": 2}
TF_TABLE = {"1m": "bars_1m", "5m": "bars_5m", "15m": "bars_15m", "1h": "bars_1h", "1d": "bars_1d"}


def _pass_of(f: Path) -> str:
    return f.stem.rsplit("-", 1)[-1]


def partition_rows(table: str, date: str, symbol: Optional[str] = None, cols: Optional[list[str]] = None,
                   root: Optional[Path] = None) -> tuple[list[dict[str, Any]], str]:
    d = partition_dir(table, date, parquet=True, root=root)
    files = sorted(d.glob("*.parquet"), key=lambda f: PASS_RANK.get(_pass_of(f), 9)) if d.exists() else []
    rows: list[dict] = []
    src = "parquet"
    if files:
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
        seen = set()
        for f in files:
            t = pq.read_table(f)
            if symbol and "symbol" in t.column_names:
                t = t.filter(pc.equal(t["symbol"], symbol))
            for r in t.to_pylist():
                k = tuple(r.get(c) for c in KEYS[table])
                if k not in seen:
                    seen.add(k); rows.append(r)
    else:
        src = "jsonl"
        rows = [r for r in iter_jsonl(jsonl_parts(table, date, root)) if not symbol or r.get("symbol") == symbol]
    if cols:
        keep = [c for c in cols if c in columns(table)]
        rows = [{c: r.get(c) for c in keep} for r in rows]
    return rows, src


def _dates(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def bars(symbol: str, tf: str, start_ns: int, end_ns: int, cap: int = 20000, root: Optional[Path] = None) -> list[dict]:
    """Bars for one symbol/timeframe over [start, end). Today's (uncompacted) 1m comes from JSONL and is rolled up live."""
    table = TF_TABLE[tf]
    a = dt.datetime.fromtimestamp(start_ns / NS, ET).date()
    b = dt.datetime.fromtimestamp((end_ns - 1) / NS, ET).date()
    out: list[dict] = []
    for date in _dates(a, b):
        rows, src = partition_rows(table, date, symbol, root=root)
        if not rows and tf in ("5m", "15m", "1h"):
            m1, src1 = partition_rows("bars_1m", date, symbol, root=root)
            if src1 == "jsonl" and m1:
                rows = rollup(_dedupe_live(m1), tf, "reader")
        elif src == "jsonl" and tf == "1m":
            rows = _dedupe_live(rows)
        key = "bar_start_ns"
        out.extend(r for r in rows if start_ns <= r[key] < end_ns)
        if len(out) >= cap:
            break
    out.sort(key=lambda r: r["bar_start_ns"])
    return out[:cap]


def _dedupe_live(rows: list[dict]) -> list[dict]:
    by: dict[int, dict] = {}
    for r in sorted(rows, key=lambda r: r["ingest_ts_ns"]):
        by.setdefault(r["bar_start_ns"], r)
    return [by[k] for k in sorted(by)]


def tables_summary(root: Optional[Path] = None) -> list[dict[str, Any]]:
    import json
    r = root or archive_root()
    out = []
    for t in KEYS:
        dates = set()
        for base in (r / t, r / "parquet" / t):
            if base.exists():
                dates |= {p.name[5:] for p in base.glob("date=*") if p.is_dir()}
        rows = 0
        for d in dates:
            m = r / "parquet" / t / f"date={d}" / "_manifest.json"
            if m.exists():
                try:
                    rows += json.loads(m.read_text()).get("rows", 0)
                except ValueError:
                    pass
        out.append({"table": t, "schema_version": "v1", "dates": len(dates), "first_date": min(dates) if dates else None,
                    "last_date": max(dates) if dates else None, "compacted_rows": rows})
    return out
