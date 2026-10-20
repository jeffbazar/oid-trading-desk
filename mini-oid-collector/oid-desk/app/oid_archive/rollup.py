"""bars_1m -> bars_5m/15m/1h (SCHEMAS §5): never span a session; 5m/15m on ET clock multiples; RTH 1h anchored
at 09:30 ET (15:30-16:00 is a 30-min bar); pre/post 1h on ET clock hours (09:00-09:30 short)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from .common import ET, HALF_DAYS, NS, common, iso_ns

TF_MIN = {"5m": 5, "15m": 15, "1h": 60}
SESSION_MIN = {"pre": (240, 570), "rth": (570, 960), "post": (960, 1200)}


def _bounds(date: str, session: str, half_days) -> tuple[int, int]:
    a, b = SESSION_MIN[session]
    if date in half_days:
        if session == "rth":
            b = 780
        elif session == "post":
            a = 780
    return a, b


def _midnight_ns(date: str) -> int:
    d = dt.date.fromisoformat(date)
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS


def _min_ns(date: str, minute: int) -> int:
    # DST-safe: build the wall-clock time in ET rather than adding minutes to midnight
    d = dt.date.fromisoformat(date)
    return int(dt.datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=ET).timestamp()) * NS


def bucket_minutes(minute: int, session: str, tf: str, date: str, half_days=HALF_DAYS) -> tuple[int, int]:
    size = TF_MIN[tf]
    a, b = _bounds(date, session, set(half_days))
    if tf == "1h" and session == "rth":
        k = 570 + ((minute - 570) // 60) * 60
    else:
        k = minute - minute % size
    return max(k, a), min(k + size, b)


def rollup(bars: Iterable[dict[str, Any]], tf: str, writer: str, half_days=HALF_DAYS) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict]] = {}
    for b in bars:
        if b.get("session") not in SESSION_MIN or b.get("volume") is None:
            continue
        t = dt.datetime.fromtimestamp(b["bar_start_ns"] / NS, ET)
        date, minute = t.strftime("%Y-%m-%d"), t.hour * 60 + t.minute
        s, e = bucket_minutes(minute, b["session"], tf, date, half_days)
        if not s <= minute < e:
            continue  # bar outside its own session bounds (should not happen)
        groups.setdefault((b["symbol"], date, b["session"], s, e), []).append(b)
    out = []
    for (sym, date, sess, s, e), bs in sorted(groups.items()):
        bs.sort(key=lambda r: r["bar_start_ns"])
        start, end = _min_ns(date, s), _min_ns(date, e)
        vol = sum(int(r["volume"] or 0) for r in bs)
        pv = sum(float(r["vwap"]) * int(r["volume"] or 0) for r in bs if r.get("vwap") is not None)
        vv = sum(int(r["volume"] or 0) for r in bs if r.get("vwap") is not None)
        highs = [r["high"] for r in bs if r.get("high") is not None]
        lows = [r["low"] for r in bs if r.get("low") is not None]
        revs = [r["revised_ts_ns"] for r in bs if r.get("revised_ts_ns") is not None]
        row = {"symbol": sym, "timeframe": tf, "bar_start_ns": start, "bar_start_iso": iso_ns(start), "bar_end_ns": end,
               "session": sess, "open": bs[0].get("open"), "high": max(highs) if highs else None,
               "low": min(lows) if lows else None, "close": bs[-1].get("close"), "volume": vol,
               "vwap": (pv / vv) if vv else None, "trade_count": sum(int(r.get("trade_count") or 0) for r in bs),
               "src": "rollup", "feed": bs[0].get("feed"), "adjustment": "raw",
               "final": all(bool(r.get("final")) for r in bs), "revised_ts_ns": max(revs) if revs else None,
               "n_1m_bars": len(bs), "span_s": (end - start) // NS}
        # point-in-time: a rollup is knowable once its last input was
        row.update(common(start, max(int(r["ingest_ts_ns"]) for r in bs), writer))
        out.append(row)
    return out
