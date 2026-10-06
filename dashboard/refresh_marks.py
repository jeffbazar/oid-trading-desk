#!/usr/bin/env python3
"""Apply live option marks to paper-trades/trades.json (research / paper only).

Cost basis: entryAsk (fallback entryMark/entryBid) via outcome_helper.entry_ref.
P&L: (mark - entry) / entry * 100 (%); (mark - entry) * qty * 100 (USD).

Quotes source (pick one for options):
  --quotes-file PATH   JSON from RH get_option_quotes (or simplified map)
  --quotes-stdin       same JSON on stdin
  --list-ids           print open instrumentIds as JSON and exit (for MCP fetch)

Equity / session (optional, combine with option quotes or alone):
  --list-symbols       print open underlying symbols JSON (for get_equity_quotes)
  --equity-quotes-file PATH   JSON from RH get_equity_quotes
  --equity-quotes-stdin       same JSON on stdin

Does NOT call Robinhood MCP itself (MCP lives in the agent executor).
Never places orders.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
PT_DIR = ROOT.parent / "paper-trades"
TRADES_PATH = PT_DIR / "trades.json"
SHAY_WATCH_PATH = PT_DIR / "shay-semi-watch.json"
SHAY_MA_WATCH_PATH = PT_DIR / "shay-ma-levels-watch.json"
sys.path.insert(0, str(PT_DIR))

from outcome_helper import apply_mark_update, format_pt, entry_ref  # noqa: E402
from market_session import market_session, session_label  # noqa: E402
sys.path.insert(0, str(ROOT.parent / "market-data"))
try:
    from cache_io import write_feed  # noqa: E402
except Exception:  # pragma: no cover
    write_feed = None  # type: ignore

OPEN_STATUSES = frozenset({"open", "watching", "paper", "live"})
# External watches (Leopold/ZH) — refreshed for marks but NEVER counted as paper seats
WATCH_STATUSES = frozenset({"leopold_watch", "watch_external"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_ledger() -> dict:
    return json.loads(TRADES_PATH.read_text())


def open_trades(ledger: dict) -> list[dict]:
    return [t for t in ledger.get("trades", []) if (t.get("status") or "").lower() in OPEN_STATUSES]


def leopold_watches(ledger: dict) -> list[dict]:
    """Top-level leopoldWatches array, plus any trades with watch statuses (belt+suspenders)."""
    watches = list(ledger.get("leopoldWatches") or [])
    for t in ledger.get("trades", []):
        if (t.get("status") or "").lower() in WATCH_STATUSES:
            watches.append(t)
    return watches


def markable_rows(ledger: dict) -> list[dict]:
    """Open paper seats + Leopold/external watches (marks refresh targets)."""
    return open_trades(ledger) + leopold_watches(ledger)


def load_shay_watch() -> dict:
    """StockSavvyShay semiconductor 2027-PE equity watch (soft; no seats)."""
    if not SHAY_WATCH_PATH.exists():
        return {}
    try:
        return json.loads(SHAY_WATCH_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def shay_watch_symbols(watch: Optional[dict] = None) -> list[str]:
    w = watch if watch is not None else load_shay_watch()
    out: list[str] = []
    for row in w.get("symbols") or []:
        s = (row.get("symbol") or "").strip().upper()
        if s and s not in out:
            out.append(s)
    # SPY needed for vsSpySincePost
    if out and "SPY" not in out:
        out.append("SPY")
    return out


def load_shay_ma_watch() -> dict:
    """StockSavvyShay key-levels MA soft watch (soft; no seats; never elevate alone)."""
    if not SHAY_MA_WATCH_PATH.exists():
        return {}
    try:
        return json.loads(SHAY_MA_WATCH_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def shay_ma_watch_symbols(watch: Optional[dict] = None) -> list[str]:
    w = watch if watch is not None else load_shay_ma_watch()
    out: list[str] = []
    for row in w.get("symbols") or []:
        s = (row.get("symbol") or "").strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def apply_shay_ma_equity_quotes(watch: dict, quotes: dict[str, dict], *, stamp_pt: Optional[str] = None) -> dict:
    """Update Shay MA watch spots + %Var vs cached MAs (do not recompute MAs here)."""
    stamp = stamp_pt or format_pt()
    now_iso = _now_iso()
    session = market_session()
    human = {"rth": "RTH", "pre": "PRE-MARKET", "ah": "AFTER-HOURS", "closed": "CLOSED"}
    lab = human.get(session, session_label(session))

    def _pct_var(spot: Optional[float], ma: Optional[float]) -> Optional[float]:
        if spot is None or ma is None or float(ma) == 0:
            return None
        return round((float(spot) - float(ma)) / float(ma) * 100.0, 4)

    def _trend(spot, e9, e21, s50, s200) -> str:
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

    updated = 0
    missing: list[str] = []
    for row in watch.get("symbols") or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        q = quotes.get(sym)
        if not q:
            missing.append(sym)
            continue
        last = q.get("last")
        last_non_reg = q.get("last_non_reg")
        prev = q.get("prev_close")
        display = last
        live_ext = False
        if session in ("pre", "ah") and last_non_reg is not None:
            display = last_non_reg
            live_ext = True
        elif session == "closed" and last_non_reg is not None:
            # Weekend / closed: prefer last AH print when available
            display = last_non_reg
        elif session == "closed" and last is not None:
            display = last
        if last is not None:
            row["lastRth"] = float(last)
        if last_non_reg is not None:
            row["lastNonReg"] = float(last_non_reg)
        if display is not None:
            row["last"] = float(display)
        if prev is not None:
            row["prevClose"] = float(prev)
        if q.get("previous_close_date"):
            row["prevCloseDate"] = q["previous_close_date"]
        day_pct = None
        if display is not None and prev is not None and float(prev) != 0:
            day_pct = round((float(display) - float(prev)) / float(prev) * 100.0, 4)
            row["dayPct"] = day_pct
        else:
            row.pop("dayPct", None)

        e9 = _f(row.get("ema9"))
        e21 = _f(row.get("ema21"))
        s50 = _f(row.get("sma50"))
        s200 = _f(row.get("sma200"))
        spot_f = float(display) if display is not None else None
        row["ema9VarPct"] = _pct_var(spot_f, e9)
        row["ema21VarPct"] = _pct_var(spot_f, e21)
        row["sma50VarPct"] = _pct_var(spot_f, s50)
        row["sma200VarPct"] = _pct_var(spot_f, s200)
        trend = _trend(spot_f, e9, e21, s50, s200)
        row["totalTrend"] = trend
        sb = row.get("shayBucket")
        if sb and str(sb) != trend:
            row["shayBucketNote"] = f"Shay tweet={sb}; OID computed={trend}"
        elif "shayBucketNote" in row and (not sb or str(sb) == trend):
            row.pop("shayBucketNote", None)

        row["session"] = session
        sess_lab = lab
        if live_ext:
            sess_lab = f"{lab} · LIVE"
        elif session == "closed":
            sess_lab = f"{lab} · last AH" if last_non_reg is not None else lab
        row["sessionLabel"] = sess_lab
        row["updatedAt"] = now_iso
        row["updatedAtPT"] = stamp
        updated += 1

    # Refresh summary counts
    syms = watch.get("symbols") or []
    watch["summary"] = {
        "n": len(syms),
        "bullish": sum(1 for r in syms if r.get("totalTrend") == "Bullish"),
        "hold": sum(1 for r in syms if r.get("totalTrend") == "Hold"),
        "bearish": sum(1 for r in syms if r.get("totalTrend") == "Bearish"),
    }
    watch["updatedAt"] = now_iso
    watch["updatedAtPT"] = stamp
    watch["session"] = session
    watch["sessionLabel"] = lab
    return {
        "updated": updated,
        "missing": missing,
        "session": session,
        "n": len(syms),
        "bullish": watch["summary"]["bullish"],
        "hold": watch["summary"]["hold"],
        "bearish": watch["summary"]["bearish"],
    }


SOFT_WATCH_EXCLUDE = frozenset({"shay-semi-watch.json", "shay-ma-levels-watch.json"})


def load_soft_watches() -> list[tuple[Path, dict]]:
    """Pinned soft watches (mu-earnings / be-oe / …) — research/color only, no seats."""
    out: list[tuple[Path, dict]] = []
    seen: set[str] = set()
    for sp in sorted(PT_DIR.glob("*-watch.json")):
        if sp.name in SOFT_WATCH_EXCLUDE:
            continue
        try:
            sw = json.loads(sp.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(sw, dict):
            continue
        stype = str(sw.get("type") or "").lower()
        if not (sw.get("softOnly") is True or stype in ("earnings_watch", "oe_darkpool_watch", "soft_watch")):
            continue
        sid = str(sw.get("id") or sp.stem)
        if sid in seen:
            continue
        seen.add(sid)
        out.append((sp, sw))
    return out


def soft_watch_symbols() -> list[str]:
    out: list[str] = []
    for _path, sw in load_soft_watches():
        s = (sw.get("symbol") or "").strip().upper()
        if s and s not in out:
            out.append(s)
        for row in sw.get("symbols") or []:
            if not isinstance(row, dict):
                continue
            rs = (row.get("symbol") or "").strip().upper()
            if rs and rs not in out:
                out.append(rs)
    return out


def apply_soft_watch_equity_quotes(quotes: dict[str, dict], *, stamp_pt: Optional[str] = None) -> dict:
    """Piggyback equity marks onto soft watch JSON (last / dayPct only — never invent)."""
    stamp = stamp_pt or format_pt()
    session = market_session()
    human = {"rth": "RTH", "pre": "PRE-MARKET", "ah": "AFTER-HOURS", "closed": "CLOSED"}
    updated = 0
    missing: list[str] = []
    files: list[str] = []
    for sp, sw in load_soft_watches():
        # Multi-symbol soft watches (universe support map)
        rows = sw.get("symbols") if isinstance(sw.get("symbols"), list) else None
        if rows is not None:
            changed = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = (row.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                q = quotes.get(sym)
                if not q:
                    missing.append(sym)
                    continue
                last = q.get("last")
                last_non_reg = q.get("last_non_reg")
                prev = q.get("prev_close")
                display = last
                if session in ("pre", "ah") and last_non_reg is not None:
                    display = last_non_reg
                elif session == "closed" and last is not None:
                    display = last
                if display is not None:
                    row["last"] = float(display)
                if prev is not None:
                    row["prevClose"] = float(prev)
                if display is not None and prev is not None and float(prev) != 0:
                    row["dayPct"] = round((float(display) - float(prev)) / float(prev) * 100.0, 4)
                row["session"] = session
                row["sessionLabel"] = human.get(session, session.upper())
                row["updatedAtPT"] = stamp
                # refresh distance-to-put if put wall present
                put = row.get("faPutWall") or row.get("putWall")
                if put and display is not None and float(put) != 0:
                    spot = float(display)
                    pw = float(put)
                    pct = (spot - pw) / pw * 100.0
                    row["distanceToPutWallPct"] = round(pct, 2)
                    band = abs(pct) <= 0.5 or spot <= pw * 1.005
                    row["inGoodLowBand"] = bool(band)
                    if band:
                        row["statusHint"] = "GOOD_LOW"
                    elif spot < pw:
                        row["statusHint"] = "THRU_PUT"
                    else:
                        row["statusHint"] = "ABOVE_PUT"
                changed = True
                updated += 1
            if changed:
                sw["updatedAtPT"] = stamp
                sw["session"] = session
                sw["sessionLabel"] = human.get(session, session.upper())
                sp.write_text(json.dumps(sw, indent=2) + "\n")
                files.append(sp.name)
            continue
        sym = (sw.get("symbol") or "").strip().upper()
        if not sym:
            continue
        q = quotes.get(sym)
        if not q:
            missing.append(sym)
            continue
        last = q.get("last")
        last_non_reg = q.get("last_non_reg")
        prev = q.get("prev_close")
        display = last
        if session in ("pre", "ah") and last_non_reg is not None:
            display = last_non_reg
        elif session == "closed" and last is not None:
            display = last
        if display is not None:
            sw["last"] = float(display)
        if prev is not None:
            sw["prevClose"] = float(prev)
        if display is not None and prev is not None and float(prev) != 0:
            sw["dayPct"] = round((float(display) - float(prev)) / float(prev) * 100.0, 4)
        else:
            sw.pop("dayPct", None)
        sw["session"] = session
        sw["sessionLabel"] = human.get(session, session_label(session))
        sw["updatedAtPT"] = stamp
        sp.write_text(json.dumps(sw, indent=2) + "\n")
        files.append(sp.name)
        updated += 1
    return {"updated": updated, "missing": missing, "files": files, "session": session}


def apply_shay_equity_quotes(watch: dict, quotes: dict[str, dict], *, stamp_pt: Optional[str] = None) -> dict:
    """Update Shay equity watch marks: last, dayPct, sincePostPct, vsSpySincePost, session."""
    stamp = stamp_pt or format_pt()
    now_iso = _now_iso()
    session = market_session()
    human = {"rth": "RTH", "pre": "PRE-MARKET", "ah": "AFTER-HOURS", "closed": "CLOSED"}
    lab = human.get(session, session_label(session))

    spy_q = quotes.get("SPY") or {}
    spy_base = _f(watch.get("spyBaseline"))
    # Prefer extended in PRE/AH; else last (RTH / CLOSED Fri close)
    spy_last = spy_q.get("last")
    spy_non = spy_q.get("last_non_reg")
    if session in ("pre", "ah") and spy_non is not None:
        spy_display = spy_non
    else:
        spy_display = spy_last if spy_last is not None else spy_non
    spy_since = None
    if spy_display is not None and spy_base and float(spy_base) != 0:
        spy_since = round((float(spy_display) - float(spy_base)) / float(spy_base) * 100.0, 4)
        watch["spyLast"] = float(spy_display)
        watch["spySincePostPct"] = spy_since
    elif spy_display is not None:
        watch["spyLast"] = float(spy_display)

    updated = 0
    missing: list[str] = []
    for row in watch.get("symbols") or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        q = quotes.get(sym)
        if not q:
            missing.append(sym)
            continue
        last = q.get("last")
        last_non_reg = q.get("last_non_reg")
        prev = q.get("prev_close")
        display = last
        live_ext = False
        if session in ("pre", "ah") and last_non_reg is not None:
            display = last_non_reg
            live_ext = True
        elif session == "closed" and last is not None:
            display = last
        if last_non_reg is not None:
            row["lastNonReg"] = float(last_non_reg)
        if display is not None:
            row["last"] = float(display)
        if prev is not None:
            row["prevClose"] = float(prev)
        if q.get("previous_close_date"):
            row["prevCloseDate"] = q["previous_close_date"]

        day_pct = None
        if display is not None and prev is not None and float(prev) != 0:
            day_pct = round((float(display) - float(prev)) / float(prev) * 100.0, 4)
            row["dayPct"] = day_pct
        else:
            row.pop("dayPct", None)

        base = _f(row.get("baselinePrice"))
        since = None
        if display is not None and base and float(base) != 0:
            since = round((float(display) - float(base)) / float(base) * 100.0, 4)
            row["sincePostPct"] = since
        else:
            row.pop("sincePostPct", None)

        if since is not None and spy_since is not None:
            row["vsSpySincePost"] = round(since - spy_since, 4)
        else:
            row.pop("vsSpySincePost", None)

        row["session"] = session
        sess_lab = lab
        if live_ext:
            sess_lab = f"{lab} · LIVE"
        row["sessionLabel"] = sess_lab
        row["updatedAt"] = now_iso
        row["updatedAtPT"] = stamp
        updated += 1

    watch["updatedAt"] = now_iso
    watch["updatedAtPT"] = stamp
    watch["session"] = session
    watch["sessionLabel"] = lab
    return {
        "updated": updated,
        "missing": missing,
        "session": session,
        "spy_since_post_pct": spy_since,
        "n": len(watch.get("symbols") or []),
    }



def list_instrument_ids(ledger: dict) -> list[str]:
    ids = []
    for t in markable_rows(ledger):
        iid = t.get("instrumentId")
        if iid and iid not in ids:
            ids.append(str(iid))
    return ids


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_quotes(payload: Any) -> dict[str, dict]:
    """Map instrument_id -> {mark, bid, ask, underlying, delayed, raw}.

    Accepts:
      - RH get_option_quotes: {data:{results:[{quote:{...}}]}} or {results:[...]}
      - Simplified: { "<uuid>": {"mark"|"lastMark"|"mid": ..., "bid": ..., "ask": ...}, ... }
      - List of {instrument_id|instrumentId|id, mark|adjusted_mark_price|..., ...}
    """
    out: dict[str, dict] = {}

    def ingest(item: dict, key_hint: Optional[str] = None) -> None:
        q = item.get("quote") if isinstance(item.get("quote"), dict) else item
        iid = (
            key_hint
            or item.get("instrument_id")
            or item.get("instrumentId")
            or q.get("instrument_id")
            or q.get("instrumentId")
            or item.get("id")
            or item.get("instrument")
        )
        if not iid:
            return
        iid = str(iid)
        mark = (
            _f(q.get("adjusted_mark_price"))
            or _f(q.get("mark_price"))
            or _f(q.get("mark"))
            or _f(q.get("lastMark"))
            or _f(q.get("mid"))
            or _f(q.get("last_trade_price"))
            or _f(q.get("price"))
        )
        bid = _f(q.get("bid")) or _f(q.get("bid_price")) or _f(q.get("lastBid"))
        ask = _f(q.get("ask")) or _f(q.get("ask_price")) or _f(q.get("lastAsk"))
        if mark is None and bid is not None and ask is not None:
            mark = round((bid + ask) / 2.0, 4)
        und = (
            _f(q.get("underlying"))
            or _f(q.get("underlying_price"))
            or _f(q.get("lastUnderlying"))
            or _f(item.get("underlying_price"))
            or _f(item.get("lastUnderlying"))
        )
        delayed = bool(
            q.get("delayed")
            or q.get("quoteDelayed")
            or item.get("delayed")
            or item.get("quoteDelayed")
            or False
        )
        # Prefer official results[].close.price when present
        close_obj = item.get("close") if isinstance(item.get("close"), dict) else {}
        prior_close = (
            _f(close_obj.get("price"))
            or _f(q.get("previous_close_price"))
            or _f(q.get("previous_close"))
            or _f(item.get("previous_close_price"))
        )
        prior_close_date = (
            close_obj.get("date")
            or q.get("previous_close_date")
            or item.get("previous_close_date")
        )
        out[iid] = {
            "mark": mark,
            "bid": bid,
            "ask": ask,
            "underlying": und,
            "delayed": delayed,
            "delta": _f(q.get("delta")),
            "gamma": _f(q.get("gamma")),
            "theta": _f(q.get("theta")),
            "vega": _f(q.get("vega")),
            "iv": _f(q.get("implied_volatility")) or _f(q.get("iv")),
            "break_even": _f(q.get("break_even_price")) or _f(q.get("breakEven")),
            "quoted_at": q.get("updated_at") or q.get("lastQuotedAt"),
            "prior_close": prior_close,
            "prior_close_date": prior_close_date,
        }

    # Unwrap common MCP envelope {data: {...}}
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], (dict, list)):
        inner = payload["data"]
        if isinstance(inner, dict) and "results" in inner:
            payload = inner
        elif isinstance(inner, list):
            payload = inner

    if isinstance(payload, dict):
        skip = {
            "results", "quotes", "data", "instruments", "closes",
            "closes_error", "error", "meta", "guide",
        }
        sample_keys = [k for k in list(payload.keys())[:5] if k not in skip]
        if sample_keys and all(
            isinstance(payload[k], dict)
            and any(
                x in payload[k]
                for x in (
                    "mark", "bid", "ask", "adjusted_mark_price",
                    "bid_price", "lastMark", "mark_price", "quote",
                )
            )
            for k in sample_keys
        ):
            for k, v in payload.items():
                if k in skip:
                    continue
                if isinstance(v, dict):
                    ingest(v, key_hint=k)
            if out:
                return out

        for key in ("results", "quotes", "instruments"):
            arr = payload.get(key)
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict):
                        ingest(item)
                if out:
                    return out

        if any(k in payload for k in ("instrument_id", "instrumentId", "adjusted_mark_price", "mark", "quote")):
            ingest(payload)
            return out

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                ingest(item)

    return out



def list_underlying_symbols(ledger: dict) -> list[str]:
    """Unique underlying symbols for open seats + Leopold + Shay + soft watches."""
    syms: list[str] = []
    for t in markable_rows(ledger):
        s = (t.get("symbol") or t.get("ticker") or "").strip().upper()
        if s and s not in syms:
            syms.append(s)
    for s in shay_watch_symbols():
        if s and s not in syms:
            syms.append(s)
    for s in shay_ma_watch_symbols():
        if s and s not in syms:
            syms.append(s)
    for s in soft_watch_symbols():
        if s and s not in syms:
            syms.append(s)
    return syms


def normalize_equity_quotes(payload: Any) -> dict[str, dict]:
    """Map SYMBOL -> {last, last_non_reg, prev_close, bid, ask, delayed, raw bits}.

    Accepts RH get_equity_quotes: {data:{results:[{quote:{...}, close:{...}}]}}
    or simplified { "AMD": {"last_trade_price": ..., "adjusted_previous_close": ...}, ... }.
    """
    out: dict[str, dict] = {}

    def ingest(item: dict, key_hint: Optional[str] = None) -> None:
        q = item.get("quote") if isinstance(item.get("quote"), dict) else item
        close = item.get("close") if isinstance(item.get("close"), dict) else {}
        sym = (
            key_hint
            or q.get("symbol")
            or item.get("symbol")
            or item.get("ticker")
            or close.get("symbol")
        )
        if not sym:
            return
        sym = str(sym).strip().upper()
        last = _f(q.get("last_trade_price")) or _f(q.get("last")) or _f(q.get("price"))
        last_non_reg = (
            _f(q.get("last_non_reg_trade_price"))
            or _f(q.get("last_non_reg"))
            or _f(q.get("lastNonReg"))
            or _f(q.get("extended_hours_price"))
        )
        prev = (
            _f(q.get("adjusted_previous_close"))
            or _f(q.get("previous_close"))
            or _f(q.get("prev_close"))
            or _f(close.get("price"))
        )
        out[sym] = {
            "last": last,
            "last_non_reg": last_non_reg,
            "prev_close": prev,
            "previous_close_date": q.get("previous_close_date") or close.get("date"),
            "bid": _f(q.get("bid_price")) or _f(q.get("bid")),
            "ask": _f(q.get("ask_price")) or _f(q.get("ask")),
            "last_trade_time": q.get("venue_last_trade_time") or q.get("updated_at"),
            "last_non_reg_time": q.get("venue_last_non_reg_trade_time"),
            "state": q.get("state"),
            "has_traded": q.get("has_traded"),
        }

    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], (dict, list)):
        inner = payload["data"]
        if isinstance(inner, dict) and "results" in inner:
            payload = inner
        elif isinstance(inner, list):
            payload = inner

    if isinstance(payload, dict):
        skip = {
            "results", "quotes", "data", "instruments", "closes",
            "closes_error", "error", "meta", "guide",
        }
        sample_keys = [k for k in list(payload.keys())[:5] if k not in skip]
        if sample_keys and all(
            isinstance(payload[k], dict)
            and any(
                x in payload[k]
                for x in (
                    "last_trade_price", "last", "adjusted_previous_close",
                    "previous_close", "quote", "last_non_reg_trade_price",
                )
            )
            for k in sample_keys
        ):
            for k, v in payload.items():
                if k in skip:
                    continue
                if isinstance(v, dict):
                    ingest(v, key_hint=k)
            if out:
                return out

        # Shared rh-quotes cache: {quotes: {SYM: {...}}, count: N, ...}
        qmap = payload.get("quotes")
        if isinstance(qmap, dict) and qmap:
            sample = next(iter(qmap.values()), None)
            if isinstance(sample, dict):
                for k, v in qmap.items():
                    if isinstance(v, dict):
                        ingest(v, key_hint=k)
                if out:
                    return out

        for key in ("results", "quotes", "instruments"):
            arr = payload.get(key)
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict):
                        ingest(item)
                if out:
                    return out

        if any(k in payload for k in ("symbol", "last_trade_price", "adjusted_previous_close", "quote")):
            ingest(payload)
            return out

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                ingest(item)

    return out


def apply_equity_quotes(ledger: dict, quotes: dict[str, dict], *, stamp_pt: Optional[str] = None) -> dict:
    """Stamp session + day% fields onto open seats / Leopold watches."""
    stamp = stamp_pt or format_pt()
    now_iso = _now_iso()
    session = market_session()
    updated = 0
    missing: list[str] = []

    for t in markable_rows(ledger):
        sym = (t.get("symbol") or t.get("ticker") or "").strip().upper()
        if not sym:
            continue
        q = quotes.get(sym)
        if not q:
            missing.append(sym)
            continue

        last = q.get("last")
        last_non_reg = q.get("last_non_reg")
        prev = q.get("prev_close")

        # Prefer extended-hours print in PRE/AH when available
        display = last
        if last_non_reg is not None:
            t["lastNonRegUnderlying"] = float(last_non_reg)
            if session == "ah":
                t["underlyingAh"] = float(last_non_reg)
            elif session == "pre":
                t["underlyingPre"] = float(last_non_reg)
            elif session == "closed":
                # Keep last known AH/PRE print for weekend / overnight display
                if "underlyingAh" not in t and "underlyingPre" not in t:
                    t["underlyingAh"] = float(last_non_reg)
        else:
            t.pop("lastNonRegUnderlying", None)

        live_ext = False
        if session in ("pre", "ah") and last_non_reg is not None:
            display = last_non_reg
            live_ext = True
            t["underlyingExtendedLive"] = True
            t["underlyingPriceSource"] = "extended"  # PRE/AH live print
        elif session == "closed" and last is not None:
            display = last
            t["underlyingExtendedLive"] = False
            t["underlyingPriceSource"] = "rth_close"
        else:
            t["underlyingExtendedLive"] = False
            t["underlyingPriceSource"] = "rth" if session == "rth" else session

        if display is not None:
            t["lastUnderlying"] = float(display)
            t["underlyingNow"] = float(display)
        if prev is not None:
            t["underlyingPrevClose"] = float(prev)

        # Day% uses the displayed print (extended in PRE/AH, RTH close when closed)
        day_pct = None
        if display is not None and prev is not None and float(prev) != 0:
            day_pct = round((float(display) - float(prev)) / float(prev) * 100.0, 4)
            t["underlyingDayPct"] = day_pct
        else:
            t.pop("underlyingDayPct", None)

        t["underlyingSession"] = session
        # Human labels for blotter (not just PRE/AH)
        human = {"rth": "RTH", "pre": "PRE-MARKET", "ah": "AFTER-HOURS", "closed": "CLOSED"}
        lab = human.get(session, session_label(session))
        if live_ext:
            lab = f"{lab} · LIVE"
        t["underlyingSessionLabel"] = lab
        if q.get("previous_close_date"):
            t["underlyingPrevCloseDate"] = q["previous_close_date"]
        t["underlyingQuotedAt"] = now_iso
        t["underlyingQuotedAtPT"] = stamp
        t["updatedAt"] = now_iso
        t["updatedAtPT"] = stamp
        updated += 1

    ledger["updatedAt"] = now_iso
    ledger["updatedAtPT"] = stamp
    ledger.setdefault("meta", {})
    ledger["meta"]["marketSession"] = session
    ledger["meta"]["marketSessionLabel"] = session_label(session)
    ledger["meta"]["lastEquityRefreshAt"] = now_iso
    ledger["meta"]["lastEquityRefreshAtPT"] = stamp
    ledger["meta"]["lastEquityUpdatedCount"] = updated
    ledger["meta"]["lastEquityMissing"] = missing
    if session in ("pre", "ah"):
        ledger["meta"]["lastUnderlyingRefreshNote"] = (
            f"{session_label(session)} live — spot uses extended-hours print when available (not RTH)"
        )
    elif session == "closed":
        ledger["meta"]["lastUnderlyingRefreshNote"] = (
            "CLOSED — spot = last RTH close; last AH/PRE print kept when RH still returns last_non_reg"
        )
    else:
        ledger["meta"]["lastUnderlyingRefreshNote"] = "RTH — normal hours spot"
    return {
        "session": session,
        "session_label": session_label(session),
        "updated": updated,
        "missing": missing,
        "symbols": len(quotes),
    }


def apply_quotes(ledger: dict, quotes: dict[str, dict], *, stamp_pt: Optional[str] = None) -> dict:
    stamp = stamp_pt or format_pt()
    now_iso = _now_iso()
    updated = 0
    missing = []
    updated_open = 0
    updated_watch = 0
    for t in markable_rows(ledger):
        iid = str(t.get("instrumentId") or "")
        q = quotes.get(iid)
        if not q or q.get("mark") is None:
            missing.append(t.get("id") or iid)
            continue
        mark = float(q["mark"])
        apply_mark_update(t, mark, at_pt=stamp)
        if q.get("bid") is not None:
            t["lastBid"] = float(q["bid"])
        if q.get("ask") is not None:
            t["lastAsk"] = float(q["ask"])
        if q.get("underlying") is not None:
            t["lastUnderlying"] = float(q["underlying"])
            t["underlyingNow"] = float(q["underlying"])
        t["lastOptionMark"] = mark
        t["lastQuotedAt"] = now_iso
        t["lastQuotedAtPT"] = stamp
        t["lastCheckedAt"] = now_iso
        t["updatedAt"] = now_iso
        t["updatedAtPT"] = stamp
        t["quoteDelayed"] = bool(q.get("delayed"))
        t["quoteAgeSec"] = 0
        # Greeks (RH per-share); thetaUsdPerDay = θ × 100 × qty for premium bleed
        for gk, field in (("delta", "delta"), ("gamma", "gamma"), ("theta", "theta"), ("vega", "vega"), ("iv", "iv")):
            if q.get(gk) is not None:
                t[field] = float(q[gk])
        if q.get("quoted_at"):
            t["greeksAt"] = q["quoted_at"]
        th = _f(t.get("theta"))
        try:
            qty = max(1, int(t.get("qtySuggested") or 1))
        except (TypeError, ValueError):
            qty = 1
        if th is not None:
            t["thetaUsdPerDay"] = round(th * 100.0 * qty, 2)
            t["thetaUsdPerDayNote"] = "RH θ × 100 × qty (long premium bleed when negative)"
        de = _f(t.get("delta"))
        if de is not None:
            t["deltaShares"] = round(de * 100.0 * qty, 1)
        if q.get("break_even") is not None:
            t["breakEvenRh"] = float(q["break_even"])
        try:
            from breakeven import apply_breakeven
            apply_breakeven(t)
        except Exception:
            pass
        # Day P&L vs prior-session option close; Week ≈ vs entry (this week)
        if q.get("prior_close") is not None:
            pc = float(q["prior_close"])
            t["markPriorClose"] = pc
            if q.get("prior_close_date"):
                t["markPriorCloseDate"] = q["prior_close_date"]
            t["dayPnlUsd"] = round((mark - pc) * 100.0 * qty, 2)
        er_w = entry_ref(t)
        if er_w is not None:
            t["weekPnlUsd"] = round((mark - float(er_w)) * 100.0 * qty, 2)
        # Ensure entry cost basis fields stay visible
        if t.get("costBasis") is None:
            er = entry_ref(t)
            if er is not None:
                t["costBasis"] = er
        updated += 1
        st = (t.get("status") or "").lower()
        if st in WATCH_STATUSES or t.get("agent") == "Leopold":
            updated_watch += 1
        else:
            updated_open += 1

    ledger["updatedAt"] = now_iso
    ledger["updatedAtPT"] = stamp
    ledger.setdefault("meta", {})
    ledger["meta"]["lastMarksRefreshAt"] = now_iso
    ledger["meta"]["lastMarksRefreshAtPT"] = stamp
    ledger["meta"]["lastMarksUpdatedCount"] = updated
    ledger["meta"]["lastMarksMissing"] = missing
    ledger["meta"]["lastMarksUpdatedOpen"] = updated_open
    ledger["meta"]["lastMarksUpdatedWatch"] = updated_watch
    try:
        _rollup_period_pnl(ledger, stamp)
    except Exception as e:
        ledger["meta"]["periodPnlError"] = str(e)[:200]
    return {
        "updated": updated,
        "updated_open": updated_open,
        "updated_watch": updated_watch,
        "missing": missing,
        "open": len(open_trades(ledger)),
        "watches": len(leopold_watches(ledger)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh paper ticket marks from RH quotes JSON")
    ap.add_argument("--quotes-file", type=Path, help="Path to option quotes JSON")
    ap.add_argument("--quotes-stdin", action="store_true", help="Read option quotes JSON from stdin")
    ap.add_argument("--equity-quotes-file", type=Path, help="Path to equity quotes JSON (get_equity_quotes)")
    ap.add_argument("--equity-quotes-stdin", action="store_true", help="Read equity quotes JSON from stdin")
    ap.add_argument("--list-ids", action="store_true", help="Print open instrumentIds JSON and exit")
    ap.add_argument("--list-symbols", action="store_true", help="Print open underlying symbols JSON and exit")
    ap.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    args = ap.parse_args()

    ledger = load_ledger()

    if args.list_ids:
        ids = list_instrument_ids(ledger)
        print(json.dumps({
            "instrument_ids": ids,
            "count": len(ids),
            "open_tickets": len(open_trades(ledger)),
            "leopold_watches": len(leopold_watches(ledger)),
            "session": market_session(),
            "session_label": session_label(),
        }, indent=2))
        return 0

    if args.list_symbols:
        syms = list_underlying_symbols(ledger)
        shay_syms = [s for s in shay_watch_symbols() if s != "SPY"]
        shay_ma_syms = shay_ma_watch_symbols()
        soft_syms = soft_watch_symbols()
        print(json.dumps({
            "symbols": syms,
            "count": len(syms),
            "open_tickets": len(open_trades(ledger)),
            "leopold_watches": len(leopold_watches(ledger)),
            "shay_watch_n": len(shay_syms),
            "shay_symbols": shay_syms,
            "shay_ma_watch_n": len(shay_ma_syms),
            "shay_ma_symbols": shay_ma_syms,
            "soft_watch_n": len(soft_syms),
            "soft_symbols": soft_syms,
            "session": market_session(),
            "session_label": session_label(),
        }, indent=2))
        return 0

    has_opt = bool(args.quotes_file or args.quotes_stdin)
    has_eq = bool(args.equity_quotes_file or args.equity_quotes_stdin)
    if not has_opt and not has_eq:
        ap.error("Provide --quotes-file/--quotes-stdin and/or --equity-quotes-file/--equity-quotes-stdin, or --list-ids/--list-symbols")

    if args.quotes_stdin and args.equity_quotes_stdin:
        ap.error("Cannot use both --quotes-stdin and --equity-quotes-stdin (pass files instead)")

    summary: dict[str, Any] = {}
    eq_summary: dict[str, Any] = {}

    if has_opt:
        raw = sys.stdin.read() if args.quotes_stdin else args.quotes_file.read_text()
        payload = json.loads(raw)
        quotes = normalize_quotes(payload)
        if not quotes:
            print("ERROR: no option quotes parsed from payload", file=sys.stderr)
            print(json.dumps({"preview_keys": list(payload.keys())[:20] if isinstance(payload, dict) else type(payload).__name__}, indent=2), file=sys.stderr)
            return 2
        summary = apply_quotes(ledger, quotes)
        # Keep Data Sources `rh-option-marks` fresh whenever option marks land (TTL 300s).
        if write_feed is not None and not args.dry_run:
            try:
                write_feed(
                    "rh-option-marks",
                    source="user-robinhood-trading get_option_quotes",
                    writer="refresh_marks.py",
                    symbols=sorted({str(q.get("symbol") or "") for q in quotes.values() if isinstance(q, dict)} - {""})
                    or None,
                    payload={
                        "marks": quotes if isinstance(quotes, dict) else {"n": len(quotes)},
                        "open_updated": (summary or {}).get("updated") if isinstance(summary, dict) else None,
                    },
                    ttl_seconds=300,
                )
                if isinstance(summary, dict):
                    summary["rh_option_marks_feed"] = "wrote"
            except Exception as e:
                if isinstance(summary, dict):
                    summary["rh_option_marks_feed_error"] = str(e)

    if has_eq:
        raw_eq = sys.stdin.read() if args.equity_quotes_stdin else args.equity_quotes_file.read_text()
        eq_payload = json.loads(raw_eq)
        eq_quotes = normalize_equity_quotes(eq_payload)
        if not eq_quotes:
            print("ERROR: no equity quotes parsed from payload", file=sys.stderr)
            print(json.dumps({"preview_keys": list(eq_payload.keys())[:20] if isinstance(eq_payload, dict) else type(eq_payload).__name__}, indent=2), file=sys.stderr)
            return 2
        eq_summary = apply_equity_quotes(ledger, eq_quotes)
        # Keep Data Sources `rh-quotes` fresh whenever equities land (TTL 120s).
        if write_feed is not None and not args.dry_run:
            try:
                write_feed(
                    "rh-quotes",
                    source="user-robinhood-trading get_equity_quotes",
                    writer="refresh_marks.py",
                    symbols=sorted(eq_quotes.keys()),
                    payload={
                        "quotes": {
                            sym: {
                                "last": q.get("last"),
                                "previous_close": q.get("prev_close") or q.get("previous_close"),
                                "bid": q.get("bid"),
                                "ask": q.get("ask"),
                                "venue_last_trade_time": q.get("last_trade_time") or q.get("last_non_reg_time"),
                                "state": q.get("state"),
                            }
                            for sym, q in eq_quotes.items()
                        },
                        "count": len(eq_quotes),
                    },
                    ttl_seconds=120,
                )
                eq_summary["rh_quotes_feed"] = "wrote"
            except Exception as e:
                eq_summary["rh_quotes_feed_error"] = str(e)
        soft_sum = apply_soft_watch_equity_quotes(eq_quotes)
        if soft_sum.get("updated"):
            eq_summary["soft_watches"] = soft_sum
        shay_ma = load_shay_ma_watch()
        if shay_ma.get("symbols"):
            shay_ma_sum = apply_shay_ma_equity_quotes(shay_ma, eq_quotes)
            if not args.dry_run:
                SHAY_MA_WATCH_PATH.write_text(json.dumps(shay_ma, indent=2) + "\n")
                (ROOT / "shay-ma-levels-watch.json").write_text(json.dumps(shay_ma, indent=2) + "\n")
                md_latest = ROOT.parent / "market-data" / "latest"
                if md_latest.is_dir():
                    stamp_ma = {
                        "as_of": shay_ma.get("updatedAt"),
                        "as_of_pt": shay_ma.get("updatedAtPT"),
                        "writer": "refresh_marks.py",
                        "feed": "shay-ma-levels",
                        "n": shay_ma_sum.get("n"),
                        "updated": shay_ma_sum.get("updated"),
                        "session": shay_ma_sum.get("session"),
                        "bullish": shay_ma_sum.get("bullish"),
                        "hold": shay_ma_sum.get("hold"),
                        "bearish": shay_ma_sum.get("bearish"),
                        "path": str(SHAY_MA_WATCH_PATH),
                        "postUrl": shay_ma.get("postUrl"),
                    }
                    (md_latest / "shay-ma-levels-watch.json").write_text(json.dumps(stamp_ma, indent=2) + "\n")
            eq_summary["shay_ma"] = shay_ma_sum
            ledger.setdefault("meta", {})
            ledger["meta"]["shayMaWatchUpdated"] = shay_ma_sum.get("updated")
            ledger["meta"]["shayMaWatchPath"] = str(SHAY_MA_WATCH_PATH.name)
            ledger["shayMaWatchesPath"] = SHAY_MA_WATCH_PATH.name
        shay = load_shay_watch()
        if shay.get("symbols"):
            shay_sum = apply_shay_equity_quotes(shay, eq_quotes)
            if not args.dry_run:
                SHAY_WATCH_PATH.write_text(json.dumps(shay, indent=2) + "\n")
                # Soft stamp for Data sources tab
                md_latest = ROOT.parent / "market-data" / "latest"
                if md_latest.is_dir():
                    stamp = {
                        "as_of": shay.get("updatedAt"),
                        "as_of_pt": shay.get("updatedAtPT"),
                        "writer": "refresh_marks.py",
                        "feed": "shay-semi-watch",
                        "n": shay_sum.get("n"),
                        "updated": shay_sum.get("updated"),
                        "session": shay_sum.get("session"),
                        "path": str(SHAY_WATCH_PATH),
                        "baselineDate": shay.get("baselineDate"),
                        "postUrl": shay.get("postUrl"),
                    }
                    (md_latest / "shay-semi-watch.json").write_text(json.dumps(stamp, indent=2) + "\n")
            eq_summary["shay"] = shay_sum
            ledger.setdefault("meta", {})
            ledger["meta"]["shayWatchUpdated"] = shay_sum.get("updated")
            ledger["meta"]["shayWatchPath"] = str(SHAY_WATCH_PATH.name)
            ledger["meta"]["lastShayRefreshAtPT"] = ledger["meta"].get("lastEquityRefreshAtPT")
            # Soft pointer only — watches live in shay-semi-watch.json (no seats)
            ledger["shayWatchesPath"] = SHAY_WATCH_PATH.name
            ledger["equityWatchesNote"] = (
                "Shay / equity watches in shay-semi-watch.json — soft only, do not consume seats"
            )
    else:
        # Still stamp current session onto ledger meta when only option marks refresh
        session = market_session()
        ledger.setdefault("meta", {})
        ledger["meta"]["marketSession"] = session
        ledger["meta"]["marketSessionLabel"] = session_label(session)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "options": summary, "equity": eq_summary}, indent=2))
        return 0

    TRADES_PATH.write_text(json.dumps(ledger, indent=2) + "\n")
    # Mirror into dashboard for static hosting
    (ROOT / "trades.json").write_text(json.dumps(ledger, indent=2) + "\n")
    print(json.dumps({"ok": True, "wrote": str(TRADES_PATH), "options": summary, "equity": eq_summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
