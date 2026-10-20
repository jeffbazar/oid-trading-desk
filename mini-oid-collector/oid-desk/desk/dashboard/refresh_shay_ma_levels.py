#!/usr/bin/env python3
"""Full recompute of Shay · key levels (MA) soft watch from RH day bars + equity quotes.

Usage (executor has Robinhood MCP — research/paper only, never RH orders):
  1) MCP get_equity_historicals (day, regular, split) for symbols in batches ≤10
     → save JSON files; pass via --historicals-file (repeatable)
  2) MCP get_equity_quotes for same symbols → --quotes-file
  3) python3 dashboard/refresh_shay_ma_levels.py \\
       --historicals-file h1.json --historicals-file h2.json \\
       --quotes-file eq.json [--rebuild]

Live spot/%Var piggybacks on refresh_marks.py; this script rebuilds MAs.
Soft only · never elevate alone · zero RH orders.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PT_DIR = REPO / "paper-trades"
OUT_PATH = PT_DIR / "shay-ma-levels-watch.json"
DASH_PATH = ROOT / "shay-ma-levels-watch.json"
MD_LATEST = REPO / "market-data" / "latest"
PT = ZoneInfo("America/Los_Angeles")

DEFAULT_SYMBOLS = [
    "SPY", "QQQ", "NVDA", "TSLA", "PLTR", "GOOGL", "NFLX", "META", "AMZN",
    "AMD", "CBRS", "MU", "AVGO", "NBIS", "BE", "ASML", "TSM", "INTC",
    "IREN", "MRVL", "SNDK", "CRWV", "AAOI",
]

SHAY_BUCKET = {
    "NVDA": "Bullish", "AMD": "Bullish", "PLTR": "Bullish", "MU": "Bullish",
    "HOOD": "Bullish", "NBIS": "Bullish", "AEHR": "Bullish", "IONQ": "Bullish",
    "TSLA": "Hold", "RKLB": "Hold", "HIMS": "Hold", "IREN": "Hold",
    "AVGO": "Bearish", "ONDS": "Bearish", "CIFR": "Bearish", "OKLO": "Bearish",
    "ASTS": "Bearish", "OPEN": "Bearish", "SOFI": "Bearish", "AAOI": "Bearish",
}

TREND_RULE = (
    "OID Total Trend (Shay-style soft heuristic on live RH day-bar MAs): "
    "Bullish = spot > EMA9 AND spot > EMA21 AND spot > SMA50 (preferably also > SMA200; "
    "if above 9/21/50 but below 200 still Bullish). "
    "Bearish = spot < EMA9 AND spot < EMA21 AND spot < SMA50 "
    "(or spot below ≥3 of {9,21,50,200} including SMA50). "
    "Hold = mixed signs vs 9/21/50. "
    "Primary label uses 9/21/50; 200 is preference not hard gate for Bullish. "
    "Soft color only — never elevate from MAs alone."
)

POST_URL = "https://x.com/StockSavvyShay/status/2103868164987887851"
POST_ID = "2103868164987887851"


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _now() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    now_pt = now.astimezone(PT)
    iso = now.isoformat().replace("+00:00", "Z")
    stamp = now_pt.strftime("%Y-%m-%d ") + now_pt.strftime("%I:%M %p").lstrip("0") + " PT"
    return iso, stamp


def _load_json(path: Path) -> Any:
    raw = path.read_text()
    i = raw.find("{")
    j = raw.find("[")
    start = i if i >= 0 and (j < 0 or i < j) else j
    if start < 0:
        raise ValueError(f"no JSON in {path}")
    return json.loads(raw[start:])


def parse_historicals(payload: Any) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    results = []
    if isinstance(payload, dict):
        results = payload.get("results") or []
        if not results and "symbol" in payload and "bars" in payload:
            results = [payload]
    elif isinstance(payload, list):
        results = payload
    for r in results:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").upper()
        bars = r.get("bars") or []
        if not sym or not isinstance(bars, list):
            continue
        closes = []
        for b in bars:
            if not isinstance(b, dict) or b.get("interpolated"):
                continue
            c = _f(b.get("close_price") or b.get("close"))
            if c is not None:
                closes.append(c)
        if closes:
            out[sym] = closes
    return out


def parse_quotes(payload: Any) -> dict[str, dict]:
    """Minimal equity quote normalize (mirrors refresh_marks keys)."""
    out: dict[str, dict] = {}

    def ingest(item: dict, key_hint: Optional[str] = None) -> None:
        q = item.get("quote") if isinstance(item.get("quote"), dict) else item
        sym = key_hint or q.get("symbol") or item.get("symbol")
        if not sym:
            return
        sym = str(sym).upper()
        out[sym] = {
            "last": _f(q.get("last_trade_price") or q.get("last")),
            "last_non_reg": _f(
                q.get("last_non_reg_trade_price")
                or q.get("last_non_reg")
                or q.get("lastNonReg")
            ),
            "prev_close": _f(
                q.get("adjusted_previous_close")
                or q.get("previous_close")
                or q.get("prev_close")
            ),
            "previous_close_date": q.get("previous_close_date"),
        }

    if isinstance(payload, dict) and "data" in payload:
        inner = payload["data"]
        if isinstance(inner, dict) and "results" in inner:
            payload = inner
        elif isinstance(inner, list):
            payload = inner
    if isinstance(payload, dict):
        arr = payload.get("results") or payload.get("quotes")
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, dict):
                    ingest(item)
            return out
        for k, v in payload.items():
            if isinstance(v, dict) and k.isalpha() and k.isupper():
                ingest(v, key_hint=k)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                ingest(item)
    return out


def sma(vals: list[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def ema(vals: list[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    seed = sum(vals[:n]) / n
    mult = 2.0 / (n + 1)
    e = seed
    for v in vals[n:]:
        e = (v - e) * mult + e
    return e


def pct_var(spot: Optional[float], ma: Optional[float]) -> Optional[float]:
    if spot is None or ma is None or ma == 0:
        return None
    return round((spot - ma) / ma * 100.0, 4)


def total_trend(spot, e9, e21, s50, s200) -> str:
    if spot is None or e9 is None or e21 is None or s50 is None:
        return "Hold"
    a9, a21, a50 = spot > e9, spot > e21, spot > s50
    a200 = (spot > s200) if s200 is not None else None
    if a9 and a21 and a50:
        return "Bullish"
    if (not a9) and (not a21) and (not a50):
        return "Bearish"
    known = [a9, a21, a50] + ([a200] if a200 is not None else [])
    below_n = sum(1 for x in known if x is False)
    if (not a50) and below_n >= 3:
        return "Bearish"
    return "Hold"


def build(closes_by_sym: dict[str, list[float]], quotes: dict[str, dict], symbols: list[str]) -> dict:
    iso, stamp = _now()
    # Session label: prefer closed/AH on weekend via market_session if available
    session = "closed"
    session_label = "CLOSED"
    try:
        sys.path.insert(0, str(PT_DIR))
        from market_session import market_session, session_label as _sl  # type: ignore
        session = market_session()
        session_label = {"rth": "RTH", "pre": "PRE-MARKET", "ah": "AFTER-HOURS", "closed": "CLOSED"}.get(
            session, _sl(session)
        )
    except Exception:
        pass

    rows = []
    for sym in symbols:
        closes = closes_by_sym.get(sym) or []
        e9, e21 = ema(closes, 9), ema(closes, 21)
        s50, s200 = sma(closes, 50), sma(closes, 200)
        q = quotes.get(sym) or {}
        last = q.get("last")
        last_nr = q.get("last_non_reg")
        prev = q.get("prev_close")
        if session in ("pre", "ah", "closed") and last_nr is not None:
            spot = last_nr
        else:
            spot = last if last is not None else last_nr
        day_pct = None
        if spot is not None and prev:
            day_pct = round((float(spot) - float(prev)) / float(prev) * 100.0, 4)
        trend = total_trend(spot, e9, e21, s50, s200)
        row = {
            "symbol": sym,
            "last": round(float(spot), 4) if spot is not None else None,
            "lastRth": last,
            "lastNonReg": last_nr,
            "prevClose": prev,
            "prevCloseDate": q.get("previous_close_date"),
            "dayPct": day_pct,
            "ema9": round(e9, 4) if e9 is not None else None,
            "ema9VarPct": pct_var(spot, e9),
            "ema21": round(e21, 4) if e21 is not None else None,
            "ema21VarPct": pct_var(spot, e21),
            "sma50": round(s50, 4) if s50 is not None else None,
            "sma50VarPct": pct_var(spot, s50),
            "sma200": round(s200, 4) if s200 is not None else None,
            "sma200VarPct": pct_var(spot, s200),
            "totalTrend": trend,
            "barsUsed": len(closes),
            "session": session,
            "sessionLabel": (
                f"{session_label} · last AH" if session == "closed" and last_nr is not None else session_label
            ),
            "updatedAt": iso,
            "updatedAtPT": stamp,
        }
        if sym in SHAY_BUCKET:
            row["shayBucket"] = SHAY_BUCKET[sym]
            if SHAY_BUCKET[sym] != trend:
                row["shayBucketNote"] = f"Shay tweet={SHAY_BUCKET[sym]}; OID computed={trend}"
        rows.append(row)

    rank = {"Bullish": 0, "Hold": 1, "Bearish": 2}
    rows.sort(key=lambda r: (rank.get(r["totalTrend"], 9), r["symbol"]))
    n_bull = sum(1 for r in rows if r["totalTrend"] == "Bullish")
    n_hold = sum(1 for r in rows if r["totalTrend"] == "Hold")
    n_bear = sum(1 for r in rows if r["totalTrend"] == "Bearish")

    return {
        "id": "SHAY-MA-LEVELS-20260926",
        "kind": "equity_watch",
        "status": "shay_ma_watch",
        "softOnly": True,
        "neverElevateAlone": True,
        "consumesSeats": False,
        "handle": "StockSavvyShay",
        "author": "Shay Boloor",
        "postUrl": POST_URL,
        "postId": POST_ID,
        "postCreatedAt": "2026-09-26T00:00:00Z",
        "postCreatedAtPT": "2026-09-26 (Sat) · Fintwit Darlings key-levels post",
        "theme": "Shay · key levels (MA) — Spot · Total Trend · 9d EMA · 21d EMA · 50d SMA · 200d SMA + %Var",
        "sourceNote": (
            "Framing from @StockSavvyShay Sat 2026-09-26 Fintwit Darlings key-levels image; "
            "levels recomputed live from RH day bars (split-adj, regular bounds). "
            "Soft color only — MAs never elevate alone."
        ),
        "sourceImage": "tmp/shay-key-levels-20260926.png",
        "trendRule": TREND_RULE,
        "maMethod": (
            "EMA9/EMA21: multiplier 2/(n+1), seed=SMA of first n closes on RH day bars. "
            "SMA50/SMA200: simple mean of last n closes. %Var=(spot−MA)/MA×100."
        ),
        "historyInterval": "day",
        "historyBounds": "regular",
        "historyAdjustment": "split",
        "spotSource": "RH get_equity_quotes",
        "addedAt": iso,
        "addedAtPT": stamp,
        "updatedAt": iso,
        "updatedAtPT": stamp,
        "session": session,
        "sessionLabel": session_label,
        "note": (
            "Soft equity watch only — does NOT consume paper seats. Soft color only — "
            "never elevate from MAs alone; elevate stays with Q5/opening + walls. "
            "Research/paper · zero RH orders."
        ),
        "summary": {"n": len(rows), "bullish": n_bull, "hold": n_hold, "bearish": n_bear},
        "symbols": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Recompute Shay MA key-levels soft watch (research/paper only)")
    ap.add_argument("--historicals-file", type=Path, action="append", required=True)
    ap.add_argument("--quotes-file", type=Path, required=True)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    closes: dict[str, list[float]] = {}
    for hf in args.historicals_file:
        closes.update(parse_historicals(_load_json(hf)))
    quotes = parse_quotes(_load_json(args.quotes_file))
    symbols = [s.upper() for s in (args.symbols or DEFAULT_SYMBOLS)]
    missing_h = [s for s in symbols if s not in closes]
    missing_q = [s for s in symbols if s not in quotes]
    if missing_h:
        print("WARN missing historicals:", missing_h, file=sys.stderr)
    if missing_q:
        print("WARN missing quotes:", missing_q, file=sys.stderr)

    doc = build(closes, quotes, [s for s in symbols if s in closes or s in quotes])
    if args.dry_run:
        print(json.dumps({"summary": doc["summary"], "n": len(doc["symbols"])}, indent=2))
        return 0

    text = json.dumps(doc, indent=2) + "\n"
    OUT_PATH.write_text(text)
    DASH_PATH.write_text(text)
    MD_LATEST.mkdir(parents=True, exist_ok=True)
    stamp = {
        "as_of": doc["updatedAt"],
        "as_of_pt": doc["updatedAtPT"],
        "writer": "refresh_shay_ma_levels.py",
        "feed": "shay-ma-levels",
        "n": doc["summary"]["n"],
        "bullish": doc["summary"]["bullish"],
        "hold": doc["summary"]["hold"],
        "bearish": doc["summary"]["bearish"],
        "session": doc.get("session"),
        "postUrl": POST_URL,
        "path": str(OUT_PATH),
    }
    (MD_LATEST / "shay-ma-levels-watch.json").write_text(json.dumps(stamp, indent=2) + "\n")
    print("wrote", OUT_PATH, doc["summary"])
    if args.rebuild:
        import subprocess
        subprocess.check_call([sys.executable, str(ROOT / "rebuild.py")], cwd=str(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
