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
  --no-mini                   don't overlay fresh Mac-mini marks (cache/mini-quotes.json)

Mini overlay: after the RH trade-date stale guard, core-20 rows get bid/ask/last (RTH) or
last_non_reg (PRE/AH) from the mini poller cache when <=15s (RTH) / <=120s (PRE/AH) old.
prev_close always stays RH. rh-quotes.json is still written with pure RH values.

Option marks (2026-10-10): cache/mini-option-quotes.json (Alpaca OPRA via the mini, quotes/option_marks.py)
is the PRIMARY option mark source when live (<=60 s RTH); RH get_option_quotes is the fallback. Outside
RTH the newer of the two final quotes wins. Every marked row records quoteSource / markSource /
markClass (live|final|stale). Seats neither source can price keep their last good mark with markStale.
Multi-leg seats (legs[], e.g. Hal credit spreads) are marked leg by leg from the same sources.
  --options-from-mini   mark options from the mini OPRA cache alone (no RH option file needed)
  --no-mini-options     RH option payload only (old behaviour)

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
def _fq(v):
    """Paper seat size: int when whole; fractional after a scale-out (e.g. 0.5). 2026-10-08 SCALE_OUT_+20PCT."""
    try:
        q = float(v)
    except (TypeError, ValueError):
        return 1
    if q <= 0:
        return 1
    return int(q) if q.is_integer() else q

from market_session import market_session, session_label  # noqa: E402
from quote_freshness import (  # noqa: E402
    check_quotes, EQUITY_TIME_KEYS, OPTION_TIME_KEYS, STALE_EXIT_CODE,
)
sys.path.insert(0, str(ROOT.parent / "market-data"))
try:
    from cache_io import write_feed  # noqa: E402
except Exception:  # pragma: no cover
    write_feed = None  # type: ignore
# Mac mini 5s collector (core-20) — preferred fresh equity marks; RH stays the base/fallback.
sys.path.insert(0, str(ROOT.parent / "quotes"))
try:
    from mini_client import overlay_rh_quotes  # noqa: E402
except Exception:  # pragma: no cover
    overlay_rh_quotes = None  # type: ignore
# Mac mini Alpaca OPRA option marks (2026-10-10): mini first when live, RH fallback, last good + stale flag.
try:
    import option_marks as om  # noqa: E402
except Exception:  # pragma: no cover
    om = None  # type: ignore

OPEN_STATUSES = frozenset({"open", "watching", "paper", "live"})
# External watches (Leopold/ZH) — refreshed for marks but NEVER counted as paper seats
WATCH_STATUSES = frozenset({"leopold_watch", "watch_external"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        raw = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _quote_age_sec(quoted_at: Any, *, now: Optional[datetime] = None) -> Optional[int]:
    dt = _parse_iso(quoted_at) if not isinstance(quoted_at, datetime) else quoted_at
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0, int((now - dt).total_seconds()))


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
        if not iid and isinstance(t.get("legs"), list) and t.get("legs"):
            continue  # multi-leg seat: apply_multileg_marks() owns it
        q = quotes.get(iid)
        if not q or q.get("mark") is None:
            missing.append(t.get("id") or iid)
            exp = str(t.get("expiry") or t.get("expiration") or "")[:10]
            if exp and exp < datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d"):
                _flag_last_good(t, now_iso, f"contract expired {exp}; no venue quotes exist (retire this row)")
            else:
                _flag_last_good(t, now_iso, "no quote from mini OPRA or RH this cycle")
            continue
        mark = float(q["mark"])
        # Refuse older RH quote stamps over fresher seat quoteUpdatedAt/greeksAt (stale second-writer guard).
        incoming_qat = q.get("quoted_at")
        incoming_dt = _parse_iso(incoming_qat)
        prev_candidates = [_parse_iso(t.get("quoteUpdatedAt")), _parse_iso(t.get("greeksAt"))]
        prev_dt = max((d for d in prev_candidates if d is not None), default=None)
        if incoming_dt is not None and prev_dt is not None and incoming_dt < prev_dt:
            missing.append(f"{t.get('id') or iid}:stale_quote_skipped")
            continue
        apply_mark_update(t, mark, at_pt=stamp)
        if q.get("bid") is not None:
            t["lastBid"] = float(q["bid"])
            t["bid"] = float(q["bid"])
        if q.get("ask") is not None:
            t["lastAsk"] = float(q["ask"])
            t["ask"] = float(q["ask"])
        # Keep elevate/OPEN mark/bid/ask in sync with live last* (dual-field drift bug).
        t["mark"] = mark
        try:
            _qty_prem = _fq(t.get("qtySuggested") or 1)
        except (TypeError, ValueError):
            _qty_prem = 1
        t["premiumAtMarkUsd"] = round(mark * 100.0 * _qty_prem, 2)
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
        # Advance quoteUpdatedAt only when RH stamp is present; never regress; age from quote stamp not wall clock.
        now_dt = datetime.now(timezone.utc)
        if incoming_dt is not None:
            t["quoteUpdatedAt"] = incoming_qat if isinstance(incoming_qat, str) else incoming_dt.isoformat().replace("+00:00", "Z")
        elif t.get("quoteUpdatedAt") is None:
            t["quoteUpdatedAt"] = now_iso
        age = _quote_age_sec(t.get("quoteUpdatedAt"), now=now_dt)
        if age is None:
            age = 0
        t["quoteAgeSec"] = age
        t["quoteAgeClass"] = "stale" if (t["quoteDelayed"] or age > 120) else "live"
        t["quoteRealtime"] = not bool(t["quoteDelayed"])
        _stamp_mark_source(t, q)
        if not q.get("mark_source"):
            if t.get("quoteSource") in (None, "rh_live") or str(t.get("quoteSource", "")).startswith("rh"):
                t["quoteSource"] = "rh_live"
        # Greeks (RH per-share); thetaUsdPerDay = θ × 100 × qty for premium bleed
        for gk, field in (("delta", "delta"), ("gamma", "gamma"), ("theta", "theta"), ("vega", "vega"), ("iv", "iv")):
            if q.get(gk) is not None:
                t[field] = float(q[gk])
        if q.get("quoted_at"):
            t["greeksAt"] = q["quoted_at"]
        th = _f(t.get("theta"))
        try:
            qty = _fq(t.get("qtySuggested") or 1)
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


MARK_SOURCE_LABEL = {
    "mini-opra": "mini_opra",  # Alpaca OPRA via Mac mini collector
    "rh": "rh_live",
}


def _stamp_mark_source(t: dict, q: dict) -> None:
    """Record which feed produced the mark (mini OPRA vs RH) + live/final/stale class."""
    src = q.get("mark_source")
    if not src:
        return
    t["quoteSource"] = MARK_SOURCE_LABEL.get(src, src)
    t["markSourceFeed"] = src
    t["markClass"] = q.get("mark_class")
    t["markStale"] = q.get("mark_class") == "stale"
    if q.get("mark_age_s") is not None:
        t["markAgeSec"] = int(float(q["mark_age_s"]))
    if src == "mini-opra":
        t["quoteDelayed"] = False
        t["quoteRealtime"] = True
        if q.get("mark_class") == "live":
            t["quoteAgeClass"] = "live"
    t.pop("markStaleReason", None)


def _flag_last_good(t: dict, now_iso: str, reason: str) -> None:
    """Never blank: keep the last good mark, flag it stale with the reason."""
    if t.get("lastMark") is None and t.get("mark") is None:
        return
    t["markStale"] = True
    t["markClass"] = "stale"
    t["quoteAgeClass"] = "stale"
    t["markStaleReason"] = reason
    t["markStaleCheckedAt"] = now_iso


def apply_multileg_marks(ledger: dict, *, rh_quotes: Optional[dict[str, dict]] = None,
                         mini_rows: Optional[dict] = None, session: Optional[str] = None,
                         stamp_pt: Optional[str] = None) -> dict:
    """Mark open multi-leg seats (legs[]) leg by leg: mini OPRA first, RH (by leg instrumentId) fallback.

    Credit structures (entryCredit set): mark = cost-to-close = sum(short mids) - sum(long mids);
    P&L = (entryCredit - mark) x qty x 100 (lower mark is better). Debit structures: mark = net value,
    long-premium P&L via apply_mark_update. Writes only when EVERY leg is priced and the newest leg
    quote is not older than the seat's quoteUpdatedAt (stale second-writer guard).
    """
    if om is None:
        return {"skipped": "option_marks unavailable"}
    stamp = stamp_pt or format_pt()
    now_iso = _now_iso()
    rh_quotes = rh_quotes or {}
    out: dict[str, Any] = {"updated": [], "partial": [], "skipped_older": [], "sources": {}}
    for t in open_trades(ledger):
        legs = t.get("legs")
        if t.get("instrumentId") or not isinstance(legs, list) or not legs:
            continue
        tid = t.get("id") or "?"
        priced = []
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            lg = dict(leg)
            lg.setdefault("symbol", t.get("symbol") or t.get("underlying"))
            lg.setdefault("expiry", t.get("expiry"))
            occ = om.row_occ(lg)
            rh = rh_quotes.get(str(leg.get("instrumentId") or ""))
            best = om.pick_mark(occ, rh=rh, mini_rows=mini_rows, session=session) if occ else None
            priced.append((leg, occ, best, rh))
        if not priced or any(b is None for _, _, b, _ in priced):
            out["partial"].append(tid)
            _flag_last_good(t, now_iso, "not every leg priced by mini OPRA or RH this cycle")
            continue
        newest = max((om.mc._parse_ts(b.get("quoted_at")) or 0.0) for _, _, b, _ in priced)
        prev = _parse_iso(t.get("quoteUpdatedAt"))
        if prev is not None and newest and newest + 1 < prev.timestamp():
            out["skipped_older"].append(tid)
            continue
        base_q = min(abs(float(l.get("qty") or 1)) for l, _, _, _ in priced) or 1.0
        value = 0.0
        leg_marks = dict(t.get("legMarks") or {})
        srcs = set()
        classes = set()
        for leg, occ, b, rh in priced:
            ratio = abs(float(leg.get("qty") or 1)) / base_q
            sign = 1.0 if (leg.get("side") or "").lower() == "long" else -1.0
            value += sign * ratio * float(b["mark"])
            leg["bid"], leg["ask"] = b.get("bid"), b.get("ask")
            leg["mark"] = leg["lastMark"] = float(b["mark"])
            leg["quotedAt"] = b.get("quoted_at")
            leg["quotedAtPT"] = stamp
            leg["delayed"] = bool(b.get("delayed"))
            leg["occ"] = occ
            leg["markSource"] = b["mark_source"]
            lm = dict(leg_marks.get(om.leg_key(leg)) or {})
            lm.update({"bid": b.get("bid"), "ask": b.get("ask"), "mark": float(b["mark"]), "updatedAt": b.get("quoted_at"),
                       "source": b["mark_source"], "markClass": b["mark_class"]})
            if rh:  # greeks only exist on the RH payload
                for gk in ("delta", "gamma", "theta", "vega", "iv"):
                    if rh.get(gk) is not None:
                        lm[gk] = rh[gk]
            leg_marks[om.leg_key(leg)] = lm
            srcs.add(b["mark_source"])
            classes.add(b["mark_class"])
        t["legMarks"] = leg_marks
        q = _fq(t.get("qty") or t.get("qtySuggested") or 1)
        credit = _f(t.get("entryCredit"))
        if credit is not None:
            mark = round(-value, 4)
            t["costToClose"] = mark
            t["lastCreditMid"] = mark
            shorts = [float(b["mark"]) for l, _, b, _ in priced if (l.get("side") or "").lower() == "short"]
            longs = [float(b["mark"]) for l, _, b, _ in priced if (l.get("side") or "").lower() == "long"]
            if len(shorts) == 1:
                t["shortMid"] = shorts[0]
            if len(longs) == 1:
                t["longMid"] = longs[0]
            t["lastMark"] = t["mark"] = mark
            pnl = round((credit - mark) * q * 100.0, 2)
            t["pnlUsd"] = t["unrealizedPnlUsd"] = t["unrealizedUsd"] = pnl
            if credit:
                pct = round((credit - mark) / credit * 100.0, 2)
                t["pnlPct"] = t["unrealizedPnlPct"] = t["unrealizedPct"] = pct
            if t.get("realizedPnlUsd") is not None:
                t["seatTotalPnlUsd"] = round(pnl + float(t["realizedPnlUsd"]), 2)
            if t.get("troughMark") is None or mark < float(t["troughMark"]):
                t["troughMark"], t["troughMarkAtPT"] = mark, stamp
            if t.get("peakMark") is None or mark > float(t["peakMark"]):
                t["peakMark"], t["peakMarkAtPT"] = mark, stamp
        else:
            mark = round(value, 4)
            apply_mark_update(t, mark, at_pt=stamp)
            t["mark"] = mark
        src_label = "mini_opra" if srcs == {"mini-opra"} else ("rh_live" if srcs == {"rh"} else "mini_opra+rh")
        t["quoteSource"] = src_label
        t["markSourceFeed"] = ",".join(sorted(srcs))
        t["markSource"] = f"leg mids via {src_label} ({'credit cost-to-close' if credit is not None else 'net debit'} {mark})"
        t["markClass"] = "stale" if "stale" in classes else ("live" if classes == {"live"} else "final")
        t["markStale"] = t["markClass"] == "stale"
        t.pop("markStaleReason", None)
        t["lastOptionMark"] = mark
        t["lastMarkWriter"] = t["lastWriter"] = "refresh_marks.py (multi-leg)"
        t["lastMarkedAtPT"] = t["lastMarkAtPT"] = t["lastQuotedAtPT"] = t["updatedAtPT"] = stamp
        t["lastQuotedAt"] = t["updatedAt"] = now_iso
        if newest:
            t["quoteUpdatedAt"] = datetime.fromtimestamp(newest, timezone.utc).isoformat().replace("+00:00", "Z")
            t["quoteUpdatedAtPT"] = format_pt(datetime.fromtimestamp(newest, timezone.utc))
            t["quoteAgeSec"] = max(0, int(datetime.now(timezone.utc).timestamp() - newest))
        t["quoteDelayed"] = any(bool(b.get("delayed")) for _, _, b, _ in priced)
        out["updated"].append(tid)
        out["sources"][tid] = src_label
    return out


def sync_paper_open(ledger: dict, path: Optional[Path] = None) -> int:
    """Mirror fresh marks/P&L of open seats into paper-open.json seat summaries (same ids)."""
    p = path or (PT_DIR / "paper-open.json")
    try:
        po = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    by_id = {t.get("id"): t for t in open_trades(ledger) if t.get("id")}
    n = 0
    for key in ("seats", "roseSeats", "halSeats"):
        for s in po.get(key) or []:
            t = by_id.get(s.get("id")) if isinstance(s, dict) else None
            if not t or t.get("lastMark") is None:
                continue
            s["lastMark"] = t.get("lastMark")
            for k_src, k_dst in (("pnlUsd", "pnlUsd"), ("pnlPct", "pnlPct"), ("seatTotalPnlUsd", "seatTotalPnlUsd"),
                                 ("lastCreditMid", "lastCreditMid"), ("quoteUpdatedAtPT", "quotedAtPT"),
                                 ("quoteSource", "quoteSource"), ("markClass", "markClass")):
                if t.get(k_src) is not None:
                    s[k_dst] = t[k_src]
            n += 1
    if n:
        p.write_text(json.dumps(po, indent=2) + "\n")
        mirror = ROOT / "paper-open.json"
        if mirror.exists():
            mirror.write_text(json.dumps(po, indent=2) + "\n")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh paper ticket marks from RH quotes JSON")
    ap.add_argument("--quotes-file", type=Path, help="Path to option quotes JSON")
    ap.add_argument("--quotes-stdin", action="store_true", help="Read option quotes JSON from stdin")
    ap.add_argument("--equity-quotes-file", type=Path, help="Path to equity quotes JSON (get_equity_quotes)")
    ap.add_argument("--equity-quotes-stdin", action="store_true", help="Read equity quotes JSON from stdin")
    ap.add_argument("--list-ids", action="store_true", help="Print open instrumentIds JSON and exit")
    ap.add_argument("--list-symbols", action="store_true", help="Print open underlying symbols JSON and exit")
    ap.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    ap.add_argument("--no-mini", action="store_true",
                    help="Skip Mac-mini 5s mark overlay (use RH equity payload only)")
    ap.add_argument("--options-from-mini", action="store_true",
                    help="Mark options from cache/mini-option-quotes.json (Alpaca OPRA) without an RH option file")
    ap.add_argument("--no-mini-options", action="store_true",
                    help="Option marks from the RH payload only (skip mini OPRA)")
    ap.add_argument(
        "--allow-stale",
        action="store_true",
        help="Bypass the trade-date freshness guard (backfill/debug only; never in live routines)",
    )
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

    has_rh_opt = bool(args.quotes_file or args.quotes_stdin)
    use_mini_opt = om is not None and not args.no_mini_options
    has_opt = has_rh_opt or (args.options_from_mini and use_mini_opt)
    has_eq = bool(args.equity_quotes_file or args.equity_quotes_stdin)
    if not has_opt and not has_eq:
        ap.error("Provide --quotes-file/--quotes-stdin, --options-from-mini and/or --equity-quotes-file/--equity-quotes-stdin, or --list-ids/--list-symbols")

    if args.quotes_stdin and args.equity_quotes_stdin:
        ap.error("Cannot use both --quotes-stdin and --equity-quotes-stdin (pass files instead)")

    summary: dict[str, Any] = {}
    eq_summary: dict[str, Any] = {}

    if has_opt:
        mini_rows: Optional[dict] = None
        mini_info: dict[str, Any] = {}
        if use_mini_opt:
            try:
                c = om.read_option_cache()
                mini_rows = c["quotes"]
                mini_info = {"file_age_s": c.get("file_age_s"), "fresh_file": c.get("fresh_file"), "rows": len(mini_rows)}
            except Exception as e:  # never block RH marks on the mini path
                mini_info = {"error": type(e).__name__}
        if has_rh_opt:
            raw = sys.stdin.read() if args.quotes_stdin else args.quotes_file.read_text()
            payload = json.loads(raw)
            quotes = normalize_quotes(payload)
        else:
            payload, quotes = {}, {}
        if has_rh_opt and not quotes and not mini_rows:
            print("ERROR: no option quotes parsed from payload", file=sys.stderr)
            print(json.dumps({"preview_keys": list(payload.keys())[:20] if isinstance(payload, dict) else type(payload).__name__}, indent=2), file=sys.stderr)
            return 2
        fr = check_quotes(quotes, OPTION_TIME_KEYS) if quotes else {"stale": {}, "abort": False, "fresh": quotes}
        if fr["stale"] and not args.allow_stale:
            if fr["abort"] and mini_rows:
                # RH payload is from an old session: drop it entirely and mark from mini OPRA alone.
                print(json.dumps({"warning": "STALE_RH_OPTION_QUOTES_DROPPED_USING_MINI_OPRA",
                                  "min_trade_date": fr["min_trade_date"]}), file=sys.stderr)
                fr = {**fr, "abort": False, "fresh": {}}
            if fr["abort"]:
                print(json.dumps({
                    "ok": False,
                    "error": "STALE_OPTION_QUOTES_REFUSED",
                    "min_trade_date": fr["min_trade_date"],
                    "stale": fr["stale"],
                    "stale_fraction": fr["stale_fraction"],
                    "file": str(args.quotes_file) if args.quotes_file else "stdin",
                }, indent=2), file=sys.stderr)
                return STALE_EXIT_CODE
            quotes = fr["fresh"]
        rh_raw_quotes = {k: dict(v) for k, v in quotes.items()}
        opra_sum: dict[str, Any] = {"skipped": "disabled (--no-mini-options)"} if not use_mini_opt else {}
        if use_mini_opt:
            try:
                opra_sum = om.overlay_rh_option_quotes(quotes, om.instrument_occ_map(ledger), mini_rows=mini_rows or {})
                opra_sum["cache"] = mini_info
            except Exception as e:
                opra_sum = {"skipped": f"error: {type(e).__name__}"}
        summary = apply_quotes(ledger, quotes)
        summary["mini_opra"] = opra_sum
        if use_mini_opt or rh_raw_quotes:
            try:
                summary["multileg"] = apply_multileg_marks(ledger, rh_quotes=rh_raw_quotes,
                                                           mini_rows=(mini_rows or {}) if use_mini_opt else {})
            except Exception as e:
                summary["multileg"] = {"error": f"{type(e).__name__}: {e}"[:200]}
        ledger.setdefault("meta", {})["lastOptionMarkSources"] = {
            "atPT": format_pt(),
            "mini_opra": list(opra_sum.get("mini_opra") or []),
            "rh": list(opra_sum.get("rh") or []),
            "none": list(opra_sum.get("none") or []),
            "multileg": (summary.get("multileg") or {}).get("sources"),
        }
        if fr["stale"] and not args.allow_stale:
            summary["stale_dropped"] = fr["stale"]
            summary["min_trade_date"] = fr["min_trade_date"]
        if write_feed is not None and not args.dry_run and use_mini_opt:
            try:  # status only (sources/counts); raw OPRA quotes never leave cache/
                write_feed("mini-option-marks", source="oid-mini collector · Alpaca OPRA", writer="refresh_marks.py",
                           symbols=None, payload=ledger["meta"]["lastOptionMarkSources"], ttl_seconds=300)
            except Exception as e:
                summary["mini_option_marks_feed_error"] = str(e)[:200]
        # Keep Data Sources `rh-option-marks` fresh whenever option marks land (TTL 300s).
        if write_feed is not None and not args.dry_run and has_rh_opt and rh_raw_quotes:
            try:
                write_feed(
                    "rh-option-marks",
                    source="user-robinhood-trading get_option_quotes",
                    writer="refresh_marks.py",
                    symbols=sorted({str(q.get("symbol") or "") for q in quotes.values() if isinstance(q, dict)} - {""})
                    or None,
                    payload={
                        "marks": rh_raw_quotes,
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
        efr = check_quotes(eq_quotes, EQUITY_TIME_KEYS)
        if efr["stale"] and not args.allow_stale:
            if efr["abort"]:
                print(json.dumps({
                    "ok": False,
                    "error": "STALE_EQUITY_QUOTES_REFUSED",
                    "min_trade_date": efr["min_trade_date"],
                    "stale_n": len(efr["stale"]),
                    "stale_sample": dict(list(efr["stale"].items())[:8]),
                    "stale_fraction": efr["stale_fraction"],
                    "file": str(args.equity_quotes_file) if args.equity_quotes_file else "stdin",
                    "note": "nothing written; re-pull get_equity_quotes into the repo tmp/ file",
                }, indent=2), file=sys.stderr)
                return STALE_EXIT_CODE
            eq_quotes = efr["fresh"]
        # Pure-RH copy for the shared rh-quotes feed (Hal/elevate semantics stay RH-only).
        rh_eq_quotes = {k: dict(v) for k, v in eq_quotes.items()}
        mini_sum: dict[str, Any] = {"skipped": "disabled (--no-mini)"} if args.no_mini else {}
        if not args.no_mini and overlay_rh_quotes is not None:
            try:
                mini_sum = overlay_rh_quotes(eq_quotes)
            except Exception as e:  # never block RH marks on the mini path
                mini_sum = {"skipped": f"error: {type(e).__name__}"}
        eq_summary = apply_equity_quotes(ledger, eq_quotes)
        eq_summary["mini_overlay"] = mini_sum
        ledger.setdefault("meta", {})["lastEquityMiniOverlay"] = {
            "symbols": list(mini_sum.get("overlaid") or []),
            "skipped": mini_sum.get("skipped"),
            "session": mini_sum.get("session"),
        }
        if efr["stale"] and not args.allow_stale:
            eq_summary["stale_dropped"] = efr["stale"]
            eq_summary["min_trade_date"] = efr["min_trade_date"]
        # Keep Data Sources `rh-quotes` fresh whenever equities land (TTL 120s).
        # Full layout (last + previous_close + bid/ask + last_non_reg) so support-map /
        # market-tape piggyback can classify even when the inbound pull was slim
        # (last-only). Fill missing previous_close from the prior cache when present.
        if write_feed is not None and not args.dry_run:
            try:
                prior_prev: dict[str, float] = {}
                try:
                    from cache_io import extract_rh_quote_map as _extract_rh  # type: ignore
                    prior_path = ROOT.parent / "market-data" / "latest" / "rh-quotes.json"
                    if prior_path.is_file():
                        prior_rec = json.loads(prior_path.read_text(encoding="utf-8"))
                        prior_map = _extract_rh(prior_rec.get("payload") if isinstance(prior_rec, dict) else prior_rec)
                        for _s, _q in prior_map.items():
                            _p = _q.get("prev_close") if isinstance(_q, dict) else None
                            if _p is not None:
                                prior_prev[_s] = float(_p)
                except Exception:
                    prior_prev = {}
                quotes_out: dict[str, dict] = {}
                for sym, q in rh_eq_quotes.items():
                    prev = q.get("prev_close") or q.get("previous_close")
                    if prev is None:
                        prev = prior_prev.get(sym)
                    quotes_out[sym] = {
                        "last": q.get("last"),
                        "last_non_reg": q.get("last_non_reg"),
                        "previous_close": prev,
                        "prev_close": prev,
                        "bid": q.get("bid"),
                        "ask": q.get("ask"),
                        "venue_last_trade_time": q.get("last_trade_time") or q.get("last_non_reg_time"),
                        "venue_last_non_reg_trade_time": q.get("last_non_reg_time"),
                        "state": q.get("state"),
                    }
                write_feed(
                    "rh-quotes",
                    source="user-robinhood-trading get_equity_quotes",
                    writer="refresh_marks.py",
                    symbols=sorted(quotes_out.keys()),
                    payload={
                        "quotes": quotes_out,
                        "count": len(quotes_out),
                    },
                    ttl_seconds=120,
                )
                eq_summary["rh_quotes_feed"] = "wrote"
                eq_summary["rh_quotes_prior_prev_filled"] = sum(
                    1 for s, q in quotes_out.items()
                    if q.get("previous_close") is not None
                    and (rh_eq_quotes.get(s) or {}).get("prev_close") is None
                )
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
    if has_opt:
        try:
            summary["paper_open_synced"] = sync_paper_open(ledger)
        except Exception as e:
            summary["paper_open_sync_error"] = str(e)[:200]
    print(json.dumps({"ok": True, "wrote": str(TRADES_PATH), "options": summary, "equity": eq_summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
