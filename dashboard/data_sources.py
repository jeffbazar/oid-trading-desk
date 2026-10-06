#!/usr/bin/env python3
"""Build Data sources status rows for OID Live Book (Rose + Hal).

Reads market-data/latest/*.json (+ _index.json), QUERY-DEDUP TTLs,
and soft stamps (close triggers / ledger meta). Research only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "market-data"
LATEST = MD / "latest"
sys.path.insert(0, str(MD))

try:
    from cache_io import DEFAULT_TTLS  # type: ignore
except Exception:
    DEFAULT_TTLS = {
        "fa-levels": 600,
        "fa-flow-levels": 600,
        "fa-soft": 1800,
        "uw-flow-alerts": 900,
        "uw-net-prem": 900,
        "uw-oe": 1800,
        "uw-form4": 21600,
        "rh-quotes": 120,
        "rh-rvol": 1800,
        "rh-option-marks": 300,
        "paper-open": 0,
        "market-tape": 300,
        "shay-semi-watch": 300,
        "shay-ma-levels": 300,
        "fidelity-three": 1800,
        "macro-spot": 300,
        "fred-hy-oas": 86400,
        "fred-ig-oas": 86400,
    }


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _parse_as_of(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    try:
        if t.endswith("Z"):
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
        return datetime.fromisoformat(t)
    except Exception:
        return None


def _fmt_pt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(PT)
    return local.strftime("%Y-%m-%d %-I:%M %p PT")


def _age_sec(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


# Catalog: all feeds Rose + Hal track (even if file missing)
FEED_CATALOG: list[dict[str, Any]] = [
    {
        "source": "FlashAlpha",
        "feed": "fa-levels",
        "file": "fa-levels.json",
        "owner": "Rose",
        "cadence": "Walls pulse primary (11:45/12:45/13:45/14:45 ET); Q5 gated",
        "ttl": 600,
        "notes": "Last file Fri 1:00 PM PT is STALE_CARRY because FlashAlpha quota was 0. Prior walls write 12:46 PM PT. Weekend CARRY is not a Sunday outage. Hal read-only.",
    },
    {
        "source": "FlashAlpha",
        "feed": "fa-flow-levels",
        "file": "fa-flow-levels.json",
        "owner": "Rose",
        "cadence": "Sibling of fa-levels when stored separately; walls-pulse primary",
        "ttl": 600,
        "notes": "Alias/sibling — often empty if walls writes only fa-levels",
    },
    {
        "source": "FlashAlpha",
        "feed": "fa-soft",
        "file": "fa-soft.json",
        "owner": "Rose",
        "cadence": "Piggyback after levels when soft context needed",
        "ttl": 1800,
        "notes": "No writer. Exposure summary is not collected. Not a failed fetch.",
        "forced_status": "NOT_BUILT",
    },
    {
        "source": "Unusual Whales",
        "feed": "uw-flow-alerts",
        "file": "uw-flow-alerts.json",
        "owner": "Rose",
        "cadence": "Near-wall / soft-catalyst (Q5, open, FH, walls-on-notify)",
        "ttl": 900,
        "notes": "Hal read-only",
    },
    {
        "source": "Unusual Whales",
        "feed": "uw-net-prem",
        "file": "uw-net-prem.json",
        "owner": "Rose",
        "cadence": "Near-wall or session wrap",
        "ttl": 900,
        "notes": "flow_per_strike + market_tide",
    },
    {
        "source": "Unusual Whales",
        "feed": "uw-oe",
        "file": "uw-oe.json",
        "owner": "Rose",
        "cadence": "Near-wall notify",
        "ttl": 1800,
        "notes": "No writer. Dark pool is not collected. Not a failed fetch.",
        "forced_status": "NOT_BUILT",
    },
    {
        "source": "Unusual Whales",
        "feed": "uw-form4",
        "file": "uw-form4.json",
        "owner": "Rose",
        "cadence": "Premarket universe + afternoon midday forced",
        "ttl": 21600,
        "notes": "Form-4 / insider; Hal read-only",
    },
    {
        "source": "Robinhood",
        "feed": "rh-quotes",
        "file": "rh-quotes.json",
        "owner": "shared",
        "cadence": "Scan color; dashboard session/day%; elevate always live",
        "ttl": 120,
        "notes": "Equity quotes · session badge / day%",
    },
    {
        "source": "Robinhood",
        "feed": "rh-option-marks",
        "file": "rh-option-marks.json",
        "owner": "shared",
        "cadence": "Q5 + walls + Hal intraday :11/:26/:41/:56 ET",
        "ttl": 300,
        "notes": "Open paper marks; elevate/invalidate need live",
    },
    {
        "source": "Robinhood",
        "feed": "rh-rvol",
        "file": "rh-rvol.json",
        "owner": "Rose",
        "cadence": "Near-wall writers",
        "ttl": 1800,
        "notes": "No writer. Session RVOL is not collected. Not a failed fetch.",
        "forced_status": "NOT_BUILT",
    },
    {
        "source": "X",
        "feed": "x-core8",
        "file": "x-core8.json",
        "owner": "Rose",
        "cadence": "Drafted weekday :48 10–15 ET — enabled=false",
        "ttl": None,
        "notes": "OID Core-8 disabled; see HAL-X-ALLOWLIST for Hal list",
        "forced_status": "DISABLED",
    },
    {
        "source": "X",
        "feed": "hal-x-scan",
        "file": "hal-x-scan.json",
        "owner": "Hal",
        "cadence": "8:11–20:11 PT every 2h, 7 days (HAL-CADENCE-V1)",
        "ttl": 7200,
        "notes": "Trader/options insights; notify on high signal only",
    },
    {
        "source": "Dashboard",
        "feed": "live-refresh",
        "file": None,
        "owner": "shared",
        "cadence": "Piggyback after elevate / invalidate / walls / Hal marks",
        "ttl": 300,
        "notes": "dashboard/live_refresh.py → here.now bold-tulip-nejq",
        "stamp_from": "ledger_marks",
    },
    {
        "source": "Hal",
        "feed": "hal-intraday-marks",
        "file": "hal-marks.json",
        "owner": "Hal",
        "cadence": ":11/:26/:41/:56 ET, 9–15 weekdays",
        "ttl": 900,
        "notes": "Marks + Greeks + soft triggers; quiet unless material · file market-data/latest/hal-marks.json. Last success Friday 1:02 PM PT. Weekend hold is carry, not a failed pull. Book flat.",
        "stamp_from": "ledger_marks",  # fallback if file missing
    },
    {
        "source": "Robinhood",
        "feed": "hal-rh-watch",
        "file": "hal-rh-watch-pulse.json",
        "owner": "Hal",
        "cadence": "Weekdays :05/:35 ET, 10–15. Soft tape only.",
        "ttl": 3600,
        "notes": "Tech + chip play watch pulse. Soft color. Never elevates. Last RTH pulse Friday 12:42 PM PT. Weekend hold is carry, not a failed fetch.",
    },
    {
        "source": "EDGAR",
        "feed": "premarket-edgar",
        "file": None,
        "owner": "Rose",
        "cadence": "8:15 ET premarket (Form-4 sweep owner)",
        "ttl": 21600,
        "notes": "oid-premarket-edgar-ping; Form-4 universe",
        "stamp_from": "uw-form4",
    },
    {
        "source": "Soft",
        "feed": "close-triggers",
        "file": None,
        "owner": "shared",
        "cadence": "After marks (live_refresh hook)",
        "ttl": 600,
        "notes": "Alerts only — never auto-close / never RH",
        "stamp_from": "close_triggers",
    },
    {
        "source": "Soft",
        "feed": "book-triggers",
        "file": None,
        "owner": "Rose",
        "cadence": "After marks / scorecard",
        "ttl": 600,
        "notes": "BOOK_TP / BOOK_GIVEBACK soft flags",
        "stamp_from": "book_triggers",
    },
    {
        "source": "OID",
        "feed": "paper-open",
        "file": "paper-open.json",
        "owner": "shared",
        "cadence": "On change (not TTL-gated)",
        "ttl": 0,
        "notes": "Open seat snapshot for peers",
    },
    {
        "source": "Quota",
        "feed": "api-quotas",
        "file": "api-quotas.json",
        "owner": "shared",
        "cadence": "Refresh on Data sources rebuild / Hal marks / Rose walls",
        "ttl": 3600,
        "notes": "FlashAlpha daily calls + X credit balance at top of this page",
    },
    {
        "source": "Catalysts",
        "feed": "desk-catalysts",
        "file": "desk-catalysts.json",
        "owner": "Hal",
        "cadence": "Refresh on ask / premarket; FA earnings primary",
        "ttl": 21600,
        "notes": "Watchlist earnings + other events → Events tab. Hal owns soft calendar. Restamped 2026-10-05 ~7:38 AM PT (hal-catalysts-restamp-20261005), 30 events. Soft color only — not a live calendar; never elevates alone.",
    },
    {
        "source": "X",
        "feed": "x-spend",
        "file": "x-spend.json",
        "owner": "Hal",
        "cadence": "After each Hal X scan + quota refresh",
        "ttl": 7200,
        "notes": "X $ spend: today / week / month / total since tracking start",
    },
    {
        "source": "Robinhood",
        "feed": "market-tape",
        "file": "market-tape.json",
        "owner": "shared",
        "cadence": "Piggyback on live_refresh / Hal marks (with equity quotes)",
        "ttl": 300,
        "notes": "SPY·QQQ·DIA strip + RSP/VTV/VUG helpers · soft/paper",
    },
    {
        "source": "Robinhood",
        "feed": "shay-semi-watch",
        "file": "shay-semi-watch.json",
        "owner": "Rose",
        "cadence": "Piggyback on live_refresh equity quotes",
        "ttl": 300,
        "notes": "Shay 2027-PE equity soft watch · since-post% vs Fri baseline · no seats",
    },
    {
        "source": "Robinhood",
        "feed": "chart-daily",
        "file": "chart-daily-observations.json",
        "owner": "Chart Bot",
        "cadence": "Weekdays 2:24 PM PT after the cash close (routine chart-daily-refresh). Weekend and holiday keep the last completed session.",
        "ttl": None,
        "notes": "CB-DAILY-V1 · universe RH-TECH-CHIP-20261004 (37; GOOG Class C only; QQQ+SMH on lists; SOXX not fetched). Sole writer of post-close daily historicals via get_equity_historicals (interval day, bounds regular, adjustment split, start ~2024-01-01Z; ~37 calls/weekday). Does not share Rose/Hal live quote pulse. EMA9/21 SMA50/200 Shay lineage; SMA20+ATR14 engineering-only; total_trend; RS 20s vs QQQ/SMH. Last session 2026-10-02 · computed 2026-10-04 2:33 PM PT. SKHY/SPCX insufficient history. Forecasts null · pattern detector off · softOnly · never elevates. N/A: Databento Massive 5/15/60-min weekly 1-min RVOL patterns SOXX forecasts push receiver changes API.",
    },
    {
        "source": "Desk store",
        "feed": "supply-chain-identity",
        "file": "supply-chain-identity.json",
        "owner": "Customer/Supplier Bot",
        "cadence": "On demand / identity seed. No weekday collector loop. collector=false.",
        "ttl": None,
        "notes": "Desk-store identity only (supply-chain/supply-chain.db). 37 entities / 37 instruments / 0 relationships / 0 claims. Empty edges = unknown exposure, not failed (empty ≠ STALE). GOOG Class C only. SKHY/MH ticker-only unverified legal name. Shared watchlist + get_sec_filing_index when needed (not second EDGAR). softOnly · never opens a seat · profit probs null. N/A: Benzinga FactSet EIA Form4 issuer-IR policy Postgres read API push FA/UW/X for map.",
    },
    {
        "source": "X+web",
        "feed": "peanut-news",
        "file": "peanut-news.json",
        "owner": "Peanut",
        "cadence": "Weekdays 5:30 AM PT premarket, then every 5 min 6:11 AM–1:56 PM PT. File updates only on a move-worthy alert.",
        "ttl": None,
        "notes": "Wire/headline lane (X news search + public web; shared X pool). No FA/UW/RH quote calls. Universe RH Tech∪chip ~37. Chat + Rose/Hal alerts; Live Book marquee (after prior RTH close) + news-archive.html. Quiet scans do not rewrite — stamp is last alert. Lane split: Peanut=wire/headline; X Summarizer=X-edge — do not double-count. softOnly. N/A: SEC IR Form4 policy Benzinga websocket immutable revisions read API. Package path peanut/ present (cutover 2026-10-05); live writer remains dashboard/peanut_news.py → market-data/latest/peanut-news.json.",
    },
    {
        "source": "Robinhood",
        "feed": "shay-ma-levels",
        "file": "shay-ma-levels-watch.json",
        "owner": "Rose",
        "cadence": "Spots piggyback live_refresh; full MA recompute via refresh_shay_ma_levels.py (daily/on demand)",
        "ttl": 300,
        "notes": "Shay key-levels MA soft watch · EMA9/21 SMA50/200 + Total Trend · softOnly · never elevate alone",
    },
    {
        "source": "FlashAlpha+RH",
        "feed": "support-map",
        "file": "support-map.json",
        "owner": "Rose",
        "cadence": "Weekdays every 15 min, 6:05 AM–1:50 PM PT. Soft only.",
        "ttl": 300,
        "notes": "Put-wall distance for the support watch. Piggybacks fresh shared rh-quotes (Duplicates #2; refresh_support_map.py) — never a second rh-quotes writer. Walls may be STALE_CARRY when FA quota is 0. Soft only — never elevates.",
    },
    {
        "source": "FRED",
        "feed": "fred-hy-oas",
        "file": "fred-hy-oas.json",
        "owner": "shared",
        "cadence": "With fidelity-three refresh (daily-ish)",
        "ttl": 86400,
        "notes": "ICE BofA HY OAS BAMLH0A0HYM2 · public CSV · no key",
    },
    {
        "source": "FRED",
        "feed": "fred-ig-oas",
        "file": "fred-ig-oas.json",
        "owner": "shared",
        "cadence": "With fidelity-three refresh (daily-ish)",
        "ttl": 86400,
        "notes": "ICE BofA IG Corp OAS BAMLC0A0CM · public CSV · no key",
    },
    {
        "source": "FRED+RH",
        "feed": "macro-spot",
        "file": "macro-spot.json",
        "owner": "shared",
        "cadence": "Piggyback on live_refresh / market-tape",
        "ttl": 300,
        "notes": "File stamp Fri 1:02 PM PT is weekend carry, not an outage. VIX is that Friday quote. WTI/Brent futures match the Macro morning note. 10Y inside is FRED/UW 4.96% as of 2026-09-22, not Friday's tape. FRED spot oil is 2026-09-15 and is not the score. soft only.",
    },
    {
        "source": "Macro",
        "feed": "macro-morning",
        "file": "macro-morning.json",
        "owner": "Macro Bot",
        "cadence": "Weekdays 5:45 AM PT chat pack; mirrored to this file by Macro morning file writer (6:14 AM PT).",
        "ttl": None,
        "notes": "Last judgment Mon 2026-10-05 5:50 AM PT. daily_macro neutral/0, macro_tech neutral/−1. Seven scores are evidence, not a sum. Snapshot of the chat pack, not an immutable revision. Not a live quote. softOnly.",
    },
    {
        "source": "Dashboard",
        "feed": "fidelity-three",
        "file": "fidelity-three.json",
        "owner": "shared",
        "cadence": "Piggyback on live_refresh (equity quotes + FRED + Yahoo hist)",
        "ttl": 1800,
        "notes": "Median-growth proxy (RSP−SPY) · credit OAS · VTV/VUG valuation proxy",
    },
]


def _session_now() -> str:
    """rth|pre|ah|closed — prefer OID market_session helper."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "paper-trades"))
        from market_session import market_session  # type: ignore
        return str(market_session() or "closed").lower()
    except Exception:
        # Weekend fallback
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZI
        et = _dt.now(_ZI("America/New_York"))
        if et.weekday() >= 5:
            return "closed"
        return "rth"


def _status_for(rec: Optional[dict], ttl: Optional[int], forced: Optional[str] = None) -> str:
    """OK / STALE / CARRY / ERROR / NEVER. CARRY = last good write held outside RTH (weekend/closed)."""
    if forced:
        return forced
    if rec is None:
        return "NEVER"
    if rec.get("error"):
        return "ERROR"
    as_of = _parse_as_of(rec.get("as_of") or rec.get("asOf") or rec.get("scoredAt") or rec.get("updatedAt"))
    age = _age_sec(as_of)
    if age is None:
        # try as_of_pt only — treat as OK if present and no error
        if rec.get("as_of_pt") or rec.get("scoredAtPT") or rec.get("lastMarksRefreshAtPT") or rec.get("updatedAtPT") or rec.get("timePT"):
            return "OK"
        return "NEVER"
    if ttl is None:
        return "OK"
    if ttl <= 0:
        return "OK"  # on-change feeds
    if age > float(ttl):
        # Outside RTH: Friday snaps are expected carry, not a failed writer
        if _session_now() != "rth":
            return "CARRY"
        return "STALE"
    return "OK"


def _row_from_catalog(entry: dict, index: dict, ledger: dict, close_triggers: dict) -> dict:
    feed = entry["feed"]
    ttl = entry.get("ttl")
    if ttl is None and feed in DEFAULT_TTLS:
        ttl = DEFAULT_TTLS[feed]

    rec: Optional[dict] = None
    stamp_from = entry.get("stamp_from")
    file_name = entry.get("file")

    # File wins when present (e.g. hal-marks.json for hal-intraday-marks)
    if file_name:
        file_rec = _load_json(LATEST / file_name)
        if file_rec is not None:
            rec = file_rec
    if rec is None and stamp_from == "ledger_marks":
        meta = ledger.get("meta") or {}
        as_of = meta.get("lastMarksRefreshAt") or meta.get("lastEquityRefreshAt") or ledger.get("updatedAt")
        as_of_pt = meta.get("lastMarksRefreshAtPT") or meta.get("lastEquityRefreshAtPT") or ledger.get("updatedAtPT")
        rec = {"as_of": as_of, "as_of_pt": as_of_pt, "error": None, "source": "ledger", "writer": "dashboard"}
    elif rec is None and stamp_from == "close_triggers":
        rec = {
            "as_of": close_triggers.get("scoredAt"),
            "as_of_pt": close_triggers.get("scoredAtPT"),
            "error": close_triggers.get("error"),
            "source": "close_triggers",
            "writer": "OID",
        } if close_triggers else None
    elif rec is None and stamp_from == "book_triggers":
        book = (close_triggers or {}).get("book") or {}
        meta = ledger.get("meta") or {}
        rec = {
            "as_of": close_triggers.get("scoredAt") or meta.get("lastMarksRefreshAt"),
            "as_of_pt": close_triggers.get("scoredAtPT") or meta.get("lastMarksRefreshAtPT"),
            "error": None,
            "source": "book_triggers",
            "writer": "Rose",
            "payload_hint": book.get("alert") or book.get("flags"),
        } if (close_triggers or meta) else None
    elif rec is None and stamp_from == "uw-form4":
        rec = _load_json(LATEST / "uw-form4.json")
    elif rec is None and file_name:
        # merge index sidecar stamp if file missing but index has it
        if isinstance(index.get(feed), dict):
            side = index[feed]
            rec = {
                "as_of": side.get("as_of"),
                "as_of_pt": side.get("as_of_pt"),
                "error": side.get("error"),
                "source": "index",
                "writer": side.get("writer"),
            }

    # Prefer file ttl_seconds when present — except catalog on-change (ttl 0)
    catalog_ttl = entry.get("ttl")
    if rec and rec.get("ttl_seconds") is not None and catalog_ttl != 0:
        try:
            ttl = int(rec["ttl_seconds"])
        except Exception:
            pass

    forced = entry.get("forced_status")
    status = _status_for(rec, ttl, forced)

    as_of = _parse_as_of((rec or {}).get("as_of") or (rec or {}).get("scoredAt") or (rec or {}).get("updatedAt"))
    as_of_pt = (rec or {}).get("as_of_pt") or (rec or {}).get("scoredAtPT") or (rec or {}).get("updatedAtPT") or (rec or {}).get("timePT") or _fmt_pt(as_of)

    return {
        "source": entry["source"],
        "feed": feed,
        "owner": entry["owner"],
        "cadence": entry["cadence"],
        "ttl": ttl,
        "ttl_label": ("—" if ttl is None else ("on change" if ttl == 0 else f"{ttl}s")),
        "last_success_pt": as_of_pt if rec else "—",
        "status": status,
        "notes": entry.get("notes") or "",
        "error": (rec or {}).get("error"),
        "writer": (rec or {}).get("writer"),
    }


def load_quotas() -> Optional[dict]:
    return _load_json(LATEST / "api-quotas.json")


def quotas_panel_html(rec: Optional[dict] = None) -> str:
    """Top-of-page query limits + cost cards."""
    rec = rec if rec is not None else load_quotas()
    if not rec or not rec.get("vendors"):
        return (
            '<div class="quota-panel empty">'
            '<div class="quota-title">Query limits &amp; cost</div>'
            '<div class="quota-miss muted">No <code>api-quotas.json</code> yet — Hal/Rose write on refresh.</div>'
            '</div>'
        )
    as_of = _esc(rec.get("as_of_pt") or "—")
    cards = []
    for v in rec.get("vendors") or []:
        label = _esc(v.get("label") or v.get("id") or "?")
        plan = _esc(v.get("plan") or "")
        note = _esc(v.get("cost_note") or "")
        owner = _esc(v.get("owner") or "")
        metric = v.get("metric")
        used = v.get("used")
        limit = v.get("limit")
        rem = v.get("remaining")
        # progress / primary number
        primary = "—"
        cls = "flat"
        bar = ""
        if metric == "calls" and limit:
            try:
                u = float(used or 0)
                lim = float(limit)
                pct = min(100.0, round(u / lim * 100.0, 1)) if lim else 0
                primary = f"{int(u):,}/{int(lim):,} · {int(float(rem or 0)):,} left"
                cls = "ok" if pct < 70 else ("warn" if pct < 90 else "bad")
                bar = (
                    f'<div class="qbar"><div class="qfill {cls}" style="width:{pct}%"></div></div>'
                    f'<div class="qtiny">{pct:.0f}% of daily limit</div>'
                )
            except Exception:
                primary = str(used)
        elif metric == "usd" and rem is not None:
            try:
                bal = float(rem)
                primary = f"${bal:,.2f} left"
                cls = "ok" if bal >= 20 else ("warn" if bal >= 5 else "bad")
                # Prefer explicit spend_* fields; else load x-spend.json
                st = v.get("spend_today")
                sw = v.get("spend_week")
                sm = v.get("spend_month")
                sto = v.get("spend_total")
                if st is None:
                    xs = _load_json(LATEST / "x-spend.json") or {}
                    sp = (xs.get("spend") or {})
                    st, sw, sm, sto = sp.get("today"), sp.get("week"), sp.get("month"), sp.get("total")
                if st is not None:
                    bar = (
                        f'<div class="qspend">'
                        f'<span>today <b>${float(st):,.2f}</b></span>'
                        f'<span>week <b>${float(sw or 0):,.2f}</b></span>'
                        f'<span>month <b>${float(sm or 0):,.2f}</b></span>'
                        f'<span>total <b>${float(sto or 0):,.2f}</b></span>'
                        f'</div>'
                    )
            except Exception:
                primary = str(rem)
        elif v.get("status") == "NO_METER":
            primary = "no meter"
            cls = "flat"
        elif v.get("status") == "NO_COST":
            primary = "no $ cost"
            cls = "ok"
        cards.append(
            f'<div class="qcard">'
            f'<div class="qk">{label} <span class="qplan">{plan}</span></div>'
            f'<div class="qv {cls}">{_esc(primary)}</div>'
            f'{bar}'
            f'<div class="qtiny">{note}</div>'
            f'<div class="qtiny">owner: {owner}</div>'
            f'</div>'
        )
    xs = _load_json(LATEST / "x-spend.json") or {}
    sp = xs.get("spend") or ((rec or {}).get("x_spend") if isinstance(rec, dict) else None) or {}
    spend_strip = ""
    if sp:
        since = _esc(xs.get("tracking_started_at_pt") or (rec or {}).get("x_spend_tracking_since") or "—")
        try:
            bal_s = f"{float(xs.get('current_balance')):,.2f}"
        except Exception:
            bal_s = "—"
        spend_strip = (
            f'<div class="x-spend-strip">'
            f'<span class="xslab">X spend</span>'
            f'<span>today <b>${float(sp.get("today") or 0):,.2f}</b></span>'
            f'<span>week <b>${float(sp.get("week") or 0):,.2f}</b></span>'
            f'<span>month <b>${float(sp.get("month") or 0):,.2f}</b></span>'
            f'<span>total <b>${float(sp.get("total") or 0):,.2f}</b></span>'
            f'<span class="qtiny">bal ${bal_s} · since {since}</span>'
            f'</div>'
        )

    return (
        f'<div class="quota-panel">'
        f'<div class="quota-head"><div class="quota-title">Query limits &amp; cost</div>'
        f'<div class="qtiny">as of {as_of}</div></div>'
        f'<div class="quota-grid">{"".join(cards)}</div>'
        f'{spend_strip}'
        f'</div>'
    )



def collect_rows(ledger: Optional[dict] = None) -> list[dict]:
    index = _load_json(LATEST / "_index.json") or {}
    if ledger is None:
        tp = ROOT / "paper-trades" / "trades.json"
        ledger = _load_json(tp) or {}
    ct = _load_json(ROOT / "tmp" / "close-triggers-last.json") or {}
    return [_row_from_catalog(e, index, ledger, ct) for e in FEED_CATALOG]


def status_class(status: str) -> str:
    s = (status or "").upper()
    if s == "OK":
        return "ok"
    if s == "STALE":
        return "warn"
    if s == "CARRY":
        return "flat"  # expected weekend / closed hold
    if s == "ERROR":
        return "bad"
    if s == "DISABLED":
        return "flat"
    return "flat"


def rows_html(rows: Optional[list[dict]] = None) -> str:
    rows = rows or collect_rows()
    parts = []
    for r in rows:
        st = r["status"]
        tip = _esc(r.get("error") or r.get("writer") or "")
        parts.append(
            f"<tr>"
            f"<td>{_esc(r['source'])}</td>"
            f"<td><code>{_esc(r['feed'])}</code></td>"
            f"<td>{_esc(r['owner'])}</td>"
            f"<td class='cadence'>{_esc(r['cadence'])}</td>"
            f"<td class='num'>{_esc(r['ttl_label'])}</td>"
            f"<td class='num'>{_esc(r['last_success_pt'])}</td>"
            f"<td><span class='tchip {status_class(st)}' title='{tip}'>{_esc(st)}</span></td>"
            f"<td class='notes'>{_esc(r['notes'])}</td>"
            f"</tr>"
        )
    return "\n".join(parts)


def summary_counts(rows: Optional[list[dict]] = None) -> dict[str, int]:
    rows = rows or collect_rows()
    out = {"OK": 0, "STALE": 0, "CARRY": 0, "ERROR": 0, "NEVER": 0, "DISABLED": 0}
    for r in rows:
        st = (r.get("status") or "NEVER").upper()
        out[st] = out.get(st, 0) + 1
    return out


if __name__ == "__main__":
    rows = collect_rows()
    print(json.dumps({"count": len(rows), "summary": summary_counts(rows), "rows": rows}, indent=2))
