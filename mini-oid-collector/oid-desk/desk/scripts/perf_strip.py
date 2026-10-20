#!/usr/bin/env python3
"""Performance strip for the top of the production OID blotter (Jeffrey 2026-10-09).

Computed at package time straight from paper-trades/trades.json using the SAME win/loss and
open/closed rules as paper-trades/refresh_scorecard.py (so the desk win rate matches the
scorecard). Scale-out rows (…-SO1) are separate closed tickets in the ledger, so their realized
P&L is counted once. Nothing is invented: missing numbers render as '—'.

Live Agentic (••••8444) row is a placeholder until a live ledger exists.

Usage: python3 scripts/perf_strip.py   # prints the JSON payload
"""
from __future__ import annotations

import copy
import html
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper-trades"


def _scorecard_mod():
    if str(PAPER) not in sys.path:
        sys.path.insert(0, str(PAPER))
    spec = importlib.util.spec_from_file_location("oid_refresh_scorecard", PAPER / "refresh_scorecard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _close_date_pt(t: dict):
    for k in ("closedAt", "exitAt", "invalidatedAt"):
        v = t.get(k)
        if isinstance(v, str) and v:
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(PT).date().isoformat()
            except ValueError:
                pass
    for k in ("closedAtPT", "exitAtPT", "invalidatedAtPT"):
        v = t.get(k)
        if isinstance(v, str) and len(v) >= 10 and v[4] == "-":
            return v[:10]
    return None


def _agent(t: dict) -> str:
    a = (t.get("agent") or t.get("agentSeat") or "").strip().lower()
    if a.startswith("hal"):
        return "hal"
    if a.startswith("rose"):
        return "rose"
    return "other"


def compute(root: Path = ROOT) -> dict:
    sc = _scorecard_mod()
    ledger = json.loads((root / "paper-trades" / "trades.json").read_text(encoding="utf-8"))
    trades = [copy.deepcopy(t) for t in ledger.get("trades", [])]
    for t in trades:
        sc.ensure_outcome_fields(t)
    now = datetime.now(PT)
    today = now.date().isoformat()

    def blank():
        return {"realizedUsd": 0.0, "openUnrealizedUsd": 0.0, "openN": 0, "closedN": 0,
                "winsN": 0, "lossesN": 0, "scratchN": 0, "winRatePct": None, "todayRealizedUsd": 0.0, "todayClosedN": 0}

    groups = {"desk": blank(), "rose": blank(), "hal": blank()}
    for t in trades:
        status = (t.get("status") or "").lower()
        keys = ["desk", _agent(t)]
        for k in keys:
            if k not in groups:
                continue
            g = groups[k]
            if status in sc.CLOSED_STATUSES:
                g["closedN"] += 1
                res = sc.pnl_result(t)  # shared rule: realized P&L sign (refresh_scorecard.py)
                g[{"win": "winsN", "loss": "lossesN"}.get(res, "scratchN")] += 1
                usd = sc.realized_usd(t)
                if usd is not None:
                    g["realizedUsd"] += usd
                    if _close_date_pt(t) == today:
                        g["todayRealizedUsd"] += usd
                        g["todayClosedN"] += 1
            elif status in sc.OPEN_STATUSES:
                g["openN"] += 1
                u = t.get("unrealizedPnlUsd")
                if u is None:
                    u = t.get("pnlUsd")
                u = _num(u)
                if u is not None:
                    g["openUnrealizedUsd"] += u
    for g in groups.values():
        dec = g["winsN"] + g["lossesN"]
        g["winRatePct"] = round(g["winsN"] / dec * 100.0, 1) if dec else None
        for k in ("realizedUsd", "openUnrealizedUsd", "todayRealizedUsd"):
            g[k] = round(g[k], 2)
    return {
        "as_of_pt": now.strftime("%Y-%m-%d %-I:%M %p PT"),
        "session_date": today,
        "ledger_updated_pt": ledger.get("updatedAtPT"),
        "source": "paper-trades/trades.json · win/loss = realized P&L sign (>0 win, <0 loss, 0 scratch excluded) · shared with paper-trades/refresh_scorecard.py",
        "desk": groups["desk"], "rose": groups["rose"], "hal": groups["hal"],
        "live_agentic": {"account": "Agentic (••••8444)", "status": "no live trades yet",
                         "note": "Live trading authorized 2026-10-09 · $10k/trade · max 2 open · each order needs Jeffrey's yes"},
        "mandate": "Paper rows = research/paper ledger only. Live row = Agentic account only.",
    }


def _usd(v, signed=True):
    if v is None:
        return "—"
    s = f"${abs(v):,.2f}".replace(".00", "")
    if not signed:
        return s
    return ("+" if v > 0 else "−" if v < 0 else "") + s


def _cls(v):
    return "pos" if (v or 0) > 0 else "neg" if (v or 0) < 0 else ""


def render_html(p: dict) -> str:
    """Server-side HTML (same markup the JS painter produces) so the strip shows before JS runs."""
    e = html.escape

    def row(label, g):
        wr = "—" if g["winRatePct"] is None else f"{g['winRatePct']:.1f}%"
        return (f'<tr><th scope="row">{e(label)}</th>'
                f'<td class="{_cls(g["realizedUsd"])}">{_usd(g["realizedUsd"])}</td>'
                f'<td class="{_cls(g["openUnrealizedUsd"])}">{_usd(g["openUnrealizedUsd"])}<small> {g["openN"]} open</small></td>'
                f'<td>{g["closedN"]}</td><td>{g["winsN"]}/{g["lossesN"]}{f'<small> {g["scratchN"]} scr</small>' if g["scratchN"] else ''}</td><td><strong>{wr}</strong></td>'
                f'<td class="{_cls(g["todayRealizedUsd"])}">{_usd(g["todayRealizedUsd"])}<small> {g["todayClosedN"]} closed</small></td></tr>')

    la = p["live_agentic"]
    return (
        '<div class="perf-head"><strong>PERFORMANCE</strong><span>paper ledger · as of '
        f'{e(p["as_of_pt"])} · today = {e(p["session_date"])}</span></div>'
        '<div class="perf-scroll"><table class="perf-table"><thead><tr><th></th><th>Realized P&amp;L</th>'
        '<th>Open unrealized</th><th>Closed</th><th>W/L</th><th>Win rate</th><th>Today realized</th></tr></thead><tbody>'
        + row("Desk total (paper)", p["desk"]) + row("Rose (paper)", p["rose"]) + row("Hal (paper)", p["hal"])
        + f'<tr class="perf-live"><th scope="row">Live – {e(la["account"])}</th><td colspan="6">{e(la["status"])}'
          f'<small> · {e(la["note"])}</small></td></tr>'
        '</tbody></table></div>'
    )


PERF_CSS = (
    "\n/* perf strip (Jeffrey 2026-10-09) — injected by scripts/package_prod_dist.py */\n"
    ".perf-strip{background:#0f2a23;color:#eaf5ef;padding:8px 24px 10px;font-size:12px}"
    ".perf-head{display:flex;gap:14px;align-items:baseline;margin-bottom:4px}"
    ".perf-head strong{font-size:10px;letter-spacing:1.2px}.perf-head span{font-size:10px;color:#a9c7bb}"
    ".perf-scroll{overflow-x:auto}.perf-table{min-width:640px;width:100%;border-collapse:collapse;font-size:12px}"
    ".perf-table th,.perf-table td{background:none;border:0;border-bottom:1px solid #24453b;padding:4px 10px;"
    "color:#eaf5ef;text-align:right;white-space:nowrap;max-width:none;min-width:0;font-family:var(--mono)}"
    ".perf-table thead th{color:#a9c7bb;font:600 9px -apple-system,BlinkMacSystemFont,sans-serif;letter-spacing:.45px}"
    ".perf-table th[scope=row]{text-align:left;font:600 12px -apple-system,BlinkMacSystemFont,sans-serif}"
    ".perf-table tbody tr:first-child th,.perf-table tbody tr:first-child td{font-weight:700}"
    ".perf-table small{display:inline;color:#a9c7bb;font-size:10px;margin:0}"
    ".perf-table td.pos{color:#7fe0b4}.perf-table td.neg{color:#ff9b9b}"
    ".perf-table tr.perf-live td{text-align:left;color:#f3d79b}.perf-table tr.perf-live th{color:#f3d79b}"
    "@media(max-width:640px){.perf-strip{padding:7px 10px}}\n"
)

# JS painter: re-renders #perf-strip from state.snapshot.performance on every render (60s poll).
PERF_JS_FN = (
    "function perfStripPaint(){const el=document.getElementById('perf-strip');const p=state.snapshot&&state.snapshot.performance;"
    "if(!el||!p)return;const h=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"
    "const u=v=>v==null?'—':((v>0?'+':v<0?'−':'')+'$'+Math.abs(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).replace(/\\.00$/,''));"
    "const c=v=>(v||0)>0?'pos':(v||0)<0?'neg':'';"
    "const row=(l,g)=>`<tr><th scope=\"row\">${h(l)}</th><td class=\"${c(g.realizedUsd)}\">${u(g.realizedUsd)}</td>"
    "<td class=\"${c(g.openUnrealizedUsd)}\">${u(g.openUnrealizedUsd)}<small> ${g.openN} open</small></td><td>${g.closedN}</td>"
    "<td>${g.winsN}/${g.lossesN}${g.scratchN?`<small> ${g.scratchN} scr</small>`:''}</td><td><strong>${g.winRatePct==null?'—':g.winRatePct.toFixed(1)+'%'}</strong></td>"
    "<td class=\"${c(g.todayRealizedUsd)}\">${u(g.todayRealizedUsd)}<small> ${g.todayClosedN} closed</small></td></tr>`;"
    "const la=p.live_agentic||{};"
    "el.innerHTML=`<div class=\"perf-head\"><strong>PERFORMANCE</strong><span>paper ledger · as of ${h(p.as_of_pt)} · today = ${h(p.session_date)}</span></div>"
    "<div class=\"perf-scroll\"><table class=\"perf-table\"><thead><tr><th></th><th>Realized P&amp;L</th><th>Open unrealized</th><th>Closed</th><th>W/L</th><th>Win rate</th><th>Today realized</th></tr></thead><tbody>"
    "${row('Desk total (paper)',p.desk)}${row('Rose (paper)',p.rose)}${row('Hal (paper)',p.hal)}"
    "<tr class=\"perf-live\"><th scope=\"row\">Live – ${h(la.account)}</th><td colspan=\"6\">${h(la.status)}<small> · ${h(la.note)}</small></td></tr></tbody></table></div>`;}\n"
)


def inject_js(app_js: str) -> tuple[str, str]:
    anchor = "function render(){if(!state.snapshot)return;"
    if anchor not in app_js:
        return app_js, "WARN render anchor missing; perf strip stays server-rendered only"
    app_js = app_js.replace(anchor, PERF_JS_FN + anchor + "try{perfStripPaint();}catch(e){}", 1)
    return app_js, "ok"


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2, ensure_ascii=False))
