#!/usr/bin/env python3
"""Rebuild index.html as OID Live Book ticker from ../paper-trades/trades.json (+ scorecard)."""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
OPEN_STATUSES = frozenset({"open", "watching", "paper", "live"})
CLOSED_STATUSES = frozenset({"closed", "stopped", "expired", "invalidated"})

root = Path(__file__).resolve().parent
pt = root.parent / "paper-trades"
ledger = json.loads((pt / "trades.json").read_text())
trades = ledger.get("trades", [])

shay_watch: dict = {}
_shay_path = pt / "shay-semi-watch.json"
if _shay_path.exists():
    try:
        shay_watch = json.loads(_shay_path.read_text())
    except json.JSONDecodeError:
        shay_watch = {}

shay_ma_watch: dict = {}
_shay_ma_path = pt / "shay-ma-levels-watch.json"
if _shay_ma_path.exists():
    try:
        shay_ma_watch = json.loads(_shay_ma_path.read_text())
    except json.JSONDecodeError:
        shay_ma_watch = {}

# Soft watches (research/color only — never seats; never elevate language)
SOFT_WATCH_EXCLUDE = frozenset({"shay-semi-watch.json", "shay-ma-levels-watch.json"})
soft_watches: list[dict] = []
_soft_seen: set[str] = set()
for _sp in sorted(pt.glob("*-watch.json")):
    if _sp.name in SOFT_WATCH_EXCLUDE:
        continue
    try:
        _sw = json.loads(_sp.read_text())
    except (json.JSONDecodeError, OSError):
        continue
    if not isinstance(_sw, dict):
        continue
    # Prefer explicit softOnly; also accept known soft types
    _stype = str(_sw.get("type") or "").lower()
    if not (_sw.get("softOnly") is True or _stype in ("earnings_watch", "oe_darkpool_watch", "soft_watch")):
        continue
    _sid = str(_sw.get("id") or _sp.stem)
    # A desk soft_watch may be one file carrying many symbol rows. Expand it
    # into blotter rows while retaining the source payload for write-back.
    if _stype == "soft_watch" and isinstance(_sw.get("symbols"), list):
        for _row in _sw.get("symbols") or []:
            if not isinstance(_row, dict):
                continue
            _expanded = dict(_sw)
            _expanded.pop("symbols", None)
            _expanded.update(_row)
            _expanded["_sourceFile"] = _sp.name
            _expanded["_sourceExpanded"] = True
            _expanded["_sourcePayload"] = _sw
            _row_sym = str(_row.get("symbol") or "").upper()
            _expanded_id = f"{_sid}:{_row_sym}" if _row_sym else f"{_sid}:{len(soft_watches)}"
            if _expanded_id in _soft_seen:
                continue
            _soft_seen.add(_expanded_id)
            _expanded["id"] = _expanded_id
            soft_watches.append(_expanded)
        continue
    if _sid in _soft_seen:
        continue
    _soft_seen.add(_sid)
    _sw = dict(_sw)
    _sw["_sourceFile"] = _sp.name
    soft_watches.append(_sw)

scorecard: dict = {}
sc_path = pt / "scorecard.json"
if sc_path.exists():
    try:
        scorecard = json.loads(sc_path.read_text())
    except json.JSONDecodeError:
        scorecard = {}

close_triggers: dict = {}
ct_path = root.parent / "tmp" / "close-triggers-last.json"
if ct_path.exists():
    try:
        close_triggers = json.loads(ct_path.read_text())
    except json.JSONDecodeError:
        close_triggers = {}



def agent_label(t):
    """Jeffrey wants Agent column: Rose | Hal on paper desks; Leopold on ZH watches."""
    a = (t.get("agent") or "").strip()
    if a in ("Hal", "Rose", "Leopold"):
        return a
    if a.startswith("ZH/") or "Leopold" in a or t.get("desk") == "ZH":
        return "Leopold"
    if "Hal" in a or str(t.get("id", "")).startswith("OT2-") or t.get("desk") == "OT2":
        return "Hal"
    return "Rose"


def session_badge_html(session=None, *, title=None, live=False):
    """Session chip: RTH | PRE-MARKET | AFTER-HOURS | CLOSED (+ LIVE when extended hours print)."""
    s = (session or (ledger.get("meta") or {}).get("marketSession") or "closed")
    s = str(s).lower()
    lab = {
        "rth": "RTH",
        "pre": "PRE-MARKET",
        "ah": "AFTER-HOURS",
        "closed": "CLOSED",
    }.get(s, str(s).upper() or "CLOSED")
    if live and s in ("pre", "ah"):
        lab = f"{lab} · LIVE"
    tip = title or {
        "rth": "Regular trading hours (09:30–16:00 ET) — normal session",
        "pre": "Premarket (04:00–09:30 ET) — not regular hours; live extended print when available",
        "ah": "After-hours (16:00–20:00 ET) — not regular hours; live extended print when available",
        "closed": "Market closed — spot = last RTH close; day% vs prior close (not live)",
    }.get(s, lab)
    live_cls = " sess-live" if (live and s in ("pre", "ah")) else ""
    return f'<span class="sess-badge sess-{esc(s)}{live_cls}" title="{esc(tip)}">{esc(lab)}</span>'


def day_pct_chip(t):
    """Green/red day% chip; PRE/AH tips say extended hours; CLOSED notes last RTH."""
    pct = _f(t.get("underlyingDayPct"))
    if pct is None:
        return ""
    sess = (t.get("underlyingSession") or (ledger.get("meta") or {}).get("marketSession") or "").lower()
    if pct < 0:
        label = f"−{abs(pct):.2f}%"
    else:
        label = f"+{pct:.2f}%"
    cls = "pos" if pct > 0 else ("neg" if pct < 0 else "flat")
    tip = f"Day {label}"
    if sess == "closed":
        tip = "last RTH session · " + tip
        prev = _f(t.get("underlyingPrevClose"))
        last = _f(t.get("lastUnderlying")) or _f(t.get("underlyingNow"))
        if last is not None and prev is not None:
            tip += f" ({last:.2f} vs prev {prev:.2f})"
        ah = _f(t.get("underlyingAh")) or _f(t.get("lastNonRegUnderlying"))
        if ah is not None:
            tip += f" · last AH print {ah:.2f}"
    elif sess == "pre":
        tip = "PRE-MARKET (not RTH) · " + tip
    elif sess == "ah":
        tip = "AFTER-HOURS (not RTH) · " + tip
    return f'<span class="daychip {cls}" title="{esc(tip)}">{esc(label)}</span>'


def ticker_cell_html(t):
    """Slim ticker: SYMBOL + session label + spot + day%; PRE/AH show LIVE when extended print used."""
    sess = (t.get("underlyingSession") or (ledger.get("meta") or {}).get("marketSession") or "closed")
    sess = str(sess).lower()
    sym = (t.get("symbol") or "").strip() or "—"
    # Prefer live extended-hours print in PRE/AH
    und = _f(t.get("lastUnderlying")) or _f(t.get("underlyingNow")) or _f(t.get("underlying"))
    ext = _f(t.get("lastNonRegUnderlying")) or _f(t.get("underlyingAh")) or _f(t.get("underlyingPre"))
    live_ext = bool(t.get("underlyingExtendedLive")) or (
        sess in ("pre", "ah") and ext is not None
    )
    if sess in ("pre", "ah") and ext is not None:
        und = ext
    badge = session_badge_html(sess, live=live_ext)
    chip = day_pct_chip(t)
    # Secondary line: when CLOSED, show last AH print if we have one and it differs from RTH close
    sub = ""
    if sess == "closed":
        ah = _f(t.get("underlyingAh")) or _f(t.get("lastNonRegUnderlying"))
        rth = und
        if ah is not None and (rth is None or abs(ah - float(rth)) >= 0.005):
            sub = f'<div class="tl-ext muted">last AH {esc(fmt_px(ah, 2))}</div>'
        else:
            sub = '<div class="tl-ext muted">not live · last RTH</div>'
    elif sess in ("pre", "ah"):
        kind = "pre-market" if sess == "pre" else "after-hours"
        live_bit = " · live" if live_ext else ""
        sub = f'<div class="tl-ext tl-ext-{esc(sess)}">{esc(kind)}{esc(live_bit)} · not RTH</div>'
    if und is not None:
        return (
            f'<td class="ticker-live">'
            f'<div class="tl-sym">{esc(sym)} {badge}</div>'
            f'<div class="tl-px num">{esc(fmt_px(und, 2))} {chip}</div>'
            f'{sub}'
            f'</td>'
        )
    return (
        f'<td class="ticker-live">'
        f'<div class="tl-sym">{esc(sym)} {badge}</div>'
        f'<div class="tl-px muted">— {chip}</div>'
        f'{sub}'
        f'</td>'
    )




def trade_qty(t: dict) -> int:
    for k in ("qty", "qtySuggested", "quantity", "contracts"):
        v = t.get(k)
        if v is None:
            continue
        try:
            return max(1, int(v))
        except (TypeError, ValueError):
            continue
    return 1


def total_cost_usd(t: dict) -> float | None:
    """Total cash debit (or credit magnitude) = per-share cost × 100 × qty."""
    c = entry_cost(t)
    if c is None:
        return None
    return float(c) * 100.0 * trade_qty(t)


def cost_qty_cells(t: dict) -> str:
    """Cost (per share) · Qty · Total $ for main row."""
    cost = entry_cost(t)
    qn = trade_qty(t)
    tot = total_cost_usd(t)
    tot_s = f"${tot:,.0f}" if tot is not None else "—"
    return (
        f'<td class="num" title="Per-share premium (entry ask)">{esc(fmt_px(cost))}</td>'
        f'<td class="num" title="Contracts">{qn}</td>'
        f'<td class="num" title="Total cash = premium × 100 × qty">{esc(tot_s)}</td>'
    )



def load_desk_catalysts() -> dict:
    for p in (
        Path(__file__).resolve().parent.parent / "market-data" / "latest" / "desk-catalysts.json",
        Path(__file__).resolve().parent.parent / "trader-intel" / "catalysts.json",
    ):
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
    return {}


def events_within_days(symbol: str, *, within: int = 30) -> list:
    """Upcoming earnings + other catalysts for symbol in [0, within] days."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    data = load_desk_catalysts()
    today = datetime.now(PT).date()
    out = []
    for e in data.get("earnings") or []:
        if (e.get("symbol") or "").upper() != sym:
            continue
        try:
            d = date.fromisoformat(str(e.get("date") or "")[:10])
        except Exception:
            continue
        days = (d - today).days
        if 0 <= days <= within:
            timing = e.get("timing") or ""
            lab = f"Earnings {d.isoformat()}" + (f" {timing}" if timing else "")
            out.append({
                "date": d.isoformat(),
                "days": days,
                "kind": "earnings",
                "label": lab,
                "implied_move_pct": e.get("implied_move_pct"),
            })
    for e in data.get("other_events") or []:
        if (e.get("symbol") or "").upper() != sym:
            continue
        try:
            d = date.fromisoformat(str(e.get("date") or "")[:10])
        except Exception:
            continue
        days = (d - today).days
        if 0 <= days <= within:
            out.append({
                "date": d.isoformat(),
                "days": days,
                "kind": e.get("type") or "event",
                "label": e.get("title") or (e.get("type") or "event"),
                "implied_move_pct": None,
            })
    out.sort(key=lambda x: x["days"])
    return out


def event_chip_html(t: dict, *, within: int = 30) -> str:
    """Badge when ticker has an event ≤ within days."""
    evs = events_within_days(t.get("symbol") or "", within=within)
    if not evs:
        return ""
    nearest = evs[0]
    n = len(evs)
    days = nearest["days"]
    kind = nearest["kind"]
    short = "Earn" if kind == "earnings" else "Evt"
    tip_bits = []
    for e in evs[:4]:
        im = e.get("implied_move_pct")
        im_s = f" · ~{im:.1f}% impl" if isinstance(im, (int, float)) else ""
        tip_bits.append(f"{e['date']} ({e['days']}d) {e['label']}{im_s}")
    if n > 4:
        tip_bits.append(f"+{n - 4} more")
    tip = esc(" · ".join(tip_bits))
    cls = "earn" if kind == "earnings" else "evt"
    extra = f"+{n - 1}" if n > 1 else ""
    return f'<span class="evchip {cls}" title="{tip}">{short} {days}d{extra}</span>'


def trade_in_out(t: dict) -> tuple[str, str]:
    """Human PT/ET timestamps for entry (in) and exit (out)."""
    inn = (
        t.get("offeredAtPT")
        or t.get("elevatedAtPT")
        or t.get("openedAtPT")
        or t.get("offeredAtET")
        or t.get("elevatedAtET")
    )
    if not inn:
        raw = t.get("offeredAt") or t.get("elevatedAt") or t.get("openedAt")
        if raw:
            inn = str(raw)
    out = (
        t.get("exitAtPT")
        or t.get("closedAtPT")
        or t.get("invalidatedAtPT")
        or t.get("exitAtET")
        or t.get("closedAtET")
    )
    if not out:
        st = (t.get("status") or "").lower()
        if st in ("closed", "invalidated", "expired"):
            raw = t.get("exitAt") or t.get("closedAt") or t.get("invalidatedAt") or t.get("updatedAt")
            if raw:
                out = str(raw)
            if t.get("exitAtApprox"):
                out = (out or "—") + " (approx)"
        else:
            out = "—"  # still open
    return (inn or "—", out or "—")


def in_out_cells(t: dict) -> str:
    """Two drawer tiles: In · Out."""
    inn, out = trade_in_out(t)
    return (
        f'<div><span class="dk">In</span><div class="dv">{esc(inn)}</div></div>'
        f'<div><span class="dk">Out</span><div class="dv">{esc(out)}</div></div>'
    )





def rationale_full(t) -> str:
    """Full trade rationale. Prefer explicit `rationale`, else Thesis: line in softCatalystDetail."""
    r = (t.get("rationale") or t.get("thesis") or "").strip()
    if not r:
        scd = t.get("softCatalystDetail")
        if isinstance(scd, list):
            for line in scd:
                s = str(line).strip()
                m = re.match(r"(?i)^thesis:\s*(.+)$", s)
                if m:
                    r = m.group(1).strip()
                    break
            if not r:
                bits = [str(x).strip() for x in scd[:2] if str(x).strip()]
                r = " · ".join(bits)
        if not r:
            r = (t.get("softCatalyst") or "").strip()
    return r


def rationale_cell(t, preview_len=40) -> str:
    """Compact Why column: one-line preview; click expands a popover with full rationale."""
    full = rationale_full(t)
    if not full:
        return '<td class="rationale muted">—</td>'
    preview = full if len(full) <= preview_len else full[: preview_len - 1] + "…"
    # data-full on the details for title; body holds full text
    return (
        f'<td class="rationale">'
        f'<details class="rat">'
        f'<summary title="{esc(full)}"><span class="rat-preview">{esc(preview)}</span></summary>'
        f'<div class="rat-pop" role="dialog">{esc(full)}</div>'
        f'</details></td>'
    )



def greeks_cell(t: dict) -> str:
    """Compact Δ · θ$/day; expand for γ / IV / θ raw."""
    de = _f(t.get("delta"))
    th_usd = _f(t.get("thetaUsdPerDay"))
    if th_usd is None and _f(t.get("theta")) is not None:
        try:
            qty = max(1, int(t.get("qtySuggested") or 1))
        except (TypeError, ValueError):
            qty = 1
        th_usd = round(float(t["theta"]) * 100.0 * qty, 2)
    ga = _f(t.get("gamma"))
    iv = _f(t.get("iv"))
    th_raw = _f(t.get("theta"))
    if de is None and th_usd is None:
        return '<td class="greeks muted">—</td>'
    de_s = f"Δ {de:.2f}" if de is not None else "Δ —"
    if th_usd is not None:
        th_s = f"θ {th_usd:+.0f}/d"
        th_cls = "neg" if th_usd < 0 else "pos"
    else:
        th_s = "θ —"
        th_cls = ""
    preview = f"{de_s} · {th_s}"
    bits = []
    if de is not None:
        bits.append(f"Delta {de:.3f}")
    if th_usd is not None:
        bits.append(f"Theta ${th_usd:+.2f}/day (premium bleed when negative)")
    if th_raw is not None:
        bits.append(f"θ raw {th_raw:.4f}/share")
    if ga is not None:
        bits.append(f"Gamma {ga:.4f}")
    if iv is not None:
        bits.append(f"IV {iv*100:.1f}%")
    be = break_even_of(t)
    rh = _f(t.get("breakEvenRh"))
    if be is not None:
        bits.append(f"Entry BE {be:.2f}")
    if rh is not None:
        bits.append(f"RH mark BE {rh:.2f}")
    full = " · ".join(bits) if bits else preview
    return (
        f'<td class="greeks">'
        f'<details class="gk">'
        f'<summary title="{esc(full)}"><span class="gk-preview"><span class="gk-d">{esc(de_s)}</span>'
        f' <span class="{th_cls}">{esc(th_s)}</span></span></summary>'
        f'<div class="gk-pop" role="dialog">{esc(full)}</div>'
        f'</details></td>'
    )



def break_even_of(t: dict) -> Optional[float]:
    be = _f(t.get("breakEven")) or _f(t.get("breakEvenEntry"))
    if be is not None:
        return be
    try:
        import sys
        sys.path.insert(0, str(pt))
        from breakeven import break_even_entry
        return break_even_entry(t)
    except Exception:
        return _f(t.get("breakEvenRh"))


def be_cell(t: dict) -> str:
    """Thin breakeven column (entry-based); title includes RH mark BE if present."""
    be = break_even_of(t)
    rh = _f(t.get("breakEvenRh"))
    und = _f(t.get("lastUnderlying")) or _f(t.get("underlyingNow")) or _f(t.get("underlying"))
    if be is None:
        return '<td class="num be muted">—</td>'
    tip = f"Entry BE {be:.2f}"
    if rh is not None:
        tip += f" · RH mark BE {rh:.2f}"
    if und is not None:
        dist = und - be
        tip += f" · spot {und:.2f} ({dist:+.2f} vs BE)"
    return f'<td class="num be" title="{esc(tip)}">{esc(fmt_px(be, 2))}</td>'


def esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _f(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def entry_cost(t: dict) -> Optional[float]:
    for k in ("entryAsk", "entryMark", "entryBid", "costBasis"):
        x = _f(t.get(k))
        if x is not None:
            return x
    return None


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def age_str(t: dict) -> str:
    start = parse_iso(t.get("offeredAt")) or parse_iso(t.get("elevatedAt"))
    if not start:
        return "—"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - start).total_seconds() / 3600.0
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 48:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def quote_stale(t: dict) -> tuple[bool, str]:
    """Return (stale, reason). Stale if >2 min or delayed flag."""
    if t.get("quoteDelayed"):
        return True, "delayed"
    qat = parse_iso(t.get("lastQuotedAt"))
    if not qat:
        return True, "no quote"
    if qat.tzinfo is None:
        qat = qat.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - qat).total_seconds()
    if age > 120:
        mins = int(age // 60)
        return True, f"{mins}m old"
    return False, "live"


def fmt_px(v: Optional[float], digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def fmt_usd(v: Optional[float]) -> str:
    if v is None:
        return "—"
    if v > 0:
        return f"+${v:,.2f}"
    if v < 0:
        return f"-${abs(v):,.2f}"
    return "$0.00"


def fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"



def fmt_mfe_mae(t: dict, kind: str) -> tuple[str, str, Optional[float]]:
    """Return (usd_str, pct_str, pct_for_class) for mfe or mae."""
    usd = _f(t.get(f"{kind}Usd"))
    pct = _f(t.get(f"{kind}Pct"))
    return fmt_usd(usd), fmt_pct(pct), pct


def short_pt(s: Optional[str]) -> str:
    """Compress peak/trough PT stamps for blotter (e.g. 10:42a)."""
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()
    # common forms: "2026-09-18 10:42 AM PT" or ISO
    for sep in (" PT", " PDT", " PST"):
        if sep in s:
            s = s.split(sep)[0].strip()
            break
    parts = s.replace(",", "").split()
    # try find time token like 10:42 or 10:42:15
    time_tok = None
    ampm = ""
    for i, part in enumerate(parts):
        if ":" in part and part[0].isdigit():
            time_tok = part.rsplit(":", 1)[0] if part.count(":") >= 2 else part  # drop seconds
            if i + 1 < len(parts) and parts[i + 1].upper() in ("AM", "PM"):
                ampm = parts[i + 1][0].lower()
            break
    if time_tok:
        return f"{time_tok}{ampm}"
    return s[-8:] if len(s) > 8 else s


def mfe_cell(tr: dict) -> str:
    pct = _f(tr.get("mfePct"))
    usd = _f(tr.get("mfeUsd"))
    when = tr.get("peakMarkAtPT") or tr.get("mfeAtPT") or tr.get("peakMarkAt") or ""
    when_s = short_pt(when) if when else ""
    cls = pnl_class(pct)
    top = esc(fmt_pct(pct))
    sub = ""
    if when_s:
        sub = f'<div class="tiny" title="MFE at {esc(when)}">{esc(when_s)}</div>'
    tip = f'MFE $ {esc(fmt_usd(usd))}' + (f' @ {esc(when)}' if when else '')
    return f'<td class="num {cls}" title="{tip}">{top}{sub}</td>'


def mae_cell(tr: dict) -> str:
    pct = _f(tr.get("maePct"))
    usd = _f(tr.get("maeUsd"))
    when = tr.get("troughMarkAtPT") or tr.get("maeAtPT") or tr.get("troughMarkAt") or ""
    when_s = short_pt(when) if when else ""
    cls = pnl_class(pct)
    top = esc(fmt_pct(pct))
    sub = ""
    if when_s:
        sub = f'<div class="tiny" title="MAE at {esc(when)}">{esc(when_s)}</div>'
    tip = f'MAE $ {esc(fmt_usd(usd))}' + (f' @ {esc(when)}' if when else '')
    return f'<td class="num {cls}" title="{tip}">{top}{sub}</td>'

def pnl_class(v: Optional[float]) -> str:
    if v is None:
        return ""
    if v > 0:
        return "pos"
    if v < 0:
        return "neg"
    return "flat"


def qty_of(t: dict) -> int:
    try:
        return max(1, int(t.get("qtySuggested") or 1))
    except (TypeError, ValueError):
        return 1


def premium_cost_usd(t: dict) -> Optional[float]:
    """Premium/cost in $ (entry × qty × 100)."""
    c = entry_cost(t)
    if c is None:
        return None
    return c * qty_of(t) * 100.0


def trade_pnl_usd(t: dict) -> Optional[float]:
    return _f(t.get("pnlUsd")) or _f(t.get("unrealizedPnlUsd"))


def trade_pnl_pct(t: dict) -> Optional[float]:
    return _f(t.get("pnlPct")) or _f(t.get("unrealizedPnlPct"))


def agg_section(rows: list) -> dict:
    """Aggregate n · cost · P&L $ · P&L % · W/L for a blotter section."""
    n = len(rows)
    cost = 0.0
    cost_known = False
    pnl = 0.0
    wins = 0
    losses = 0
    flats = 0
    for t in rows:
        pc = premium_cost_usd(t)
        if pc is not None:
            cost += pc
            cost_known = True
        pu = trade_pnl_usd(t)
        if pu is None:
            pu = 0.0
        pnl += pu
        if pu > 0:
            wins += 1
        elif pu < 0:
            losses += 1
        else:
            flats += 1
    pct = (pnl / cost * 100.0) if cost_known and cost else None
    return {
        "n": n,
        "cost": cost if cost_known else None,
        "pnl": pnl,
        "pct": pct,
        "wins": wins,
        "losses": losses,
        "flats": flats,
    }



def totals_bar_html(agg: dict, label: str = "", *, day_usd=None, day_pct=None, week_usd=None, week_pct=None) -> str:
    """Totals bar with Day / Week % on top of Total P&L."""
    if not agg or agg.get("n", 0) == 0:
        lab = esc(label + " · ") if label else ""
        return f'<div class="totals-bar empty-totals">{lab}0 seats</div>'
    n = agg["n"]
    cost = agg.get("cost")
    pnl = agg.get("pnl")
    pct = agg.get("pct")
    w = agg.get("wins", 0)
    l = agg.get("losses", 0)
    f = agg.get("flats", 0)
    cost_s = f"${cost:,.2f}" if cost is not None else "—"
    pnl_s = esc(fmt_usd(pnl))
    pct_s = esc(fmt_pct(pct)) if pct is not None else "—"
    wl = f"{w}W/{l}L" + (f"/{f}F" if f else "")
    cls = pnl_class(pnl)
    prefix = f'<span class="tb-label">{esc(label)}</span> · ' if label else ""
    # Prefer explicit day/week args, else agg fields
    du = day_usd if day_usd is not None else agg.get("dayUsd")
    dp = day_pct if day_pct is not None else agg.get("dayPct")
    wu = week_usd if week_usd is not None else agg.get("weekUsd")
    wp = week_pct if week_pct is not None else agg.get("weekPct")
    period = (
        f'<div class="tb-period">'
        f'<span class="tb-pill">Day <span class="{pnl_class(du)}">{esc(fmt_pct(dp) if dp is not None else "—")}</span>'
        f' <span class="tb-muted">({esc(fmt_usd(du))})</span></span>'
        f'<span class="tb-pill">Week <span class="{pnl_class(wu)}">{esc(fmt_pct(wp) if wp is not None else "—")}</span>'
        f' <span class="tb-muted">({esc(fmt_usd(wu))})</span></span>'
        f'</div>'
    )
    return (
        f'<div class="totals-bar" role="status">'
        f'{period}'
        f'<div class="tb-main">{prefix}<span class="tb-n">{n}</span>'
        f' · cost <span class="tb-cost">{esc(cost_s)}</span>'
        f' · Total P&amp;L <span class="tb-pnl {cls}">{pnl_s}</span>'
        f' <span class="tb-pct {cls}">({pct_s})</span>'
        f' · <span class="tb-wl">{wl}</span></div>'
        f'</div>'
    )



def trigger_chips(t: dict) -> str:
    """Armed / Giveback / DTE≤1 / Thesis OK / θ tax (+ alert badge)."""
    flags = t.get("closeTriggerFlags") or []
    if not flags and close_triggers:
        for s in close_triggers.get("seats") or []:
            if s.get("id") == t.get("id"):
                flags = s.get("flags") or []
                break
    armed = bool(t.get("closeTriggerArmed")) or ("ARMED" in flags)
    giveback = "GIVEBACK" in flags
    dte1 = "DTE_LE_1" in flags or "OPEX_MORNING" in flags
    thesis_ok = "THESIS_OK" in flags or (
        "THESIS_FAIL" not in flags and not t.get("invalidatedAt")
    )
    alert = t.get("closeTriggerAlert")
    if not alert and close_triggers:
        for s in close_triggers.get("seats") or []:
            if s.get("id") == t.get("id"):
                alert = s.get("alert")
                break
    chips = []
    chips.append(f'<span class="tchip {"on" if armed else "off"}">Armed</span>')
    chips.append(f'<span class="tchip {"hit" if giveback else "off"}">Giveback</span>')
    chips.append(f'<span class="tchip {"warn" if dte1 else "off"}">DTE≤1</span>')
    chips.append(f'<span class="tchip {"ok" if thesis_ok else "bad"}">{"Thesis OK" if thesis_ok else "Thesis FAIL"}</span>')
    theta_tax = "THETA_TAX" in flags
    chips.append(f'<span class="tchip {"warn" if theta_tax else "off"}">θ tax</span>')
    if alert:
        chips.append(f'<span class="tchip alert">{esc(alert)}</span>')
    note = t.get("closeTriggerNote") or ""
    tip = esc(note) if note else "Close-trigger state"
    return f'<div class="tchips" title="{tip}">{" ".join(chips)}</div>'


open_trades = [t for t in trades if (t.get("status") or "").lower() in OPEN_STATUSES]
closed_trades = [t for t in trades if (t.get("status") or "").lower() in CLOSED_STATUSES]
# Recent closed first (full list; totals use all)
closed_trades = sorted(
    closed_trades,
    key=lambda t: t.get("exitAt") or t.get("updatedAt") or t.get("offeredAt") or "",
    reverse=True,
)

# Leopold / ZH external watches — separate from seats (top-level array preferred)
leopold_trades = list(ledger.get("leopoldWatches") or [])
WATCH_STATUSES = frozenset({"leopold_watch", "watch_external"})
for t in trades:
    if (t.get("status") or "").lower() in WATCH_STATUSES and t not in leopold_trades:
        leopold_trades.append(t)

max_seats = int(ledger.get("maxOpenTickets") or 8)
open_n = len(open_trades)  # paper seats only — excludes Leopold watches
book_pnl = sum(_f(t.get("pnlUsd")) or _f(t.get("unrealizedPnlUsd")) or 0.0 for t in open_trades)
book_cost = 0.0
for t in open_trades:
    c = entry_cost(t)
    q = t.get("qtySuggested") or 1
    try:
        q = max(1, int(q))
    except (TypeError, ValueError):
        q = 1
    if c is not None:
        book_cost += c * q * 100.0
book_pct = (book_pnl / book_cost * 100.0) if book_cost else None

# Rose / OID book (primary soft book triggers) — exclude Leopold + Hal/OT2
def _is_rose_oid_seat(t):
    if (t.get("status") or "").lower() not in OPEN_STATUSES:
        return False
    lab = agent_label(t)
    if lab in ("Leopold", "Hal"):
        return False
    desk = (t.get("desk") or "").upper()
    if desk in ("OT2", "ZH"):
        return False
    return lab == "Rose" and (not desk or desk == "OID")

rose_open = [t for t in open_trades if _is_rose_oid_seat(t)]
rose_book_pnl = sum(_f(t.get("pnlUsd")) or _f(t.get("unrealizedPnlUsd")) or 0.0 for t in rose_open)
rose_book_cost = 0.0
for t in rose_open:
    c = entry_cost(t)
    q = t.get("qtySuggested") or 1
    try:
        q = max(1, int(q))
    except (TypeError, ValueError):
        q = 1
    if c is not None:
        rose_book_cost += c * q * 100.0
rose_book_pct = (rose_book_pnl / rose_book_cost * 100.0) if rose_book_cost else None

hal_open = [t for t in open_trades if agent_label(t) == "Hal"]

# Prefer scored book block from close-triggers snapshot; fall back to ledger meta
_book = (close_triggers.get("book") or {}).get("rose") or {}
_meta = ledger.get("meta") or {}
rose_peak = _f(_book.get("bookPeakPnlUsd"))
if rose_peak is None:
    rose_peak = _f(_meta.get("bookPeakPnlUsd"))
rose_peak_at = _book.get("bookPeakAtPT") or _meta.get("bookPeakAtPT") or "—"
rose_giveback = _book.get("givebackPct")
if rose_giveback is None and rose_peak and rose_peak > 0:
    rose_giveback = round(max(0.0, (1.0 - (rose_book_pnl / rose_peak)) * 100.0), 2)
rose_book_flags = list(_book.get("flags") or _meta.get("bookTriggerFlags") or [])
rose_book_alert = _book.get("alert") or _meta.get("bookTriggerAlert")
shared_book = (close_triggers.get("book") or {}).get("shared") or {}
shared_pnl = _f(shared_book.get("pnlUsd"))
if shared_pnl is None:
    shared_pnl = book_pnl
shared_pct = _f(shared_book.get("pnlPct"))
if shared_pct is None:
    shared_pct = book_pct

meta = ledger.get("meta") or {}
last_refresh = (
    meta.get("lastMarksRefreshAtPT")
    or ledger.get("updatedAtPT")
    or scorecard.get("updatedAtPT")
    or "—"
)
shared_day_pct = _f((ledger.get("meta") or {}).get("sharedDayPnlPct"))
shared_day_usd = _f((ledger.get("meta") or {}).get("sharedDayPnlUsd"))
shared_week_pct = _f((ledger.get("meta") or {}).get("sharedWeekPnlPct"))
shared_week_usd = _f((ledger.get("meta") or {}).get("sharedWeekPnlUsd"))
rose_day_pct = _f((ledger.get("meta") or {}).get("bookDayPnlPct"))
rose_day_usd = _f((ledger.get("meta") or {}).get("bookDayPnlUsd"))
rose_week_pct = _f((ledger.get("meta") or {}).get("bookWeekPnlPct"))
rose_week_usd = _f((ledger.get("meta") or {}).get("bookWeekPnlUsd"))
now_pt = datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")

stale_any = any(quote_stale(t)[0] for t in open_trades) or any(quote_stale(t)[0] for t in leopold_trades)

def _sort_pnl(rows):
    return sorted(rows, key=lambda x: (_f(x.get("pnlPct")) is None, -(_f(x.get("pnlPct")) or -9999)))



def open_seat_row(t: dict) -> str:
    """Slim main row + expandable detail drawer (Greeks, Why, triggers, etc.)."""
    cost = entry_cost(t)
    mark = _f(t.get("lastMark"))
    bid = _f(t.get("lastBid"))
    ask = _f(t.get("lastAsk"))
    pnl_u = trade_pnl_usd(t)
    pnl_p = trade_pnl_pct(t)
    und = _f(t.get("lastUnderlying")) or _f(t.get("underlyingNow")) or _f(t.get("underlying"))
    sym = (t.get("symbol") or "").strip() or "—"
    stale, stale_reason = quote_stale(t)
    ba = f"{fmt_px(bid)} / {fmt_px(ask)}"
    stale_badge = f'<span class="badge stale" title="Quote stale or delayed">{esc(stale_reason)}</span>' if stale else '<span class="badge live">live</span>'
    be = break_even_of(t)
    be_gap = None
    if be is not None and und is not None:
        be_gap = und - be
    # Live ticker cell: SYMBOL + session + spot + day%
    ticker_html = ticker_cell_html(t)
    # Stock BE with gap hint
    if be is None:
        be_html = '<td class="num be muted">—</td>'
    else:
        gap_s = f" ({be_gap:+.2f})" if be_gap is not None else ""
        tip = f"Projected stock price for entry breakeven: {be:.2f}"
        if und is not None:
            tip += f" · live {und:.2f}{gap_s}"
        tip += " · long call = strike+debit; long put = strike−debit"
        be_html = (
            f'<td class="num be" title="{esc(tip)}">'
            f'<div class="be-px">{esc(fmt_px(be, 2))}</div>'
            f'<div class="be-gap muted">{esc(gap_s.strip() if gap_s else "")}</div>'
            f'</td>'
        )
    # Detail drawer contents
    why_full = rationale_full(t) or "—"
    de = _f(t.get("delta"))
    th_usd = _f(t.get("thetaUsdPerDay"))
    if th_usd is None and _f(t.get("theta")) is not None:
        th_usd = round(float(t["theta"]) * 100.0 * qty_of(t), 2)
    ga = _f(t.get("gamma"))
    iv = _f(t.get("iv"))
    th_raw = _f(t.get("theta"))
    greeks_bits = []
    if de is not None:
        greeks_bits.append(f"Δ {de:.3f}")
    if th_usd is not None:
        greeks_bits.append(f"θ ${th_usd:+.2f}/day")
    if th_raw is not None:
        greeks_bits.append(f"θ raw {th_raw:.4f}")
    if ga is not None:
        greeks_bits.append(f"γ {ga:.4f}")
    if iv is not None:
        greeks_bits.append(f"IV {iv*100:.1f}%")
    greeks_line = " · ".join(greeks_bits) if greeks_bits else "—"
    mfe_s, mfe_when, _ = fmt_mfe_mae(t, "mfe")
    mae_s, mae_when, _ = fmt_mfe_mae(t, "mae")
    drawer_id = esc(t.get("id") or sym)
    _evs = events_within_days(t.get("symbol") or "", within=30)
    if _evs:
        _ev_lines = []
        for _e in _evs[:5]:
            _im = _e.get("implied_move_pct")
            _im_s = f" · ~{_im:.1f}% impl" if isinstance(_im, (int, float)) else ""
            _ev_lines.append(f"{_e['date']} ({_e['days']}d) {_e['label']}{_im_s}")
        _ev_drawer = esc(" · ".join(_ev_lines))
    else:
        _ev_drawer = "—"
    detail = f"""
      <td colspan="11" class="drawer-td">
        <div class="drawer-grid">
          <div><span class="dk">Why</span><div class="dv">{esc(why_full)}</div></div>
          <div><span class="dk">Bid / Ask</span><div class="dv num">{esc(ba)}</div></div>
          <div><span class="dk">Greeks</span><div class="dv">{esc(greeks_line)}</div></div>
          <div><span class="dk">MFE · time</span><div class="dv">{esc(mfe_s)} <span class="muted">{esc(mfe_when)}</span></div></div>
          <div><span class="dk">MAE · time</span><div class="dv">{esc(mae_s)} <span class="muted">{esc(mae_when)}</span></div></div>
          <div><span class="dk">Age</span><div class="dv">{esc(age_str(t))}</div></div>
          {in_out_cells(t)}
          <div><span class="dk">Events ≤30d</span><div class="dv">{_ev_drawer}</div></div>
          <div><span class="dk">Stock BE</span><div class="dv">Projected underlying for entry BE: <strong>{esc(fmt_px(be, 2) if be is not None else "—")}</strong>
            {" · live " + esc(fmt_px(und, 2)) + (f" ({be_gap:+.2f} vs BE)" if be_gap is not None else "") if und is not None else ""}</div></div>
          <div class="drawer-triggers"><span class="dk">Triggers</span><div class="dv">{trigger_chips(t)}</div></div>
        </div>
      </td>"""
    return f"""
    <tr class="ticker-row main-row {'stale-row' if stale else ''}" data-id="{drawer_id}">
      <td><strong>{esc(agent_label(t))}</strong></td>
      {ticker_html}
      <td class="contract">{esc(t.get('contract',''))}</td>
      {cost_qty_cells(t)}
      <td class="num mark">{esc(fmt_px(mark))}</td>
      <td class="num {pnl_class(pnl_u)}">{esc(fmt_usd(pnl_u))}</td>
      <td class="num {pnl_class(pnl_p)}">{esc(fmt_pct(pnl_p))}</td>
      {be_html}
      <td>{esc(t.get('status','open'))} {stale_badge} {event_chip_html(t)}</td>
      <td class="details-cell"><button type="button" class="drawer-btn" aria-expanded="false">Details ▾</button></td>
    </tr>
    <tr class="drawer-row" hidden>
      {detail}
    </tr>"""



# Open ticker rows — Rose and Hal sections (do not mix into BOOK_TP)
rose_rows = [open_seat_row(t) for t in _sort_pnl(rose_open)]
hal_rows = [open_seat_row(t) for t in _sort_pnl(hal_open)]
rose_tbody = "\n".join(rose_rows) if rose_rows else '<tr><td colspan="9" class="empty">No open Rose / OID seats.</td></tr>'
hal_tbody = "\n".join(hal_rows) if hal_rows else '<tr><td colspan="9" class="empty">No open Hal / OT2 seats.</td></tr>'
rose_agg = agg_section(rose_open)
hal_agg = agg_section(hal_open)

# Day / week book P&L (from meta / book-state; refreshed with option prior closes)
_bs_path = pt / "book-state.json"
_book_state = {}
if _bs_path.exists():
    try:
        _book_state = json.loads(_bs_path.read_text())
    except json.JSONDecodeError:
        _book_state = {}
_meta = ledger.get("meta") or {}

def _period_from(agent_key: str, meta_prefix: str):
    b = (_book_state.get(agent_key) or {})
    return {
        "dayUsd": _f(b.get("dayPnlUsd")) if b.get("dayPnlUsd") is not None else _f(_meta.get(f"{meta_prefix}DayPnlUsd")),
        "dayPct": _f(b.get("dayPnlPct")) if b.get("dayPnlPct") is not None else _f(_meta.get(f"{meta_prefix}DayPnlPct")),
        "weekUsd": _f(b.get("weekPnlUsd")) if b.get("weekPnlUsd") is not None else _f(_meta.get(f"{meta_prefix}WeekPnlUsd")),
        "weekPct": _f(b.get("weekPnlPct")) if b.get("weekPnlPct") is not None else _f(_meta.get(f"{meta_prefix}WeekPnlPct")),
    }

_rose_period = _period_from("rose", "book")
_hal_period = _period_from("hal", "hal")
_shared_period = _period_from("shared", "shared")

rose_totals_bar = totals_bar_html(rose_agg, "Open (Rose)", day_usd=_rose_period["dayUsd"], day_pct=_rose_period["dayPct"], week_usd=_rose_period["weekUsd"], week_pct=_rose_period["weekPct"])
hal_totals_bar = totals_bar_html(hal_agg, "Open (Hal)", day_usd=_hal_period["dayUsd"], day_pct=_hal_period["dayPct"], week_usd=_hal_period["weekUsd"], week_pct=_hal_period["weekPct"])

# Leopold / ZH watch rows (marks vs bot-print reference cost — NOT paper fills)
leopold_rows = []
for t in sorted(leopold_trades, key=lambda x: (_f(x.get("pnlPct")) is None, -(_f(x.get("pnlPct")) or -9999))):
    cost = entry_cost(t)
    mark = _f(t.get("lastMark"))
    bid = _f(t.get("lastBid"))
    ask = _f(t.get("lastAsk"))
    pnl_u = _f(t.get("pnlUsd")) or _f(t.get("unrealizedPnlUsd"))
    pnl_p = _f(t.get("pnlPct")) or _f(t.get("unrealizedPnlPct"))
    und = _f(t.get("lastUnderlying")) or _f(t.get("underlyingNow")) or _f(t.get("underlying"))
    stale, stale_reason = quote_stale(t)
    ba = f"{fmt_px(bid)} / {fmt_px(ask)}"
    stale_badge = f'<span class="badge stale" title="Quote stale or delayed">{esc(stale_reason)}</span>' if stale else '<span class="badge live">live</span>'
    print_note = esc(t.get("sourceNote") or t.get("fillNote") or "watch ref = Leopold bot print")
    leo_ticker = ticker_cell_html(t)
    leopold_rows.append(
        f"""
    <tr class="ticker-row leopold-row {'stale-row' if stale else ''}">
      <td><strong>{esc(agent_label(t))}</strong></td>
      {leo_ticker}
      <td class="contract">{esc(t.get('contract',''))}<div class="tiny">{print_note}</div></td>
      <td class="num" title="Watch reference (bot print), not paper fill">{esc(fmt_px(cost))}</td>
      <td class="num mark">{esc(fmt_px(mark))}</td>
      <td class="num muted">{esc(ba)}</td>
      <td class="num {pnl_class(pnl_u)}">{esc(fmt_usd(pnl_u))}</td>
      <td class="num {pnl_class(pnl_p)}">{esc(fmt_pct(pnl_p))}</td>
      {mfe_cell(t)}
      {mae_cell(t)}
      <td class="num">{esc(fmt_px(und, 2))} {day_pct_chip(t)}</td>
      <td>{esc(age_str(t))}</td>
      <td>watch {stale_badge} {event_chip_html(t)}</td>
    </tr>"""
    )
leopold_tbody = "\n".join(leopold_rows) if leopold_rows else '<tr><td colspan="13" class="empty">No Leopold / ZH watches.</td></tr>'
leopold_n = len(leopold_trades)
leopold_pnl = sum(trade_pnl_usd(t) or 0.0 for t in leopold_trades)
leopold_agg = agg_section(leopold_trades)
leopold_totals_bar = totals_bar_html(leopold_agg, "Leopold / ZH watch")

# Shay · 2027 PE equity watch (soft; no seats) — spot vs Fri-before-post baseline
shay_syms = list(shay_watch.get("symbols") or [])
_sort_mode = (shay_watch.get("sort") or "sincePostPct").lower()
if _sort_mode == "pe":
    shay_syms = sorted(shay_syms, key=lambda r: (_f(r.get("pe2027")) is None, -(_f(r.get("pe2027")) or -9999)))
else:
    shay_syms = sorted(shay_syms, key=lambda r: (_f(r.get("sincePostPct")) is None, -(_f(r.get("sincePostPct")) or -9999)))

def _shay_pct_cell(v, *, digits=2):
    if v is None:
        return '<td class="num muted">—</td>'
    cls = pnl_class(v)
    return f'<td class="num {cls}">{esc(fmt_pct(v))}</td>'

shay_rows = []
for r in shay_syms:
    sym = esc(r.get("symbol") or "")
    pe = r.get("pe2027")
    pe_s = f"{int(pe)}x" if isinstance(pe, (int, float)) and float(pe) == int(pe) else (f"{pe}x" if pe is not None else "—")
    spot = _f(r.get("last"))
    day = _f(r.get("dayPct"))
    since = _f(r.get("sincePostPct"))
    vs = _f(r.get("vsSpySincePost"))
    sess = (r.get("session") or (ledger.get("meta") or {}).get("marketSession") or "closed")
    sess_lab = r.get("sessionLabel") or str(sess).upper()
    tip = f"baseline {r.get('baselinePrice')} · {r.get('baselineDate') or shay_watch.get('baselineDate')} RTH"
    shay_rows.append(
        f"""
    <tr class="ticker-row shay-row">
      <td><strong>{sym}</strong></td>
      <td class="num" title="2027 forward PE from Shay post (color only)">{esc(pe_s)}</td>
      <td class="num" title="{esc(tip)}">{esc(fmt_px(spot, 2))}</td>
      {_shay_pct_cell(day)}
      {_shay_pct_cell(since)}
      {_shay_pct_cell(vs)}
      <td>{session_badge_html(sess, live=('LIVE' in str(sess_lab).upper()))}</td>
    </tr>"""
    )
shay_tbody = "\n".join(shay_rows) if shay_rows else '<tr><td colspan="7" class="empty">No Shay semi watches.</td></tr>'
shay_n = len(shay_syms)
_shay_since = [_f(r.get("sincePostPct")) for r in shay_syms]
_shay_since_v = sorted([x for x in _shay_since if x is not None])
shay_med = None
if _shay_since_v:
    mid = len(_shay_since_v) // 2
    if len(_shay_since_v) % 2:
        shay_med = _shay_since_v[mid]
    else:
        shay_med = round((_shay_since_v[mid - 1] + _shay_since_v[mid]) / 2.0, 4)
shay_win = sum(1 for x in _shay_since if x is not None and x > 0)
shay_lose = sum(1 for x in _shay_since if x is not None and x < 0)
shay_flat = sum(1 for x in _shay_since if x is not None and x == 0)
_spy_since = _f(shay_watch.get("spySincePostPct"))
shay_base_note = esc(
    shay_watch.get("baselineLabel")
    or "Fri RTH close before weekend post"
)
shay_post = esc(shay_watch.get("postUrl") or "")
shay_totals_bar = (
    f'<div class="totals-bar shay-totals">'
    f'<span><strong>Shay · 2027 PE watch</strong> · n={shay_n}</span>'
    f'<span>median since-post <strong class="{pnl_class(shay_med)}">{esc(fmt_pct(shay_med) if shay_med is not None else "—")}</strong></span>'
    f'<span>winners <strong class="pos">{shay_win}</strong> · losers <strong class="neg">{shay_lose}</strong> · flat {shay_flat}</span>'
    f'<span>SPY since-post <strong class="{pnl_class(_spy_since)}">{esc(fmt_pct(_spy_since) if _spy_since is not None else "—")}</strong></span>'
    f'</div>'
)


# Shay · key levels (MA) soft watch — Spot · Trend · EMAs/SMAs + %Var
shay_ma_syms = list(shay_ma_watch.get("symbols") or [])
_trend_rank = {"Bullish": 0, "Hold": 1, "Bearish": 2}
shay_ma_syms = sorted(
    shay_ma_syms,
    key=lambda r: (_trend_rank.get(str(r.get("totalTrend") or ""), 9), str(r.get("symbol") or "")),
)

def _shay_ma_pct_cell(v, *, digits=2):
    if v is None:
        return '<td class="num muted">—</td>'
    cls = pnl_class(v)
    return f'<td class="num {cls}">{esc(fmt_pct(v))}</td>'

def _shay_ma_level_cell(level, var):
    if level is None:
        return '<td class="num muted">—</td>'
    tip = f"%Var {var:+.2f}%" if var is not None else ""
    return f'<td class="num" title="{esc(tip)}">{esc(fmt_px(level, 2))}</td>'

def _trend_chip(trend: str) -> str:
    t = (trend or "Hold").strip()
    cls = {"Bullish": "trend-bull", "Bearish": "trend-bear", "Hold": "trend-hold"}.get(t, "trend-hold")
    return f'<span class="trend-chip {cls}">{esc(t)}</span>'

shay_ma_rows = []
for r in shay_ma_syms:
    sym = esc(r.get("symbol") or "")
    spot = _f(r.get("last"))
    trend = str(r.get("totalTrend") or "Hold")
    shay_b = r.get("shayBucket")
    tip_extra = ""
    if shay_b and str(shay_b) != trend:
        tip_extra = f' <span class="tiny" title="Shay tweet bucket">Shay:{esc(str(shay_b))}</span>'
    shay_ma_rows.append(
        f"""
    <tr class="ticker-row shay-ma-row">
      <td><strong>{sym}</strong></td>
      <td class="num">{esc(fmt_px(spot, 2))}</td>
      <td>{_trend_chip(trend)}{tip_extra}</td>
      {_shay_ma_level_cell(_f(r.get("ema9")), _f(r.get("ema9VarPct")))}
      {_shay_ma_pct_cell(_f(r.get("ema9VarPct")))}
      {_shay_ma_level_cell(_f(r.get("ema21")), _f(r.get("ema21VarPct")))}
      {_shay_ma_pct_cell(_f(r.get("ema21VarPct")))}
      {_shay_ma_level_cell(_f(r.get("sma50")), _f(r.get("sma50VarPct")))}
      {_shay_ma_pct_cell(_f(r.get("sma50VarPct")))}
      {_shay_ma_level_cell(_f(r.get("sma200")), _f(r.get("sma200VarPct")))}
      {_shay_ma_pct_cell(_f(r.get("sma200VarPct")))}
    </tr>"""
    )
shay_ma_tbody = "\n".join(shay_ma_rows) if shay_ma_rows else '<tr><td colspan="11" class="empty">No Shay MA key-level watches.</td></tr>'
shay_ma_n = len(shay_ma_syms)
_sum = shay_ma_watch.get("summary") or {}
shay_ma_bull = int(_sum.get("bullish") or sum(1 for r in shay_ma_syms if r.get("totalTrend") == "Bullish"))
shay_ma_hold = int(_sum.get("hold") or sum(1 for r in shay_ma_syms if r.get("totalTrend") == "Hold"))
shay_ma_bear = int(_sum.get("bearish") or sum(1 for r in shay_ma_syms if r.get("totalTrend") == "Bearish"))
shay_ma_post = esc(shay_ma_watch.get("postUrl") or "")
shay_ma_upd = esc(shay_ma_watch.get("updatedAtPT") or "")
shay_ma_totals_bar = (
    f'<div class="totals-bar shay-ma-totals">'
    f'<span><strong>Shay · key levels (MA)</strong> · n={shay_ma_n}</span>'
    f'<span>Bullish <strong class="pos">{shay_ma_bull}</strong> · Hold <strong style="color:var(--warn)">{shay_ma_hold}</strong> · Bearish <strong class="neg">{shay_ma_bear}</strong></span>'
    f'<span class="tiny">updated {shay_ma_upd}</span>'
    f'</div>'
)

# Soft watches blotter section (color only — softOnly / no seats)
def _soft_type_label(w: dict) -> str:
    return str(w.get("type") or "soft_watch").replace("_", " ")

def _soft_event_timing(w: dict) -> str:
    parts = []
    ed = w.get("eventDate")
    timing = w.get("timing")
    if ed and timing:
        parts.append(f"{ed} {timing}")
    elif ed:
        parts.append(str(ed))
    elif timing:
        parts.append(str(timing))
    ev = w.get("event")
    if ev:
        parts.append(str(ev))
    period = w.get("period")
    if period:
        parts.append(str(period))
    return " · ".join(parts) if parts else "—"

def _soft_levels(w: dict) -> str:
    bits = []
    if w.get("faCallWall") is not None:
        bits.append(f"call {w.get('faCallWall')}")
    if w.get("faPutWall") is not None:
        bits.append(f"put {w.get('faPutWall')}")
    if w.get("faFlip") is not None:
        bits.append(f"flip {w.get('faFlip')}")
    if w.get("faNote"):
        bits.append(str(w.get("faNote")))
    return " · ".join(bits) if bits else "—"

def _soft_claims_html(w: dict) -> str:
    claims = w.get("claims") or []
    if not claims:
        return "—"
    links = []
    for c in claims:
        c = str(c)
        if c.startswith("http"):
            links.append(f'<a href="{esc(c)}" target="_blank" rel="noopener">claim</a>')
        else:
            short = c.split("/")[-1] if "/" in c else c
            links.append(f'<span class="tiny" title="{esc(c)}">{esc(short)}</span>')
    return " · ".join(links)

soft_rows = []
for w in sorted(soft_watches, key=lambda x: (str(x.get("symbol") or ""), str(x.get("id") or ""))):
    sym = esc(w.get("symbol") or "—")
    typ = esc(_soft_type_label(w))
    event = esc(_soft_event_timing(w))
    levels = esc(_soft_levels(w))
    base = _f(w.get("baselineFriClose")) or _f(w.get("baselinePrice"))
    last = _f(w.get("last"))
    day = _f(w.get("dayPct"))
    base_s = fmt_px(base, 2) if base is not None else "—"
    mark_bits = [f"Fri {base_s}"]
    if last is not None:
        mark_bits.append(f"last {fmt_px(last, 2)}")
    if day is not None:
        mark_bits.append(f"day {fmt_pct(day)}")
    baseline_cell = esc(" · ".join(mark_bits))
    st = esc(w.get("status") or "pinned")
    soft_note = "softOnly · research/color — never elevate"
    if w.get("noElevateIntoPrint") or w.get("noElevateOnOeAlone"):
        soft_note += " · noElevate"
    notes = esc((w.get("note") or w.get("notes") or "")[:220])
    claims = _soft_claims_html(w)
    soft_rows.append(
        f"""
    <tr class="ticker-row soft-row">
      <td><strong>{sym}</strong></td>
      <td>{typ}</td>
      <td class="contract">{event}</td>
      <td class="contract">{levels}</td>
      <td class="num">{baseline_cell}</td>
      <td>{st} <span class="badge soft">soft</span></td>
      <td class="tiny">{esc(soft_note)}</td>
      <td class="tiny">{notes}</td>
      <td>{claims}</td>
    </tr>"""
    )
soft_tbody = "\n".join(soft_rows) if soft_rows else '<tr><td colspan="9" class="empty">No soft watches pinned.</td></tr>'
soft_n = len(soft_watches)
soft_totals_bar = (
    f'<div class="totals-bar soft-totals">'
    f'<span><strong>Soft watches</strong> · n={soft_n}</span>'
    f'<span>research / color only — does not consume seats</span>'
    f'<span>never elevate into print</span>'
    f'</div>'
)


closed_rows = []
for t in closed_trades:
    cost = entry_cost(t)
    mark = _f(t.get("lastMark")) or _f(t.get("exitPremium")) or _f(t.get("exitPrice"))
    pnl_u = _f(t.get("pnlUsd"))
    pnl_p = _f(t.get("pnlPct"))
    closed_rows.append(
        f"""
    <tr>
      <td><strong>{esc(agent_label(t))}</strong></td>
      <td>{esc(t.get('symbol',''))}</td>
      <td class="contract">{esc(t.get('contract',''))}</td>
      {rationale_cell(t)}
      <td class="tiny-time">{esc(trade_in_out(t)[0])}</td>
      <td class="tiny-time">{esc(trade_in_out(t)[1])}</td>
      {cost_qty_cells(t)}
      <td class="num">{esc(fmt_px(mark))}</td>
      <td class="num {pnl_class(pnl_u)}">{esc(fmt_usd(pnl_u))}</td>
      <td class="num {pnl_class(pnl_p)}">{esc(fmt_pct(pnl_p))}</td>
      {mfe_cell(t)}
      {mae_cell(t)}
      <td>{esc(t.get('status',''))}</td>
      <td><code>{esc(t.get('outcomeTag') or '—')}</code></td>
    </tr>"""
    )
closed_tbody = "\n".join(closed_rows) if closed_rows else '<tr><td colspan="16" class="empty">No closed tickets yet.</td></tr>'
closed_agg = agg_section(closed_trades)
closed_totals_bar = totals_bar_html(closed_agg, "Closed (all)")

# Lessons (compact)
lesson_blocks = []
for L in (scorecard.get("lessons") or [])[-4:]:
    lesson_blocks.append(
        f"<div class='lesson'><div class='lid'>{esc(L.get('id',''))} · "
        f"<code>{esc(L.get('outcomeTag',''))}</code></div>"
        f"<div>{esc(L.get('lesson',''))}</div></div>"
    )
lessons_html = "\n".join(lesson_blocks) if lesson_blocks else '<div class="empty">No lessons yet.</div>'

s = scorecard.get("summary") or {}
wr = s.get("closedWinRatePct")
wr_s = f"{wr}%" if wr is not None else "—"
exp = s.get("expectancyUsdPerTicket")
exp_s = f"${exp}" if exp is not None else "—"

book_pnl_cls = pnl_class(book_pnl)
book_pct_s = fmt_pct(book_pct) if book_pct is not None else "—"
stale_banner = (
    '<div class="warn">⚠ One or more open quotes are delayed or &gt;2 min old — treat marks as stale until next refresh.</div>'
    if stale_any
    else ""
)



def book_flag_chips(flags, alert) -> str:
    chips = []
    tp = "BOOK_TP" in (flags or [])
    gb = "BOOK_GIVEBACK" in (flags or [])
    chips.append(f'<span class="tchip {"hit" if tp else "off"}">BOOK_TP</span>')
    chips.append(f'<span class="tchip {"warn" if gb else "off"}">BOOK_GIVEBACK</span>')
    if alert:
        chips.append(f'<span class="tchip alert">{esc(alert)}</span>')
    return " ".join(chips)

# --- Close triggers panel ---
ct_by_id = {s.get("id"): s for s in (close_triggers.get("seats") or []) if s.get("id")}
ct_rows = []
for t in sorted(open_trades, key=lambda x: (_f(x.get("pnlPct")) is None, -(_f(x.get("pnlPct")) or -9999))):
    s = ct_by_id.get(t.get("id"), {})
    flags = t.get("closeTriggerFlags") or s.get("flags") or []
    alert = t.get("closeTriggerAlert") or s.get("alert") or "—"
    note = t.get("closeTriggerNote") or s.get("note") or ""
    dte = s.get("state", {}).get("dte") if isinstance(s.get("state"), dict) else t.get("dte")
    mfe = _f(t.get("mfePct"))
    ct_rows.append(
        f"""
    <tr>
      <td><strong>{esc(agent_label(t))}</strong></td>
      <td class="sym"><strong>{esc(t.get('symbol',''))}</strong></td>
      <td class="contract">{esc(t.get('contract',''))}</td>
      <td class="num">{esc(fmt_pct(mfe))}</td>
      <td class="num">{esc("" if dte is None else str(dte))}</td>
      <td class="triggers">{trigger_chips(t)}</td>
      <td><code>{esc(alert)}</code></td>
      <td class="tiny">{esc(note[:160] + ("…" if len(note) > 160 else ""))}</td>
    </tr>"""
    )
ct_tbody = "\n".join(ct_rows) if ct_rows else '<tr><td colspan="8" class="empty">No open seats to score.</td></tr>'
ct_scored = close_triggers.get("scoredAtPT") or "—"
ct_reviews = close_triggers.get("reviewCount")
if ct_reviews is None:
    ct_reviews = sum(1 for t in open_trades if t.get("closeTriggerAlert") in ("CLOSE_TRIGGER_REVIEW", "FORCE_REVIEW", "INVALIDATE"))

close_triggers_panel = f"""
<h2>Close triggers · soft alerts (zero execution)</h2>
<div class="ct-panel">
  <div class="zero">⚠ Paper alerts only · Never place RH orders · Chat approval ≠ ticket · Do not auto-close</div>
  <div class="rules">
    <strong>Hard:</strong> thesis fail (named flip/put break) → <code>INVALIDATE</code> alert.<br/>
    <strong>Soft:</strong> theta tax (long θ$/day bleed ≥ max($10, 1.5% premium) while P&amp;L &lt; +25%) → <code>CLOSE_TRIGGER_REVIEW</code> / θ tax chip.
    <strong>Arm:</strong> mfePct ≥ +50% → Armed.
    <strong>Soft giveback:</strong> armed AND (mark ≤ 50% of peak OR still-green half-MFE giveback) → <code>CLOSE_TRIGGER_REVIEW</code>.
    <strong>Soft time:</strong> DTE ≤ 1 or morning-of-expiry 0DTE → <code>FORCE_REVIEW</code>.
    <strong>Book (Rose/OID):</strong> unrealized ≥ +$1k OR ≥ +30% premium → <code>BOOK_CLOSE_REVIEW</code>; giveback ≥50% of book peak → <code>BOOK_GIVEBACK</code> (soft; never auto-close).<br/>
    Docs: <code>CLOSE-TRIGGERS-V1.md</code> · scored {esc(ct_scored)} · review alerts: <strong>{ct_reviews}</strong>
  </div>
  <div class="table-wrap"><table>
  <thead><tr>
    <th>Agent</th><th>Symbol</th><th>Contract</th><th class="num">MFE %</th><th class="num">DTE</th>
    <th>State</th><th>Alert</th><th>Note</th>
  </tr></thead>
  <tbody>
  {ct_tbody}
  </tbody></table></div>
</div>
"""


# Hal open section HTML (always show — empty state when 0 seats, same as Rose)
hal_open_section = f"""
<h2>Open (Hal) · live marks vs cost basis</h2>
{hal_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Agent</th><th>Ticker</th><th>Contract</th><th class="num">Cost</th><th class="num">Qty</th><th class="num">Total $</th><th class="num">Mark</th>
  <th class="num">P&amp;L $</th><th class="num">P&amp;L %</th>
  <th class="num">Stock BE</th><th>Status</th><th></th>
</tr></thead>
<tbody>
{hal_tbody}
</tbody></table></div>
"""


# Session badge (America/New_York calendar)
_meta = ledger.get("meta") or {}
market_sess = (_meta.get("marketSession") or "closed")
header_session_badge = session_badge_html(market_sess, live=str(market_sess).lower() in ("pre","ah"))

# Market overview strip (indices + Fidelity-3)
try:
    from market_overview import (
        render_macro_banner,
        render_market_detail,
        STRIP_CSS as MARKET_STRIP_CSS,
    )
    macro_banner_html = render_macro_banner(session_badge_html=session_badge_html, ledger=ledger)
    market_detail_html = render_market_detail(session_badge_html=session_badge_html, ledger=ledger)
except Exception as _mkt_e:
    MARKET_STRIP_CSS = ""
    macro_banner_html = (
        '<div class="macro-banner empty-banner"><div class="mb-meta muted">Macro banner unavailable</div></div>'
    )
    market_detail_html = ""
    print("market_overview failed:", _mkt_e)

# Peanut (News Alerts) fixed bottom marquee
try:
    from peanut_news import (
        render_banner_html as render_peanut_banner,
        render_banner_js as render_peanut_banner_js,
    )
    peanut_banner_html, PEANUT_BANNER_CSS = render_peanut_banner()
    PEANUT_BANNER_JS = render_peanut_banner_js()
except Exception as _pn_e:
    PEANUT_BANNER_CSS = ""
    PEANUT_BANNER_JS = ""
    peanut_banner_html = ""
    print("peanut_news failed:", _pn_e)

tab_nav_blotter = '<div class="tabs"><a class="active" href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
tab_nav_sources = '<div class="tabs"><a href="index.html">Blotter</a><a class="active" href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
tab_nav_intel = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a class="active" href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
tab_nav_events = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a class="active" href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
tab_nav_grader = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a class="active" href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
tab_nav_news = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a class="active" href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'

page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="60"/>
<title>OID Live Book · Rose + Hal</title>
<style>
:root{{
  --bg:#070b10; --panel:#0e141c; --panel2:#121a24; --line:#1a2533;
  --text:#e8eef7; --muted:#7f91a8; --accent:#4da3ff;
  --good:#3dd68c; --bad:#ff6b7a; --warn:#f0b429; --flat:#9aa8b8;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,sans-serif;background:
  radial-gradient(900px 420px at 8% -8%,#142033 0%,transparent 55%),
  radial-gradient(700px 380px at 100% 0%,#1a1528 0%,transparent 50%),
  var(--bg);color:var(--text);min-height:100vh}}
.wrap{{max-width:1340px;margin:0 auto;padding:14px 16px 48px}}
.top{{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:10px;margin-bottom:10px}}
h1{{font-size:1.45rem;margin:0;letter-spacing:.02em}}
h1 .pulse{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--good);margin-right:8px;box-shadow:0 0 10px var(--good);animation:blink 1.6s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.sub{{color:var(--muted);font-size:.88rem;margin-top:4px}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:0 0 10px}}
.card{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:10px;padding:8px 11px}}
.card .k{{color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.07em}}
.card .v{{font-size:1.12rem;font-weight:700;margin-top:2px;font-variant-numeric:tabular-nums}}
.card .v.pos,.pos{{color:var(--good)}}
.card .v.neg,.neg{{color:var(--bad)}}
.card .v.flat,.flat{{color:var(--flat)}}
.warn{{background:#2a1f0a;border:1px solid #5c4414;color:#f0c96a;border-radius:10px;padding:8px 10px;margin-bottom:8px;font-size:.84rem}}
h2{{font-size:.78rem;margin:14px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:650}}
.table-wrap{{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel)}}
table{{width:100%;border-collapse:collapse;min-width:720px}}
th,td{{padding:9px 11px;text-align:left;font-size:.84rem;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{color:var(--muted);font-weight:600;font-size:.68rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}}
td.num,.num{{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}}
td.sym{{letter-spacing:.04em}}
td.contract{{color:var(--muted);font-size:.8rem;max-width:220px}}
td.muted{{color:var(--muted)}}
td.mark{{font-weight:650}}
.ticker-row:hover{{background:#141c28}}
.stale-row{{opacity:.85}}
.badge{{display:inline-block;font-size:.65rem;padding:2px 6px;border-radius:999px;margin-left:4px;vertical-align:middle;text-transform:uppercase;letter-spacing:.04em}}
.badge.live{{background:#123526;color:var(--good);border:1px solid #1e5c40}}
.badge.stale{{background:#3a2a10;color:var(--warn);border:1px solid #6a4e18}}
.leopold-row{{background:rgba(88,70,160,.08)}}
.shay-row{{background:rgba(40,110,90,.08)}}
.shay-totals{{border-color:#2a5a48}}
.shay-ma-row{{background:rgba(40,90,120,.08)}}
.shay-ma-totals{{border-color:#2a4a5a}}
.trend-chip{{display:inline-block;font-size:.68rem;padding:2px 8px;border-radius:999px;font-weight:650;letter-spacing:.02em}}
.trend-bull{{background:#123526;color:var(--good);border:1px solid #1e5c40}}
.trend-hold{{background:#3a2a10;color:var(--warn);border:1px solid #6a4e18}}
.trend-bear{{background:#3a1518;color:var(--bad);border:1px solid #6a2830}}
.soft-row{{background:rgba(160,110,40,.10)}}
.soft-totals{{border-color:#6a4e18}}
.note-chip.soft-note{{color:#f0c96a;background:#2a1f0a;border-color:#5c4414}}
.badge.soft{{background:#2a1f0a;color:#f0c96a;border:1px solid #6a4e18}}
.tiny{{font-size:.68rem;color:var(--muted);margin-top:2px;line-height:1.25;max-width:280px}}
.note-chip{{display:inline-block;font-size:.72rem;color:#c4b5fd;background:#1a1430;border:1px solid #3b2f66;border-radius:6px;padding:3px 8px;margin:0 0 6px}}
.empty{{color:var(--muted);text-align:center;padding:22px 12px!important}}
.lessons{{display:grid;gap:8px;margin-top:8px}}
.lesson{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:.86rem;line-height:1.4}}
.lesson .lid{{color:var(--muted);font-size:.72rem;margin-bottom:3px}}
footer{{margin-top:20px;color:var(--muted);font-size:.8rem;line-height:1.45}}
code{{font-size:.8em;background:#0a1018;padding:1px 5px;border-radius:4px}}
@media(max-width:980px){{.stats{{grid-template-columns:1fr 1fr 1fr}}}}
@media(max-width:640px){{.stats{{grid-template-columns:1fr 1fr}}}}

td.rationale{{width:132px;max-width:132px;vertical-align:middle;position:relative}}
.rat{{position:relative}}
.rat > summary{{list-style:none;cursor:pointer;display:flex;align-items:center;gap:4px;color:var(--muted);font-size:.72rem;line-height:1.2}}
.rat > summary::-webkit-details-marker{{display:none}}
.rat > summary::after{{content:"▾";font-size:.65rem;opacity:.7;flex:0 0 auto}}
.rat[open] > summary::after{{content:"▴"}}
.rat-preview{{display:block;max-width:108px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.rat-pop{{position:absolute;z-index:40;left:0;top:calc(100% + 4px);min-width:280px;max-width:min(420px,70vw);padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#121a24;color:var(--text);font-size:.78rem;line-height:1.4;box-shadow:0 12px 28px rgba(0,0,0,.45);white-space:normal}}
td.greeks{{width:118px;max-width:118px;vertical-align:middle;position:relative}}
td.be{{width:72px;max-width:72px;font-variant-numeric:tabular-nums}}.gk{{position:relative}}.gk > summary{{list-style:none;cursor:pointer;color:var(--muted);font-size:.72rem;line-height:1.2}}.gk > summary::-webkit-details-marker{{display:none}}.gk > summary::after{{content:"▾";font-size:.65rem;opacity:.7;margin-left:3px}}.gk[open] > summary::after{{content:"▴"}}.gk-preview{{display:inline}}.gk-pop{{position:absolute;z-index:40;left:0;top:calc(100% + 4px);min-width:260px;max-width:min(400px,70vw);padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#121a24;color:var(--text);font-size:.78rem;line-height:1.4;box-shadow:0 12px 28px rgba(0,0,0,.45);white-space:normal}}

.ticker-live .tl-sym{{font-weight:700;letter-spacing:.04em}}
.ticker-live .tl-px{{font-family:var(--mono);font-size:.78rem;color:var(--text);margin-top:2px}}
.be-px{{font-weight:650}}
.be-gap{{font-size:.68rem;margin-top:1px}}
.drawer-btn{{background:#152030;border:1px solid var(--line);color:var(--accent);border-radius:8px;padding:4px 10px;font-size:.72rem;cursor:pointer}}
.drawer-btn[aria-expanded="true"]{{background:#1a2a40}}
.drawer-row td{{background:#0a1018;padding:0}}
.drawer-td{{padding:12px 14px!important}}
.drawer-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px 16px}}
.drawer-grid .dk{{display:block;font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px}}
.drawer-grid .dv{{font-size:.82rem;line-height:1.4;color:var(--text)}}
.drawer-triggers{{grid-column:1/-1}}
.main-row.open-drawer{{background:#141c28}}

.tchips{{display:flex;flex-wrap:wrap;gap:4px;max-width:280px}}
.tchip{{font-size:.62rem;padding:2px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:#0a1018;text-transform:uppercase;letter-spacing:.03em}}
.tchip.on{{color:#c4b5fd;border-color:#5b4a9a;background:#1a1430}}
.tchip.hit{{color:#ffb4a2;border-color:#8a4030;background:#2a1510}}
.tchip.warn{{color:var(--warn);border-color:#6a4e18;background:#2a1f0a}}
.tchip.ok{{color:var(--good);border-color:#1e5c40;background:#123526}}
.tchip.bad{{color:var(--bad);border-color:#7a3038;background:#2a1216}}
.tchip.alert{{color:#fff;border-color:#4da3ff;background:#14304a;font-weight:650}}
.tchip.off{{opacity:.45}}
.ct-panel{{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:10px 12px;margin:4px 0 12px}}
.ct-panel .rules{{color:var(--muted);font-size:.82rem;line-height:1.45;margin:0 0 12px}}
.ct-panel .rules strong{{color:var(--text)}}
.ct-panel .zero{{color:var(--warn);font-size:.78rem;margin-bottom:10px}}

.totals-bar{{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 6px;padding:7px 12px;border:1px solid var(--line);border-radius:10px;background:linear-gradient(180deg,#121a24,#0e141c);font-size:.84rem;font-variant-numeric:tabular-nums;color:var(--text)}}
.totals-bar .tb-label{{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-size:.72rem;font-weight:650}}
.totals-bar .tb-n{{font-weight:700}}
.totals-bar .tb-pnl,.totals-bar .tb-pct{{font-weight:700}}
.totals-bar .tb-wl{{color:var(--muted)}}
.totals-bar.empty-totals{{color:var(--muted)}}
.section-head{{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin:12px 0 6px}}
.section-head h2{{margin:0}}

.sess-badge{{display:inline-block;font-size:.58rem;padding:1px 6px;border-radius:999px;margin-left:6px;vertical-align:middle;letter-spacing:.05em;font-weight:700;border:1px solid var(--line)}}
.sess-badge.sess-rth{{background:#123526;color:var(--good);border-color:#1e5c40}}
.sess-badge.sess-pre{{background:#1a2a40;color:#7db7ff;border-color:#2a4a70}}
.sess-badge.sess-ah{{background:#2a1f40;color:#c4b5fd;border-color:#5b4a9a}}
.sess-badge.sess-closed{{background:#1a1f28;color:var(--muted);border-color:#2a3340}}
.evchip{{display:inline-block;font-size:.58rem;padding:1px 6px;border-radius:999px;margin-left:4px;vertical-align:middle;letter-spacing:.03em;font-weight:700;border:1px solid var(--line)}}
.evchip.earn{{background:#2a1f0a;color:var(--warn);border-color:#6a4e18}}
.evchip.evt{{background:#1a2a40;color:#7db7ff;border-color:#2a4a70}}
.daychip{{display:inline-block;font-size:.68rem;font-family:var(--mono);padding:1px 6px;border-radius:6px;margin-left:6px;font-weight:650;border:1px solid transparent}}
.daychip.pos{{color:var(--good);background:#123526;border-color:#1e5c40}}
.daychip.neg{{color:var(--bad);background:#2a1216;border-color:#7a3038}}
.daychip.flat{{color:var(--flat);background:#121820;border-color:var(--line)}}
.tabs{{display:flex;gap:8px;margin:0 0 10px;flex-wrap:wrap}}
.tabs a{{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}}
.tabs a.active,.tabs a:hover{{color:var(--text);border-color:#2a4a70;background:#152030}}
.header-sess{{display:flex;align-items:center;gap:10px;justify-content:flex-end}}
.refresh-btn{{background:var(--accent);border:1px solid #74b7ff;color:#07111d;border-radius:8px;padding:7px 13px;font-size:.78rem;font-weight:750;cursor:pointer;box-shadow:0 2px 8px rgba(77,163,255,.22)}}
.refresh-btn:hover{{background:#74b7ff}}
.refresh-btn:focus-visible{{outline:2px solid #fff;outline-offset:2px}}
.refresh-cluster{{display:flex;flex-direction:column;align-items:flex-end;gap:2px}}
.tchip.ok{{color:var(--good);border-color:#1e5c40;background:#123526}}
.tchip.warn{{color:var(--warn);border-color:#6a4e18;background:#2a1f0a}}
.tchip.bad{{color:var(--bad);border-color:#7a3038;background:#2a1216}}
.tchip.flat{{color:var(--muted);opacity:.85}}
td.cadence,td.notes{{font-size:.78rem;color:var(--muted);max-width:280px;line-height:1.35}}
.ds-summary{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px}}
.ds-summary .tchip{{font-size:.72rem;padding:4px 10px}}
{MARKET_STRIP_CSS}
{PEANUT_BANNER_CSS}
</style>
</head><body><div class="wrap">
{tab_nav_blotter}
<div class="top">
  <div>
    <h1><span class="pulse" aria-hidden="true"></span>OID Live Book · Rose + Hal</h1>
    <div class="sub">Mandate {esc(ledger.get('mandate','V1.8'))} · Research / paper only · Zero execution · Auto-refresh 60s · Built {esc(now_pt)}</div>
  </div>
  <div class="header-sess">
    {header_session_badge}
    <div class="sub">Marks refresh: <strong style="color:var(--text)">{esc(last_refresh)}</strong></div>
    <div class="refresh-cluster">
      <button class="refresh-btn" type="button" onclick="location.href=location.pathname.split('?')[0]+'?t='+Date.now();" title="Reloads published page · marks auto-refresh on desk cadence (not live from browser)">Reload</button>
      <div class="tiny">Reloads published page · marks auto-refresh on desk cadence (not live from browser)</div>
    </div>
  </div>
</div>
{stale_banner}
{macro_banner_html}
<div class="stats stats-book">
  <div class="card"><div class="k">Open seats</div><div class="v">{open_n}/{max_seats}</div></div>
  <div class="card"><div class="k">Day P&amp;L %</div><div class="v {pnl_class(shared_day_pct)}">{esc(fmt_pct(shared_day_pct) if shared_day_pct is not None else "—")}<div class="tiny">{esc(fmt_usd(shared_day_usd))} · shared</div></div></div>
  <div class="card"><div class="k">Week P&amp;L %</div><div class="v {pnl_class(shared_week_pct)}">{esc(fmt_pct(shared_week_pct) if shared_week_pct is not None else "—")}<div class="tiny">{esc(fmt_usd(shared_week_usd))} · vs entry</div></div></div>
  <div class="card"><div class="k">Total / Shared</div><div class="v {pnl_class(shared_pnl)}">{esc(fmt_usd(shared_pnl))}<div class="tiny">{esc(fmt_pct(shared_pct) if shared_pct is not None else "—")} · Rose+Hal</div></div></div>
  <div class="card"><div class="k">Rose total</div><div class="v {pnl_class(rose_book_pnl)}">{esc(fmt_usd(rose_book_pnl))}<div class="tiny">Day {esc(fmt_pct(rose_day_pct) if rose_day_pct is not None else "—")} · Week {esc(fmt_pct(rose_week_pct) if rose_week_pct is not None else "—")}</div></div></div>
  <div class="card"><div class="k">Rose peak</div><div class="v {pnl_class(rose_peak)}">{esc(fmt_usd(rose_peak))}<div class="tiny">{esc(rose_peak_at or "—")}</div></div></div>
</div>

<h2>Open (Rose) · live marks vs cost basis</h2>
{rose_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Agent</th><th>Ticker</th><th>Contract</th><th class="num">Cost</th><th class="num">Qty</th><th class="num">Total $</th><th class="num">Mark</th>
  <th class="num">P&amp;L $</th><th class="num">P&amp;L %</th>
  <th class="num">Stock BE</th><th>Status</th><th></th>
</tr></thead>
<tbody>
{rose_tbody}
</tbody></table></div>

{hal_open_section}

{close_triggers_panel}

<h2>Soft watches · research / color only</h2>
<div class="note-chip soft-note">Pinned soft watches only — does not consume open seats ({open_n}/{max_seats}). Color for open routines; never elevate on OE/DP/earnings walls alone · zero RH orders.</div>
{soft_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Sym</th><th>Type</th><th>Event / timing</th><th>Key levels</th>
  <th class="num">Baseline / marks</th><th>Status</th><th>Soft</th><th>Notes</th><th>Claims</th>
</tr></thead>
<tbody>
{soft_tbody}
</tbody></table></div>

<h2>Shay · key levels (MA)</h2>
<div class="note-chip">Soft color only — MAs never elevate alone; elevate stays with Q5/opening + walls. Sourced from <a href="{shay_ma_post}" target="_blank" rel="noopener">@StockSavvyShay</a> key-levels framing; levels recomputed from RH day bars. Research/paper · zero RH orders.</div>
{shay_ma_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Sym</th><th class="num">Spot</th><th>Trend</th>
  <th class="num">9 EMA</th><th class="num">%vs9</th>
  <th class="num">21 EMA</th><th class="num">%vs21</th>
  <th class="num">50 SMA</th><th class="num">%vs50</th>
  <th class="num">200 SMA</th><th class="num">%vs200</th>
</tr></thead>
<tbody>
{shay_ma_tbody}
</tbody></table></div>

<h2>Shay · 2027 PE watch · equity vs Fri baseline</h2>
<div class="note-chip">Soft equity watch only — does not consume open seats ({open_n}/{max_seats}). Baseline = {shay_base_note}. since-post% = (spot−baseline)/baseline · vs SPY = since-post − SPY since-post. PE from <a href="{shay_post}" target="_blank" rel="noopener">@StockSavvyShay</a> for color only · zero RH orders.</div>
{shay_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Sym</th><th class="num">2027 PE</th><th class="num">Spot</th>
  <th class="num">Day%</th><th class="num">Since post%</th><th class="num">vs SPY</th><th>Status</th>
</tr></thead>
<tbody>
{shay_tbody}
</tbody></table></div>

<h2>Leopold / ZH watch · marks vs bot-print reference</h2>
<div class="note-chip">External watch only — does not consume open seats ({open_n}/{max_seats}). Cost = Leopold bot print (not OID paper fill). Source: ZH status 2100677841612378464.</div>
{leopold_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Agent</th><th>Symbol</th><th>Contract</th><th class="num">Ref cost</th><th class="num">Mark</th>
  <th class="num">Bid / Ask</th><th class="num">P&amp;L $</th><th class="num">P&amp;L %</th>
  <th class="num">MFE · time</th><th class="num">MAE · time</th>
  <th class="num">Underlying</th><th>Age</th><th>Status</th>
</tr></thead>
<tbody>
{leopold_tbody}
</tbody></table></div>

<h2>Recently closed / invalidated</h2>
{closed_totals_bar}
<div class="table-wrap"><table>
<thead><tr>
  <th>Agent</th><th>Symbol</th><th>Contract</th><th>Why</th><th>In</th><th>Out</th><th class="num">Cost</th><th class="num">Qty</th><th class="num">Total $</th><th class="num">Exit/Mark</th>
  <th class="num">P&amp;L $</th><th class="num">P&amp;L %</th><th class="num">MFE · time</th><th class="num">MAE · time</th><th>Status</th><th>Tag</th>
</tr></thead>
<tbody>
{closed_tbody}
</tbody></table></div>

{market_detail_html}

<h2>Lessons (scorecard)</h2>
<div class="lessons">{lessons_html}</div>

<footer>
{esc(ledger.get('disclaimer') or 'Research / paper tracking only. Zero live execution from OID.')}
 <strong>Stock BE</strong> = projected <em>underlying</em> price for entry breakeven (long call: strike+debit; long put: strike−debit) — not option premium. Seats with a watchlist event in ≤30d show <code>Earn Nd</code> / <code>Evt Nd</code> chips (Events tab). Detail drawer holds <strong>In</strong> (entry/offer time) / <strong>Out</strong> (exit/close time) · Greeks / Why / triggers / MFE. Greeks = Δ · θ$/day (click ▾ for γ/IV); soft <code>THETA_TAX</code> when long-premium bleed is large vs a weak P&amp;L. Why = ticket <code>rationale</code> (click ▾ to expand; Rose + Hal fill on elevate). Ticker session labels: <strong>RTH</strong> = normal hours; <strong>PRE-MARKET</strong> / <strong>AFTER-HOURS</strong> = live extended print when available (not RTH); <strong>CLOSED</strong> shows last RTH + last AH print. Day P&amp;L = option mark vs prior-session close; Week P&amp;L ≈ vs entry (this week). Shown above Total on each section bar. Cost = per-share entryAsk; <strong>Qty</strong> = contracts; <strong>Total $</strong> = Cost × 100 × Qty (cash debit). Leopold Ref cost = ZH bot print (watch only, not a paper fill). Mark from Robinhood option quotes. Multiplier ×100. Leopold watches do not count toward open seats. Shay · 2027 PE watch = equity soft list (shay-semi-watch.json); baseline Fri RTH before post; since-post% vs that close; optional vs SPY; does not consume seats. Shay · key levels (MA) = soft MA blotter (shay-ma-levels-watch.json); Total Trend from EMA9/21 + SMA50/200; softOnly · never elevate alone. Soft watches = pinned research/color only (mu-earnings-watch / be-oe-watch etc.); softOnly · never elevate · do not consume seats.
 Close triggers: soft seat + Rose-book alerts only (see <code>CLOSE-TRIGGERS-V1.md</code>); never auto-close / never RH. Site: static here.now — browser meta-refresh 60s; server-side marks via <code>dashboard/live_refresh.py</code>. Bottom <strong>Peanut news</strong> marquee = net-new Tech/chip alerts (±1–5) since prior RTH close; full history on <a href="news-archive.html">News Archive</a>.
</footer>
</div>
<script>
// Soft reload if tab stays open; meta refresh covers most cases
setInterval(function(){{ if (!document.hidden) location.href=location.pathname.split('?')[0]+'?t='+Date.now(); }}, 60000);
// Accordion: only one Why popover open at a time
document.addEventListener('toggle', function(e){{
  var d = e.target;
  if (!d.classList || !(d.classList.contains('rat') || d.classList.contains('gk')) || !d.open) return;
  document.querySelectorAll('details.rat[open], details.gk[open]').forEach(function(x){{ if (x !== d) x.open = false; }});
}}, true);
document.addEventListener('click', function(e){{
  var btn = e.target.closest && e.target.closest('.drawer-btn');
  if (btn) {{
    e.preventDefault();
    var main = btn.closest('tr.main-row');
    var drawer = main && main.nextElementSibling;
    if (!drawer || !drawer.classList.contains('drawer-row')) return;
    var open = drawer.hasAttribute('hidden');
    document.querySelectorAll('tr.drawer-row').forEach(function(r){{ r.setAttribute('hidden',''); }});
    document.querySelectorAll('.drawer-btn').forEach(function(b){{ b.setAttribute('aria-expanded','false'); b.textContent = 'Details ▾'; }});
    document.querySelectorAll('tr.main-row').forEach(function(r){{ r.classList.remove('open-drawer'); }});
    if (open) {{
      drawer.removeAttribute('hidden');
      btn.setAttribute('aria-expanded','true');
      btn.textContent = 'Details ▴';
      main.classList.add('open-drawer');
    }}
    return;
  }}
  if (e.target.closest && (e.target.closest('details.rat') || e.target.closest('details.gk'))) return;
  document.querySelectorAll('details.rat[open], details.gk[open]').forEach(function(x){{ x.open = false; }});
}});
</script>
{peanut_banner_html}
<script>
{PEANUT_BANNER_JS}
</script>
</body></html>
"""

(root / "index.html").write_text(page)
(root / "trades.json").write_text(json.dumps(ledger, indent=2))
if shay_watch:
    (root / "shay-semi-watch.json").write_text(json.dumps(shay_watch, indent=2) + "\n")
if shay_ma_watch:
    (root / "shay-ma-levels-watch.json").write_text(json.dumps(shay_ma_watch, indent=2) + "\n")
_pn = root.parent / "paper-trades" / "peanut-news.json"
if _pn.exists():
    (root / "peanut-news.json").write_text(_pn.read_text())
for _sw in soft_watches:
    _src = _sw.get("_sourceFile")
    if _src:
        if _sw.get("_sourceExpanded") and isinstance(_sw.get("_sourcePayload"), dict):
            (root / _src).write_text(json.dumps(_sw["_sourcePayload"], indent=2) + "\n")
            continue
        _out = {k: v for k, v in _sw.items() if k not in {"_sourceFile", "_sourceExpanded", "_sourcePayload"}}
        (root / _src).write_text(json.dumps(_out, indent=2) + "\n")
if scorecard:
    (root / "scorecard.json").write_text(json.dumps(scorecard, indent=2))
print("rebuilt", root / "index.html", f"open={open_n}/{max_seats}", f"leopold={leopold_n}", f"soft={soft_n}", f"shay={shay_n}", f"shay_ma={shay_ma_n}", f"bookPnL={book_pnl:.2f}", f"leopoldPnL={leopold_pnl:.2f}")


# --- Data sources page ---
try:
    from data_sources import collect_rows, rows_html, summary_counts, status_class, quotas_panel_html
except Exception as _e:
    collect_rows = None
    print("data_sources import failed:", _e)

if collect_rows is not None:
    ds_rows = collect_rows(ledger)
    ds_sum = summary_counts(ds_rows)
    ds_tbody = rows_html(ds_rows)
    quota_panel = quotas_panel_html()
    sum_chips = " ".join(
        f'<span class="tchip {status_class(k)}">{k}: {v}</span>'
        for k, v in ds_sum.items() if v
    )
    ds_page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="120"/>
<title>OID · Data sources</title>
<style>
:root{{
  --bg:#070b10; --panel:#0e141c; --panel2:#121a24; --line:#1a2533;
  --text:#e8eef7; --muted:#7f91a8; --accent:#4da3ff;
  --good:#3dd68c; --bad:#ff6b7a; --warn:#f0b429; --flat:#9aa8b8;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,sans-serif;background:
  radial-gradient(900px 420px at 8% -8%,#142033 0%,transparent 55%),
  radial-gradient(700px 380px at 100% 0%,#1a1528 0%,transparent 50%),
  var(--bg);color:var(--text);min-height:100vh}}
.wrap{{max-width:1340px;margin:0 auto;padding:14px 16px 48px}}
h1{{font-size:1.35rem;margin:0 0 6px}}
.sub{{color:var(--muted);font-size:.88rem}}
.tabs{{display:flex;gap:8px;margin:0 0 10px;flex-wrap:wrap}}
.tabs a{{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}}
.tabs a.active,.tabs a:hover{{color:var(--text);border-color:#2a4a70;background:#152030}}
.table-wrap{{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel)}}
table{{width:100%;border-collapse:collapse;min-width:960px}}
th,td{{padding:9px 11px;text-align:left;font-size:.84rem;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:.68rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}}
td.num,.num{{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}}
td.cadence,td.notes{{font-size:.78rem;color:var(--muted);max-width:300px;line-height:1.35}}
code{{font-size:.8em;background:#0a1018;padding:1px 5px;border-radius:4px}}
.tchip{{display:inline-block;font-size:.62rem;padding:2px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:#0a1018;text-transform:uppercase;letter-spacing:.03em}}
.tchip.ok{{color:var(--good);border-color:#1e5c40;background:#123526}}
.tchip.warn{{color:var(--warn);border-color:#6a4e18;background:#2a1f0a}}
.tchip.bad{{color:var(--bad);border-color:#7a3038;background:#2a1216}}
.tchip.flat{{color:var(--muted)}}
.quota-panel{{margin:14px 0 16px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(180deg,#121a24,#0e141c)}}
.quota-head{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:10px}}
.quota-title{{font-size:.78rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.quota-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
@media(max-width:980px){{.quota-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:560px){{.quota-grid{{grid-template-columns:1fr}}}}
.qcard{{padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#0a1018}}
.qk{{font-size:.72rem;color:var(--muted);font-weight:650;margin-bottom:4px}}
.qplan{{font-weight:500;opacity:.85;text-transform:uppercase;font-size:.62rem;margin-left:4px}}
.qv{{font-size:1.05rem;font-weight:700;font-variant-numeric:tabular-nums}}
.qv.ok{{color:var(--good)}}.qv.warn{{color:var(--warn)}}.qv.bad{{color:var(--bad)}}.qv.flat{{color:var(--muted)}}
.qbar{{height:5px;background:#1a2533;border-radius:999px;overflow:hidden;margin:8px 0 4px}}
.qfill{{height:100%;border-radius:999px}}
.qfill.ok{{background:var(--good)}}.qfill.warn{{background:var(--warn)}}.qfill.bad{{background:var(--bad)}}
.qtiny{{font-size:.68rem;color:var(--muted);line-height:1.35;margin-top:2px}}
.quota-panel.empty .quota-miss{{font-size:.84rem}}
.qspend{{display:flex;flex-wrap:wrap;gap:6px 10px;margin-top:8px;font-size:.68rem;color:var(--muted)}}
.qspend b{{color:var(--text);font-weight:700}}
.x-spend-strip{{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font-size:.82rem;font-variant-numeric:tabular-nums}}
.x-spend-strip .xslab{{font-size:.68rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.x-spend-strip b{{color:var(--text)}}

.ds-summary{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 14px}}
.ds-summary .tchip{{font-size:.72rem;padding:4px 10px}}
.header-sess{{margin:8px 0 4px}}
.sess-badge{{display:inline-block;font-size:.65rem;padding:2px 8px;border-radius:999px;letter-spacing:.05em;font-weight:700;border:1px solid var(--line)}}
.sess-badge.sess-rth{{background:#123526;color:var(--good);border-color:#1e5c40}}
.sess-badge.sess-pre{{background:#1a2a40;color:#7db7ff;border-color:#2a4a70}}
.sess-badge.sess-ah{{background:#2a1f40;color:#c4b5fd;border-color:#5b4a9a}}
.sess-badge.sess-closed{{background:#1a1f28;color:var(--muted);border-color:#2a3340}}
footer{{margin-top:20px;color:var(--muted);font-size:.8rem;line-height:1.45}}
</style>
</head><body><div class="wrap">
{tab_nav_sources}
<h1>Data sources · Rose + Hal</h1>
<div class="sub">Live status from <code>market-data/latest/</code> · Cadence from QUERY-DEDUP / HAL-CADENCE-V1 / HAL-X-ALLOWLIST · Built {esc(now_pt)}</div>
<div class="header-sess">{header_session_badge}</div>
{quota_panel}
<div class="ds-summary">{sum_chips}</div>
<div class="table-wrap"><table>
<thead><tr>
  <th>Source</th><th>Feed</th><th>Owner</th><th>Cadence</th>
  <th class="num">TTL</th><th class="num">Last success (PT)</th><th>Status</th><th>Notes</th>
</tr></thead>
<tbody>
{ds_tbody}
</tbody></table></div>
<footer>
Research / paper only · Zero RH execution. Top bar = FlashAlpha daily calls + X credit $ · UW has no meter · RH no $. Status: <strong>OK</strong> within TTL · <strong>STALE</strong> past TTL in RTH · <strong>CARRY</strong> last write held outside RTH (weekend/closed) ·
<strong>ERROR</strong> vendor/error flag · <strong>NEVER</strong> no cache file · <strong>DISABLED</strong> routine off.
See <code>dashboard/DATA-SOURCES.md</code>.
</footer>
</div></body></html>
"""
    (root / "data-sources.html").write_text(ds_page)
    print("wrote", root / "data-sources.html", f"feeds={len(ds_rows)}", ds_sum)

# --- Trader intel page ---
try:
    from trader_intel_page import build_html as build_trader_intel_html, collect as collect_trader_intel
    ti_html = build_trader_intel_html(tab_nav_intel, now_pt=now_pt)
    (root / "trader-intel.html").write_text(ti_html)
    _ti = collect_trader_intel()
    print(
        "wrote", root / "trader-intel.html",
        f"handles={len(_ti['handles'])}",
        f"claims={len(_ti['claims'])}",
        f"lessons={len(_ti['lessons'])}",
    )
except Exception as _ti_e:
    print("trader_intel page failed:", _ti_e)

try:
    from catalysts_page import build_html as build_catalysts_html
    (root / "catalysts.html").write_text(build_catalysts_html(tab_nav_events, now_pt=now_pt))
    print("wrote", root / "catalysts.html")
except Exception as _cat_e:
    print("catalysts page failed:", _cat_e)

try:
    from soft_grader_page import build_html as build_soft_grader_html
    (root / "soft-grader.html").write_text(build_soft_grader_html(tab_nav_grader, now_pt=now_pt))
    print("wrote", root / "soft-grader.html")
except Exception as _sg_e:
    print("soft_grader page failed:", _sg_e)


try:
    from peanut_news import build_news_archive_html, split_banner_archive, fmt_cutoff_pt
    (root / "news-archive.html").write_text(build_news_archive_html(tab_nav_news, now_pt=now_pt))
    _bn, _ar, _pc = split_banner_archive()
    print(
        "wrote", root / "news-archive.html",
        f"banner={len(_bn)}", f"archive={len(_ar)}",
        f"priorClose={fmt_cutoff_pt(_pc)}",
    )
except Exception as _na_e:
    print("news_archive page failed:", _na_e)

try:
    from map_page import build_html as build_map_html
    tab_nav_map = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a class="active" href="map.html">Map</a><a href="chart.html">Chart</a></div>'
    (root / "map.html").write_text(build_map_html(tab_nav_map, now_pt=now_pt))
    print("wrote", root / "map.html")
except Exception as _map_e:
    print("map page failed:", _map_e)

try:
    from chart_page import build_html as build_chart_html
    tab_nav_chart = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="architecture.html">Architecture</a><a href="setup.html">Setup</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a class="active" href="chart.html">Chart</a></div>'
    (root / "chart.html").write_text(build_chart_html(tab_nav_chart, now_pt=now_pt))
    print("wrote", root / "chart.html")
except Exception as _ch_e:
    print("chart page failed:", _ch_e)

try:
    from docs_pages import build_architecture_html, build_setup_html, make_tab_nav
    (root / "architecture.html").write_text(build_architecture_html(make_tab_nav("architecture.html"), now_pt=now_pt))
    print("wrote", root / "architecture.html")
    (root / "setup.html").write_text(build_setup_html(make_tab_nav("setup.html"), now_pt=now_pt))
    print("wrote", root / "setup.html")
except Exception as _doc_e:
    print("docs pages failed:", _doc_e)

