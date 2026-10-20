#!/usr/bin/env python3
"""Chart Bot daily read page. Observation files only. Not a trade signal."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
DASH = Path(__file__).resolve().parent
OBS_DIR = DASH.parent / "chart-bot" / "observations"


ROLLUP = DASH.parent / "chart-bot" / "latest" / "chart-daily-observations.json"


def _inline_md(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


def _md_to_html(md: str) -> str:
    """Tiny markdown subset for Chart analysis files: ##/### headings, bullets, tables (as bullets), paragraphs."""
    out: list[str] = []
    in_list = False
    para: list[str] = []
    lines = md.splitlines()

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + _inline_md(" ".join(para)) + "</p>")
            para = []

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        st = line.strip()
        if not st:
            flush_para(); close_list(); continue
        if st.startswith("# "):
            flush_para(); close_list(); continue  # page already has a title
        m = re.match(r"^(#{2,4})\s+(.*)$", st)
        if m:
            flush_para(); close_list()
            lvl = min(len(m.group(1)) + 1, 5)
            out.append(f"<h{lvl}>{_inline_md(m.group(2))}</h{lvl}>")
            continue
        if st.startswith("|"):
            cells = [c.strip() for c in st.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if nxt.startswith("|") and re.fullmatch(r"[|:\-\s]+", nxt):
                continue  # header row
            flush_para()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + " — ".join(_inline_md(c) for c in cells if c) + "</li>")
            continue
        if st.startswith(("- ", "* ")):
            flush_para()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + _inline_md(st[2:]) + "</li>")
            continue
        close_list()
        para.append(st)
    flush_para(); close_list()
    return "\n".join(out)


def _latest_analysis(session: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if session:
        path = OBS_DIR / f"ANALYSIS-{session}.md"
        if path.is_file():
            return session, path.read_text()
    files = sorted(OBS_DIR.glob("ANALYSIS-*.md"))
    if not files:
        return None, None
    return files[-1].stem.replace("ANALYSIS-", ""), files[-1].read_text()


def _chart_reads() -> list[dict]:
    """Newest-first plain-English reads from chart-bot/observations/reads (chart_reads.py)."""
    import importlib.util
    path = DASH.parent / "chart-bot" / "chart_reads.py"
    if not path.is_file():
        return []
    try:
        spec = importlib.util.spec_from_file_location("chart_reads", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        reads = mod.load_reads()
        for r in reads:
            r["title"] = mod.title_for(r)
        return reads
    except Exception:
        return []


def _read_paras(r: dict) -> str:
    return "".join(
        f"<p>{('<strong>' + _esc(x['lead']) + '</strong> ') if x.get('lead') else ''}{_esc(x.get('body'))}</p>"
        for x in r.get("paragraphs") or []
    )


def _rollup() -> dict:
    try:
        return json.loads(ROLLUP.read_text())
    except (OSError, json.JSONDecodeError):
        return {}

TREND_ORDER = ("Bearish", "Hold", "UNAVAILABLE", "Bullish")
TREND_RANK = {name: i for i, name in enumerate(TREND_ORDER)}


def _esc(v: Any) -> str:
    if v is None:
        return "—"
    return html.escape(str(v))


def _num(v: Any, *, signed: bool = False) -> str:
    if v is None or isinstance(v, bool):
        return "—"
    if isinstance(v, (int, float)):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        if not s or s == "-":
            s = "0"
        if signed and v > 0:
            s = "+" + s
        return s
    return _esc(v)


def _load_observations() -> list[dict]:
    rows = []
    if not OBS_DIR.is_dir():
        return rows
    for path in sorted(OBS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("symbol"):
            rows.append(data)
    return rows


def _sort_key(row: dict) -> tuple:
    trend = str(row.get("total_trend") or "")
    return (TREND_RANK.get(trend, 99), str(row.get("symbol") or ""))


def _rs(row: dict, bench: str) -> Any:
    rs = row.get("relative_strength") or {}
    block = rs.get(bench) or {}
    return block.get("value_pct")


def build_html(tab_nav: str, *, now_pt: Optional[str] = None) -> str:
    if not now_pt:
        now_pt = datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT").replace(" 0", " ")
    rows = _load_observations()
    rows.sort(key=_sort_key)

    counts = {name: 0 for name in TREND_ORDER}
    sessions = []
    calculated = []
    versions = []
    for row in rows:
        trend = str(row.get("total_trend") or "")
        if trend in counts:
            counts[trend] += 1
        else:
            counts[trend] = counts.get(trend, 0) + 1
        if row.get("last_bar_session_date"):
            sessions.append(str(row["last_bar_session_date"]))
        if row.get("calculated_at_pt"):
            calculated.append(str(row["calculated_at_pt"]))
        if row.get("config_version"):
            versions.append(str(row["config_version"]))

    session_txt = ", ".join(sorted(set(sessions))) if sessions else "—"
    calc_txt = ", ".join(sorted(set(calculated))) if calculated else "—"
    rule = versions[0] if versions and len(set(versions)) == 1 else (", ".join(sorted(set(versions))) or "CB-DAILY-V1")

    chips = []
    chip_class = {
        "Bullish": "ok",
        "Bearish": "bad",
        "Hold": "warn",
        "UNAVAILABLE": "flat",
    }
    for name in TREND_ORDER:
        chips.append(
            f'<span class="tchip {chip_class.get(name, "flat")}">{_esc(name)}: {counts.get(name, 0)}</span>'
        )
    for name, n in counts.items():
        if name not in TREND_ORDER and n:
            chips.append(f'<span class="tchip flat">{_esc(name)}: {n}</span>')

    body_rows = []
    current = None
    for row in rows:
        trend = str(row.get("total_trend") or "")
        if trend != current:
            current = trend
            n = counts.get(trend, 0)
            body_rows.append(
                f'<tr class="group"><td colspan="11">{_esc(trend or "—")} · {n}</td></tr>'
            )
        pct = row.get("pct_var") or {}
        sess = row.get("last_bar_session_date") or (row.get("last_completed_bar") or {}).get("session_date")
        body_rows.append(
            "<tr>"
            f"<td class='sym'><strong>{_esc(row.get('symbol'))}</strong></td>"
            f"<td><span class='tchip {chip_class.get(trend, 'flat')}'>{_esc(trend or '—')}</span></td>"
            f"<td>{_esc(row.get('data_status'))}{' · <strong>PROVISIONAL</strong>' if row.get('provisional') else ''}</td>"
            f"<td class='num'>{_esc(sess)}</td>"
            f"<td class='num'>{_num(row.get('close'))}</td>"
            f"<td class='num'>{_num(pct.get('ema9'), signed=True)}</td>"
            f"<td class='num'>{_num(pct.get('ema21'), signed=True)}</td>"
            f"<td class='num'>{_num(pct.get('sma50'), signed=True)}</td>"
            f"<td class='num'>{_num(pct.get('sma200'), signed=True)}</td>"
            f"<td class='num'>{_num(_rs(row, 'vs_QQQ'), signed=True)}</td>"
            f"<td class='num'>{_num(_rs(row, 'vs_SMH'), signed=True)}</td>"
            "</tr>"
        )
    tbody = "\n".join(body_rows) or "<tr><td colspan='11' class='empty'>No observation files.</td></tr>"

    prov_syms = sorted(str(r.get("symbol")) for r in rows if r.get("provisional"))
    roll = (_rollup().get("payload") or {})
    board_label = roll.get("board_label") if prov_syms else None
    if prov_syms and not board_label:
        board_label = "PROVISIONAL (built from RH closing quotes; real daily bars pending)"
    title_suffix = f" — {board_label}" if board_label else ""
    banner = ""
    if prov_syms:
        real_syms = sorted(str(r.get("symbol")) for r in rows if not r.get("provisional"))
        banner = (
            f'<p class="warn"><strong>{_esc(board_label)}</strong>. Robinhood had not posted real daily bars for '
            f'{len(prov_syms)} of {len(rows)} names when this board was built, so their last bar uses the official RH '
            f'regular-session closing price (exact) with open/high/low/volume from RH intraday bars (volume approximate). '
            f'Real RH day bars already used for: {_esc(", ".join(real_syms) or "none")}. '
            f'The next refresh replaces every provisional bar with the real RH daily bar. '
            f'Approval: {_esc((roll.get("provisional") or {}).get("approved_by") or "see feed-registry.json")}.</p>'
        )
    a_sess = sessions and max(sessions) or None
    a_date, a_md = _latest_analysis(a_sess)
    analysis_html = ""
    quick_html = ""
    if a_md:
        stale_tag = "" if a_date == a_sess else f" (latest available; board session is {_esc(a_sess)})"
        analysis_html = (f'<h2>Written read — session {_esc(a_date)}{stale_tag}</h2>\n<div class="analysis">'
                         + _md_to_html(a_md) + "</div>")
    reads = _chart_reads()
    reads_html = ""
    if reads:
        latest, older = reads[0], reads[1:]
        reads_html = (f'<h2>Latest chart read — {_esc(latest["title"])}</h2>\n<div class="analysis read-latest">'
                      + _read_paras(latest) + '<p class="sub">Forecasts unavailable · soft observation only · never elevates.</p></div>')
        if older:
            reads_html += ('\n<h2>Earlier chart reads</h2>\n<div class="analysis read-archive">'
                           + "".join(f'<details><summary>{_esc(r["title"])}</summary>{_read_paras(r)}</details>' for r in older)
                           + "</div>")
        quick_html = (f'<p class="callout"><strong>Latest chart read — {_esc(latest["title"])}.</strong> '
                      f'Full read and earlier reads are below the board.</p>')


    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>OID · Chart</title>
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
.sub{{color:var(--muted);font-size:.88rem;line-height:1.45}}
.tabs{{display:flex;gap:8px;margin:0 0 10px;flex-wrap:wrap}}
.tabs a{{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}}
.tabs a.active,.tabs a:hover{{color:var(--text);border-color:#2a4a70;background:#152030}}
.table-wrap{{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel)}}
table{{width:100%;border-collapse:collapse;min-width:1100px}}
th,td{{padding:9px 11px;text-align:left;font-size:.84rem;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{color:var(--muted);font-weight:600;font-size:.68rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}}
td.num,.num{{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}}
td.sym{{letter-spacing:.04em}}
.tchip{{display:inline-block;font-size:.62rem;padding:2px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:#0a1018;text-transform:uppercase;letter-spacing:.03em}}
.tchip.ok{{color:var(--good);border-color:#1e5c40;background:#123526}}
.tchip.warn{{color:var(--warn);border-color:#6a4e18;background:#2a1f0a}}
.tchip.bad{{color:var(--bad);border-color:#7a3038;background:#2a1216}}
.tchip.flat{{color:var(--muted)}}
.ds-summary{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 14px}}
.ds-summary .tchip{{font-size:.72rem;padding:4px 10px}}
tr.group td{{background:#121a24;color:var(--text);font-weight:700;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase}}
.note{{font-size:.82rem;color:var(--muted);margin:8px 0 16px;line-height:1.45}}
code{{font-size:.8em;background:#0a1018;padding:1px 5px;border-radius:4px}}
footer{{margin-top:20px;color:var(--muted);font-size:.8rem;line-height:1.45}}
.empty{{color:var(--muted);padding:16px;text-align:center}}
p.warn{{border:1px solid #6a4e18;background:#2a1f0a;color:#f6d38a;border-radius:10px;padding:10px 12px;font-size:.88rem;line-height:1.45}}
h2{{font-size:1.05rem;margin:18px 0 6px}} h3{{font-size:.95rem;margin:14px 0 4px}} h4{{font-size:.88rem;margin:10px 0 4px}}
.analysis{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:6px 16px 12px;font-size:.88rem;line-height:1.5}}
.analysis li{{margin:3px 0}}
.analysis details{{margin:6px 0;border-top:1px solid var(--line);padding-top:6px}} .analysis summary{{cursor:pointer;font-weight:650}}
p.callout{{border:1px solid #2a4a70;background:#101b2a;border-radius:10px;padding:10px 12px;font-size:.88rem;line-height:1.45}}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>Chart Bot daily read{_esc(title_suffix)}</h1>
{banner}
{quick_html}
<div class="sub">Rule <code>{_esc(rule)}</code> · Soft only · Never a trade signal · Forecasts off</div>
<div class="sub">Last completed session <strong>{_esc(session_txt)}</strong> · calculated_at_pt <strong>{_esc(calc_txt)}</strong> · {len(rows)} symbols · Built {_esc(now_pt)}</div>
<div class="ds-summary">{' '.join(chips)}</div>
<p class="note">Rule <code>CB-DAILY-V1</code> · universe <code>RH-TECH-CHIP-20261004</code> · <strong>GOOG Class C only</strong> · Chart is the <strong>sole writer</strong> of post-close daily historicals (does not share Rose/Hal live quote pulse). SKHY and SPCX are insufficient history (<code>INSUFFICIENT_HISTORY</code>), not a failed pull. Close is the split-adjusted regular-session close, USD/share. % vs EMA9 / EMA21 / SMA50 / SMA200 is close versus that average (Shay lineage). SMA20 + ATR14 are engineering-only / unvalidated. RS is the 20-session close-to-close return minus QQQ or SMH, in percentage points. N/A: Databento, Massive, 5/15/60-min bars, weekly bars, 1-min RVOL, pattern detector, SOXX, forecasts, push receiver, changes API. Nulls are an em dash. Soft only · never elevates · not trade readiness.</p>
<div class="table-wrap"><table>
<thead><tr>
  <th>Symbol</th><th>Trend</th><th>Data status</th><th class="num">Last session</th>
  <th class="num">Close</th>
  <th class="num">% vs EMA9</th><th class="num">% vs EMA21</th><th class="num">% vs SMA50</th><th class="num">% vs SMA200</th>
  <th class="num">RS 20s vs QQQ</th><th class="num">RS 20s vs SMH</th>
</tr></thead>
<tbody>
{tbody}
</tbody></table></div>
<footer>
Research / paper only. Chart Bot MA-state observation from <code>chart-bot/observations/</code>. Soft only. Never a trade signal. Forecasts off. No order instructions. Does not replace the Shay MA table.
</footer>
{reads_html}
{analysis_html.replace("<h2>Written read", "<h2>Detailed analysis", 1)}
</div></body></html>
"""


if __name__ == "__main__":
    nav = (
        '<div class="tabs"><a href="index.html">Blotter</a>'
        '<a href="data-sources.html">Data sources</a>'
        '<a href="trader-intel.html">Trader intel</a>'
        '<a href="catalysts.html">Events</a>'
        '<a href="soft-grader.html">Soft Grader</a>'
        '<a href="news-archive.html">News Archive</a>'
        '<a href="map.html">Map</a>'
        '<a class="active" href="chart.html">Chart</a></div>'
    )
    out = DASH / "chart.html"
    out.write_text(build_html(nav))
    print("wrote", out)
