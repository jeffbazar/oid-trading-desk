#!/usr/bin/env python3
"""Build catalysts.html — earnings + macro market movers + other events for desk watchlist."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "market-data" / "latest"
TI = ROOT / "trader-intel"
DASH = Path(__file__).resolve().parent


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_catalysts() -> dict:
    for p in (LATEST / "desk-catalysts.json", TI / "catalysts.json"):
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
    return {}


def _dte(iso: Optional[str], today: date) -> Optional[int]:
    if not iso:
        return None
    try:
        return (date.fromisoformat(iso[:10]) - today).days
    except Exception:
        return None


def _fmt_weekday(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
        return d.strftime("%a %b %-d").replace(" 0", " ")
    except Exception:
        return iso


def _importance_label(n: Any) -> str:
    try:
        v = int(n)
    except Exception:
        return "—"
    if v >= 5:
        return "★★★★★"
    if v == 4:
        return "★★★★"
    if v == 3:
        return "★★★"
    if v == 2:
        return "★★"
    if v == 1:
        return "★"
    return "—"


def _nearest_callout(data: dict, today: date) -> str:
    """Pick soonest upcoming soft catalyst among macro + MU earn."""
    candidates: list[tuple[int, str, str]] = []

    for m in data.get("macro_events") or []:
        dte = _dte(m.get("date"), today)
        if dte is None or dte < 0:
            continue
        label = f"{_esc(m.get('event'))} <strong>{_esc(_fmt_weekday(m.get('date')))}</strong>"
        t = m.get("time_et")
        if t:
            label += f" {_esc(t)}"
        candidates.append((dte, "macro", label))

    for e in data.get("earnings") or []:
        if e.get("symbol") != "MU":
            continue
        dte = _dte(e.get("date"), today)
        if dte is None or dte < 0:
            continue
        # Prefer near-term MU pin (within 14d) over far Q1
        if dte > 45:
            continue
        im = e.get("implied_move_pct")
        im_s = f" · FA implied move ~<strong>{im:.1f}%</strong>" if isinstance(im, (int, float)) else ""
        timing = e.get("timing") or "AMC"
        label = (
            f"MU earnings <strong>{_esc(_fmt_weekday(e.get('date')))} {_esc(timing)}</strong>"
            f"{im_s} (desk pin; soft event-risk)"
        )
        candidates.append((dte, "earn", label))

    if not candidates:
        return (
            '<div class="callout"><strong>Nearest:</strong> no dated catalysts loaded.</div>'
        )

    candidates.sort(key=lambda x: (x[0], 0 if x[1] == "macro" else 1))
    # Show soonest macro if sooner/equal morning vs MU; always surface MU if within 7d
    soonest = candidates[0]
    parts = [soonest[2]]
    # If soonest is macro and MU is same day or within 3d, append MU
    mu = next((c for c in candidates if c[1] == "earn"), None)
    if soonest[1] == "macro" and mu and mu[0] <= max(soonest[0] + 3, 7):
        if mu[2] not in parts:
            parts.append(mu[2])
    # If soonest is MU but a macro is same calendar day / earlier same week, prepend that macro
    if soonest[1] == "earn":
        same_week_macro = [
            c for c in candidates if c[1] == "macro" and c[0] <= soonest[0]
        ]
        if same_week_macro:
            parts = [same_week_macro[0][2], soonest[2]]

    joined = " · ".join(parts)
    return (
        f'<div class="callout"><strong>Nearest:</strong> {joined}. '
        f"Soft research only — does not elevate gates.</div>"
    )


def build_html(tab_nav: str, *, now_pt: Optional[str] = None) -> str:
    data = load_catalysts()
    now = datetime.now(PT)
    today = now.date()
    now_pt = now_pt or now.strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")
    as_of = _esc(data.get("as_of_pt") or "—")
    earnings = data.get("earnings") or []
    macro = data.get("macro_events") or []
    other = data.get("other_events") or []
    notes = data.get("notes") or []

    e_rows = []
    for e in sorted(earnings, key=lambda x: x.get("date") or ""):
        im = e.get("implied_move_pct")
        im_s = f"{im:.1f}%" if isinstance(im, (int, float)) else "—"
        urgent = ""
        dte = e.get("days_to_event")
        if dte is None:
            dte = _dte(e.get("date"), today)
        if dte is not None and 0 <= dte <= 5:
            urgent = " class='urgent'"
        conf = "✓" if e.get("confirmed") else "?"
        e_rows.append(
            f"<tr{urgent}>"
            f"<td class='num'>{_esc(e.get('date'))}</td>"
            f"<td><strong>{_esc(e.get('symbol'))}</strong></td>"
            f"<td>{_esc(e.get('timing') or '—')}</td>"
            f"<td>{_esc(e.get('period') or '—')}</td>"
            f"<td class='num'>{_esc(e.get('eps_est') if e.get('eps_est') is not None else '—')}</td>"
            f"<td class='num'>{_esc(im_s)}</td>"
            f"<td>{conf}</td>"
            f"<td class='notes'>{_esc(e.get('source') or '')}</td>"
            f"</tr>"
        )
    e_tbody = "\n".join(e_rows) or "<tr><td colspan='8' class='empty'>No earnings loaded.</td></tr>"

    m_rows = []
    for ev in sorted(macro, key=lambda x: (x.get("date") or "9999", x.get("time_et") or "")):
        dte = _dte(ev.get("date"), today)
        urgent = ""
        if dte is not None and 0 <= dte <= 5:
            urgent = " class='urgent'"
        m_rows.append(
            f"<tr{urgent}>"
            f"<td class='num'>{_esc(ev.get('date') or 'TBD')}</td>"
            f"<td><strong>{_esc(ev.get('event') or '—')}</strong></td>"
            f"<td class='num'>{_esc(ev.get('time_et') or '—')}</td>"
            f"<td>{_esc(_importance_label(ev.get('importance')))}</td>"
            f"<td class='notes'>{_esc(ev.get('note') or '')}</td>"
            f"</tr>"
        )
    m_tbody = "\n".join(m_rows) or (
        "<tr><td colspan='5' class='empty'>No macro movers loaded.</td></tr>"
    )

    o_rows = []
    for ev in sorted(other, key=lambda x: x.get("date") or "9999"):
        o_rows.append(
            f"<tr>"
            f"<td class='num'>{_esc(ev.get('date') or 'TBD')}</td>"
            f"<td><strong>{_esc(ev.get('symbol'))}</strong></td>"
            f"<td><span class='tchip flat'>{_esc(ev.get('type') or 'event')}</span></td>"
            f"<td>{_esc(ev.get('title') or '—')}</td>"
            f"<td class='notes'>{_esc(ev.get('note') or '')}</td>"
            f"</tr>"
        )
    o_tbody = "\n".join(o_rows) or (
        "<tr><td colspan='5' class='empty'>Product / interview / conference events — refreshing…</td></tr>"
    )

    notes_html = "".join(f"<li>{_esc(n)}</li>" for n in notes)
    callout = _nearest_callout(data, today)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="300"/>
<title>OID · Events</title>
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
.wrap{{max-width:1340px;margin:0 auto;padding:22px 18px 56px}}
h1{{font-size:1.35rem;margin:0 0 6px}}
h2{{font-size:1.05rem;margin:22px 0 10px}}
.sub{{color:var(--muted);font-size:.88rem}}
.tabs{{display:flex;gap:8px;margin:0 0 16px;flex-wrap:wrap}}
.tabs a{{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}}
.tabs a.active,.tabs a:hover{{color:var(--text);border-color:#2a4a70;background:#152030}}
.table-wrap{{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel)}}
table{{width:100%;border-collapse:collapse;min-width:720px}}
th,td{{padding:9px 11px;text-align:left;font-size:.84rem;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:.68rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}}
td.num,.num{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
td.notes{{font-size:.78rem;color:var(--muted);max-width:420px;line-height:1.35}}
tr.urgent{{background:rgba(240,180,41,.08)}}
.tchip{{display:inline-block;font-size:.62rem;padding:2px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:#0a1018;text-transform:uppercase}}
.tchip.flat{{color:var(--muted)}}
.empty{{color:var(--muted);padding:16px;text-align:center}}
.note{{font-size:.82rem;color:var(--muted);margin:8px 0 16px;line-height:1.4}}
.note ul{{margin:6px 0 0;padding-left:18px}}
.callout{{border:1px solid #6a4e18;background:#2a1f0a;border-radius:10px;padding:10px 14px;margin:12px 0;color:var(--warn);font-size:.88rem}}
footer{{margin-top:24px;color:var(--muted);font-size:.8rem;line-height:1.45}}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>Events · earnings &amp; catalysts</h1>
<div class="sub">Desk watchlist · FlashAlpha primary · Built {_esc(now_pt)} · as of {as_of}</div>
{callout}
<div class="note"><ul>{notes_html}</ul></div>

<h2>Market movers (macro / econ)</h2>
<p class="note" style="margin-top:0">Soft research only — PCE, jobs, inflation, FOMC, ISM. Does not elevate gates. Oil/rates stay on blotter strip.</p>
<div class="table-wrap"><table>
<thead><tr>
  <th>Date</th><th>Event</th><th>Time ET</th><th>Importance</th><th>Note</th>
</tr></thead>
<tbody>
{m_tbody}
</tbody></table></div>

<h2>Earnings (next ~90d)</h2>
<div class="table-wrap"><table>
<thead><tr>
  <th>Date</th><th>Ticker</th><th>Session</th><th>Period</th><th class="num">EPS est</th><th class="num">Impl move</th><th>Conf</th><th>Source</th>
</tr></thead>
<tbody>
{e_tbody}
</tbody></table></div>

<h2>Other catalysts (product / conference / interview)</h2>
<div class="table-wrap"><table>
<thead><tr>
  <th>Date</th><th>Ticker</th><th>Type</th><th>Title</th><th>Note</th>
</tr></thead>
<tbody>
{o_tbody}
</tbody></table></div>

<footer>
Research / paper only. Earnings from desk pin + FlashAlpha <code>get_earnings_calendar</code>. Macro from BEA/BLS/Fed (+ ISM convention). Other events soft/web — confirm on company IR before sizing. Path: <code>market-data/latest/desk-catalysts.json</code>.
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    nav = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="trader-intel.html">Trader intel</a><a class="active" href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a></div>'
    (DASH / "catalysts.html").write_text(build_html(nav))
    print("wrote catalysts.html")
