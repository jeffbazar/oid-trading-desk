"""S5 short-interest / borrow archive (Jeffrey 2026-10-13). Append-only, research only.

(a) UW borrow snapshot: latest /api/shorts/{T}/data row (fee_rate, rebate_rate, short_shares_available) per desk-universe
    name, once per ET trading day -> data/short-borrow/uw-borrow/YYYY-MM.jsonl (needs UW_API_KEY via run-job.sh).
(b) FINRA consolidated short interest (public api.finra.org, no key) by settlement date, appended the first run each
    (symbol, settlementDate, revision) is seen; first_seen_pt = observed publication time
    -> data/short-borrow/finra-si/short-interest.jsonl.
Summary/heartbeat -> market-data/latest/short-borrow.json. Files are only ever appended (never rewritten).
--if-due: weekdays, first run at/after short_borrow.due_et (launchd fires hourly). Universe = edgar_form4.universe.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import edgar_form4, util

JOB = "short-borrow"
UW_API = "https://api.unusualwhales.com/api"
FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
FINRA_KEEP = ["settlementDate", "symbolCode", "issueName", "marketClassCode", "currentShortPositionQuantity",
              "previousShortPositionQuantity", "changePreviousNumber", "changePercent", "averageDailyVolumeQuantity",
              "daysToCoverQuantity", "revisionFlag", "stockSplitFlag"]


def arch() -> Path:
    return util.desk() / "data" / "short-borrow"


def cfg_() -> dict:
    return util.desk_config("mini-desk.json").get("short_borrow") or {}


def universe() -> list[str]:
    return edgar_form4.universe(util.desk_config("mini-desk.json").get("edgar") or {})


def append_jsonl(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":"), default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return len(rows)


def read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def uw_get(path: str, key: str) -> Any:
    req = urllib.request.Request(UW_API + path, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                                         "User-Agent": "oid-short-borrow/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from None  # never echo headers / key


def uw_snapshot(syms: list[str], trade_date: str) -> dict:
    key = util.read_secret("UW_API_KEY")
    if not key:
        return {"status": "skipped", "reason": "UW_API_KEY missing", "rows": 0}
    path = arch() / "uw-borrow" / f"{trade_date[:7]}.jsonl"
    done = {r.get("symbol") for r in read_jsonl(path) if r.get("trade_date") == trade_date}
    rows, errors = [], {}
    now_pt, now_utc = util.now_pt_str(), util.utc_iso()
    for s in syms:
        if s in done:
            continue
        try:
            d = uw_get(f"/shorts/{s}/data", key)
            data = (d.get("data") if isinstance(d, dict) else d) or []
            if not data:
                errors[s] = "no_rows"
                continue
            last = max(data, key=lambda r: r.get("timestamp") or "")
            rows.append({"trade_date": trade_date, "symbol": s, "snapshot_pt": now_pt, "snapshot_utc": now_utc,
                         "uw_timestamp": last.get("timestamp"), "fee_rate": _f(last.get("fee_rate")),
                         "rebate_rate": _f(last.get("rebate_rate")),
                         "short_shares_available": last.get("short_shares_available"), "source": "uw:/shorts/{t}/data"})
        except Exception as e:  # noqa: BLE001
            errors[s] = str(e)[:60] if isinstance(e, RuntimeError) else type(e).__name__
        time.sleep(0.25)
    n = append_jsonl(path, rows)
    return {"status": "ok" if not errors else "partial", "file": str(path.relative_to(util.desk())),
            "rows": n, "already_had": len(done), "errors": errors}


def finra_snapshot(syms: list[str], lookback_days: int) -> dict:
    start = (datetime.now(util.ET) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = datetime.now(util.ET).strftime("%Y-%m-%d")
    body = json.dumps({"limit": 5000, "domainFilters": [{"fieldName": "symbolCode", "values": syms}],
                       "dateRangeFilters": [{"fieldName": "settlementDate", "startDate": start, "endDate": end}]}).encode()
    req = urllib.request.Request(FINRA_URL, data=body, headers={"Content-Type": "application/json", "Accept": "application/json",
                                                                "User-Agent": "oid-short-borrow/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read() or b"[]")
    path = arch() / "finra-si" / "short-interest.jsonl"
    seen = {(r.get("symbolCode"), r.get("settlementDate"), r.get("revisionFlag"), r.get("currentShortPositionQuantity"))
            for r in read_jsonl(path)}
    now_pt = util.now_pt_str()
    rows = []
    for x in sorted(data, key=lambda r: (r.get("settlementDate") or "", r.get("symbolCode") or "")):
        k = (x.get("symbolCode"), x.get("settlementDate"), x.get("revisionFlag"), x.get("currentShortPositionQuantity"))
        if k in seen:
            continue
        seen.add(k)
        rec = {f: x.get(f) for f in FINRA_KEEP}
        rec["first_seen_pt"] = now_pt
        rows.append(rec)
    n = append_jsonl(path, rows)
    dates = sorted({r.get("settlementDate") for r in data if r.get("settlementDate")})
    return {"status": "ok", "file": str(path.relative_to(util.desk())), "rows": n, "fetched": len(data),
            "settlement_dates": dates, "new_settlement_dates": sorted({r["settlementDate"] for r in rows})}


def due(cfg: dict, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(util.ET)
    if now.weekday() >= 5:
        return False
    h, m = map(int, str(cfg.get("due_et") or "16:45").split(":"))
    if now < now.replace(hour=h, minute=m, second=0, microsecond=0):
        return False
    last = util.read_json(util.desk() / "market-data" / "latest" / "short-borrow.json") or {}
    return (last.get("payload") or {}).get("trade_date") != now.strftime("%Y-%m-%d")


def run(cfg: dict) -> dict:
    syms = universe()
    trade_date = datetime.now(util.ET).strftime("%Y-%m-%d")
    out: dict[str, Any] = {"trade_date": trade_date, "symbols": syms, "archive": str(arch().relative_to(util.desk()))}
    for name, fn in (("uw", lambda: uw_snapshot(syms, trade_date)),
                     ("finra", lambda: finra_snapshot(syms, int(cfg.get("finra_lookback_days", 75))))):
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001
            out[name] = {"status": "error", "error": type(e).__name__, "rows": 0}
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini S5 short-interest / borrow archive")
    ap.add_argument("--if-due", action="store_true")
    a = ap.parse_args(argv)
    cfg = cfg_()
    if a.if_due and not due(cfg):
        print(json.dumps({"skipped": "not due"}))
        return 0
    p = run(cfg)
    err = None if all((p.get(k) or {}).get("status") in ("ok", "partial") for k in ("uw", "finra")) else "see payload"
    util.write_feed("short-borrow", source="UW /shorts/{t}/data + FINRA consolidatedShortInterest", writer="mini:oid_desk.short_borrow",
                    symbols=p["symbols"], payload=p, ttl_seconds=302400, error=err)
    util.log(JOB, json.dumps({k: (p.get(k) or {}).get("rows") for k in ("uw", "finra")}))
    print(json.dumps({k: {kk: vv for kk, vv in (p.get(k) or {}).items() if kk != "errors"} for k in ("uw", "finra")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
