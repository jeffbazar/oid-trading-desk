#!/usr/bin/env python3
"""OID paper-trade outcome fields helper (research / paper only)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo


def _fq(v):
    """Paper seat size: int when whole; fractional after a scale-out (e.g. 0.5). 2026-10-08 SCALE_OUT_+20PCT."""
    try:
        q = float(v)
    except (TypeError, ValueError):
        return 1
    if q <= 0:
        return 1
    return int(q) if q.is_integer() else q


PT = ZoneInfo("America/Los_Angeles")

OUTCOME_TAGS = frozenset({
    "win_exit",
    "win_open",
    "thesis_fail",
    "time_decay",
    "event_whip",
    "chase_fail",
    "loss_exit",
    "other",
})


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_pt(dt: Optional[datetime] = None) -> str:
    dt = dt or _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(PT)
    # e.g. 2026-09-17 7:51 AM PT
    return local.strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")


def entry_ref(trade: dict) -> Optional[float]:
    for k in ("entryAsk", "entryMark", "entryBid"):
        v = trade.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def qty(trade: dict) -> int:
    q = trade.get("qtySuggested", 1)
    try:
        return _fq(q)
    except (TypeError, ValueError):
        return 1


def compute_mfe_mae(trade: dict) -> None:
    entry = entry_ref(trade)
    peak = trade.get("peakMark")
    trough = trade.get("troughMark")
    if entry is None or entry == 0:
        return
    q = qty(trade)
    if isinstance(peak, (int, float)):
        trade["mfePct"] = round((float(peak) - entry) / entry * 100.0, 2)
        trade["mfeUsd"] = round((float(peak) - entry) * q * 100.0, 2)
    if isinstance(trough, (int, float)):
        trade["maePct"] = round((float(trough) - entry) / entry * 100.0, 2)
        trade["maeUsd"] = round((float(trough) - entry) * q * 100.0, 2)


def end_time_for_hold(trade: dict) -> datetime:
    status = (trade.get("status") or "").lower()
    if status in ("closed", "stopped", "expired"):
        for k in ("exitAt", "closedAt", "updatedAt"):
            dt = _parse_iso(trade.get(k))
            if dt:
                return dt
    if status == "invalidated":
        for k in ("invalidatedAt", "exitAt", "updatedAt"):
            dt = _parse_iso(trade.get(k))
            if dt:
                return dt
    return _now_utc()


def compute_hold_hours(trade: dict) -> None:
    start = _parse_iso(trade.get("offeredAt"))
    if not start:
        return
    end = end_time_for_hold(trade)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    hours = (end - start).total_seconds() / 3600.0
    trade["holdHours"] = round(max(0.0, hours), 2)


def init_outcome_on_elevate(trade: dict, at_pt: Optional[str] = None) -> dict:
    """Seed peak/trough at entry on elevation."""
    entry = entry_ref(trade)
    if entry is None:
        return trade
    stamp = at_pt or trade.get("offeredAtPT") or format_pt()
    trade["peakMark"] = float(entry)
    trade["troughMark"] = float(entry)
    trade["peakMarkAtPT"] = stamp
    trade["troughMarkAtPT"] = stamp
    trade["mfeMaePartial"] = False
    compute_mfe_mae(trade)
    compute_hold_hours(trade)
    if trade.get("status") in ("open", "watching", "paper", "live") and trade.get("outcomeTag") is None:
        trade["outcomeTag"] = "win_open" if float(trade.get("lastMark") or entry) >= entry else "other"
    return trade


def apply_mark_update(
    trade: dict,
    mark: float,
    at_pt: Optional[str] = None,
    *,
    partial_ok: bool = False,
) -> dict:
    """Update lastMark path + peak/trough MFE/MAE. Does not place orders."""
    mark = float(mark)
    stamp = at_pt or format_pt()
    trade["lastMark"] = mark
    entry = entry_ref(trade)

    if trade.get("peakMark") is None or trade.get("troughMark") is None:
        # Seed from entry then apply mark
        if entry is not None:
            init_outcome_on_elevate(trade, at_pt=trade.get("offeredAtPT") or stamp)
            if partial_ok:
                trade["mfeMaePartial"] = True
        else:
            trade["peakMark"] = mark
            trade["troughMark"] = mark
            trade["peakMarkAtPT"] = stamp
            trade["troughMarkAtPT"] = stamp
            trade["mfeMaePartial"] = True

    if mark > float(trade["peakMark"]):
        trade["peakMark"] = mark
        trade["peakMarkAtPT"] = stamp
    if mark < float(trade["troughMark"]):
        trade["troughMark"] = mark
        trade["troughMarkAtPT"] = stamp

    compute_mfe_mae(trade)
    compute_hold_hours(trade)

    status = (trade.get("status") or "").lower()
    if status in ("open", "watching", "paper", "live") and entry is not None:
        if mark >= entry:
            trade["outcomeTag"] = trade.get("outcomeTag") if trade.get("outcomeTag") in (
                "win_open",
            ) or trade.get("result") else "win_open"
            if trade.get("outcomeTag") not in OUTCOME_TAGS or trade.get("outcomeTag") in (None, "other"):
                trade["outcomeTag"] = "win_open"
        # Keep existing outcomeTag if already set to something specific while open
        if not trade.get("outcomeTag"):
            trade["outcomeTag"] = "win_open" if mark >= entry else "other"

    # Unrealized helpers (paper opens + external Leopold/ZH watches)
    if entry is not None and status in (
        "open", "watching", "paper", "live", "leopold_watch", "watch_external"
    ):
        q = qty(trade)
        trade["unrealizedPnlPct"] = round((mark - entry) / entry * 100.0, 2)
        trade["unrealizedPnlUsd"] = round((mark - entry) * q * 100.0, 2)
        trade["pnlPct"] = trade["unrealizedPnlPct"]
        trade["pnlUsd"] = trade["unrealizedPnlUsd"]

    return trade


def finalize_outcome(
    trade: dict,
    *,
    outcome_tag: str,
    lesson: str,
    refine_hint: str,
    result: Optional[str] = None,
) -> dict:
    if outcome_tag not in OUTCOME_TAGS:
        raise ValueError(f"outcomeTag must be one of {sorted(OUTCOME_TAGS)}")
    trade["outcomeTag"] = outcome_tag
    trade["lesson"] = lesson.strip()
    trade["refineHint"] = refine_hint.strip()
    if result is not None:
        trade["result"] = result
    # Include final mark in peak/trough if present
    lm = trade.get("lastMark")
    if isinstance(lm, (int, float)):
        apply_mark_update(trade, float(lm), at_pt=trade.get("updatedAtPT") or trade.get("invalidatedAtPT"))
    ensure_outcome_fields(trade)
    return trade


def ensure_outcome_fields(trade: dict) -> dict:
    """Idempotent: fill derived MFE/MAE/holdHours; seed peak/trough if missing."""
    entry = entry_ref(trade)
    lm = trade.get("lastMark")
    if trade.get("peakMark") is None or trade.get("troughMark") is None:
        seed = None
        if isinstance(lm, (int, float)):
            seed = float(lm)
        elif entry is not None:
            seed = float(entry)
        if seed is not None:
            if trade.get("peakMark") is None:
                trade["peakMark"] = seed
                trade["peakMarkAtPT"] = trade.get("peakMarkAtPT") or trade.get("lastMarkedAtPT") or trade.get("updatedAtPT") or "unknown"
            if trade.get("troughMark") is None:
                trade["troughMark"] = seed if entry is None else min(seed, float(entry))
                trade["troughMarkAtPT"] = trade.get("troughMarkAtPT") or trade.get("offeredAtPT") or "unknown"
            # If we only have lastMark and not a recovered series, flag partial
            if trade.get("mfeMaePartial") is None:
                trade["mfeMaePartial"] = True
            # Ensure peak >= trough and peak includes entry
            if entry is not None:
                trade["peakMark"] = max(float(trade["peakMark"]), float(entry))
                trade["troughMark"] = min(float(trade["troughMark"]), float(entry))

    compute_mfe_mae(trade)
    compute_hold_hours(trade)

    tag = trade.get("outcomeTag")
    if tag and tag not in OUTCOME_TAGS:
        trade["outcomeTag"] = "other"
    if not tag:
        status = (trade.get("status") or "").lower()
        result = trade.get("result")
        if status == "closed" and result == "win":
            trade["outcomeTag"] = "win_exit"
        elif status == "invalidated" or result == "thesis_fail":
            trade["outcomeTag"] = "thesis_fail"
        elif status in ("open", "watching", "paper", "live"):
            if entry is not None and isinstance(lm, (int, float)) and float(lm) >= entry:
                trade["outcomeTag"] = "win_open"
            else:
                trade["outcomeTag"] = "other"
        else:
            trade["outcomeTag"] = "other"

    trade.setdefault("lesson", "")
    trade.setdefault("refineHint", "")
    return trade


def validate_outcome_tag(tag: str) -> bool:
    return tag in OUTCOME_TAGS
