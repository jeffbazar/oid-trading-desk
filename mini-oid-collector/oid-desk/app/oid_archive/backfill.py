"""One-time 1-year backfill of 1-minute (+ daily) SIP bars from Alpaca REST into Parquet (src=alpaca-rest,
excluded from forward evaluation). Resumable; one request covers all symbols for a 7-day chunk (paged, 10k/page).

  python -m oid_archive.backfill --depth-test NVDA        # 1 symbol: how far back 1Min/1Day go; writes no bars
  python -m oid_archive.backfill --full [--days 365]      # all universe symbols, resumable (state file)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from typing import Any, Optional

from .bars import daily_rows, rest_1m_row
from .common import ET, JsonlWriter, WRITER, archive_root, atomic_write_json, data_root, et_date, iso_ns, now_ns, \
    read_universe
from .pq import write_table
from .rollup import rollup

STATE = "backfill-status.json"


def depth_test(client, sym: str, days: int = 365) -> dict[str, Any]:
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=days + 3)
    t0 = time.time()
    first = client.get("/v2/stocks/bars", {"symbols": sym, "timeframe": "1Min", "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           "end": (start + dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           "feed": "sip", "adjustment": "raw", "limit": 10000, "sort": "asc"}, symbols=sym)
    bs = (first.get("bars") or {}).get(sym) or []
    daily = client.bars([sym], "1Day", (end - dt.timedelta(days=days + 10)).strftime("%Y-%m-%dT00:00:00Z"),
                        end.strftime("%Y-%m-%dT%H:%M:%SZ"))
    ds = daily.get(sym) or []
    return {"symbol": sym, "requested_start": start.strftime("%Y-%m-%d"), "minute_bars_first_week": len(bs),
            "first_minute_bar": bs[0]["t"] if bs else None, "has_more_pages": bool(first.get("next_page_token")),
            "daily_bars": len(ds), "first_daily": ds[0]["t"] if ds else None, "last_daily": ds[-1]["t"] if ds else None,
            "rate_limit": client.last_rl, "calls": client.n_calls, "elapsed_s": round(time.time() - t0, 2),
            "ok": bool(bs) and len(ds) >= 240}


def _chunks(start: dt.date, end: dt.date, days: int):
    a = start
    while a < end:
        b = min(end, a + dt.timedelta(days=days))
        yield a, b
        a = b


def _utc(d: dt.date) -> str:
    # midnight ET of date d, as UTC RFC3339 (chunks align to ET trading dates)
    return dt.datetime(d.year, d.month, d.day, tzinfo=ET).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def full(client, syms: list[str], days: int = 365, chunk_days: int = 7, force: bool = False,
         root=None, end_date: Optional[dt.date] = None, log=print) -> dict[str, Any]:
    root = root or archive_root()
    sp = data_root() / "state" / STATE
    try:
        st = json.loads(sp.read_text()) if sp.exists() and not force else {}
    except ValueError:
        st = {}
    end = end_date or dt.datetime.now(ET).date()  # exclusive: today is left to the live writers + daily passes
    start = end - dt.timedelta(days=days)
    done = set(st.get("chunks_done", []))
    st.update({"symbols": len(syms), "start": start.isoformat(), "end_exclusive": end.isoformat(),
               "started_iso": st.get("started_iso") or iso_ns(now_ns())})
    st.setdefault("rows_1m", 0); st.setdefault("dates", 0)
    t0 = time.time()
    for a, b in _chunks(start, end, chunk_days):
        key = f"{a}..{b}"
        if key in done:
            continue
        got = client.bars(syms, "1Min", _utc(a), _utc(b))
        ing = now_ns()
        by_date: dict[str, list] = {}
        for sym, bs in got.items():
            for b_ in bs:
                r = rest_1m_row(sym, b_, ing, WRITER, final=True)
                if r:
                    by_date.setdefault(et_date(r["bar_start_ns"]), []).append(r)
        for date, rows in sorted(by_date.items()):
            write_table("bars_1m", date, "backfill", rows, WRITER, 0, root)
            for tf in ("5m", "15m", "1h"):
                write_table(f"bars_{tf}", date, "backfill", rollup(rows, tf, WRITER), WRITER, 0, root)
            st["rows_1m"] += len(rows); st["dates"] += 1
        done.add(key)
        st.update({"chunks_done": sorted(done), "calls": client.n_calls, "bytes": client.bytes,
                   "elapsed_s": round(time.time() - t0, 1), "updated_iso": iso_ns(now_ns())})
        atomic_write_json(sp, st)
        log(json.dumps({"chunk": key, "dates": len(by_date), "rows": sum(len(v) for v in by_date.values()),
                        "calls": client.n_calls}))
    if not st.get("daily_done"):
        raw = client.bars(syms, "1Day", _utc(start), _utc(end), adjustment="raw")
        spl = client.bars(syms, "1Day", _utc(start), _utc(end), adjustment="split")
        rows = daily_rows(raw, spl, now_ns(), WRITER)
        by: dict[str, list] = {}
        for r in rows:
            by.setdefault(r["trade_date"], []).append(r)
        for date, rs in by.items():
            write_table("bars_1d", date, "backfill", rs, WRITER, 0, root)
        st.update({"daily_done": True, "rows_1d": len(rows)})
    st.update({"finished_iso": iso_ns(now_ns()), "calls": client.n_calls, "bytes": client.bytes})
    atomic_write_json(sp, st)
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OID 1-year Alpaca bar backfill (data-only)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--depth-test", metavar="SYM")
    g.add_argument("--full", action="store_true")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--chunk-days", type=int, default=7)
    ap.add_argument("--max-per-min", type=int, default=150)
    ap.add_argument("--symbols", help="comma list (default: collector universe)")
    ap.add_argument("--force", action="store_true", help="ignore the resume state")
    a = ap.parse_args(argv)
    from .alpaca import Client
    client = Client("bars-backfill", max_per_min=a.max_per_min, fetch_log=JsonlWriter("fetch_log", "bars-backfill"))
    if a.depth_test:
        print(json.dumps(depth_test(client, a.depth_test.upper(), a.days), default=str))
        return 0
    syms = [s.strip().upper() for s in a.symbols.split(",")] if a.symbols else read_universe()
    st = full(client, syms, a.days, a.chunk_days, a.force)
    print(json.dumps({k: v for k, v in st.items() if k != "chunks_done"}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
