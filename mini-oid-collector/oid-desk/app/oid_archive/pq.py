"""Parquet I/O (pyarrow, zstd) with the frozen v1 schemas + per-partition _manifest.json."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from . import SCHEMA_VERSION
from .common import atomic_write_json, iso_ns, now_ns, partition_dir
from .schemas import KEYS, TABLE_COLUMNS, conform

_PA = {"string": "string", "int64": "int64", "int32": "int32", "int16": "int16", "int8": "int8", "float64": "float64", "bool": "bool_"}


def arrow_schema(table: str):
    import pyarrow as pa
    return pa.schema([(c, getattr(pa, _PA[t])()) for c, t in TABLE_COLUMNS[table]])


def write_table(table: str, date: str, pass_name: str, rows: list[dict[str, Any]], writer: str,
                source_files: int = 0, root: Optional[Path] = None) -> Optional[Path]:
    """Write <root>/parquet/<table>/date=<date>/<table>-<date>-<pass>.parquet (replaces the same pass atomically)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    if not rows:
        return None
    rows = sorted((conform(table, r) for r in rows), key=lambda r: tuple((r[k] is None, r[k]) for k in KEYS[table]))
    sch = arrow_schema(table)
    meta = {"oid.schema_version": SCHEMA_VERSION, "oid.table": table, "oid.writer": writer,
            "oid.compacted_at_iso": iso_ns(now_ns()), "oid.source_files": str(source_files), "oid.row_count": str(len(rows)),
            "oid.pass": pass_name, "oid.date": date}
    t = pa.Table.from_pylist(rows, schema=sch).replace_schema_metadata(meta)
    d = partition_dir(table, date, parquet=True, root=root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{table}-{date}-{pass_name}.parquet"
    tmp = p.with_suffix(".parquet.tmp")
    pq.write_table(t, tmp, compression="zstd")
    tmp.replace(p)
    write_manifest(table, date, root=root)
    return p


def write_manifest(table: str, date: str, root: Optional[Path] = None) -> dict[str, Any]:
    import pyarrow.parquet as pq
    d = partition_dir(table, date, parquet=True, root=root)
    files = []
    for f in sorted(d.glob("*.parquet")):
        files.append({"file": f.name, "rows": pq.ParquetFile(f).metadata.num_rows, "bytes": f.stat().st_size,
                      "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    m = {"schema_version": SCHEMA_VERSION, "table": table, "date": date, "files": files,
         "rows": sum(x["rows"] for x in files), "written_at_iso": iso_ns(now_ns())}
    atomic_write_json(d / "_manifest.json", m)
    return m


def read_parquet_rows(table: str, date: str, root: Optional[Path] = None, columns: Optional[list[str]] = None,
                      exclude_pass: Iterable[str] = ()) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq
    d = partition_dir(table, date, parquet=True, root=root)
    out: list[dict[str, Any]] = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.parquet")):
        if any(f.name.endswith(f"-{x}.parquet") for x in exclude_pass):
            continue
        out.extend(pq.read_table(f, columns=columns).to_pylist())
    return out


def parquet_keys(table: str, date: str, root: Optional[Path] = None) -> set:
    ks = KEYS[table]
    return {tuple(r[k] for k in ks) for r in read_parquet_rows(table, date, root=root, columns=list(ks))}
