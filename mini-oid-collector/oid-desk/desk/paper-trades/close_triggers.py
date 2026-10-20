#!/usr/bin/env python3
"""OID soft close-triggers — paper alerts only (ZERO execution / no RH orders).

Scores open seats after marks update. Writes:
  - tmp/close-triggers-last.json
  - optional fields on each open trade: closeTriggerArmed, closeTriggerFlags, closeTriggerNote

See CLOSE-TRIGGERS-V1.md. Research only; never auto-closes tickets.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
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
ET = ZoneInfo("America/New_York")

ROOT = Path(__file__).resolve().parent.parent
PT_DIR = Path(__file__).resolve().parent
TRADES_PATH = PT_DIR / "trades.json"
TMP_OUT = ROOT / "tmp" / "close-triggers-last.json"

OPEN_STATUSES = frozenset({"open", "watching", "paper", "live"})

ARM_MFE_PCT = 50.0
SCALE_OUT_PCT = 20.0  # Jeffrey 2026-10-08 paper scale-out band (half off at +20%)
GIVEBACK_MARK_FRAC = 0.50  # lastMark <= 50% of peakMark
STILL_GREEN_FLOOR_PCT = 25.0  # optional: still ≥+25% but gave back half of MFE
DTE_FORCE = 1
THETA_MIN_USD = 10.0  # soft tax if |θ$/d| ≥ max($10, 1.5% of entry premium)
THETA_PREMIUM_FRAC = 0.015
THETA_WIN_SKIP_PCT = 25.0  # skip tax alert when pnlPct ≥ +25%


def _f(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _now_pt() -> datetime:
    return datetime.now(PT)


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


def parse_expiry_from_contract(contract: str) -> Optional[date]:
    """Parse YYYY-MM-DD from e.g. 'NVDA 2026-09-18 220 call'."""
    if not contract:
        return None
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", contract)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def compute_dte(trade: dict, today: Optional[date] = None) -> Optional[int]:
    today = today or _now_pt().date()
    if trade.get("dte") is not None:
        try:
            return int(trade["dte"])
        except (TypeError, ValueError):
            pass
    exp = trade.get("expiry") or trade.get("expiration")
    if isinstance(exp, str) and len(exp) >= 10:
        try:
            return (date.fromisoformat(exp[:10]) - today).days
        except ValueError:
            pass
    parsed = parse_expiry_from_contract(str(trade.get("contract") or ""))
    if parsed:
        return (parsed - today).days
    return None


def _notes_blob(trade: dict) -> str:
    parts = []
    for k in (
        "openNote", "q5Note", "sessionNote", "closeCarryNote", "faWallsNote",
        "invalidationReason", "lesson", "statusNote", "closeTriggerNote",
    ):
        v = trade.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    return "\n".join(parts)


def thesis_failed(trade: dict) -> bool:
    """Hard invalidate: named flip/put break already recorded."""
    status = (trade.get("status") or "").lower()
    if status in ("invalidated", "stopped"):
        return True
    if (trade.get("result") or "").lower() == "thesis_fail":
        return True
    if (trade.get("outcomeTag") or "").lower() == "thesis_fail":
        return True
    if trade.get("invalidatedAt") or trade.get("invalidationReason"):
        return True
    blob = _notes_blob(trade).lower()
    if re.search(r"\bnot\s+invalidat", blob):
        return False
    if re.search(r"\binvalidat(e|ed|ion)\b", blob) and re.search(
        r"(flip|put)\s+(break|fail|broke|failed|broken)", blob
    ):
        return True
    return False


def score_trade(trade: dict, *, today: Optional[date] = None) -> dict:
    """Return scoring dict; mutates trade with closeTrigger* fields when open."""
    today = today or _now_pt().date()
    tid = trade.get("id") or "?"
    sym = trade.get("symbol") or "?"
    mfe = _f(trade.get("mfePct"))
    pnl = _f(trade.get("pnlPct")) or _f(trade.get("unrealizedPnlPct")) or _f(trade.get("markPnlPct"))
    last = _f(trade.get("lastMark")) or _f(trade.get("lastOptionMark"))
    peak = _f(trade.get("peakMark"))
    entry = entry_ref(trade)
    dte = compute_dte(trade, today)

    flags: list[str] = []
    alert: Optional[str] = None  # INVALIDATE | CLOSE_TRIGGER_REVIEW | FORCE_REVIEW | None
    note_bits: list[str] = []

    # --- 1. Hard invalidate (existing thesis fail) ---
    thesis_ok = not thesis_failed(trade)
    if not thesis_ok:
        flags.append("THESIS_FAIL")
        alert = "INVALIDATE"
        note_bits.append("Hard invalidate: thesis fail (named flip/put break)")

    # --- 2. Arm trail when mfePct ≥ +50% ---
    armed = bool(trade.get("closeTriggerArmed"))
    if mfe is not None and mfe >= ARM_MFE_PCT:
        armed = True
        flags.append("ARMED")
        note_bits.append(f"Trail armed (mfePct={mfe:.1f}% ≥ +{ARM_MFE_PCT:.0f}%)")
    elif armed:
        flags.append("ARMED")
        note_bits.append("Trail remains armed (prior)")

    # --- 3. Giveback exit soft ---
    giveback_hit = False
    if armed and peak is not None and peak > 0 and last is not None:
        if last <= GIVEBACK_MARK_FRAC * peak:
            giveback_hit = True
            flags.append("GIVEBACK")
            note_bits.append(
                f"Giveback: mark {last:.3f} ≤ {GIVEBACK_MARK_FRAC:.0%} of peak {peak:.3f}"
            )
    if (
        armed
        and mfe is not None
        and mfe >= ARM_MFE_PCT
        and pnl is not None
        and pnl >= STILL_GREEN_FLOOR_PCT
        and (mfe - pnl) >= (mfe * 0.5)
    ):
        giveback_hit = True
        if "GIVEBACK" not in flags:
            flags.append("GIVEBACK")
        note_bits.append(
            f"Still-green giveback: pnlPct={pnl:.1f}% ≥ +{STILL_GREEN_FLOOR_PCT:.0f}% "
            f"but gave back ≥½ of MFE ({mfe:.1f}% → {pnl:.1f}%)"
        )
    if giveback_hit and alert != "INVALIDATE":
        alert = "CLOSE_TRIGGER_REVIEW"

    # --- 3b. Jeffrey standing paper scale-out (2026-10-08): at +20% vs entry take HALF off;
    #         exception: clear running momentum -> hold & watch, take half when momentum slows.
    #         Paper only. Flags the seat until a scaleOuts[] entry exists on it.
    already_scaled = bool(trade.get("scaleOuts"))
    if not already_scaled and (
        (pnl is not None and pnl >= SCALE_OUT_PCT)
        or (mfe is not None and mfe >= SCALE_OUT_PCT)
    ):
        flags.append("SCALE_OUT_20_DUE")
        note_bits.append(
            f"Scale-out due: +{SCALE_OUT_PCT:.0f}% band reached (pnl="
            f"{('n/a' if pnl is None else f'{pnl:.1f}%')}, mfe="
            f"{('n/a' if mfe is None else f'{mfe:.1f}%')}) -> take half unless momentum still running"
        )
        if alert is None:
            alert = "CLOSE_TRIGGER_REVIEW"

    # --- 4. Time / event soft ---
    force_time = False
    if dte is not None and dte <= DTE_FORCE:
        force_time = True
        flags.append("DTE_LE_1")
        note_bits.append(f"Time: DTE={dte} ≤ {DTE_FORCE}")
    now_et = datetime.now(ET)
    if dte == 0 and now_et.hour < 12:
        force_time = True
        if "DTE_LE_1" not in flags:
            flags.append("DTE_LE_1")
        if "OPEX_MORNING" not in flags:
            flags.append("OPEX_MORNING")
            note_bits.append("Time: morning of expiry / 0DTE OPEX seat")
    if force_time and alert not in ("INVALIDATE", "CLOSE_TRIGGER_REVIEW"):
        alert = "FORCE_REVIEW"
    elif force_time and alert is None:
        alert = "FORCE_REVIEW"

    # --- 5. Theta tax soft (long premium bleed) ---
    theta_tax = False
    theta_usd = _f(trade.get("thetaUsdPerDay"))
    if theta_usd is None:
        th = _f(trade.get("theta"))
        try:
            qty = _fq(trade.get("qtySuggested") or 1)
        except (TypeError, ValueError):
            qty = 1
        if th is not None:
            theta_usd = th * 100.0 * qty
            trade["thetaUsdPerDay"] = round(theta_usd, 2)
    side = (trade.get("side") or "").lower()
    strat = (trade.get("strategy") or "").lower()
    is_long = (
        "long" in side
        or "debit" in strat
        or "leap" in strat
        or side in ("", "buy", "call", "put")
        or (strat in ("",) and "credit" not in strat)
    )
    if "credit" in strat or "short" in side:
        is_long = False
    if is_long and theta_usd is not None and theta_usd < 0:
        entry_prem = (entry * 100.0) if entry else None
        try:
            qty = _fq(trade.get("qtySuggested") or 1)
        except (TypeError, ValueError):
            qty = 1
        if entry_prem is not None:
            entry_prem *= qty
        thresh = max(THETA_MIN_USD, (entry_prem or 0) * THETA_PREMIUM_FRAC)
        strong_win = pnl is not None and pnl >= THETA_WIN_SKIP_PCT
        if abs(theta_usd) >= thresh and not strong_win:
            theta_tax = True
            flags.append("THETA_TAX")
            note_bits.append(
                f"Theta tax: θ$/day={theta_usd:.2f} (bleed ≥ ${thresh:.0f}/d) while pnlPct="
                f"{('n/a' if pnl is None else f'{pnl:.1f}%')}"
            )
            if alert is None:
                alert = "CLOSE_TRIGGER_REVIEW"

    if thesis_ok:
        flags.append("THESIS_OK")
    else:
        if "THESIS_FAIL" not in flags:
            flags.append("THESIS_FAIL")

    state = {
        "armed": armed,
        "givebackHit": giveback_hit,
        "dteLe1": dte is not None and dte <= DTE_FORCE,
        "thesisOk": thesis_ok,
        "dte": dte,
        "mfePct": mfe,
        "pnlPct": pnl,
        "lastMark": last,
        "peakMark": peak,
        "entry": entry,
        "thetaUsdPerDay": theta_usd,
        "thetaTax": theta_tax,
        "delta": _f(trade.get("delta")),
        "gamma": _f(trade.get("gamma")),
        "iv": _f(trade.get("iv")),
    }

    note = "; ".join(note_bits) if note_bits else (
        "Thesis OK · no soft alerts" if thesis_ok else "No soft close triggers"
    )
    if alert:
        note = f"{alert}: {note}"

    trade["closeTriggerArmed"] = armed
    trade["closeTriggerFlags"] = flags
    trade["closeTriggerNote"] = note
    trade["closeTriggerAlert"] = alert
    trade["closeTriggerAtPT"] = format_pt()

    return {
        "id": tid,
        "symbol": sym,
        "contract": trade.get("contract"),
        "agent": trade.get("agent") or "Rose",
        "status": trade.get("status"),
        "alert": alert,
        "flags": flags,
        "note": note,
        "state": state,
        "closeTriggerArmed": armed,
        "closeTriggerFlags": flags,
        "closeTriggerNote": note,
    }


def score_open_ledger(
    ledger: dict, *, mutate: bool = True, persist_book_state: bool = True
) -> dict:
    today = _now_pt().date()
    seats = []
    for t in ledger.get("trades", []):
        if (t.get("status") or "").lower() not in OPEN_STATUSES:
            continue
        seats.append(score_trade(t, today=today))

    reviews = [
        s
        for s in seats
        if s.get("alert") in ("CLOSE_TRIGGER_REVIEW", "FORCE_REVIEW", "INVALIDATE")
    ]

    # Book-level soft triggers (Rose/OID primary; alerts only — never auto-close / never RH)
    try:
        from book_triggers import score_book
    except ImportError:
        import importlib.util

        _bp = Path(__file__).resolve().parent / "book_triggers.py"
        _spec = importlib.util.spec_from_file_location("book_triggers", _bp)
        _mod = importlib.util.module_from_spec(_spec)
        assert _spec and _spec.loader
        _spec.loader.exec_module(_mod)
        score_book = _mod.score_book
    book = score_book(
        ledger, mutate=mutate, persist_book_state=persist_book_state and mutate
    )
    book_reviews = []
    rose_book = book.get("rose") or {}
    if rose_book.get("alert") in ("BOOK_CLOSE_REVIEW", "BOOK_GIVEBACK"):
        book_reviews.append(
            {
                "scope": "rose_book",
                "alert": rose_book.get("alert"),
                "flags": rose_book.get("flags") or [],
                "note": rose_book.get("note"),
                "pnlUsd": rose_book.get("pnlUsd"),
                "pnlPct": rose_book.get("pnlPct"),
                "bookPeakPnlUsd": rose_book.get("bookPeakPnlUsd"),
                "bookPeakAtPT": rose_book.get("bookPeakAtPT"),
                "givebackPct": rose_book.get("givebackPct"),
                "seatCount": rose_book.get("seatCount"),
                "symbols": rose_book.get("symbols"),
            }
        )

    payload = {
        "version": "CLOSE-TRIGGERS-V1",
        "scoredAtPT": format_pt(),
        "scoredAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Paper alerts only. Zero execution. Chat approval ≠ ticket. Never place RH orders."
        ),
        "openCount": len(seats),
        "reviewCount": len(reviews),
        "seats": seats,
        "reviews": reviews,
        "book": book,
        "bookReviews": book_reviews,
        "bookReviewCount": len(book_reviews),
        "rulesSummary": {
            "hard": "Thesis fail (named flip/put break) → INVALIDATE (alert only; do not auto-close)",
            "arm": f"mfePct ≥ +{ARM_MFE_PCT:.0f}% → closeTriggerArmed=true",
            "giveback": (
                f"Armed AND (mark ≤ {GIVEBACK_MARK_FRAC:.0%} peak OR still-green half-MFE "
                "giveback) → CLOSE_TRIGGER_REVIEW"
            ),
            "time": f"DTE ≤ {DTE_FORCE} or morning-of-expiry 0DTE → FORCE_REVIEW",
            "theta": (
                f"Long θ$/day bleed ≥ max(${THETA_MIN_USD:.0f}, {THETA_PREMIUM_FRAC:.1%} premium) "
                f"while pnlPct < +{THETA_WIN_SKIP_PCT:.0f}% → CLOSE_TRIGGER_REVIEW / THETA_TAX"
            ),
            "bookTp": (
                "Rose/OID book unrealized ≥ +$1,000 OR ≥ +30% of open-book premium → "
                "BOOK_CLOSE_REVIEW (soft)"
            ),
            "bookGiveback": (
                "Rose/OID book current ≤ 50% of tracked bookPeakPnlUsd (peak > 0) → "
                "BOOK_GIVEBACK (soft)"
            ),
            "execution": "NEVER place orders; NEVER auto-close tickets",
        },
    }
    return payload


def write_snapshot(payload: dict, path: Path = TMP_OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _focus_watch_peek(since_min: float = 10.0) -> dict | None:
    """Passive surface of the 5s focus watch (quotes/focus_watch.py): medium+ events from the last
    ~10 min + current readings. Peek only (no cursor). Never raises; alerts only, never orders."""
    try:
        import importlib.util

        path = ROOT / "quotes" / "focus_watch_digest.py"
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("focus_watch_digest", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        d = mod.digest(None, peek=True, min_severity="medium", since_min=since_min, max_events=10)
        return {"notify": d.get("notify"), "count": d.get("count"), "events": d.get("events"),
                "watch": d.get("watch"),
                "readings": {s: {"spot": r.get("spot"), "flags": r.get("flags"), "levels": r.get("levels")}
                             for s, r in (d.get("readings") or {}).items()}}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def run(*, write_trades: bool = True, dry_run: bool = False) -> dict:
    ledger = json.loads(TRADES_PATH.read_text())
    if dry_run:
        import copy

        ledger = copy.deepcopy(ledger)
    payload = score_open_ledger(
        ledger, mutate=True, persist_book_state=(not dry_run)
    )
    if dry_run:
        print(json.dumps(payload, indent=2))
        return payload
    payload["focusWatch"] = _focus_watch_peek()
    write_snapshot(payload)
    if write_trades:
        TRADES_PATH.write_text(json.dumps(ledger, indent=2) + "\n")
        dash = ROOT / "dashboard" / "trades.json"
        if dash.parent.exists():
            dash.write_text(json.dumps(ledger, indent=2) + "\n")
    rose = (payload.get("book") or {}).get("rose") or {}
    print(
        json.dumps(
            {
                "ok": True,
                "wrote": str(TMP_OUT),
                "open": payload["openCount"],
                "reviews": payload["reviewCount"],
                "alerts": [
                    {
                        "id": r["id"],
                        "symbol": r["symbol"],
                        "alert": r["alert"],
                        "flags": r["flags"],
                    }
                    for r in payload["reviews"]
                ],
                "book": {
                    "pnlUsd": rose.get("pnlUsd"),
                    "pnlPct": rose.get("pnlPct"),
                    "peak": rose.get("bookPeakPnlUsd"),
                    "peakAtPT": rose.get("bookPeakAtPT"),
                    "givebackPct": rose.get("givebackPct"),
                    "flags": rose.get("flags"),
                    "alert": rose.get("alert"),
                },
                "bookReviews": payload.get("bookReviews") or [],
                "focusWatch": payload.get("focusWatch"),
            },
            indent=2,
        )
    )
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="OID soft close-triggers (alerts only)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--no-write-trades", action="store_true", help="Only write tmp snapshot"
    )
    args = ap.parse_args()
    run(write_trades=not args.no_write_trades, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
