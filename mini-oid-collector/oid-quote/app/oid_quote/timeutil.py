"""Time helpers: PT-aware ISO stamps, RFC-3339 (ns) parsing, msgpack timestamps, session tags."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

try:
    from zoneinfo import ZoneInfo

    PT = ZoneInfo("America/Los_Angeles")
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - macOS always ships /usr/share/zoneinfo
    PT = dt.timezone(dt.timedelta(hours=-7), "PT")
    ET = dt.timezone(dt.timedelta(hours=-4), "ET")

UTC = dt.timezone.utc


def now() -> float:
    return time.time()


def epoch_to_pt_iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return dt.datetime.fromtimestamp(epoch, PT).isoformat(timespec="milliseconds")


def now_pt_iso() -> str:
    return epoch_to_pt_iso(time.time())  # type: ignore[return-value]


def _iso_utc_ns(seconds: int, nanos: int) -> str:
    base = dt.datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{nanos:09d}Z"


def parse_rfc3339(value: str) -> tuple[float | None, str]:
    """Parse '2024-03-11T13:35:35.13312256Z' (any fraction length / offset) -> (epoch, original)."""
    s = value.strip()
    try:
        tz_part = ""
        if s.endswith("Z") or s.endswith("z"):
            core, tz_part = s[:-1], "+00:00"
        else:
            # find offset sign after the time portion
            idx = max(s.rfind("+"), s.rfind("-"))
            if idx > 10:
                core, tz_part = s[:idx], s[idx:]
            else:
                core, tz_part = s, "+00:00"
        frac = 0.0
        if "." in core:
            core, frac_s = core.split(".", 1)
            frac = float("0." + frac_s) if frac_s.isdigit() else 0.0
        d = dt.datetime.fromisoformat(core + tz_part)
        return d.timestamp() + frac, s
    except Exception:
        return None, s


def coerce_ts(value: Any) -> tuple[float | None, str | None]:
    """Accept RFC-3339 strings, msgpack Timestamp objects, datetimes, or epoch numbers."""
    if value is None:
        return None, None
    if isinstance(value, str):
        return parse_rfc3339(value)
    # msgpack.Timestamp duck-typing (seconds, nanoseconds)
    secs = getattr(value, "seconds", None)
    nanos = getattr(value, "nanoseconds", None)
    if isinstance(secs, int) and isinstance(nanos, int):
        return secs + nanos / 1e9, _iso_utc_ns(secs, nanos)
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        e = value.timestamp()
        return e, value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (int, float)):
        e = float(value)
        if e > 1e17:  # nanoseconds
            e = e / 1e9
        elif e > 1e14:  # microseconds
            e = e / 1e6
        elif e > 1e11:  # milliseconds
            e = e / 1e3
        return e, dt.datetime.fromtimestamp(e, UTC).isoformat().replace("+00:00", "Z")
    return None, str(value)


OVERNIGHT_START_MIN = 20 * 60  # 8:00 PM ET
OVERNIGHT_END_MIN = 4 * 60  # 4:00 AM ET


def in_overnight_window(epoch: float | None) -> bool:
    """Alpaca/BOATS overnight session window by ET wall clock: 20:00-04:00, Sun night -> Fri morning.

    Evening half (>=20:00) counts Sun-Thu; morning half (<04:00) counts Mon-Fri.
    Exchange holidays are not modeled (a holiday night just carries no data).
    """
    if epoch is None:
        return False
    t = dt.datetime.fromtimestamp(epoch, ET)
    minutes = t.hour * 60 + t.minute
    wd = t.weekday()  # Mon=0 .. Sun=6
    if minutes >= OVERNIGHT_START_MIN:
        return wd in (6, 0, 1, 2, 3)
    if minutes < OVERNIGHT_END_MIN:
        return wd in (0, 1, 2, 3, 4)
    return False


def scheduled_stock_feed(epoch: float, day_feed: str, overnight_feed: str | None) -> str:
    """Which single stock websocket feed should be open now: overnight 20:00-04:00 ET, else the day (SIP) feed."""
    if overnight_feed and in_overnight_window(epoch):
        return overnight_feed
    return day_feed


def next_feed_switch_at(epoch: float, day_feed: str, overnight_feed: str | None, horizon_s: int = 8 * 86400) -> float | None:
    """Epoch of the next scheduled feed change (minute resolution), or None when switching is off."""
    if not overnight_feed:
        return None
    cur = scheduled_stock_feed(epoch, day_feed, overnight_feed)
    t = (int(epoch) // 60 + 1) * 60
    end = epoch + horizon_s
    while t <= end:
        if scheduled_stock_feed(t, day_feed, overnight_feed) != cur:
            return float(t)
        t += 60
    return None


def session_for(epoch: float | None) -> str:
    """US equities/options session by ET wall clock.

    RTH 09:30-16:00, extended 04:00-20:00 (weekdays), overnight 20:00-04:00 (Sun night -> Fri morning),
    else closed. Exchange holidays are not modeled (MVP); a holiday prints as RTH/extended only if data arrives.
    """
    if epoch is None:
        return "closed"
    if in_overnight_window(epoch):
        return "overnight"
    t = dt.datetime.fromtimestamp(epoch, ET)
    if t.weekday() >= 5:
        return "closed"
    minutes = t.hour * 60 + t.minute
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "RTH"
    if 4 * 60 <= minutes < 20 * 60:
        return "extended"
    return "closed"
