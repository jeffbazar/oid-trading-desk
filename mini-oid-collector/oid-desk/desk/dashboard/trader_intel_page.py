#!/usr/bin/env python3
"""Build trader-intel.html from trader-intel/ KB for OID Live Book.

Claims table mirrors paper blotter columns when a Ticket id joins trades.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
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
TI = ROOT / "trader-intel"
DASH = Path(__file__).resolve().parent
TRADES_PATH = ROOT / "paper-trades" / "trades.json"
RH_QUOTES_PATH = ROOT / "market-data" / "latest" / "rh-quotes.json"

# Ticket id pattern used across OID / OT2 paper books
TICKET_RE = re.compile(r"\b((?:OID|OT2)-PAPER-\d{8}-\d+[A-Z]?)\b", re.I)

# Optional blotter-aligned bullets Hal/Rose may fill on claims without a live ticket
BLOTTER_MD_KEYS = [
    ("contract", r"\*\*Contract:\*\*\s*([^\n]+)"),
    ("cost", r"\*\*Cost(?:/entry)?:\*\*\s*([^\n]+)"),
    ("qty", r"\*\*Qty:\*\*\s*([^\n]+)"),
    ("mark", r"\*\*Mark:\*\*\s*([^\n]+)"),
    ("pnl_usd", r"\*\*P&L\s*\$:\*\*\s*([^\n]+)"),
    ("pnl_pct", r"\*\*P&L\s*%:\*\*\s*([^\n]+)"),
    ("mfe", r"\*\*MFE:\*\*\s*([^\n]+)"),
    ("stock_be", r"\*\*Stock BE:\*\*\s*([^\n]+)"),
    ("status_md", r"\*\*Status:\*\*\s*([^\n]+)"),
    ("in_ts", r"\*\*In:\*\*\s*([^\n]+)"),
    ("out_ts", r"\*\*Out:\*\*\s*([^\n]+)"),
    ("invalidate", r"\*\*Invalidate:\*\*\s*([^\n]+)"),
]


def _esc(s) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _f(v: Any) -> Optional[float]:
    if v is None or v == "" or v == "—":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "").replace("$", "").replace("+", "")
    if not s or s in ("—", "-", "n/a", "N/A", "null", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_px(v: Optional[float], digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def _fmt_usd(v: Optional[float]) -> str:
    if v is None:
        return "—"
    if v > 0:
        return f"+${v:,.2f}"
    if v < 0:
        return f"-${abs(v):,.2f}"
    return "$0.00"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"


def _pnl_class(v: Optional[float]) -> str:
    if v is None:
        return ""
    if v > 0:
        return "pos"
    if v < 0:
        return "neg"
    return "flat"


def _dash(s: Optional[str]) -> str:
    t = (s or "").strip()
    if not t or t in ("—", "-", "n/a", "N/A", "null", "None"):
        return ""
    return t


def _parse_mfe_pnl_line(raw: str) -> dict:
    """Parse 'MFE / P&L / invalidate' free text into optional numeric fields."""
    out: dict = {}
    if not raw or raw.strip() in ("—", "-", ""):
        return out
    text = raw.strip()
    # Named tokens: pnlPct · mfePct · maePct
    for key, pat in [
        ("pnl_pct", r"(?i)pnl(?:Pct|%|)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)\s*%?"),
        ("mfe", r"(?i)mfe(?:Pct|%|)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)\s*%?"),
        ("pnl_usd", r"(?i)pnl\s*\$?\s*[:=]?\s*([+-]?\$?\d+(?:\.\d+)?)"),
    ]:
        m = re.search(pat, text)
        if m and key not in out:
            out[key] = m.group(1)
    # Invalidate / reason after last · or after "invalidate"
    inv = re.search(r"(?i)(?:invalidate|reason)\s*[:=]\s*(.+)$", text)
    if inv:
        out["invalidate"] = inv.group(1).strip()
    elif "·" in text:
        bits = [b.strip() for b in text.split("·")]
        if bits and not re.match(r"^[+-]?\d", bits[-1]):
            out.setdefault("invalidate", bits[-1])
    out["mfe_pnl_raw"] = text
    return out


def _extract_ticket_ids(ticket_field: str) -> list[str]:
    if not ticket_field:
        return []
    return TICKET_RE.findall(ticket_field)


def _parse_claim_md(path: Path) -> dict:
    text = path.read_text()
    out: dict = {"file": path.name, "title": path.stem, "raw": text}
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        out["title"] = m.group(1).strip()

    # Core fields — capture same line only (do not bleed into next bullet)
    for key, pat in [
        ("date", r"\*\*Date \(PT\):\*\*\s*([^\n]*)"),
        ("handle", r"\*\*Handle:\*\*\s*([^\n]*)"),
        ("claim", r"\*\*Claim[^:]*:\*\*\s*([^\n]*)"),
        ("symbols", r"\*\*Symbols:\*\*\s*([^\n]*)"),
        ("action", r"\*\*Action:\*\*\s*([^\n]*)"),
        ("ticket", r"\*\*Ticket id[^:]*:\*\*\s*([^\n]*)"),
        ("outcome", r"\*\*Outcome:\*\*\s*([^\n]*)"),
        ("rule", r"\*\*Rule update:\*\*\s*([^\n]*)"),
        ("mfe_pnl_line", r"\*\*MFE\s*/\s*P&L\s*/\s*invalidate:\*\*\s*([^\n]*)"),
        ("post_url", r"\*\*Post URL[^:]*:\*\*\s*([^\n]*)"),
    ]:
        mm = re.search(pat, text, re.I)
        if mm:
            val = mm.group(1).strip()
            if val:
                out[key] = val

    for key, pat in BLOTTER_MD_KEYS:
        mm = re.search(pat, text, re.I)
        if mm:
            val = mm.group(1).strip()
            if val and val not in ("—", "-"):
                out[key] = val

    # Derive from combined MFE/P&L line when present
    if out.get("mfe_pnl_line"):
        parsed = _parse_mfe_pnl_line(out["mfe_pnl_line"])
        for k, v in parsed.items():
            out.setdefault(k, v)

    ticket_raw = out.get("ticket") or ""
    ids = _extract_ticket_ids(ticket_raw)
    out["ticket_ids"] = ids
    out["ticket_id"] = ids[0] if ids else ""
    # Clean display ticket (first id, or empty)
    if ids:
        out["ticket"] = ids[0] if len(ids) == 1 else "; ".join(ids)
    else:
        out["ticket"] = ""

    # Primary ticker from Symbols
    syms = out.get("symbols") or ""
    tickers = [s.strip().upper() for s in re.split(r"[,/\s]+", syms) if s.strip()]
    out["ticker"] = tickers[0] if tickers else ""
    out["tickers"] = tickers
    return out


def _parse_handle_md(path: Path) -> dict:
    text = path.read_text()
    out = {"file": path.name, "handle": path.stem, "focus": "", "grade": "unrated"}
    m = re.search(r"\*\*Focus:\*\*\s*([^\n]+)", text)
    if m:
        out["focus"] = m.group(1).strip()
    m = re.search(r"\*\*Trust grade:\*\*\s*([^\n]+)", text)
    if m:
        out["grade"] = m.group(1).strip()
    return out


def _load_trades_by_id() -> dict[str, dict]:
    if not TRADES_PATH.exists():
        return {}
    try:
        data = json.loads(TRADES_PATH.read_text())
    except Exception:
        return {}
    trades = data.get("trades") or []
    return {t["id"]: t for t in trades if isinstance(t, dict) and t.get("id")}


def _load_rh_day_pct() -> dict[str, float]:
    """Optional underlying day% from shared rh-quotes cache (no API calls)."""
    if not RH_QUOTES_PATH.exists():
        return {}
    try:
        data = json.loads(RH_QUOTES_PATH.read_text())
    except Exception:
        return {}
    payload = data.get("payload") or {}
    quotes = payload.get("quotes") if isinstance(payload, dict) else None
    if not isinstance(quotes, dict):
        return {}
    out: dict[str, float] = {}
    for sym, q in quotes.items():
        if not isinstance(q, dict):
            continue
        last = _f(q.get("last") or q.get("mark") or q.get("ask"))
        prev = _f(q.get("previous_close") or q.get("previousClose"))
        if last is not None and prev is not None and prev != 0:
            out[str(sym).upper()] = (last - prev) / prev * 100.0
    return out


def _entry_cost(t: dict) -> Optional[float]:
    for k in ("entryAsk", "entryMark", "entryBid", "costBasis"):
        x = _f(t.get(k))
        if x is not None:
            return x
    return None


def _trade_qty(t: dict) -> int:
    try:
        return _fq(t.get("qtySuggested") or t.get("qty") or 1)
    except (TypeError, ValueError):
        return 1


def _total_cost_usd(t: dict) -> Optional[float]:
    prem = _f(t.get("premium"))
    if prem is not None:
        return prem
    c = _entry_cost(t)
    if c is None:
        return None
    return c * _trade_qty(t) * 100.0


def _trade_in_out(t: dict) -> tuple[str, str]:
    inn = (
        t.get("offeredAtPT")
        or t.get("elevatedAtPT")
        or t.get("openedAtPT")
        or t.get("offeredAtET")
    )
    out = (
        t.get("exitAtPT")
        or t.get("closedAtPT")
        or t.get("invalidatedAtPT")
    )
    st = (t.get("status") or "").lower()
    if not out and st in ("closed", "invalidated", "expired"):
        out = t.get("updatedAtPT") or "—"
    if not out:
        out = "—"
    return (inn or "—", out or "—")


def _join_claim_to_trade(claim: dict, trades: dict[str, dict]) -> dict:
    """Prefer live ledger fields over stale MD when ticket matches."""
    enriched = dict(claim)
    enriched["joined"] = False
    enriched["joined_id"] = ""
    tid = claim.get("ticket_id") or ""
    # try all ticket ids; first hit wins
    trade = None
    for cand in claim.get("ticket_ids") or ([tid] if tid else []):
        if cand in trades:
            trade = trades[cand]
            tid = cand
            break
    if not trade:
        return enriched

    enriched["joined"] = True
    enriched["joined_id"] = tid
    enriched["ticker"] = trade.get("symbol") or enriched.get("ticker") or ""
    enriched["contract"] = trade.get("contract") or enriched.get("contract") or ""
    cost = _entry_cost(trade)
    qty = _trade_qty(trade)
    total = _total_cost_usd(trade)
    mark = _f(trade.get("lastMark")) or _f(trade.get("exitPremium")) or _f(trade.get("exitPrice"))
    pnl_u = _f(trade.get("pnlUsd")) or _f(trade.get("unrealizedPnlUsd"))
    pnl_p = _f(trade.get("pnlPct")) or _f(trade.get("unrealizedPnlPct"))
    mfe_p = _f(trade.get("mfePct"))
    be = _f(trade.get("breakEven")) or _f(trade.get("breakEvenEntry")) or _f(trade.get("breakEvenRh"))
    inn, outt = _trade_in_out(trade)
    status = (trade.get("status") or "").strip() or "—"

    enriched["cost_f"] = cost
    enriched["qty_f"] = qty
    enriched["total_f"] = total
    enriched["mark_f"] = mark
    enriched["pnl_usd_f"] = pnl_u
    enriched["pnl_pct_f"] = pnl_p
    enriched["mfe_f"] = mfe_p
    enriched["stock_be_f"] = be
    enriched["trade_status"] = status
    enriched["in_ts"] = inn
    enriched["out_ts"] = outt
    inv = trade.get("invalidate")
    if isinstance(inv, str) and inv.strip():
        enriched["invalidate"] = inv.strip()
    elif inv is True:
        enriched["invalidate"] = "invalidated"
    return enriched


def _enrich_from_md_numbers(claim: dict) -> dict:
    """Fill numeric fields from MD blotter bullets when not joined to a ticket."""
    if claim.get("joined"):
        return claim
    c = dict(claim)
    if c.get("cost") and c.get("cost_f") is None:
        c["cost_f"] = _f(c["cost"])
    if c.get("qty") and c.get("qty_f") is None:
        try:
            c["qty_f"] = int(float(str(c["qty"]).strip()))
        except (TypeError, ValueError):
            pass
    if c.get("mark") and c.get("mark_f") is None:
        c["mark_f"] = _f(c["mark"])
    if c.get("pnl_usd") and c.get("pnl_usd_f") is None:
        c["pnl_usd_f"] = _f(c["pnl_usd"])
    if c.get("pnl_pct") and c.get("pnl_pct_f") is None:
        c["pnl_pct_f"] = _f(c["pnl_pct"])
    if c.get("mfe") and c.get("mfe_f") is None:
        c["mfe_f"] = _f(c["mfe"])
    if c.get("stock_be") and c.get("stock_be_f") is None:
        c["stock_be_f"] = _f(c["stock_be"])
    if c.get("cost_f") is not None and c.get("qty_f") and c.get("total_f") is None:
        c["total_f"] = c["cost_f"] * c["qty_f"] * 100.0
    return c


def collect() -> dict:
    handles = []
    if (TI / "handles").exists():
        for p in sorted((TI / "handles").glob("*.md")):
            handles.append(_parse_handle_md(p))
    trades = _load_trades_by_id()
    day_pct = _load_rh_day_pct()
    claims = []
    joined_n = 0
    if (TI / "claims").exists():
        for p in sorted((TI / "claims").glob("*.md"), reverse=True):
            if p.name.startswith("_"):
                continue
            c = _parse_claim_md(p)
            c = _join_claim_to_trade(c, trades)
            c = _enrich_from_md_numbers(c)
            if c.get("joined"):
                joined_n += 1
            # Optional day% for unlinked claims (display only, never invent P&L)
            if not c.get("joined") and c.get("ticker"):
                dp = day_pct.get(c["ticker"].upper())
                if dp is not None:
                    c["day_pct"] = dp
            claims.append(c)
    lessons = []
    if (TI / "lessons").exists():
        for p in sorted((TI / "lessons").glob("*.md"), reverse=True):
            lessons.append({"file": p.name, "body": p.read_text()[:4000]})
    index = {}
    ip = TI / "index.json"
    if ip.exists():
        try:
            index = json.loads(ip.read_text())
        except Exception:
            index = {}
    return {
        "handles": handles,
        "claims": claims,
        "lessons": lessons,
        "index": index,
        "joined_count": joined_n,
        "trades_count": len(trades),
    }


def _status_chips(c: dict) -> str:
    """Combine claim Outcome grade with ticket open/closed when linked."""
    outcome = (c.get("outcome") or "pending").strip() or "pending"
    o_l = outcome.lower()
    if o_l.startswith("useful"):
        ocls = "ok"
    elif "never" in o_l or o_l.startswith("noise") or o_l.startswith("thesis_fail"):
        ocls = "bad"
    elif o_l.startswith("pending") or o_l.startswith("watch"):
        ocls = "warn"
    else:
        ocls = "flat"
    chips = [f"<span class='tchip {ocls}'>{_esc(outcome)}</span>"]
    if c.get("joined"):
        st = (c.get("trade_status") or "").lower()
        if st == "open":
            chips.append("<span class='tchip warn'>open</span>")
        elif st in ("closed", "expired"):
            chips.append(f"<span class='tchip flat'>{_esc(st)}</span>")
        elif st == "invalidated":
            chips.append("<span class='tchip bad'>invalidated</span>")
        elif st:
            chips.append(f"<span class='tchip flat'>{_esc(st)}</span>")
    elif not c.get("ticket_id"):
        # unlinked watch/pending
        act = (c.get("action") or "").lower()
        if "watch" in act or o_l.startswith("pending"):
            chips.append("<span class='tchip flat'>watch</span>")
    return " ".join(chips)


def _claim_why(c: dict) -> str:
    claim = (c.get("claim") or c.get("title") or "").strip()
    # compact one-liner
    if len(claim) > 110:
        claim = claim[:107] + "…"
    return claim


def build_html(tab_nav: str, *, now_pt: Optional[str] = None) -> str:
    data = collect()
    now_pt = now_pt or datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")
    handles = data["handles"]
    claims = data["claims"]
    lessons = data["lessons"]
    idx = data["index"]
    joined_n = data.get("joined_count") or 0

    h_rows = []
    for h in handles:
        grade = h.get("grade") or "unrated"
        gcls = "ok" if "useful" in grade.lower() else ("bad" if "never" in grade.lower() else "flat")
        h_rows.append(
            f"<tr><td><strong>@{_esc(h['handle'])}</strong></td>"
            f"<td>{_esc(h.get('focus'))}</td>"
            f"<td><span class='tchip {gcls}'>{_esc(grade)}</span></td></tr>"
        )
    h_tbody = "\n".join(h_rows) or "<tr><td colspan='3' class='empty'>No handles yet.</td></tr>"

    c_rows = []
    for c in claims:
        cost = c.get("cost_f")
        qty = c.get("qty_f")
        total = c.get("total_f")
        mark = c.get("mark_f")
        pnl_u = c.get("pnl_usd_f")
        pnl_p = c.get("pnl_pct_f")
        mfe = c.get("mfe_f")
        # Optional day% hint for unlinked (shown in MFE col subtitle only — never as invented P&L)
        day_hint = ""
        if not c.get("joined") and c.get("day_pct") is not None and pnl_p is None and mfe is None:
            day_hint = (
                f"<div class='tiny' title='Underlying session day% from rh-quotes cache'>"
                f"day {_esc(_fmt_pct(c['day_pct']))}</div>"
            )

        tot_s = f"${total:,.0f}" if total is not None else "—"
        qty_s = str(qty) if qty is not None else "—"
        contract = c.get("contract") or "—"
        ticker = c.get("ticker") or (c.get("symbols") or "—")
        action = c.get("action") or "—"
        why = _claim_why(c)
        tip_bits = []
        if c.get("joined_id"):
            tip_bits.append(f"ticket {c['joined_id']}")
        if c.get("in_ts"):
            tip_bits.append(f"in {c['in_ts']}")
        if c.get("out_ts") and c.get("out_ts") != "—":
            tip_bits.append(f"out {c['out_ts']}")
        if c.get("invalidate"):
            tip_bits.append(f"inv: {c['invalidate'][:80]}")
        if c.get("rule"):
            tip_bits.append(f"rule: {c['rule'][:80]}")
        row_title = _esc(" · ".join(tip_bits)) if tip_bits else ""

        c_rows.append(
            f"<tr title='{row_title}'>"
            f"<td class='num'>{_esc(c.get('date') or '—')}</td>"
            f"<td><strong>@{_esc((c.get('handle') or '').lstrip('@'))}</strong></td>"
            f"<td><strong>{_esc(ticker)}</strong></td>"
            f"<td class='contract'>{_esc(contract)}</td>"
            f"<td class='num'>{_esc(_fmt_px(cost))}</td>"
            f"<td class='num'>{_esc(qty_s)}</td>"
            f"<td class='num'>{_esc(tot_s)}</td>"
            f"<td class='num'>{_esc(_fmt_px(mark))}</td>"
            f"<td class='num {_pnl_class(pnl_u)}'>{_esc(_fmt_usd(pnl_u))}</td>"
            f"<td class='num {_pnl_class(pnl_p)}'>{_esc(_fmt_pct(pnl_p))}</td>"
            f"<td class='num {_pnl_class(mfe)}'>{_esc(_fmt_pct(mfe))}{day_hint}</td>"
            f"<td>{_status_chips(c)}</td>"
            f"<td>{_esc(action)}</td>"
            f"<td class='notes why'>{_esc(why)}</td>"
            f"</tr>"
        )
    ncols = 14
    c_tbody = (
        "\n".join(c_rows)
        or f"<tr><td colspan='{ncols}' class='empty'>No claims yet — Hal X / Rose append high-signal only.</td></tr>"
    )

    lesson_blocks = []
    for L in lessons:
        body = L["body"]
        title = L["file"]
        m = re.search(r"^#\s+(.+)$", body, re.M)
        if m:
            title = m.group(1).strip()
        body_show = re.sub(r"^#\s+.+\n?", "", body, count=1).strip()
        lesson_blocks.append(
            f"<div class='lesson-card'><div class='lid'>{_esc(title)}</div>"
            f"<pre class='lesson-body'>{_esc(body_show[:2500])}</pre></div>"
        )
    lessons_html = "\n".join(lesson_blocks) or "<div class='empty'>No lessons yet.</div>"

    since = _esc(idx.get("as_of_pt") or "—")
    n_h = len(handles)
    n_c = len(claims)
    n_l = len(lessons)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="120"/>
<title>OID · Trader intel</title>
<style>
:root{{
  --bg:#070b10; --panel:#0e141c; --line:#1a2533;
  --text:#e8eef7; --muted:#7f91a8; --accent:#4da3ff;
  --good:#3dd68c; --bad:#ff6b7a; --warn:#f0b429; --flat:#9aa8b8;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,sans-serif;background:
  radial-gradient(900px 420px at 8% -8%,#142033 0%,transparent 55%),
  radial-gradient(700px 380px at 100% 0%,#1a1528 0%,transparent 50%),
  var(--bg);color:var(--text);min-height:100vh}}
.wrap{{max-width:1480px;margin:0 auto;padding:22px 18px 56px}}
h1{{font-size:1.35rem;margin:0 0 6px}}
h2{{font-size:1.05rem;margin:22px 0 10px;color:var(--text)}}
.sub{{color:var(--muted);font-size:.88rem}}
.tabs{{display:flex;gap:8px;margin:0 0 16px;flex-wrap:wrap}}
.tabs a{{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}}
.tabs a.active,.tabs a:hover{{color:var(--text);border-color:#2a4a70;background:#152030}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 18px}}
@media(max-width:720px){{.stats{{grid-template-columns:1fr 1fr}}}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}
.card .k{{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
.card .v{{font-size:1.35rem;font-weight:700;margin-top:4px}}
.table-wrap{{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel)}}
table{{width:100%;border-collapse:collapse;min-width:1100px}}
th,td{{padding:8px 10px;text-align:left;font-size:.82rem;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:.65rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0;z-index:1}}
th.num,td.num{{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}}
td.contract{{font-family:var(--mono);font-size:.76rem;max-width:200px;color:var(--muted)}}
td.notes,td.why{{font-size:.76rem;color:var(--muted);max-width:260px;line-height:1.35}}
.tiny{{font-size:.62rem;color:var(--muted);margin-top:2px}}
.pos{{color:var(--good)}}
.neg{{color:var(--bad)}}
.flat{{color:var(--muted)}}
code{{font-size:.8em;background:#0a1018;padding:1px 5px;border-radius:4px}}
.tchip{{display:inline-block;font-size:.62rem;padding:2px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:#0a1018;text-transform:uppercase;letter-spacing:.03em;margin:1px 2px 1px 0}}
.tchip.ok{{color:var(--good);border-color:#1e5c40;background:#123526}}
.tchip.warn{{color:var(--warn);border-color:#6a4e18;background:#2a1f0a}}
.tchip.bad{{color:var(--bad);border-color:#7a3038;background:#2a1216}}
.tchip.flat{{color:var(--muted)}}
.empty{{color:var(--muted);padding:16px;text-align:center}}
.lesson-card{{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:12px 14px;margin-bottom:10px}}
.lesson-card .lid{{font-weight:650;margin-bottom:8px}}
.lesson-body{{margin:0;white-space:pre-wrap;font-family:inherit;font-size:.82rem;color:var(--muted);line-height:1.45}}
.note{{font-size:.82rem;color:var(--muted);margin:8px 0 16px;line-height:1.4}}
footer{{margin-top:24px;color:var(--muted);font-size:.8rem;line-height:1.45}}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>Trader intel · Rose + Hal</h1>
<div class="sub">Outcome-linked KB · handle → claim → action → outcome → rule · Built {_esc(now_pt)} · index {since}</div>
<div class="note">Soft color only — never elevate from a tweet alone. Jeffrey grades: <code>useful</code> / <code>noise</code> / <code>never_again</code>.
Claims with a <strong>Ticket id</strong> join live marks from <code>paper-trades/trades.json</code> (ledger wins over MD). Unlinked rows show — for numeric cols; optional underlying day% from rh-quotes cache only.</div>
<div class="stats">
  <div class="card"><div class="k">Handles</div><div class="v">{n_h}</div></div>
  <div class="card"><div class="k">Claims</div><div class="v">{n_c}</div></div>
  <div class="card"><div class="k">Joined tickets</div><div class="v">{joined_n}</div></div>
  <div class="card"><div class="k">Lesson files</div><div class="v">{n_l}</div></div>
</div>

<h2>Claims · blotter outcomes</h2>
<div class="table-wrap"><table>
<thead><tr>
  <th>Date</th><th>Handle</th><th>Ticker</th><th>Contract</th>
  <th class="num">Cost</th><th class="num">Qty</th><th class="num">Total $</th><th class="num">Mark</th>
  <th class="num">P&amp;L $</th><th class="num">P&amp;L %</th><th class="num">MFE</th>
  <th>Status / Outcome</th><th>Action</th><th>Why</th>
</tr></thead>
<tbody>
{c_tbody}
</tbody></table></div>

<h2>Handles (allowlist)</h2>
<div class="table-wrap"><table>
<thead><tr><th>Handle</th><th>Focus</th><th>Trust grade</th></tr></thead>
<tbody>
{h_tbody}
</tbody></table></div>

<h2>Lessons</h2>
{lessons_html}

<footer>
Research / paper only · Zero RH execution. Hal X scan + Rose append high-signal claims only (not every tweet).
Path: <code>options-intelligence-desk/trader-intel/</code>.
Hover a claim row for ticket · In/Out · invalidate · rule.
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    nav = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a class="active" href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
    html = build_html(nav)
    out = DASH / "trader-intel.html"
    out.write_text(html)
    data = collect()
    print("wrote", out)
    print("claims", len(data["claims"]), "joined", data["joined_count"])
