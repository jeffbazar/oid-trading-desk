#!/usr/bin/env python3
"""Quote freshness guard (added 2026-10-07 after the 12:59 PM PT stale-payload incident).

The 12:58/12:59 PM PT dashboard live refresh read /workspace/tmp/oid-live-equity.json
(a 2026-09-21 payload left over from the 10/05 box seed) and refresh_marks.py stamped
it into rh-quotes.json / market-tape.json with a fresh 2026-10-07 as_of.

Rule: a quote is STALE when its newest venue trade/update time (ET date) is older than
market_session.min_fresh_trade_date() — i.e. not today during/after RTH, or not the last
completed session during pre-market / weekends / holidays.

Writers drop stale symbols and, when the stale share is >= STALE_ABORT_FRACTION,
refuse the write entirely (exit code 3) so nothing gets a fresh stamp.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from market_session import ET, min_fresh_trade_date

STALE_ABORT_FRACTION = 0.5
STALE_EXIT_CODE = 3


def _parse(ts: Any) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # Python <3.11 fromisoformat chokes on >6 fractional digits (RH sends nanoseconds)
    if "." in raw:
        head, _, tail = raw.partition(".")
        frac = ""
        rest = ""
        for i, ch in enumerate(tail):
            if ch.isdigit():
                frac += ch
            else:
                rest = tail[i:]
                break
        raw = f"{head}.{frac[:6].ljust(6, '0')}{rest}" if frac else f"{head}{rest}"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # 2026-10-08: RH sends 0001-01-01T00:00:00Z as a null sentinel for expired/dead
    # contracts; astimezone() on that overflows. Treat pre-1971 as no timestamp.
    if dt.year < 1971:
        return None
    return dt


def newest_time(times: Iterable[Any]) -> Optional[datetime]:
    parsed = [d for d in (_parse(t) for t in times) if d is not None]
    return max(parsed) if parsed else None


def check_quotes(
    quotes: dict[str, dict],
    time_keys: tuple[str, ...],
    *,
    when: Optional[datetime] = None,
) -> dict[str, Any]:
    """Split ``quotes`` into fresh vs stale by trade-time ET date.

    Symbols with no parseable time are kept but listed in ``undated``.
    """
    floor = min_fresh_trade_date(when)
    fresh: dict[str, dict] = {}
    stale: dict[str, str] = {}
    undated: list[str] = []
    for key, q in quotes.items():
        if not isinstance(q, dict):
            continue
        newest = newest_time(q.get(k) for k in time_keys)
        if newest is None:
            undated.append(key)
            fresh[key] = q
            continue
        d = newest.astimezone(ET).date()
        if d < floor:
            stale[key] = d.isoformat()
        else:
            fresh[key] = q
    dated = len(quotes) - len(undated)
    frac = (len(stale) / dated) if dated else 0.0
    return {
        "fresh": fresh,
        "stale": stale,
        "undated": undated,
        "min_trade_date": floor.isoformat(),
        "stale_fraction": round(frac, 3),
        "abort": bool(stale) and frac >= STALE_ABORT_FRACTION,
    }


EQUITY_TIME_KEYS = ("last_trade_time", "last_non_reg_time", "venue_last_trade_time", "venue_last_non_reg_trade_time")
OPTION_TIME_KEYS = ("quoted_at",)
