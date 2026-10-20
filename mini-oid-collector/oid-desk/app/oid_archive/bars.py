"""Alpaca bar dicts -> frozen bars_1m / bars_1d rows, and the live-vs-REST reconcile merge."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .common import HALF_DAYS, NS, common, et_date, iso_ns, parse_iso_ns, session_of

PX = ("open", "high", "low", "close")
_A = {"o": "open", "h": "high", "l": "low", "c": "close"}


def rest_1m_row(sym: str, b: dict[str, Any], ingest_ns: int, writer: str, final: bool = True,
                src: str = "alpaca-rest", feed: str = "sip") -> Optional[dict[str, Any]]:
    start = parse_iso_ns(b["t"])
    sess = session_of(start)
    if sess is None:  # overnight / weekend prints are not stored in v1
        return None
    row = {"symbol": sym, "timeframe": "1m", "bar_start_ns": start, "bar_start_iso": iso_ns(start),
           "bar_end_ns": start + 60 * NS, "session": sess, **{v: b.get(k) for k, v in _A.items()},
           "volume": b.get("v"), "vwap": b.get("vw"), "trade_count": b.get("n"), "src": src, "feed": feed,
           "adjustment": "raw", "final": final, "revised_ts_ns": None}
    row.update(common(start, ingest_ns, writer))
    return row


def daily_rows(raw: dict[str, list], split: dict[str, list], ingest_ns: int, writer: str, final: bool = True,
               half_days: Iterable[str] = HALF_DAYS) -> list[dict[str, Any]]:
    hd = set(half_days)
    out = []
    for sym, bs in raw.items():
        sp = {b["t"]: b for b in split.get(sym) or []}
        for b in bs:
            start = parse_iso_ns(b["t"])
            d = et_date(start)
            s = sp.get(b["t"])
            f = None
            if s and s.get("c") and b.get("c"):
                f = round(float(b["c"]) / float(s["c"]), 6)
            row = {"symbol": sym, "trade_date": d, "bar_start_ns": start, "bar_start_iso": iso_ns(start),
                   **{v: b.get(k) for k, v in _A.items()}, "volume": b.get("v"), "vwap": b.get("vw"),
                   "trade_count": b.get("n"), "split_factor": f if f is not None else 1.0, "half_day": d in hd,
                   "src": "alpaca-rest", "final": final}
            row.update(common(start, ingest_ns, writer))
            out.append(row)
    return out


def _differs(a: dict, b: dict) -> bool:
    if int(a.get("volume") or 0) != int(b.get("volume") or 0):
        return True
    return any(a.get(k) is not None and b.get(k) is not None and abs(float(a[k]) - float(b[k])) > 1e-9 for k in PX)


def merge_1m(live: Iterable[dict], rest: Iterable[dict], reconcile_ns: int,
             sessions: Optional[set] = None) -> list[dict[str, Any]]:
    """Live (collector) rows keep their ingest_ts (point-in-time); REST is the volume of record. A live row whose
    OHLCV differs from REST takes the REST values and gets revised_ts_ns. REST-only bars are added. Every bar REST
    confirms is final=true; live-only bars stay final=false."""
    lv: dict[tuple, dict] = {}
    for r in sorted(live, key=lambda r: r["ingest_ts_ns"]):
        if sessions and r.get("session") not in sessions:
            continue
        k = (r["symbol"], r["bar_start_ns"])
        lv.setdefault(k, dict(r))  # first arrival wins (point-in-time)
        if r.get("src") == "alpaca-ws-updated":  # updatedBars correction seen live: apply, keep first ingest
            base = lv[k]
            for c in PX + ("volume", "vwap", "trade_count"):
                base[c] = r.get(c)
            base["revised_ts_ns"] = r["ingest_ts_ns"]
    rs: dict[tuple, dict] = {}
    for r in sorted(rest, key=lambda r: r["ingest_ts_ns"]):
        if sessions and r.get("session") not in sessions:
            continue
        rs[(r["symbol"], r["bar_start_ns"])] = r  # latest REST pull wins
    out = []
    for k in sorted(set(lv) | set(rs)):
        a, b = lv.get(k), rs.get(k)
        if a and b:
            m = dict(a)
            if _differs(a, b):
                for c in PX + ("volume", "vwap", "trade_count"):
                    m[c] = b.get(c)
                m["revised_ts_ns"] = reconcile_ns
            elif b.get("vwap") is not None and m.get("vwap") is None:
                m["vwap"] = b["vwap"]
            m["final"] = True
            out.append(m)
        elif b:
            out.append(dict(b, final=True))
        else:
            out.append(dict(a, final=False))
    return out
