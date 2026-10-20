"""Compaction passes (SCHEMAS §11). Never edits JSONL; writes Parquet + _manifest.json per partition.

  python -m oid_archive.compact --pass main  [--date YYYY-MM-DD]   # 2:00 PM PT: REST reconcile pre+RTH 1m, Parquet, rollups
  python -m oid_archive.compact --pass post  [--date YYYY-MM-DD]   # 5:15 PM PT: post-session rows + bars_1d final
  python -m oid_archive.compact --pass main --no-rest              # Parquet from what's on disk only (no API calls)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .bars import daily_rows, merge_1m, rest_1m_row
from .common import ET, HALF_DAYS, JsonlWriter, WRITER, archive_root, atomic_write_json, data_root, iter_jsonl, \
    jsonl_parts, now_ns, read_universe, session_bounds_ns, iso_ns
from .pq import parquet_keys, read_parquet_rows, write_table
from .rollup import rollup
from .schemas import KEYS, schema_json

GENERIC = ("volume_5s", "surges", "fetch_log")
MAIN_SESS, POST_SESS = {"pre", "rth"}, {"post"}
RTH_BUCKETS_FULL, RTH_BUCKETS_HALF = 4680, 2520


def ensure_schemas(root: Optional[Path] = None) -> None:
    r = root or archive_root()
    for t in KEYS:
        p = r / t / "_schema.json"
        if not p.exists():
            atomic_write_json(p, schema_json(t))


def _dedupe(table: str, rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r.get("ingest_ts_ns") or 0):
        k = tuple(r.get(c) for c in KEYS[table])
        if k not in seen:
            seen.add(k); out.append(r)
    return out


def _rest_pull(client, syms: list[str], date: str, sessions: list[str], writer: JsonlWriter) -> list[dict]:
    a = session_bounds_ns(date, sessions[0])[0]
    b = min(session_bounds_ns(date, sessions[-1])[1], now_ns() - 60 * 1_000_000_000)
    if b <= a:
        return []
    got = client.bars(syms, "1Min", iso_ns(a)[:19] + "Z", iso_ns(b - 1)[:19] + "Z")
    ing = now_ns()
    rows = [r for sym, bs in got.items() for b_ in bs if (r := rest_1m_row(sym, b_, ing, "bars-reconcile", final=True))]
    rows = [r for r in rows if r["session"] in sessions]
    writer.write(rows)
    return rows


def run_pass(pass_name: str, date: str, rest: bool = True, client=None, universe: Optional[list[str]] = None,
             root: Optional[Path] = None) -> dict[str, Any]:
    root = root or archive_root()
    ensure_schemas(root)
    res: dict[str, Any] = {"pass": pass_name, "date": date, "started_iso": iso_ns(now_ns()), "tables": {}, "errors": []}
    sess = MAIN_SESS if pass_name == "main" else POST_SESS
    if rest and client is None:
        from .alpaca import Client
        client = Client("bars-reconcile", fetch_log=JsonlWriter("fetch_log", "bars-reconcile", root))
    syms = universe or (read_universe() if rest else [])
    # ---- bars_1m: live rows (collector) + REST reconcile
    rest_rows: list[dict] = []
    if rest and syms:
        try:
            rest_rows = _rest_pull(client, syms, date, sorted(sess, key=["pre", "rth", "post"].index),
                                   JsonlWriter("bars_1m", "bars-reconcile", root))
        except Exception as e:  # noqa: BLE001
            res["errors"].append(f"rest_1m: {e}"[:200])
    all_1m = list(iter_jsonl(jsonl_parts("bars_1m", date, root)))
    live = [r for r in all_1m if r.get("writer", "").split("@")[0] != "bars-reconcile"]
    rest_all = [r for r in all_1m if r.get("writer", "").split("@")[0] == "bars-reconcile"]
    merged = merge_1m(live, rest_all, now_ns(), sessions=sess)
    if pass_name == "post":
        done = parquet_keys("bars_1m", date, root)
        merged = [r for r in merged if (r["symbol"], r["bar_start_ns"]) not in done]
    p = write_table("bars_1m", date, pass_name, merged, WRITER, len(jsonl_parts("bars_1m", date, root)), root)
    res["tables"]["bars_1m"] = {"rows": len(merged), "rest_rows": len(rest_rows), "file": p and p.name,
                                "final": sum(1 for r in merged if r.get("final"))}
    for tf in ("5m", "15m", "1h"):
        rr = rollup(merged, tf, WRITER)
        p = write_table(f"bars_{tf}", date, pass_name, rr, WRITER, 0, root)
        res["tables"][f"bars_{tf}"] = {"rows": len(rr)}
    # ---- generic append tables
    for t in GENERIC:
        parts = jsonl_parts(t, date, root)
        rows = _dedupe(t, list(iter_jsonl(parts)))
        if t == "volume_5s":
            rows = [r for r in rows if r.get("session") in sess]
        if pass_name == "post":
            done = parquet_keys(t, date, root)
            rows = [r for r in rows if tuple(r.get(c) for c in KEYS[t]) not in done]
        p = write_table(t, date, pass_name, rows, WRITER, len(parts), root)
        res["tables"][t] = {"rows": len(rows), "files": len(parts)}
    # ---- validation: RTH volume_5s must be dense (61 x 4,680 on a full day)
    if pass_name == "main":
        v = [r for r in read_parquet_rows("volume_5s", date, root, columns=["symbol", "session"]) if r["session"] == "rth"]
        per = {}
        for r in v:
            per[r["symbol"]] = per.get(r["symbol"], 0) + 1
        want = RTH_BUCKETS_HALF if date in HALF_DAYS else RTH_BUCKETS_FULL
        res["validation"] = {"volume_5s_rth_rows": len(v), "symbols": len(per), "expected_per_symbol": want,
                             "short_symbols": {s: n for s, n in sorted(per.items()) if n < want}}
    # ---- bars_1d (post pass): today's official daily bar, final
    if pass_name == "post" and rest and syms:
        try:
            raw = client.bars(syms, "1Day", f"{date}T00:00:00Z", f"{date}T23:59:59Z", adjustment="raw")
            spl = client.bars(syms, "1Day", f"{date}T00:00:00Z", f"{date}T23:59:59Z", adjustment="split")
            rows = [r for r in daily_rows(raw, spl, now_ns(), WRITER) if r["trade_date"] == date]
            write_table("bars_1d", date, "post", rows, WRITER, 0, root)
            res["tables"]["bars_1d"] = {"rows": len(rows)}
        except Exception as e:  # noqa: BLE001
            res["errors"].append(f"bars_1d: {e}"[:200])
    res["finished_iso"] = iso_ns(now_ns())
    if client is not None:
        res["api_calls"] = getattr(client, "n_calls", None)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OID archive compaction")
    ap.add_argument("--pass", dest="pass_name", choices=["main", "post"], required=True)
    ap.add_argument("--date", help="ET date (default: today ET)")
    ap.add_argument("--no-rest", action="store_true", help="no Alpaca calls (Parquet from disk only)")
    ap.add_argument("--weekdays-only", action="store_true", help="exit 0 on Sat/Sun (launchd safety)")
    a = ap.parse_args(argv)
    today = dt.datetime.now(ET)
    if a.weekdays_only and today.weekday() >= 5 and not a.date:
        print(json.dumps({"skipped": "weekend"})); return 0
    date = a.date or today.strftime("%Y-%m-%d")
    res = run_pass(a.pass_name, date, rest=not a.no_rest)
    atomic_write_json(data_root() / "state" / f"compact-{a.pass_name}-status.json", res)
    print(json.dumps(res, default=str))
    return 0 if not res["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
