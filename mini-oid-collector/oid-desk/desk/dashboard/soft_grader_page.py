#!/usr/bin/env python3
"""Build soft-grader.html — Soft Grader V1 schema + live grades (soft second opinion)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "market-data" / "latest"
DASH = Path(__file__).resolve().parent


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_schema() -> dict:
    p = LATEST / "soft-grader-schema.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_grades_feed() -> dict:
    p = LATEST / "soft-grader.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def build_html(tab_nav: str, *, now_pt: Optional[str] = None) -> str:
    schema = load_schema()
    feed = load_grades_feed()
    now = datetime.now(PT)
    now_pt = now_pt or now.strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")

    payload = feed.get("payload") if isinstance(feed.get("payload"), dict) else {}
    grades = payload.get("grades") if isinstance(payload.get("grades"), list) else []
    feed_as_of = _esc(feed.get("as_of_pt") or schema.get("as_of_pt") or "—")
    schema_ver = _esc(schema.get("version") or payload.get("schemaVersion") or "1.0")
    feed_note = _esc(payload.get("note") or "Schema live. Soft only.")

    # --- Typed schema table ---
    fields = schema.get("fields") or {}
    field_order = [
        "regime",
        "direction",
        "direction_confidence",
        "toxic_flow",
        "setup_quality",
        "risk_state",
        "wrong_about",
    ]
    f_rows = []
    for key in field_order:
        meta = fields.get(key) or {}
        typ = meta.get("type") or "—"
        if "values" in meta:
            vals = " | ".join(str(v) for v in meta["values"])
        elif typ == "number":
            vals = f"{meta.get('min', 0.0)}–{meta.get('max', 1.0)}"
        elif typ == "int":
            vals = f"{meta.get('min', 0)}–{meta.get('max', 3)}"
        elif typ == "bool":
            vals = "true | false"
        else:
            vals = "short string" if key == "wrong_about" else "—"
        meaning = meta.get("meaning") or ""
        req = " · required" if meta.get("required") else ""
        f_rows.append(
            f"<tr>"
            f"<td><code>{_esc(key)}</code></td>"
            f"<td>{_esc(typ)}</td>"
            f"<td class='notes'>{_esc(vals)}</td>"
            f"<td class='notes'>{_esc(meaning)}{_esc(req)}</td>"
            f"</tr>"
        )
    f_tbody = "\n".join(f_rows) or (
        "<tr><td colspan='4' class='empty'>Schema fields loading…</td></tr>"
    )

    # --- Translation rules ---
    tr = schema.get("translationRules") or {}
    paper = tr.get("PAPER") or {}
    watch = tr.get("WATCH") or {}
    skip = tr.get("SKIP") or {}
    paper_when = "; ".join(paper.get("allOf") or []) or (
        "setup_quality ≥ 2 AND direction matches thesis AND confidence ≥ 0.80 "
        "AND risk_state ≠ reduce AND NOT toxic_flow AND regime ≠ crisis"
    )
    watch_when = "; ".join(watch.get("anyOf") or []) or (
        "setup_quality == 1 OR confidence 0.60–0.79 OR near_limit"
    )
    skip_when = skip.get("when") or "else, or stale / unavailable / crisis / toxic_flow"
    t_tbody = f"""
<tr>
  <td><span class="tchip paper">PAPER lean</span></td>
  <td class="notes">{_esc(paper_when)}</td>
  <td class="notes">Soft lean only — hard gates still required; never elevates alone</td>
</tr>
<tr>
  <td><span class="tchip watch">WATCH</span></td>
  <td class="notes">{_esc(watch_when)}</td>
  <td class="notes">Unless forced SKIP</td>
</tr>
<tr>
  <td><span class="tchip skip">SKIP</span></td>
  <td class="notes">{_esc(skip_when)}</td>
  <td class="notes">Default when stale, unavailable, or crisis</td>
</tr>
"""

    # --- Snapshot checklist ---
    snap = schema.get("snapshotFields") or [
        "symbol", "contract", "spot", "vs_call_wall_pct", "vs_put_wall_pct",
        "day_pct", "vix", "regime_hint", "flow_flags", "dte", "premium",
        "seats_used", "age_s", "thesis_direction",
    ]
    budget = schema.get("snapshotTokenBudget") or 400
    snap_items = "".join(f"<li><code>{_esc(s)}</code></li>" for s in snap)

    # --- Hard gates ---
    gates = schema.get("hardGatesAlwaysWin") or [
        "freshness (RH live ≤120s)",
        "seats",
        "premium caps",
        "noElevateIntoPrint",
        "WALLS_DATA_INSUFFICIENT",
        "Soft C never alone",
        "Close Playbook V1.1",
        "soft-catalyst + FA structure",
    ]
    gate_items = "".join(f"<li>{_esc(g)}</li>" for g in gates)

    # --- Live grades ---
    g_rows = []
    for g in grades:
        if not isinstance(g, dict):
            continue
        lean = str(g.get("lean") or "—").upper()
        lean_cls = "paper" if lean == "PAPER" else ("watch" if lean == "WATCH" else "skip")
        conf = g.get("direction_confidence")
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "—"
        sq = g.get("setup_quality")
        sq_s = str(sq) if sq is not None else "—"
        g_rows.append(
            f"<tr>"
            f"<td class='num'>{_esc(g.get('as_of_pt') or g.get('as_of') or '—')}</td>"
            f"<td><strong>{_esc(g.get('symbol') or '—')}</strong></td>"
            f"<td class='notes'>{_esc(g.get('contract') or '—')}</td>"
            f"<td><span class='tchip {lean_cls}'>{_esc(lean)}</span></td>"
            f"<td>{_esc(g.get('regime') or '—')}</td>"
            f"<td>{_esc(g.get('direction') or '—')}</td>"
            f"<td class='num'>{_esc(conf_s)}</td>"
            f"<td class='num'>{_esc(sq_s)}</td>"
            f"<td>{_esc(g.get('risk_state') or '—')}</td>"
            f"<td>{'yes' if g.get('toxic_flow') else 'no'}</td>"
            f"<td class='notes'>{_esc(g.get('wrong_about') or g.get('wrongAbout') or '—')}</td>"
            f"</tr>"
        )
    g_tbody = "\n".join(g_rows) or (
        "<tr><td colspan='11' class='empty'>"
        "No graded elevates yet — schema live. Soft only. "
        "Grades appear here after Soft Grader runs on a PAPER_CANDIDATE packet."
        "</td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="300"/>
<title>OID · Soft Grader</title>
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
.tchip{{display:inline-block;font-size:.62rem;padding:2px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:#0a1018;text-transform:uppercase;font-weight:650}}
.tchip.paper{{color:#3dd68c;border-color:#2a5a40;background:#0f2418}}
.tchip.watch{{color:#f0b429;border-color:#6a4e18;background:#2a1f0a}}
.tchip.skip{{color:#ff6b7a;border-color:#5a2a32;background:#2a1218}}
.empty{{color:var(--muted);padding:16px;text-align:center}}
.note{{font-size:.82rem;color:var(--muted);margin:8px 0 16px;line-height:1.4}}
.note ul{{margin:6px 0 0;padding-left:18px}}
.callout{{border:1px solid #6a4e18;background:#2a1f0a;border-radius:10px;padding:10px 14px;margin:12px 0;color:var(--warn);font-size:.88rem;line-height:1.45}}
.callout strong{{color:var(--text)}}
.check-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media (max-width:800px){{.check-grid{{grid-template-columns:1fr}}}}
.panel{{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:12px 14px}}
.panel h3{{margin:0 0 8px;font-size:.9rem}}
.panel ul{{margin:0;padding-left:18px;color:var(--muted);font-size:.82rem;line-height:1.45}}
code{{font-family:var(--mono);font-size:.78rem;color:#b8c9de}}
footer{{margin-top:24px;color:var(--muted);font-size:.8rem;line-height:1.45}}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>Soft Grader V1 · soft second opinion</h1>
<div class="sub">Never elevates alone · research / paper only · schema {schema_ver} · Built {_esc(now_pt)} · feed as of {feed_as_of}</div>

<div class="callout">
  <strong>What it is:</strong> a cheap typed second opinion on elevate packets / take-or-skip
  (regime · direction · setup_quality · risk_state · toxic_flow · wrongAbout) — Jev-style lean from a compact snapshot (~{budget} tokens).<br/>
  <strong>What it is not:</strong> a wall / FA / soft-catalyst replacement; a seat or premium authority;
  a Close Playbook override; an auto-elevate. Hard gates always win. Zero RH execution.
</div>

<p class="note">{feed_note}</p>

<h2>Typed answer schema</h2>
<div class="table-wrap"><table>
<thead><tr>
  <th>Field</th><th>Type</th><th>Values</th><th>Meaning</th>
</tr></thead>
<tbody>
{f_tbody}
</tbody></table></div>

<h2>Translation rules (deterministic)</h2>
<div class="table-wrap"><table>
<thead><tr>
  <th>Lean</th><th>When</th><th>Note</th>
</tr></thead>
<tbody>
{t_tbody}
</tbody></table></div>

<h2>Snapshot fields (grader input)</h2>
<div class="check-grid">
  <div class="panel">
    <h3>Compact numeric state · ≤~{budget} tokens</h3>
    <ul>{snap_items}</ul>
  </div>
  <div class="panel">
    <h3>Hard gates that always win</h3>
    <ul>{gate_items}</ul>
  </div>
</div>

<h2>Live grades</h2>
<p class="note" style="margin-top:0">From <code>market-data/latest/soft-grader.json</code> → <code>payload.grades[]</code>. Soft color only.</p>
<div class="table-wrap"><table>
<thead><tr>
  <th>As of</th><th>Symbol</th><th>Contract</th><th>Lean</th><th>Regime</th><th>Dir</th>
  <th class="num">Conf</th><th class="num">Setup</th><th>Risk</th><th>Toxic</th><th>Wrong about</th>
</tr></thead>
<tbody>
{g_tbody}
</tbody></table></div>

<footer>
Soft Grader never elevates alone. Does not override FA walls, RH ≤120s marks, Close Playbook V1.1, or mandate hard gates.
Default SKIP/WATCH if snapshot stale, grader unavailable, or crisis regime. Research / paper only · <strong>zero RH orders</strong>.
Docs: <code>SOFT-GRADER-V1.md</code> · schema <code>market-data/latest/soft-grader-schema.json</code> · elevate template
<code>paper-trades/notes/SOFT-GRADER-ELEVATE-TEMPLATE.md</code>. Mandate: Soft Grader section in <code>MANDATE-V1.8.md</code>.
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    nav = (
        '<div class="tabs">'
        '<a href="index.html">Blotter</a>'
        '<a href="data-sources.html">Data sources</a>'
        '<a href="trader-intel.html">Trader intel</a>'
        '<a href="catalysts.html">Events</a>'
        '<a class="active" href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a href="map.html">Map</a><a href="chart.html">Chart</a>'
        "</div>"
    )
    (DASH / "soft-grader.html").write_text(build_html(nav), encoding="utf-8")
    print("wrote soft-grader.html")
