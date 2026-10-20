#!/usr/bin/env python3
"""OID book-level soft close triggers — alerts only (ZERO execution / no RH orders).

Primary book = Rose / OID open paper seats (exclude Leopold watches, exclude Hal/OT2).
Optional shared-book line includes all open paper seats (Rose + Hal).

See CLOSE-TRIGGERS-V1.md § Book aggregate. Soft only — never auto-closes seats.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
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

ROOT = Path(__file__).resolve().parent.parent
PT_DIR = Path(__file__).resolve().parent
BOOK_STATE_PATH = PT_DIR / "book-state.json"

OPEN_STATUSES = frozenset({"open", "watching", "paper", "live"})

BOOK_TP_USD = 1000.0
BOOK_TP_PCT = 30.0
BOOK_GIVEBACK_FRAC = 0.50  # current <= peak * 0.5 when peak > 0


def _f(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def format_pt(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(PT)
    return local.strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")


def entry_ref(trade: dict) -> Optional[float]:
    for k in ("entryAsk", "entryMark", "entryBid", "costBasis"):
        x = _f(trade.get(k))
        if x is not None and x != 0:
            return x
    return None


def seat_qty(trade: dict) -> int:
    try:
        return _fq(trade.get("qtySuggested") or 1)
    except (TypeError, ValueError):
        return 1


def seat_pnl_usd(trade: dict) -> float:
    u = _f(trade.get("pnlUsd")) or _f(trade.get("unrealizedPnlUsd"))
    if u is not None:
        return u
    entry = entry_ref(trade)
    last = _f(trade.get("lastMark")) or _f(trade.get("lastOptionMark"))
    if entry is None or last is None:
        return 0.0
    return (last - entry) * 100.0 * seat_qty(trade)


def seat_premium_usd(trade: dict) -> float:
    """Open-book premium = entryAsk × 100 × qty."""
    entry = entry_ref(trade)
    if entry is None:
        return 0.0
    return entry * 100.0 * seat_qty(trade)


def agent_label(t: dict) -> str:
    a = (t.get("agent") or "").strip()
    if a in ("Hal", "Rose", "Leopold"):
        return a
    if a.startswith("ZH/") or "Leopold" in a or t.get("desk") == "ZH":
        return "Leopold"
    if "Hal" in a or str(t.get("id", "")).startswith("OT2-") or t.get("desk") == "OT2":
        return "Hal"
    return "Rose"


def is_open_paper(t: dict) -> bool:
    return (t.get("status") or "").lower() in OPEN_STATUSES


def is_rose_oid_seat(t: dict) -> bool:
    """Primary Rose book: open paper, agent Rose / desk OID; exclude Leopold + Hal/OT2."""
    if not is_open_paper(t):
        return False
    label = agent_label(t)
    if label in ("Leopold", "Hal"):
        return False
    desk = (t.get("desk") or "").upper()
    if desk in ("OT2", "ZH"):
        return False
    if label != "Rose":
        return False
    if desk and desk not in ("OID", ""):
        return False
    return True


def is_shared_paper_seat(t: dict) -> bool:
    """Shared book: all open paper seats (Rose + Hal); exclude Leopold watches."""
    if not is_open_paper(t):
        return False
    return agent_label(t) != "Leopold"


def _sum_book(seats: list[dict]) -> dict:
    pnl = sum(seat_pnl_usd(t) for t in seats)
    prem = sum(seat_premium_usd(t) for t in seats)
    pct = (pnl / prem * 100.0) if prem else None
    return {
        "seatCount": len(seats),
        "seatIds": [t.get("id") for t in seats],
        "symbols": [t.get("symbol") for t in seats],
        "pnlUsd": round(pnl, 2),
        "premiumUsd": round(prem, 2),
        "pnlPct": round(pct, 2) if pct is not None else None,
    }


def _load_prior_peak(ledger: dict) -> tuple[Optional[float], Optional[str]]:
    meta = ledger.get("meta") or {}
    peak = _f(meta.get("bookPeakPnlUsd"))
    peak_at = meta.get("bookPeakAtPT")
    if peak is None and BOOK_STATE_PATH.exists():
        try:
            st = json.loads(BOOK_STATE_PATH.read_text())
            rose = (st.get("rose") or st) if isinstance(st, dict) else {}
            peak = _f(rose.get("bookPeakPnlUsd"))
            peak_at = rose.get("bookPeakAtPT") or peak_at
        except (json.JSONDecodeError, OSError):
            pass
    return peak, peak_at if isinstance(peak_at, str) else None


def score_book(
    ledger: dict,
    *,
    mutate: bool = True,
    persist_book_state: bool = True,
) -> dict:
    """Score Rose primary book (+ optional shared). Updates peak in ledger meta when mutate."""
    trades = ledger.get("trades") or []
    rose_seats = [t for t in trades if is_rose_oid_seat(t)]
    shared_seats = [t for t in trades if is_shared_paper_seat(t)]

    rose = _sum_book(rose_seats)
    shared = _sum_book(shared_seats)

    prior_peak, prior_peak_at = _load_prior_peak(ledger)
    current = rose["pnlUsd"]
    peak = prior_peak
    peak_at = prior_peak_at
    peak_updated = False
    if peak is None:
        peak = current
        peak_at = format_pt()
        peak_updated = True
    elif current > peak:
        peak = current
        peak_at = format_pt()
        peak_updated = True

    giveback_pct = None
    if peak is not None and peak > 0:
        giveback_pct = round(max(0.0, (1.0 - (current / peak)) * 100.0), 2)

    flags: list[str] = []
    alerts: list[str] = []
    note_bits: list[str] = []

    # BOOK_TP → BOOK_CLOSE_REVIEW
    tp_usd = current >= BOOK_TP_USD
    tp_pct = rose["pnlPct"] is not None and rose["pnlPct"] >= BOOK_TP_PCT
    book_tp = bool(tp_usd or tp_pct)
    if book_tp:
        flags.append("BOOK_TP")
        alerts.append("BOOK_CLOSE_REVIEW")
        reasons = []
        if tp_usd:
            reasons.append(f"book unrealized ${current:.0f} >= +${BOOK_TP_USD:.0f}")
        if tp_pct:
            reasons.append(f"book pnlPct {rose['pnlPct']:.1f}% >= +{BOOK_TP_PCT:.0f}%")
        note_bits.append("BOOK_TP: " + " OR ".join(reasons))

    # BOOK_GIVEBACK when peak > 0 and current <= peak * 0.5
    book_giveback = False
    if peak is not None and peak > 0 and current <= peak * BOOK_GIVEBACK_FRAC:
        book_giveback = True
        flags.append("BOOK_GIVEBACK")
        alerts.append("BOOK_GIVEBACK")
        note_bits.append(
            f"BOOK_GIVEBACK: current ${current:.0f} <= {BOOK_GIVEBACK_FRAC:.0%} of peak "
            f"${peak:.0f} (giveback {giveback_pct if giveback_pct is not None else 'n/a'}%)"
        )

    primary_alert = None
    if "BOOK_CLOSE_REVIEW" in alerts:
        primary_alert = "BOOK_CLOSE_REVIEW"
    elif "BOOK_GIVEBACK" in alerts:
        primary_alert = "BOOK_GIVEBACK"

    peak_disp = peak if peak is not None else 0.0
    if note_bits:
        note = "; ".join(note_bits)
    else:
        note = f"Rose book ${current:.0f} / peak ${peak_disp:.0f} · no book soft alerts"
    if primary_alert:
        note = f"{primary_alert}: {note}"

    rose_block = {
        **rose,
        "bookPeakPnlUsd": round(peak, 2) if peak is not None else None,
        "bookPeakAtPT": peak_at,
        "peakUpdated": peak_updated,
        "givebackPct": giveback_pct,
        "flags": flags,
        "alerts": alerts,
        "alert": primary_alert,
        "note": note,
        "bookTp": book_tp,
        "bookGiveback": book_giveback,
    }

    payload = {
        "version": "BOOK-TRIGGERS-V1",
        "scoredAtPT": format_pt(),
        "scoredAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Paper book alerts only. Zero execution. Never auto-close seats. Never place RH orders. "
            "Primary = Rose/OID open seats (exclude Leopold + Hal/OT2)."
        ),
        "rules": {
            "bookTpUsd": BOOK_TP_USD,
            "bookTpPct": BOOK_TP_PCT,
            "bookGivebackFrac": BOOK_GIVEBACK_FRAC,
            "scope": "Rose/OID open paper seats; Leopold excluded; Hal/OT2 excluded from Rose book",
        },
        "rose": rose_block,
        "shared": {
            **shared,
            "note": (
                "Optional shared-book line (Rose + Hal open paper; Leopold excluded). "
                "Soft flags apply to Rose book only."
            ),
        },
    }

    if mutate:
        meta = ledger.setdefault("meta", {})
        meta["bookPeakPnlUsd"] = rose_block["bookPeakPnlUsd"]
        meta["bookPeakAtPT"] = rose_block["bookPeakAtPT"]
        meta["bookPnlUsd"] = rose_block["pnlUsd"]
        meta["bookPnlPct"] = rose_block["pnlPct"]
        meta["bookPremiumUsd"] = rose_block["premiumUsd"]
        meta["bookGivebackPct"] = rose_block["givebackPct"]
        meta["bookTriggerFlags"] = flags
        meta["bookTriggerAlert"] = primary_alert
        meta["bookTriggerNote"] = note
        meta["bookTriggerAtPT"] = payload["scoredAtPT"]
        meta["bookSeatCount"] = rose_block["seatCount"]
        meta["sharedBookPnlUsd"] = shared["pnlUsd"]
        meta["sharedBookPnlPct"] = shared["pnlPct"]
        meta["sharedBookSeatCount"] = shared["seatCount"]

    if persist_book_state and mutate:
        BOOK_STATE_PATH.write_text(
            json.dumps(
                {
                    "updatedAtPT": payload["scoredAtPT"],
                    "updatedAt": payload["scoredAt"],
                    "rose": {
                        "bookPeakPnlUsd": rose_block["bookPeakPnlUsd"],
                        "bookPeakAtPT": rose_block["bookPeakAtPT"],
                        "pnlUsd": rose_block["pnlUsd"],
                        "pnlPct": rose_block["pnlPct"],
                        "premiumUsd": rose_block["premiumUsd"],
                        "givebackPct": rose_block["givebackPct"],
                        "flags": flags,
                        "alert": primary_alert,
                        "note": note,
                        "seatIds": rose_block["seatIds"],
                    },
                    "shared": shared,
                    "disclaimer": payload["disclaimer"],
                },
                indent=2,
            )
            + "\n"
        )

    return payload


def main() -> int:
    import argparse
    import copy

    ap = argparse.ArgumentParser(description="OID book soft triggers (alerts only)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ledger = json.loads((PT_DIR / "trades.json").read_text())
    if args.dry_run:
        ledger = copy.deepcopy(ledger)
        out = score_book(ledger, mutate=True, persist_book_state=False)
        print(json.dumps(out, indent=2))
        return 0
    out = score_book(ledger, mutate=True, persist_book_state=True)
    (PT_DIR / "trades.json").write_text(json.dumps(ledger, indent=2) + "\n")
    dash = ROOT / "dashboard" / "trades.json"
    if dash.parent.exists():
        dash.write_text(json.dumps(ledger, indent=2) + "\n")
    print(json.dumps({"ok": True, "rose": out["rose"], "shared": out["shared"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
