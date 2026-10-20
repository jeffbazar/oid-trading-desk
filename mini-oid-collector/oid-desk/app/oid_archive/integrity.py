"""Saturday 10:00 AM PT integrity check (SCHEMAS §11): manifests vs files (sha256, row counts), JSONL vs Parquet row
counts, and deletion of JSONL older than 90 days ONLY when its Parquet rows cover every JSONL key.

  python -m oid_archive.integrity [--delete]   # without --delete it only reports
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .common import ET, archive_root, atomic_write_json, data_root, iso_ns, iter_jsonl, jsonl_parts, now_ns
from .pq import parquet_keys
from .schemas import KEYS


def check(root: Optional[Path] = None, delete: bool = False, keep_days: int = 90) -> dict[str, Any]:
    import pyarrow.parquet as pq
    r = root or archive_root()
    try:
        import duckdb
        con = duckdb.connect()
    except ImportError:
        con = None
    res: dict[str, Any] = {"checked_iso": iso_ns(now_ns()), "problems": [], "deleted": [], "partitions": 0}
    cutoff = (dt.datetime.now(ET).date() - dt.timedelta(days=keep_days)).isoformat()
    for t in KEYS:
        for d in sorted((r / "parquet" / t).glob("date=*")) if (r / "parquet" / t).exists() else []:
            res["partitions"] += 1
            mf = d / "_manifest.json"
            if not mf.exists():
                res["problems"].append(f"{t}/{d.name}: no manifest"); continue
            m = json.loads(mf.read_text())
            for f in m.get("files", []):
                p = d / f["file"]
                if not p.exists():
                    res["problems"].append(f"{t}/{d.name}/{f['file']}: missing"); continue
                if hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                    res["problems"].append(f"{t}/{d.name}/{f['file']}: sha256 mismatch")
                if pq.ParquetFile(p).metadata.num_rows != f["rows"]:
                    res["problems"].append(f"{t}/{d.name}/{f['file']}: row count mismatch")
            if con is not None and m.get("files"):
                n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(d / "*.parquet")]).fetchone()[0]
                if n != m.get("rows"):
                    res["problems"].append(f"{t}/{d.name}: duckdb count {n} != manifest {m.get('rows')}")
        base = r / t
        for d in sorted(base.glob("date=*")) if base.exists() else []:
            date = d.name[5:]
            parts = jsonl_parts(t, date, r)
            if not parts:
                continue
            jkeys = {tuple(x.get(c) for c in KEYS[t]) for x in iter_jsonl(parts)}
            pkeys = parquet_keys(t, date, r)
            missing = len(jkeys - pkeys)
            if missing:
                res["problems"].append(f"{t}/{date}: {missing} JSONL keys not in Parquet")
            elif delete and date < cutoff:
                for p in parts:
                    p.unlink()
                    res["deleted"].append(str(p.relative_to(r)))
    res["duckdb"] = con is not None
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    a = ap.parse_args(argv)
    res = check(delete=a.delete)
    tag = os.environ.get("OID_ARCHIVE_TAG", "")   # WIDECP
    atomic_write_json(data_root() / "state" / f"integrity{'-' + tag if tag else ''}-status.json", res)
    print(json.dumps({k: (v if k != "deleted" else len(v)) for k, v in res.items()}))
    return 0 if not res["problems"] else 2


if __name__ == "__main__":
    sys.exit(main())
