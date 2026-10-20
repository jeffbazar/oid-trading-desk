#!/usr/bin/env python3
"""Market overview strip HTML for OID Live Book (indices + Fidelity-3). Soft/paper only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
OID = ROOT.parent
LATEST = OID / "market-data" / "latest"


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_px(v: Optional[float], n: int = 2) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.{n}f}"


def _load_payload(feed: str):
    path = LATEST / f"{feed}.json"
    if not path.is_file():
        return None, None
    try:
        rec = json.loads(path.read_text())
    except Exception:
        return None, None
    if not isinstance(rec, dict):
        return None, None
    payload = rec.get("payload")
    return rec, payload if isinstance(payload, dict) else rec


def _pct_chip(pct, *, tip_prefix: str = "") -> str:
    if pct is None:
        return '<span class="daychip flat">—</span>'
    pct = float(pct)
    label = f"−{abs(pct):.2f}%" if pct < 0 else f"+{pct:.2f}%"
    cls = "pos" if pct > 0 else ("neg" if pct < 0 else "flat")
    tip = (tip_prefix + " " if tip_prefix else "") + f"Day {label}"
    return f'<span class="daychip {cls}" title="{_esc(tip)}">{_esc(label)}</span>'


def _soft_tone(kind: str, quartile=None, spread=None) -> str:
    if kind == "credit" and quartile is not None:
        if quartile == 1:
            return "soft-calm"
        if quartile == 4:
            return "soft-stress"
        if quartile == 3:
            return "soft-warm"
        return "soft-neutral"
    if kind == "growth" and spread is not None:
        if spread > 0.15:
            return "soft-calm"
        if spread < -0.15:
            return "soft-warm"
        return "soft-neutral"
    if kind == "valuation" and quartile is not None:
        if quartile == 4:
            return "soft-stress"
        if quartile == 1:
            return "soft-calm"
        return "soft-neutral"
    return "soft-neutral"


def _spread_label(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else "−"
    return f"{sign}{abs(v):.2f}pp"


def _fmt_oas(level) -> str:
    if level is None:
        return "—"
    return f"{float(level):.2f}"


def _fmt_pctile(p) -> str:
    if p is None:
        return "—"
    return f"{float(p):.0f}th"



def _fmt_macro_spot(cell: dict) -> str:
    spot = _f(cell.get("spot"))
    if spot is None:
        return "—"
    unit = str(cell.get("unit") or "")
    if unit == "%":
        return f"{spot:.2f}%"
    if unit in ("$/bbl", "$/bbl"):
        return f"${spot:,.2f}"
    if unit in ("pts", "pt"):
        return f"{spot:.2f}"
    return f"{spot:,.2f}{unit}"


def _macro_chip(cell: dict) -> str:
    cid = str(cell.get("id") or "")
    if cid in ("us10y", "us30y"):
        bp = cell.get("day_chg_bp")
        if bp is None:
            chg = _f(cell.get("day_chg"))
            bp = round(chg * 100.0, 2) if chg is not None else None
        if bp is None:
            return '<span class="daychip flat">—</span>'
        bp = float(bp)
        label = f"−{abs(bp):.0f} bp" if bp < 0 else f"+{bp:.0f} bp"
        cls = "pos" if bp > 0 else ("neg" if bp < 0 else "flat")
        tenor = "30Y" if cid == "us30y" else "10Y"
        tip = f"{tenor} Treasury day {label}"
        return f'<span class="daychip {cls}" title="{_esc(tip)}">{_esc(label)}</span>'
    tip_prefix = str(cell.get("label") or cid)
    return _pct_chip(_f(cell.get("day_pct")), tip_prefix=tip_prefix)


def _render_macro_panel(tape: Optional[dict], tape_rec: Optional[dict]) -> str:
    """Rates · Vol · Oil row in Market overview (directly under SPY/QQQ/DIA)."""
    # Prefer dedicated macro-spot feed (futures-primary) over any stale tape.macro embed
    _rec2, macro2 = _load_payload("macro-spot")
    macro = macro2 if isinstance(macro2, dict) else None
    if not isinstance(macro, dict) or not (macro.get("items") or macro.get("by_id")):
        macro = (tape or {}).get("macro") if isinstance(tape, dict) else None
        if not isinstance(macro, dict) or not (macro.get("items") or macro.get("by_id")):
            return ""
    order = ["us10y", "us30y", "vix", "wti", "brent"]
    bid = macro.get("by_id") if isinstance(macro.get("by_id"), dict) else {}
    raw_items = macro.get("items") or []
    by_raw = {str(c.get("id")): c for c in raw_items if isinstance(c, dict) and c.get("id")}
    items = []
    for oid in order:
        cell = bid.get(oid) or by_raw.get(oid)
        if cell:
            items.append(cell)
    if not items:
        return ""
    # FRED lagged spot note (secondary) — rates + oil
    fred_bits = []
    for fid in ("us10y_fred", "wti_fred", "brent_fred"):
        fc = bid.get(fid) or by_raw.get(fid)
        if isinstance(fc, dict) and fc.get("spot") is not None:
            fred_bits.append(f"{fc.get('label') or fid} {_fmt_macro_spot(fc)} as of {fc.get('as_of') or '—'}")
    cells = []
    for cell in items:
        if not isinstance(cell, dict):
            continue
        label = cell.get("label") or cell.get("id") or "—"
        spot_s = _fmt_macro_spot(cell)
        chip = _macro_chip(cell)
        as_of = cell.get("as_of") or ""
        src = cell.get("source") or ""
        tip = f"{label} · {src} · as of {as_of}"
        sub = ""
        cid = str(cell.get("id") or "")
        kind = str(cell.get("kind") or "")
        if cid in ("wti", "brent") and kind == "futures":
            src_l = src.lower()
            tag = 'investing.com' if 'investing' in src_l else ('Macro Bot morning' if 'macro bot' in src_l else 'futures')
            sub = f'<div class="tl-ext muted">futures · {_esc(tag)}</div>'
        elif cid in ("wti", "brent") and as_of and "PT" not in str(as_of):
            sub = f'<div class="tl-ext muted">FRED as of {_esc(as_of)}</div>'
        elif cid in ("us10y", "us30y") and kind == "wire":
            sub = f'<div class="tl-ext muted">wire · Macro Bot morning</div>'
        elif cid == "us10y":
            lag = f" · FRED as of {_esc(as_of)}" if as_of and "PT" not in str(as_of) else ""
            sub = f'<div class="tl-ext muted">US10Y yield · not T-bill{lag}</div>'
        elif cid == "us30y":
            sub = '<div class="tl-ext muted">US30Y yield · wire/FRED</div>'
        elif cid == "vix":
            sub = '<div class="tl-ext muted">RH index</div>'
        cells.append(
            f'<div class="mkt-idx macro-cell" title="{_esc(tip)}">'
            f'<div class="tl-sym">{_esc(label)}</div>'
            f'<div class="tl-px num">{_esc(spot_s)} {chip}</div>'
            f"{sub}</div>"
        )
    if not cells:
        return ""
    asof = macro.get("as_of_pt") or (tape_rec or {}).get("as_of_pt") or "—"
    note = macro.get("source_policy") or ""
    oil_note = macro.get("oil_note") or ""
    rates_note = macro.get("rates_note") or ""
    extra = []
    if rates_note:
        extra.append("Rates wire: " + str(rates_note))
    if oil_note:
        extra.append(str(oil_note))
    if fred_bits:
        extra.append("FRED lag: " + " · ".join(fred_bits))
    if extra:
        note = (note + " · " if note else "") + " · ".join(extra)
    grid = "".join(cells)
    return (
        f'<div class="macro-panel">'
        f'<div class="f3-head">Macro · Rates · Vol · Oil '
        f'<span class="mkt-sub">(futures + day · soft · {_esc(asof)})</span></div>'
        f'<div class="macro-grid">{grid}</div>'
        f'<div class="f3-note macro-note">{_esc(note)}</div>'
        f"</div>"
    )



def _tone_class(tone: str) -> str:
    t = str(tone or "neutral").lower()
    if t in ("calm", "soft-calm", "risk-on"):
        return "soft-calm"
    if t in ("stress", "soft-stress", "risk-off-hard"):
        return "soft-stress"
    if t in ("warm", "soft-warm", "mild risk-off", "risk-off"):
        return "soft-warm"
    return "soft-neutral"


def _metric_label(mid: str) -> str:
    labels = {
        "10Y_yield": "10Y",
        "oil_WTI_Brent": "Oil",
        "USD_DXY_or_USDJPY": "USD",
        "VIX": "VIX",
        "NQ_vs_ES": "NQ vs ES",
        "credit_HYG_day": "Credit",
        "event_calendar": "Events",
    }
    return labels.get(str(mid), str(mid).replace("_", " "))


def _render_metric_scores(payload: dict) -> str:
    """Per-metric tech_score chips (−2…+2): neg = Nasdaq headwind, pos = tailwind."""
    rows = payload.get("metric_scores") or []
    if not isinstance(rows, list) or not rows:
        return ""
    chips = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = row.get("metric") or row.get("id") or row.get("name") or "—"
        ts = row.get("tech_score")
        if ts is None:
            ts = row.get("score")
        try:
            tsi = int(ts)
        except (TypeError, ValueError):
            continue
        tone = _tone_class("calm" if tsi >= 1 else ("stress" if tsi <= -2 else ("warm" if tsi == -1 else "neutral")))
        tip = row.get("note") or row.get("label") or f"tech_score {tsi:+d} for Nasdaq/tech"
        chips.append(
            f'<div class="metric-chip {tone}" title="{_esc(tip)}">'
            f'<span class="metric-k">{_esc(_metric_label(str(mid)))}</span>'
            f'<span class="metric-v">{tsi:+d}</span></div>'
        )
    if not chips:
        return ""
    return (
        '<div class="metric-scores">'
        '<div class="f3-k">Metric tech scores <span class="mkt-sub">(− = headwind · + = tailwind for tech)</span></div>'
        f'<div class="metric-row">{"".join(chips)}</div></div>'
    )


def _render_morning_status() -> str:
    """Daily Macro + Macro Tech morning soft-color cards (Macro Bot JSON)."""
    rec, payload = _load_payload("macro-morning")
    if not isinstance(payload, dict):
        return ""
    asof = payload.get("as_of_pt") or (rec or {}).get("as_of_pt") or "—"
    cards = []
    for key, title in (("daily_macro", "Daily Macro"), ("macro_tech", "Macro Tech")):
        block = payload.get(key) or {}
        if not isinstance(block, dict):
            continue
        tone = _tone_class(block.get("tone"))
        label = block.get("label") or "—"
        score = block.get("score")
        score_s = f"{int(score):+d}" if isinstance(score, (int, float)) else "—"
        drivers = block.get("drivers") or []
        if isinstance(drivers, str):
            drivers = [drivers]
        lis = "".join(f"<li>{_esc(d)}</li>" for d in drivers[:3] if d)
        cards.append(
            f'<div class="f3-card morning-card {tone}">'
            f'<div class="f3-k">{_esc(title)}</div>'
            f'<div class="f3-v">{_esc(label)}'
            f'<span class="f3-meta">score {_esc(score_s)}</span></div>'
            f'<ul class="morning-drivers">{lis or "<li class=\"muted\">No drivers</li>"}</ul>'
            f"</div>"
        )
    if not cards:
        return ""
    notes = []
    for k, title in (
        ("oil_note", "Oil"),
        ("rates_note", "Rates"),
        ("usd_note", "USD"),
        ("vol_note", "Vol"),
    ):
        v = payload.get(k)
        if v:
            notes.append(f"{title}: {_esc(v)}")
    notes_html = (
        '<div class="f3-note macro-note">' + " · ".join(notes) + "</div>" if notes else ""
    )
    metrics_html = _render_metric_scores(payload)
    return (
        f'<div class="morning-panel">'
        f'<div class="f3-head">Morning macro status '
        f'<span class="mkt-sub">(soft color · Macro Bot · {_esc(asof)})</span></div>'
        f'<div class="morning-grid">{"".join(cards)}</div>'
        f"{metrics_html}"
        f"{notes_html}"
        f"</div>"
    )


def _worst_tone(*tones: str) -> str:
    """Pick worst soft tone among Daily Macro / Macro Tech for banner tint."""
    rank = {"soft-stress": 3, "soft-warm": 2, "soft-neutral": 1, "soft-calm": 0}
    worst = "soft-neutral"
    best_r = -1
    for t in tones:
        cls = _tone_class(t)
        r = rank.get(cls, 1)
        if r > best_r:
            best_r = r
            worst = cls
    return worst


def _truncate(s: str, n: int = 72) -> str:
    s = " ".join(str(s or "").split())
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip(" ,;:") + "…"


def _banner_status_pills() -> tuple[str, str, str]:
    """Compact Daily Macro + Macro Tech pills; return (html, worst_tone, asof)."""
    rec, payload = _load_payload("macro-morning")
    if not isinstance(payload, dict):
        return "", "soft-neutral", "—"
    asof = payload.get("as_of_pt") or (rec or {}).get("as_of_pt") or "—"
    tones = []
    pills = []
    for key, title in (("daily_macro", "Daily Macro"), ("macro_tech", "Macro Tech")):
        block = payload.get(key) or {}
        if not isinstance(block, dict):
            continue
        tone = _tone_class(block.get("tone"))
        tones.append(tone)
        label = block.get("label") or "—"
        score = block.get("score")
        score_s = f"{int(score):+d}" if isinstance(score, (int, float)) else "—"
        drivers = block.get("drivers") or []
        if isinstance(drivers, str):
            drivers = [drivers]
        bullets = [_truncate(d, 68) for d in drivers[:2] if d]
        drv = " · ".join(bullets) if bullets else "—"
        tip = " · ".join(str(d) for d in drivers[:3] if d) or label
        pills.append(
            f'<div class="mb-pill {tone}" title="{_esc(tip)}">'
            f'<div class="mb-pill-top">'
            f'<span class="mb-k">{_esc(title)}</span>'
            f'<span class="mb-score">{_esc(score_s)}</span>'
            f'<span class="mb-label">{_esc(_truncate(label, 36))}</span>'
            f"</div>"
            f'<div class="mb-drv">{_esc(drv)}</div>'
            f"</div>"
        )
    worst = _worst_tone(*tones) if tones else "soft-neutral"
    return "".join(pills), worst, str(asof)


def _banner_macro_chips() -> str:
    """Inline 10Y / 30Y / VIX / WTI / Brent chips for the banner."""
    _rec2, macro2 = _load_payload("macro-spot")
    macro = macro2 if isinstance(macro2, dict) else None
    if not isinstance(macro, dict) or not (macro.get("items") or macro.get("by_id")):
        tape_rec, tape = _load_payload("market-tape")
        macro = (tape or {}).get("macro") if isinstance(tape, dict) else None
        if not isinstance(macro, dict):
            return ""
    order = ["us10y", "us30y", "vix", "wti", "brent"]
    short = {"us10y": "10Y", "us30y": "30Y", "vix": "VIX", "wti": "WTI", "brent": "Brent"}
    bid = macro.get("by_id") if isinstance(macro.get("by_id"), dict) else {}
    raw_items = macro.get("items") or []
    by_raw = {str(c.get("id")): c for c in raw_items if isinstance(c, dict) and c.get("id")}
    chips = []
    for oid in order:
        cell = bid.get(oid) or by_raw.get(oid)
        if not isinstance(cell, dict):
            continue
        label = short.get(oid) or cell.get("label") or oid
        spot_s = _fmt_macro_spot(cell)
        chip = _macro_chip(cell)
        as_of = cell.get("as_of") or ""
        src = cell.get("source") or ""
        tip = f"{cell.get('label') or label} · {src} · as of {as_of}"
        chips.append(
            f'<div class="mb-chip" title="{_esc(tip)}">'
            f'<span class="mb-chip-k">{_esc(label)}</span>'
            f'<span class="mb-chip-v num">{_esc(spot_s)}</span>'
            f"{chip}</div>"
        )
    return "".join(chips)


def _rh_equity_map() -> dict[str, dict]:
    """Best-effort symbol → {last, previous_close, day_pct} from rh-quotes."""
    _rec, payload = _load_payload("rh-quotes")
    if not isinstance(payload, dict):
        return {}
    quotes = payload.get("quotes") or payload.get("equities") or {}
    if not isinstance(quotes, dict):
        return {}
    out: dict[str, dict] = {}
    for sym, row in quotes.items():
        if not isinstance(row, dict):
            continue
        last = _f(row.get("last") or row.get("last_trade_price") or row.get("mark"))
        prev = _f(row.get("previous_close") or row.get("previous_close_price"))
        day = None
        if last is not None and prev not in (None, 0):
            day = (last - prev) / prev * 100.0
        out[str(sym).upper()] = {
            "last": last,
            "previous_close": prev,
            "day_pct": day,
            "source": "rh-quotes",
        }
    return out


def _banner_key_ticker_chips(session_badge_html, ledger: dict) -> str:
    """Key macro tickers: SPY · QQQ · DIA · VIX · NVDA · USO (live last + day% only)."""
    tape_rec, tape = _load_payload("market-tape")
    session = (
        ((tape or {}).get("session") if isinstance(tape, dict) else None)
        or (ledger.get("meta") or {}).get("marketSession")
        or "closed"
    )
    # Prefer tape indices for SPY/QQQ/DIA
    by: dict[str, dict] = {}
    if isinstance(tape, dict):
        for row in tape.get("indices") or []:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            by[sym] = {
                "last": _f(row.get("spot")),
                "day_pct": _f(row.get("day_pct")),
                "source": "market-tape",
                "as_of": (tape.get("as_of_pt") or (tape_rec or {}).get("as_of_pt") or ""),
            }
    # VIX from macro-spot
    _ms_rec, macro = _load_payload("macro-spot")
    if isinstance(macro, dict):
        bid = macro.get("by_id") if isinstance(macro.get("by_id"), dict) else {}
        vix = bid.get("vix") if isinstance(bid, dict) else None
        if isinstance(vix, dict) and _f(vix.get("spot")) is not None:
            by["VIX"] = {
                "last": _f(vix.get("spot")),
                "day_pct": _f(vix.get("day_pct")),
                "source": str(vix.get("source") or "macro-spot"),
                "as_of": str(vix.get("as_of") or (macro.get("as_of_pt") or "")),
            }
    # Fill NVDA / USO (and any missing index) from rh-quotes — real marks only
    rh = _rh_equity_map()
    _rh_rec, _rh_payload = _load_payload("rh-quotes")
    rh_as_of = ((_rh_rec or {}).get("as_of_pt") or (_rh_payload or {}).get("as_of_pt") or "") if isinstance(_rh_rec, dict) else ""
    for row in rh.values():
        row.setdefault("as_of", rh_as_of)
    for sym in ("SPY", "QQQ", "DIA", "NVDA", "USO"):
        if sym in by and by[sym].get("last") is not None:
            continue
        row = rh.get(sym)
        if row and row.get("last") is not None:
            by[sym] = row

    order = ["SPY", "QQQ", "DIA", "VIX", "NVDA", "USO"]
    chips = []
    for sym in order:
        row = by.get(sym)
        if not isinstance(row, dict) or row.get("last") is None:
            continue  # never invent numbers
        spot = row.get("last")
        day = row.get("day_pct")
        src = row.get("source") or ""
        tip = f"{sym} {_fmt_px(spot, 2)} · day {_fmt_px(day, 2) if day is not None else '—'}% · {src} · session {session}"
        if row.get("as_of"):
            tip += f" · as of {row.get('as_of')}"  # last known mark clock (after hours = last close fetch)
        chips.append(
            f'<div class="mb-chip mb-idx" title="{_esc(tip)}">'
            f'<span class="mb-chip-k">{_esc(sym)}</span>'
            f'<span class="mb-chip-v num">{_esc(_fmt_px(spot, 2))}</span>'
            f"{_pct_chip(day, tip_prefix=str(sym))}</div>"
        )
    return "".join(chips)


def _banner_index_chips(session_badge_html, ledger: dict) -> str:
    """Backward-compatible alias → key macro tickers."""
    return _banner_key_ticker_chips(session_badge_html, ledger)


CORE20_ALLOWLIST = OID / "config" / "stream-quote-allowlist.json"
RH_QUOTES_TTL_S = 120.0


def _core20_symbols() -> list[str]:
    try:
        data = json.loads(CORE20_ALLOWLIST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(s).strip().upper() for s in data.get("underlyings") or [] if str(s).strip()]


def _pt_clock(ts: Any) -> str:
    """RFC-3339 / epoch -> 'YYYY-MM-DD H:MM AM PT' (empty when unparseable)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    if ts is None or ts == "":
        return ""
    try:
        if isinstance(ts, (int, float)):
            d = datetime.fromtimestamp(float(ts), timezone.utc)
        else:
            raw = str(ts).strip().replace("Z", "+00:00")
            if "." in raw:  # trim >6 fractional digits for fromisoformat
                head, _, tail = raw.partition(".")
                frac = "".join(ch for ch in tail if ch.isdigit())
                rest = tail[len(frac):]
                raw = f"{head}.{frac[:6].ljust(6, '0')}{rest}"
            d = datetime.fromisoformat(raw)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OSError):
        return ""
    return d.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %-I:%M %p PT")


def core20_rows(*, now: Optional[float] = None) -> dict[str, Any]:
    """Core-20 (config/stream-quote-allowlist.json) equity marks for the blotter.

    Per symbol: fresh Mac-mini cache row (quotes/mini_client.read_cache, equities only) else the
    shared rh-quotes row. Previous close always from RH. Stale guards:
      - mini rows only count when read_cache() says fresh *now* (file <=15s, quote/trade age
        within the session window; CLOSED -> never fresh).
      - RH rows must pass quote_freshness.check_quotes (trade date >= last completed session);
        older rows are dropped, never shown.
      - ``live`` is True only for a fresh mini row, or an RH row whose file is within the 120s
        TTL during PRE/RTH/AH. Everything else is labelled as the last mark with its real
        trade-time as-of (never re-stamped).
    No option / OPRA data.
    """
    import sys
    import time as _time

    syms = _core20_symbols()
    out: dict[str, Any] = {"symbols": syms, "rows": [], "session": "closed", "from_mini": [], "from_rh": [],
                           "missing": [], "mini_cache": None, "rh_as_of_pt": None}
    if not syms:
        return out
    for sub in ("paper-trades", "market-data", "quotes"):
        sp = str(OID / sub)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    try:
        from market_session import market_session
        session = market_session()
    except Exception:
        session = "closed"
    try:  # mini_client adds "overnight" (8 PM-4 AM ET on trading nights; mini on Alpaca overnight feed)
        from mini_client import current_session as _mini_session
        session = _mini_session() or session
    except Exception:
        pass
    out["session"] = session
    prior_close_date = None
    if session == "overnight":
        try:
            from market_session import prior_rth_close
            prior_close_date = prior_rth_close().date()
        except Exception:
            prior_close_date = None

    mini_rows: dict[str, dict] = {}
    try:
        from mini_client import read_cache
        c = read_cache(syms) if now is None else read_cache(syms, now=now)
        out["mini_cache"] = {"fresh_file": c.get("fresh_file"), "file_age_s": c.get("file_age_s"),
                             "error": c.get("error"), "fresh_symbols": len(c.get("quotes") or {})}
        if c.get("fresh_file"):
            mini_rows = {k: v for k, v in (c.get("quotes") or {}).items()
                         if isinstance(v, dict) and v.get("source") == "mini"}
    except Exception as e:  # never blocks the RH path
        out["mini_cache"] = {"error": f"{type(e).__name__}"}

    rh_rec, rh_payload = _load_payload("rh-quotes")
    rh_quotes = {}
    if isinstance(rh_payload, dict):
        q = rh_payload.get("quotes") or rh_payload.get("equities") or {}
        if isinstance(q, dict):
            rh_quotes = {str(k).upper(): v for k, v in q.items() if isinstance(v, dict)}
    rh_as_of_pt = (rh_rec or {}).get("as_of_pt") if isinstance(rh_rec, dict) else None
    out["rh_as_of_pt"] = rh_as_of_pt
    rh_file_age = None
    try:
        rp = LATEST / "rh-quotes.json"
        rh_file_age = max(0.0, (now if now is not None else _time.time()) - rp.stat().st_mtime)
    except OSError:
        pass
    rh_dropped: dict[str, str] = {}
    try:
        from quote_freshness import EQUITY_TIME_KEYS, check_quotes
        chk = check_quotes({s: rh_quotes[s] for s in syms if s in rh_quotes}, EQUITY_TIME_KEYS)
        rh_ok = chk["fresh"]
        rh_dropped = dict(chk.get("stale") or {})
    except Exception:
        rh_ok = {}  # guard unavailable -> refuse RH rows rather than risk stale stamps
    out["rh_stale_dropped"] = rh_dropped
    rh_live = bool(rh_file_age is not None and rh_file_age <= RH_QUOTES_TTL_S and session in ("pre", "rth", "ah"))

    def _et_date(ts: Any):
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        try:
            raw = str(ts).strip().replace("Z", "+00:00")
            if "." in raw:
                head, _, tail = raw.partition(".")
                frac = "".join(ch for ch in tail if ch.isdigit())
                raw = f"{head}.{frac[:6].ljust(6, '0')}{tail[len(frac):]}"
            d = datetime.fromisoformat(raw)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(ZoneInfo("America/New_York")).date()
        except (TypeError, ValueError):
            return None

    for sym in syms:
        rq = rh_ok.get(sym) or {}
        prev = _f(rq.get("previous_close") or rq.get("prev_close") or rq.get("previous_close_price"))
        if session == "overnight" and rq and prior_close_date is not None:
            # Overnight day % is vs the PRIOR REGULAR close = RH's regular-session last when it printed on
            # the most recently completed session date (RH previous_close is one session older here).
            rh_last = _f(rq.get("last") or rq.get("last_trade_price"))
            if rh_last is not None and _et_date(rq.get("venue_last_trade_time") or rq.get("last_trade_time")) == prior_close_date:
                prev = rh_last
        m = mini_rows.get(sym)
        price = src = as_of = None
        feed_session = None
        live = False
        if session == "overnight" and m:
            # Overnight mark: fresh overnight print if any (<=120s), else overnight bid/ask mid.
            # SIP leftovers (e.g. an 8 PM after-hours trade) are never shown as overnight.
            ta, qa = m.get("trade_age_s"), m.get("quote_age_s")
            if m.get("trade_feed") == "overnight" and _f(m.get("last")) is not None and ta is not None and ta <= 120:
                price, as_of = _f(m.get("last")), _pt_clock(m.get("trade_time"))
            elif m.get("quote_feed") == "overnight" and _f(m.get("mid")) is not None and qa is not None and qa <= 120:
                price, as_of = _f(m.get("mid")), _pt_clock(m.get("quote_time"))
            if price is not None:
                src, feed_session, live = "mini", "overnight", True
        if price is not None:
            pass
        elif session != "overnight" and m and (_f(m.get("last")) is not None):
            price = _f(m.get("last"))
            src = "mini"
            as_of = _pt_clock(m.get("trade_time") or m.get("quote_time"))
            live = True
        elif rq and _f(rq.get("last") or rq.get("last_trade_price")) is not None:
            price = _f(rq.get("last") or rq.get("last_trade_price"))
            src = "RH"
            as_of = _pt_clock(rq.get("venue_last_trade_time") or rq.get("last_trade_time")) or (rh_as_of_pt or "")
            live = rh_live
        if price is None:
            out["missing"].append(sym)
            continue  # never invent numbers
        day = ((price - prev) / prev * 100.0) if prev not in (None, 0) else None
        out["rows"].append({"symbol": sym, "last": price, "previous_close": prev, "day_pct": day,
                            "source": src, "as_of": as_of or "", "live": live, "session": session,
                            "feed_session": feed_session or ("sip" if src == "mini" else None)})
        (out["from_mini"] if src == "mini" else out["from_rh"]).append(sym)
    return out


def _banner_core20_chips(data: Optional[dict] = None) -> str:
    """Compact Core-20 chips (class mb-core-chip — kept out of macro.metrics on import)."""
    data = data if data is not None else core20_rows()
    session = data.get("session") or "closed"
    chips = []
    for r in data.get("rows") or []:
        sym, px, day = r["symbol"], r.get("last"), r.get("day_pct")
        state = "live" if r.get("live") else "last mark"
        fs = r.get("feed_session") or ""
        src_lbl = "mini overnight (Alpaca overnight feed)" if fs == "overnight" else str(r.get("source"))
        prev_lbl = "prior regular close (RH)" if session == "overnight" else "RH prev close"
        tip = (f"{sym} {_fmt_px(px, 2)} · day {_fmt_px(day, 2) if day is not None else '—'}% vs {prev_lbl} "
               f"{_fmt_px(r.get('previous_close'), 2)} · src {src_lbl} · {state} · session {session}"
               + (f" · as of {r.get('as_of')}" if r.get("as_of") else ""))
        chips.append(
            f'<div class="mb-core-chip" data-src="{_esc(r.get("source"))}" data-feed="{_esc(fs)}" data-live="{"1" if r.get("live") else "0"}"'
            f' data-session="{_esc(session)}" data-asof="{_esc(r.get("as_of"))}" title="{_esc(tip)}">'
            f'<span class="mb-core-k">{_esc(sym)}</span>'
            f'<span class="mb-core-v num">{_esc(_fmt_px(px, 2))}</span>'
            f"{_pct_chip(day, tip_prefix=str(sym))}"
            f'<span class="mb-core-src">{_esc("overnight" if fs == "overnight" else r.get("source"))}</span>'
            f"</div>"
        )
    return "".join(chips)


def render_macro_banner(
    *,
    session_badge_html,
    ledger: Optional[dict] = None,
) -> str:
    """Compact sticky-feel macro banner for top of blotter."""
    ledger = ledger or {}
    pills, worst, asof = _banner_status_pills()
    macro_chips = _banner_macro_chips()
    idx_chips = _banner_index_chips(session_badge_html, ledger)
    if not pills and not macro_chips and not idx_chips:
        return (
            '<div class="macro-banner empty-banner">'
            '<div class="mb-meta muted">Macro banner empty — run macro_morning / macro_spot / refresh_market_tape</div>'
            "</div>"
        )
    tape_rec, tape = _load_payload("market-tape")
    session = (tape or {}).get("session") or (ledger.get("meta") or {}).get("marketSession") or "closed"
    sess_badge = session_badge_html(session)
    row2_bits = []
    if idx_chips:
        row2_bits.append(f'<div class="mb-group"><span class="mb-group-k">Key tickers</span>{idx_chips}</div>')
    if macro_chips:
        row2_bits.append(
            f'<div class="mb-group"><span class="mb-group-k">Rates · Vol · Oil</span>{macro_chips}</div>'
        )
    row2 = f'<div class="mb-row mb-row-chips">{"".join(row2_bits)}</div>' if row2_bits else ""
    try:
        core_chips = _banner_core20_chips()
    except Exception as _core_e:  # never break the banner
        print("core20 chips failed:", _core_e)
        core_chips = ""
    if core_chips:
        row2 += (f'<div class="mb-row mb-row-core"><div class="mb-group mb-core20">'
                 f'<span class="mb-group-k">Core 20</span>{core_chips}</div></div>')
    status_row = (
        f'<div class="mb-row mb-row-status">{pills}</div>' if pills else ""
    )
    return f"""
<div class="macro-banner {worst}">
  <div class="mb-head">
    <span class="mb-title">Macro checks</span>
    <span class="mb-sub">soft color · paper only · {_esc(asof)} · {sess_badge}</span>
  </div>
  {status_row}
  {row2}
</div>
"""


def render_market_detail(
    *,
    session_badge_html,
    ledger: Optional[dict] = None,
) -> str:
    """Collapsible market detail: Fidelity-3 + metric scores + notes (data preserved)."""
    ledger = ledger or {}
    tape_rec, tape = _load_payload("market-tape")
    fid_rec, fid = _load_payload("fidelity-three")
    if not tape and not fid:
        return ""

    as_of = (tape or {}).get("as_of_pt") or (tape_rec or {}).get("as_of_pt") or "—"
    session = (tape or {}).get("session") or (ledger.get("meta") or {}).get("marketSession") or "closed"

    # Full index cells (detail) — same data as banner chips, richer layout
    idx_cells = []
    for row in (tape or {}).get("indices") or []:
        sym = row.get("symbol") or "—"
        display_sym = "DIA" if sym == "DIA" else sym
        spot = _f(row.get("spot"))
        day = _f(row.get("day_pct"))
        sess = row.get("session") or session or "closed"
        live_ext = bool(row.get("extended_live"))
        badge = session_badge_html(sess, live=live_ext and str(sess).lower() in ("pre", "ah"))
        chip = _pct_chip(day, tip_prefix=str(display_sym))
        sub = ""
        if sym == "DIA":
            sub = '<div class="tl-ext muted">Dow proxy</div>'
        elif str(sess).lower() == "closed":
            sub = '<div class="tl-ext muted">not live · last RTH</div>'
        elif str(sess).lower() in ("pre", "ah"):
            kind = "pre-market" if str(sess).lower() == "pre" else "after-hours"
            sub = f'<div class="tl-ext tl-ext-{_esc(str(sess).lower())}">{_esc(kind)} · not RTH</div>'
        px = _esc(_fmt_px(spot, 2)) if spot is not None else "—"
        idx_cells.append(
            f'<div class="mkt-idx ticker-live">'
            f'<div class="tl-sym">{_esc(display_sym)} {badge}</div>'
            f'<div class="tl-px num">{px} {chip}</div>'
            f"{sub}</div>"
        )
    indices_html = "".join(idx_cells) if idx_cells else '<div class="muted">Indices unavailable</div>'

    fid = fid or {}
    mg = fid.get("median_growth") or {}
    cr = fid.get("credit_spreads") or {}
    vs = fid.get("valuation_spreads") or {}
    hy = cr.get("hy_oas") or {}
    ig = cr.get("ig_oas") or {}
    hist = vs.get("history") or {}

    rsp_spy = _f(mg.get("rsp_minus_spy_day_pct"))
    rsp_day = _f((mg.get("rsp") or {}).get("day_pct"))
    spy_day = _f((mg.get("spy") or {}).get("day_pct"))
    growth_tone = _soft_tone("growth", spread=rsp_spy)

    hy_q = hy.get("quartile")
    ig_q = ig.get("quartile")
    credit_tone = _soft_tone("credit", quartile=hy_q)
    val_q = hist.get("quartile")
    val_tone = _soft_tone("valuation", quartile=val_q)
    ratio = _f(vs.get("price_ratio"))
    day_spr = _f(vs.get("day_spread_pct"))

    hy_d1 = hy.get("delta_1y")
    ig_d1 = ig.get("delta_1y")
    hy_d1_s = f"{hy_d1:+.2f}" if isinstance(hy_d1, (int, float)) else "—"
    ig_d1_s = f"{ig_d1:+.2f}" if isinstance(ig_d1, (int, float)) else "—"

    growth_card = (
        f'<div class="f3-card {growth_tone}" title="{_esc(mg.get("disclaimer") or "")}">'
        f'<div class="f3-k">Median growth proxy</div>'
        f'<div class="f3-v">RSP−SPY <strong>{_esc(_spread_label(rsp_spy))}</strong></div>'
        f'<div class="f3-d">RSP {_pct_chip(rsp_day)} · SPY {_pct_chip(spy_day)}</div>'
        f'<div class="f3-note">Equal-weight breadth · true median EPS = FactSet/Bloomberg later</div>'
        f"</div>"
    )
    credit_card = (
        f'<div class="f3-card {credit_tone}" title="{_esc(cr.get("logic") or "")}">'
        f'<div class="f3-k">Credit spreads (FRED OAS)</div>'
        f'<div class="f3-v">HY <strong>{_esc(_fmt_oas(hy.get("level")))}</strong>'
        f'<span class="f3-meta">Δ1y {_esc(hy_d1_s)} · {_fmt_pctile(hy.get("percentile_10y"))} · Q{_esc(hy_q or "—")}</span></div>'
        f'<div class="f3-d">IG <strong>{_esc(_fmt_oas(ig.get("level")))}</strong>'
        f'<span class="f3-meta">Δ1y {_esc(ig_d1_s)} · {_fmt_pctile(ig.get("percentile_10y"))} · Q{_esc(ig_q or "—")}</span></div>'
        f'<div class="f3-note">Tight→historically S&amp;P up next yr · Wide Q4 often near bottoms · soft only</div>'
        f"</div>"
    )
    ratio_s = f"{ratio:.4f}" if ratio is not None else "—"
    val_card = (
        f'<div class="f3-card {val_tone}" title="{_esc(vs.get("disclaimer") or "")}">'
        f'<div class="f3-k">Valuation spreads proxy</div>'
        f'<div class="f3-v">VTV/VUG <strong>{_esc(ratio_s)}</strong>'
        f'<span class="f3-meta">{_fmt_pctile(hist.get("ratio_percentile_10y"))} · Q{_esc(val_q or "—")}</span></div>'
        f'<div class="f3-d">Day spread VTV−VUG {_pct_chip(day_spr)}</div>'
        f'<div class="f3-note">Cheap vs expensive gap proxy · true quant series is vendor · soft only</div>'
        f"</div>"
    )

    fid_asof = (fid_rec or {}).get("as_of_pt") or fid.get("as_of_pt") or as_of
    macro_html = _render_macro_panel(tape, tape_rec)
    morning_html = _render_morning_status()

    return f"""
<details class="mkt-detail">
  <summary class="mkt-detail-sum">
    <span class="mkt-title">Market detail</span>
    <span class="mkt-sub">indices · Macro · Rates · Vol · Oil · Morning status · Fidelity-3 · {_esc(as_of)} · session {session_badge_html(session)}</span>
  </summary>
  <div class="mkt-strip mkt-strip-nested">
    <div class="mkt-indices">{indices_html}</div>
    {macro_html}
    {morning_html}
    <div class="f3-panel">
      <div class="f3-head">Macro stress · Fidelity-3 <span class="mkt-sub">(soft color · paper only · {_esc(fid_asof)})</span></div>
      <div class="f3-grid">
        {growth_card}
        {credit_card}
        {val_card}
      </div>
    </div>
  </div>
</details>
"""


def render(
    *,
    session_badge_html,
    ledger: Optional[dict] = None,
) -> str:
    """Return HTML for the market-overview strip (legacy full strip = banner + detail)."""
    banner = render_macro_banner(session_badge_html=session_badge_html, ledger=ledger)
    detail = render_market_detail(session_badge_html=session_badge_html, ledger=ledger)
    if not detail:
        return banner
    return banner + detail


STRIP_CSS = """
.macro-banner{margin:0 0 10px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;background:linear-gradient(180deg,#121a24,#0e141c)}
.macro-banner.soft-calm{border-color:#1e5c40;background:linear-gradient(180deg,#0f1c18,#0e141c)}
.macro-banner.soft-warm{border-color:#6a4e18;background:linear-gradient(180deg,#1c180e,#0e141c)}
.macro-banner.soft-stress{border-color:#5c3040;background:linear-gradient(180deg,#1c1014,#0e141c)}
.macro-banner.soft-neutral{border-color:var(--line)}
.macro-banner.empty-banner{opacity:.85}
.mb-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:6px}
.mb-title{font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.mb-sub{font-size:.68rem;color:var(--muted)}
.mb-row{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:stretch}
.mb-row-status{margin-bottom:6px}
.mb-pill{flex:1 1 280px;min-width:220px;padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:#0a1018}
.mb-pill.soft-calm{border-color:#1e5c40}
.mb-pill.soft-warm{border-color:#6a4e18}
.mb-pill.soft-stress{border-color:#5c3040}
.mb-pill.soft-neutral{border-color:var(--line)}
.mb-pill-top{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 8px}
.mb-k{font-size:.62rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
.mb-score{font-family:var(--mono);font-weight:700;font-size:.85rem}
.mb-label{font-size:.78rem;font-weight:650;color:var(--text)}
.mb-drv{font-size:.68rem;color:var(--muted);line-height:1.3;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mb-group{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px}
.mb-group-k{font-size:.58rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700;margin-right:2px}
.mb-chip{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:999px;border:1px solid var(--line);background:#0a1018;font-size:.72rem;white-space:nowrap}
.mb-chip-k{color:var(--muted);font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:.62rem}
.mb-chip-v{font-family:var(--mono);font-weight:650;font-variant-numeric:tabular-nums}
.mb-chip .daychip{margin-left:2px;font-size:.62rem;padding:0 5px}
.mkt-detail{margin:14px 0 10px;border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:0}
.mkt-detail-sum{cursor:pointer;list-style:none;display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px 10px;padding:8px 12px;user-select:none}
.mkt-detail-sum::-webkit-details-marker{display:none}
.mkt-detail-sum::after{content:"▸";color:var(--muted);font-size:.72rem}
.mkt-detail[open] > .mkt-detail-sum::after{content:"▾"}
.mkt-strip{margin:0 0 18px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(180deg,#121a24,#0e141c)}
.mkt-strip-nested{margin:0;border:none;border-radius:0 0 10px 10px;border-top:1px solid var(--line)}
.mkt-strip.empty-strip{opacity:.85}
.mkt-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:12px}
.mkt-title{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.mkt-sub{font-size:.72rem;color:var(--muted)}
.mkt-indices{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
@media(max-width:720px){.mkt-indices{grid-template-columns:1fr}}
.mkt-idx{padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#0a1018}
.f3-panel{margin-top:4px}
.f3-head{font-size:.68rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.f3-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
@media(max-width:900px){.f3-grid{grid-template-columns:1fr}}
.f3-card{padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#0a1018}
.f3-card.soft-calm{border-color:#1e5c40;background:linear-gradient(180deg,#0f1c18,#0a1018)}
.f3-card.soft-warm{border-color:#6a4e18;background:linear-gradient(180deg,#1c180e,#0a1018)}
.f3-card.soft-stress{border-color:#5c3040;background:linear-gradient(180deg,#1c1014,#0a1018)}
.f3-card.soft-neutral{border-color:var(--line)}
.f3-k{font-size:.62rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px}
.f3-v{font-size:.92rem;font-weight:650;font-variant-numeric:tabular-nums;margin-bottom:4px}
.f3-v strong{font-family:var(--mono)}
.f3-meta{font-size:.68rem;font-weight:500;color:var(--muted);margin-left:6px}
.f3-d{font-size:.78rem;color:var(--text);margin-bottom:4px}
.f3-note{font-size:.65rem;color:var(--muted);line-height:1.35;margin-top:4px}
.macro-panel{margin:0 0 14px;padding:10px 12px;border:1px solid #2a4a6a;border-radius:10px;background:linear-gradient(180deg,#121c28,#0a1018)}
.macro-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media(max-width:900px){.macro-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.macro-grid{grid-template-columns:1fr}}
.macro-cell .tl-sym{font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.macro-note{margin-top:8px}
.morning-panel{margin:0 0 14px;padding:10px 12px;border:1px solid #4a3a18;border-radius:10px;background:linear-gradient(180deg,#1a160e,#0a1018)}
.morning-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media(max-width:900px){.morning-grid{grid-template-columns:1fr}}
.morning-card ul.morning-drivers{margin:6px 0 0;padding-left:1.1rem;font-size:.72rem;line-height:1.4;color:var(--text)}
.morning-card ul.morning-drivers li{margin:0 0 4px}
.metric-scores{margin-top:10px}
.metric-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.metric-chip{display:flex;align-items:center;gap:6px;padding:4px 8px;border-radius:8px;border:1px solid var(--line);background:#0a1018;font-size:.72rem}
.metric-chip .metric-k{color:var(--muted);text-transform:uppercase;letter-spacing:.04em;font-weight:650}
.metric-chip .metric-v{font-family:var(--mono);font-weight:700}
.metric-chip.soft-calm{border-color:#1e5c40}
.metric-chip.soft-warm{border-color:#6a4e18}
.metric-chip.soft-stress{border-color:#5c3040}
.metric-chip.soft-neutral{border-color:var(--line)}
@media(max-width:640px){.mb-drv{white-space:normal}}
"""
