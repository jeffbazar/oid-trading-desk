#!/usr/bin/env python3
"""Update X credit spend ledger from a balance snapshot.

Usage:
  python3 update_x_spend.py --balance 76.68
  python3 update_x_spend.py --from-json /path/to/get_usage_credits.json

Writes market-data/latest/x-spend.json and patches api-quotas.json X card.
Spend = balance drops since tracking start; top-ups adjust period baselines.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent
LATEST = ROOT / "latest"
SPEND_PATH = LATEST / "x-spend.json"
QUOTAS_PATH = LATEST / "api-quotas.json"


def _now():
    now = datetime.now(PT)
    now_utc = datetime.now(timezone.utc)
    return now, now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " "), now.date()


def update(balance: float, *, free_balance=None, prepaid_balance=None, expires_at=None, writer="Hal") -> dict:
    now, now_iso, now_pt, today = _now()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    current = float(balance)

    if SPEND_PATH.exists():
        ledger = json.loads(SPEND_PATH.read_text())
    else:
        ledger = {
            "feed": "x-spend",
            "writer": writer,
            "tracking_started_at": now_iso,
            "tracking_started_at_pt": now_pt,
            "baseline_balance": current,
            "note": "Spend = credit balance drop since tracking start. Top-ups adjust period baselines.",
            "snapshots": [],
            "topups": [],
            "daily": {},
            "periods": {},
        }

    last = ledger["snapshots"][-1]["balance"] if ledger.get("snapshots") else None
    topup = 0.0
    if last is not None and current > float(last) + 0.009:
        topup = round(current - float(last), 2)
        ledger.setdefault("topups", []).append(
            {"at": now_iso, "at_pt": now_pt, "amount": topup, "from": float(last), "to": current}
        )

    periods = ledger.setdefault("periods", {})
    if periods.get("today_date") != today.isoformat():
        periods["today_date"] = today.isoformat()
        periods["balance_at_day_start"] = current
    if periods.get("week_start") != week_start.isoformat():
        periods["week_start"] = week_start.isoformat()
        periods["balance_at_week_start"] = current
    if periods.get("month_start") != month_start.isoformat():
        periods["month_start"] = month_start.isoformat()
        periods["balance_at_month_start"] = current
    periods.setdefault("today_date", today.isoformat())
    periods.setdefault("week_start", week_start.isoformat())
    periods.setdefault("month_start", month_start.isoformat())
    periods.setdefault("balance_at_day_start", ledger["baseline_balance"])
    periods.setdefault("balance_at_week_start", ledger["baseline_balance"])
    periods.setdefault("balance_at_month_start", ledger["baseline_balance"])

    if topup > 0:
        for k in ("balance_at_day_start", "balance_at_week_start", "balance_at_month_start"):
            periods[k] = round(float(periods[k]) + topup, 2)

    def spent_from(start_bal):
        return max(0.0, round(float(start_bal) - current, 2))

    total_topups = sum(float(t.get("amount") or 0) for t in ledger.get("topups") or [])
    total_spent = max(0.0, round(float(ledger["baseline_balance"]) + total_topups - current, 2))
    day_spent = spent_from(periods["balance_at_day_start"])
    week_spent = spent_from(periods["balance_at_week_start"])
    month_spent = spent_from(periods["balance_at_month_start"])

    daily = ledger.setdefault("daily", {})
    dkey = today.isoformat()
    daily[dkey] = {
        "start": float(periods["balance_at_day_start"]),
        "end": current,
        "spent": day_spent,
    }
    if len(daily) > 60:
        for k in sorted(daily.keys())[:-60]:
            del daily[k]

    snaps = ledger.setdefault("snapshots", [])
    if snaps and abs(float(snaps[-1].get("balance", 0)) - current) < 0.005:
        snaps[-1]["at"] = now_iso
        snaps[-1]["at_pt"] = now_pt
    else:
        snaps.append({
            "at": now_iso,
            "at_pt": now_pt,
            "balance": current,
            "delta": None if last is None else round(current - float(last), 2),
        })
    ledger["snapshots"] = snaps[-90:]

    spend = {
        "total": total_spent,
        "today": day_spent,
        "week": week_spent,
        "month": month_spent,
        "currency": "USD",
    }
    ledger.update({
        "as_of": now_iso,
        "as_of_pt": now_pt,
        "writer": writer,
        "current_balance": current,
        "free_balance": free_balance if free_balance is not None else ledger.get("free_balance"),
        "prepaid_balance": prepaid_balance if prepaid_balance is not None else ledger.get("prepaid_balance"),
        "expires_at": expires_at or ledger.get("expires_at"),
        "spend": spend,
        "periods": periods,
        "ttl_seconds": 3600,
        "error": None,
        "feed": "x-spend",
    })
    SPEND_PATH.write_text(json.dumps(ledger, indent=2) + "\n")

    if QUOTAS_PATH.exists():
        quotas = json.loads(QUOTAS_PATH.read_text())
        quotas["as_of"] = now_iso
        quotas["as_of_pt"] = now_pt
        quotas["writer"] = writer
        quotas["x_spend"] = spend
        quotas["x_spend_tracking_since"] = ledger.get("tracking_started_at_pt")
        for v in quotas.get("vendors") or []:
            if v.get("id") == "x":
                v["remaining"] = current
                v["total_balance"] = current
                if free_balance is not None:
                    v["free_balance"] = free_balance
                if prepaid_balance is not None:
                    v["prepaid_balance"] = prepaid_balance
                if expires_at:
                    v["expires_at"] = expires_at
                v["spend_total"] = total_spent
                v["spend_today"] = day_spent
                v["spend_week"] = week_spent
                v["spend_month"] = month_spent
                v["spend_note"] = "tracked since " + str(ledger.get("tracking_started_at_pt"))
                v["cost_note"] = (
                    f"bal ${current:.2f} · today ${day_spent:.2f} · week ${week_spent:.2f} · "
                    f"month ${month_spent:.2f} · total ${total_spent:.2f}"
                )
                break
        QUOTAS_PATH.write_text(json.dumps(quotas, indent=2) + "\n")

    return ledger


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--balance", type=float)
    ap.add_argument("--from-json", type=Path)
    ap.add_argument("--writer", default="Hal")
    args = ap.parse_args()
    bal = args.balance
    free = prepaid = expires = None
    if args.from_json:
        raw = json.loads(args.from_json.read_text())
        data = raw.get("data") or raw
        bal = float(data["total_balance"])
        free = data.get("free_balance")
        prepaid = data.get("prepaid_balance")
        grants = data.get("free_grants") or []
        if grants and isinstance(grants[0], dict):
            expires = grants[0].get("expires_at")
    if bal is None:
        raise SystemExit("need --balance or --from-json")
    out = update(bal, free_balance=free, prepaid_balance=prepaid, expires_at=expires, writer=args.writer)
    print(json.dumps({"ok": True, "spend": out["spend"], "balance": out["current_balance"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
