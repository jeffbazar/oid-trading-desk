#!/usr/bin/env python3
"""US equity session clock (America/New_York) for OID Live Book.

Returns: rth | pre | ah | closed
Weekends + NYSE full holidays → closed.
Hours (ET): PRE 04:00–09:30 · RTH 09:30–16:00 · AH 16:00–20:00 · else CLOSED.
Early-close days are treated as normal hours unless listed in EARLY_CLOSE
(AH still starts at the early close time when provided).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE full holidays (no equities session). Keep a rolling multi-year set.
NYSE_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2025
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
        # 2026
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),  # Jul 4 observed (Sat)
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
        # 2027
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 3, 26),
        date(2027, 5, 31),
        date(2027, 6, 18),  # Jun 19 Sat → Fri observe
        date(2027, 7, 5),  # Jul 4 Sun → Mon observe
        date(2027, 9, 6),
        date(2027, 11, 25),
        date(2027, 12, 24),  # Dec 25 Sat → Fri observe
    }
)

# date → cash close time (ET). Empty = use 16:00.
EARLY_CLOSE: dict[date, time] = {
    date(2025, 7, 3): time(13, 0),
    date(2025, 11, 28): time(13, 0),
    date(2025, 12, 24): time(13, 0),
    date(2026, 11, 27): time(13, 0),
    date(2026, 12, 24): time(13, 0),
    date(2027, 11, 26): time(13, 0),
}

SESSION_LABEL = {"rth": "RTH", "pre": "PRE", "ah": "AH", "closed": "CLOSED"}


def now_et(when: Optional[datetime] = None) -> datetime:
    if when is None:
        when = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(ET)


def market_session(when: Optional[datetime] = None) -> str:
    """Return lowercase session key: rth | pre | ah | closed."""
    et = now_et(when)
    d = et.date()
    if et.weekday() >= 5 or d in NYSE_HOLIDAYS:
        return "closed"
    mins = et.hour * 60 + et.minute
    rth_end = EARLY_CLOSE.get(d, time(16, 0))
    rth_end_m = rth_end.hour * 60 + rth_end.minute
    # PRE 04:00–09:30
    if 4 * 60 <= mins < 9 * 60 + 30:
        return "pre"
    # RTH 09:30–close
    if 9 * 60 + 30 <= mins < rth_end_m:
        return "rth"
    # AH close–20:00
    if rth_end_m <= mins < 20 * 60:
        return "ah"
    return "closed"



def prior_rth_close(when: Optional[datetime] = None) -> datetime:
    """Most recently *completed* regular-session close (ET-aware datetime).

    On Monday morning before open → Friday's 16:00 ET close.
    During a weekday RTH → previous trading day's close.
    After that day's cash close (AH / overnight) → today's close.
    Skips weekends and NYSE_HOLIDAYS. Honors EARLY_CLOSE when set.
    """
    from datetime import timedelta

    et = now_et(when)
    candidate = et.date()
    for _ in range(21):
        if candidate.weekday() < 5 and candidate not in NYSE_HOLIDAYS:
            rth_end = EARLY_CLOSE.get(candidate, time(16, 0))
            close_dt = datetime.combine(candidate, rth_end, tzinfo=ET)
            if et > close_dt:
                return close_dt
        candidate = candidate - timedelta(days=1)
    # Fallback: 21 calendar days back at 16:00 ET
    return datetime.combine(candidate, time(16, 0), tzinfo=ET)


def min_fresh_trade_date(when: Optional[datetime] = None) -> date:
    """Oldest ET trade date a quote may carry and still count as current.

    Trading day at/after 09:30 ET → today. Pre-market, weekend, holiday → the
    most recent completed session date. Used by quote freshness guards so a
    stale payload (e.g. a 2026-09-21 file) can never be stamped as fresh.
    """
    et = now_et(when)
    d = et.date()
    if et.weekday() < 5 and d not in NYSE_HOLIDAYS and (et.hour * 60 + et.minute) >= 9 * 60 + 30:
        return d
    return prior_rth_close(when).date()


def session_label(session: Optional[str] = None, when: Optional[datetime] = None) -> str:
    s = (session or market_session(when) or "closed").lower()
    return SESSION_LABEL.get(s, s.upper() or "CLOSED")


if __name__ == "__main__":
    s = market_session()
    et = now_et()
    pc = prior_rth_close()
    print(f"{et.isoformat()} → {s} ({session_label(s)})")
    print(f"prior_rth_close → {pc.isoformat()}")
