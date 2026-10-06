#!/usr/bin/env python3
"""Build architecture.html + setup.html from desk markdown docs (static blotter style)."""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent.parent

NAV_ITEMS = [
    ("index.html", "Blotter"),
    ("data-sources.html", "Data sources"),
    ("architecture.html", "Architecture"),
    ("setup.html", "Setup"),
    ("trader-intel.html", "Trader intel"),
    ("catalysts.html", "Events"),
    ("soft-grader.html", "Soft Grader"),
    ("news-archive.html", "News Archive"),
    ("map.html", "Map"),
    ("chart.html", "Chart"),
]


def make_tab_nav(active: str) -> str:
    """active is the href filename, e.g. 'architecture.html'."""
    parts = []
    for href, label in NAV_ITEMS:
        cls = ' class="active"' if href == active else ""
        parts.append(f'<a{cls} href="{href}">{label}</a>')
    return '<div class="tabs">' + "".join(parts) + "</div>"


def _esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _inline(text: str) -> str:
    """Escape then apply limited inline markdown."""
    s = html.escape(text, quote=False)
    # code first
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # bold / italic
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    # links
    s = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        s,
    )
    s = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a href="\2">\1</a>',
        s,
    )
    return s


def md_to_html(md: str) -> str:
    """Small subset converter: headings, tables, fences, lists, quotes, paragraphs."""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def flush_para(buf: list[str]) -> None:
        if not buf:
            return
        text = " ".join(x.strip() for x in buf if x.strip())
        if text:
            out.append(f"<p>{_inline(text)}</p>")
        buf.clear()

    while i < n:
        line = lines[i]
        # fenced code
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            body: list[str] = []
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            if i < n:
                i += 1  # closing fence
            code = html.escape("\n".join(body), quote=False)
            cls = f' class="lang-{_esc(lang)}"' if lang else ""
            note = ""
            if lang.lower() == "mermaid":
                note = '<div class="md-note">Diagram source (mermaid) — rendered as text on this static page.</div>'
                cls = ' class="lang-mermaid"'
            out.append(f'{note}<pre{cls}><code>{code}</code></pre>')
            continue

        # table block
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", lines[i + 1]):
            rows: list[list[str]] = []
            while i < n and "|" in lines[i]:
                raw = lines[i].strip()
                if re.match(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", raw):
                    i += 1
                    continue
                cells = [c.strip() for c in raw.strip("|").split("|")]
                rows.append(cells)
                i += 1
            if rows:
                head, *body = rows
                th = "".join(f"<th>{_inline(c)}</th>" for c in head)
                trs = []
                for r in body:
                    # pad/truncate to head width
                    while len(r) < len(head):
                        r.append("")
                    tds = "".join(f"<td>{_inline(c)}</td>" for c in r[: len(head)])
                    trs.append(f"<tr>{tds}</tr>")
                out.append(
                    '<div class="table-wrap"><table>'
                    f"<thead><tr>{th}</tr></thead>"
                    f"<tbody>{''.join(trs)}</tbody>"
                    "</table></div>"
                )
            continue

        # headings
        hm = re.match(r"^(#{1,4})\s+(.*)$", line)
        if hm:
            level = len(hm.group(1))
            title = hm.group(2).strip()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append(f'<h{level} id="{_esc(slug)}">{_inline(title)}</h{level}>')
            i += 1
            continue

        # blockquote
        if line.startswith(">"):
            buf_q: list[str] = []
            while i < n and lines[i].startswith(">"):
                buf_q.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f'<blockquote>{_inline(" ".join(buf_q))}</blockquote>')
            continue

        # unordered list
        if re.match(r"^[-*]\s+", line):
            items: list[str] = []
            while i < n and re.match(r"^[-*]\s+", lines[i]):
                items.append(f"<li>{_inline(re.sub(r'^[-*]\s+', '', lines[i]))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # ordered list
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                items.append(f"<li>{_inline(re.sub(r'^\d+\.\s+', '', lines[i]))}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        # blank
        if not line.strip():
            i += 1
            continue

        # paragraph
        buf: list[str] = []
        while i < n and lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("```") \
                and not lines[i].startswith(">") and not re.match(r"^[-*]\s+", lines[i]) \
                and not re.match(r"^\d+\.\s+", lines[i]) \
                and not ("|" in lines[i] and i + 1 < n and re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", lines[i + 1])):
            buf.append(lines[i])
            i += 1
        flush_para(buf)

    return "\n".join(out)


def _read(path: Path) -> str:
    if not path.exists():
        return f"_Missing source: `{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}`._\n"
    return path.read_text(encoding="utf-8")


def _cutover_brief() -> str:
    """Short cutover status for the site (not full backup/rollback playbook)."""
    raw = _read(ROOT / "CUTOVER-20261005.md")
    # Prefer Outcome + Open gaps (non-blockers summary) without long bash blocks
    outcome = ""
    gaps = ""
    section = None
    buf: list[str] = []
    for line in raw.splitlines():
        if line.startswith("## "):
            if section == "Outcome":
                outcome = "\n".join(buf).strip()
            elif section == "Open gaps":
                gaps = "\n".join(buf).strip()
            section = line[3:].strip()
            buf = []
            continue
        if section in ("Outcome", "Open gaps"):
            # skip fenced smoke/rollback dumps inside Open gaps later sections handled by heading
            buf.append(line)
    if section == "Outcome":
        outcome = "\n".join(buf).strip()
    elif section == "Open gaps":
        gaps = "\n".join(buf).strip()

    parts = ["# Cutover status — 2026-10-05 (PT)\n", "Research/paper only. Live blotter: https://bold-tulip-nejq.here.now/\n"]
    if outcome:
        parts.append("## Outcome\n")
        parts.append(outcome + "\n")
    if gaps:
        # Trim to first ~40 lines of open gaps to keep page readable
        gap_lines = gaps.splitlines()
        # Drop nested ### Blockers fluff if huge — keep whole Open gaps (it's short enough)
        parts.append("## Open gaps\n")
        parts.append("\n".join(gap_lines) + "\n")
    parts.append(
        "\nFull cutover note on desk: `CUTOVER-20261005.md`. "
        "Publish slug **bold-tulip-nejq** only (swift-dune is review-only).\n"
    )
    return "\n".join(parts)


def _ownership_note() -> str:
    dedup = ROOT / "market-data" / "QUERY-DEDUP.md"
    dup = ROOT / "hal" / "DUPLICATE-RH-QUOTES.md"
    if not dup.exists():
        dup = ROOT / "DUPLICATE-RH-QUOTES.md"
    # Pull RH ownership section from QUERY-DEDUP
    dedup_text = _read(dedup)
    rh_chunk = ""
    capture = False
    for line in dedup_text.splitlines():
        if line.startswith("## RH quotes ownership"):
            capture = True
            rh_chunk = line + "\n"
            continue
        if capture:
            if line.startswith("## ") and not line.startswith("## RH"):
                break
            rh_chunk += line + "\n"
    body = [
        "# Query ownership notes\n",
        "Short ownership excerpts from `market-data/QUERY-DEDUP.md` and `hal/DUPLICATE-RH-QUOTES.md`. "
        "Full query architecture is above.\n",
    ]
    if rh_chunk.strip():
        body.append(rh_chunk)
    body.append("\n---\n\n")
    body.append(_read(dup))
    return "\n".join(body)


DOC_CSS = """
:root{
  --bg:#070b10; --panel:#0e141c; --panel2:#121a24; --line:#1a2533;
  --text:#e8eef7; --muted:#7f91a8; --accent:#4da3ff;
  --good:#3dd68c; --bad:#ff6b7a; --warn:#f0b429;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,sans-serif;background:
  radial-gradient(900px 420px at 8% -8%,#142033 0%,transparent 55%),
  radial-gradient(700px 380px at 100% 0%,#1a1528 0%,transparent 50%),
  var(--bg);color:var(--text);min-height:100vh}
.wrap{max-width:980px;margin:0 auto;padding:14px 16px 48px}
h1{font-size:1.35rem;margin:0 0 6px}
h2{font-size:1.08rem;margin:26px 0 10px;padding-top:8px;border-top:1px solid var(--line)}
h2:first-of-type{border-top:none;padding-top:0}
h3{font-size:.95rem;margin:18px 0 8px;color:#c5d4e8}
h4{font-size:.88rem;margin:14px 0 6px;color:var(--muted)}
.sub{color:var(--muted);font-size:.88rem;margin-bottom:12px}
.tabs{display:flex;gap:8px;margin:0 0 10px;flex-wrap:wrap}
.tabs a{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}
.tabs a.active,.tabs a:hover{color:var(--text);border-color:#2a4a70;background:#152030}
.doc{line-height:1.5;font-size:.9rem}
.doc p{margin:0 0 12px}
.doc ul,.doc ol{margin:0 0 14px;padding-left:1.35rem}
.doc li{margin:4px 0}
.doc blockquote{margin:12px 0;padding:10px 14px;border-left:3px solid #5a4a1e;background:#1a160c;border-radius:0 10px 10px 0;color:var(--warn);font-size:.88rem}
.doc a{color:var(--accent)}
.doc code{font-family:var(--mono);font-size:.8em;background:#0a1018;padding:1px 5px;border-radius:4px}
.doc pre{background:#0a1018;border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow:auto;margin:0 0 14px;font-size:.76rem;line-height:1.4}
.doc pre code{background:none;padding:0;font-size:inherit}
.md-note{font-size:.72rem;color:var(--muted);margin:0 0 6px}
.table-wrap{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel);margin:0 0 16px}
table{width:100%;border-collapse:collapse;min-width:640px}
th,td{padding:8px 10px;text-align:left;font-size:.8rem;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.66rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 18px}
.toc a{font-size:.75rem;padding:5px 10px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;background:#0a1018}
.toc a:hover{color:var(--text);border-color:#2a4a70}
.section-card{margin:18px 0 8px;padding:8px 0}
.src-chip{display:inline-block;font-size:.68rem;color:var(--muted);margin-bottom:6px}
.src-chip code{font-size:.72rem}
footer{margin-top:28px;color:var(--muted);font-size:.8rem;line-height:1.45}
hr{border:none;border-top:1px solid var(--line);margin:22px 0}
"""


def _page(title: str, tab_nav: str, sub: str, body_html: str, *, now_pt: str, toc_links: list[tuple[str, str]]) -> str:
    toc = ""
    if toc_links:
        toc = '<div class="toc">' + "".join(f'<a href="{_esc(h)}">{_esc(lab)}</a>' for h, lab in toc_links) + "</div>"
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="600"/>
<title>OID · {_esc(title)}</title>
<style>
{DOC_CSS}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>{_esc(title)}</h1>
<div class="sub">{sub}</div>
{toc}
<div class="doc">
{body_html}
</div>
<footer>
Research / paper only · Zero RH execution · Alert-only close language.
Sources stay in the desk tree; this page is a readable static mirror for bold-tulip.
Built {_esc(now_pt)}.
</footer>
</div></body></html>
"""


def _section(src_label: str, md: str) -> str:
    return (
        f'<div class="section-card"><div class="src-chip">Source · <code>{_esc(src_label)}</code></div>'
        f"{md_to_html(md)}</div>"
    )


def build_architecture_html(tab_nav: str | None = None, *, now_pt: Optional[str] = None) -> str:
    now_pt = now_pt or datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT")
    tab_nav = tab_nav or make_tab_nav("architecture.html")
    arch = _read(ROOT / "docs" / "QUERY-ARCHITECTURE.md")
    ownership = _ownership_note()
    cutover = _cutover_brief()
    body = (
        _section("docs/QUERY-ARCHITECTURE.md", arch)
        + "<hr/>"
        + _section("market-data/QUERY-DEDUP.md · hal/DUPLICATE-RH-QUOTES.md", ownership)
        + "<hr/>"
        + _section("CUTOVER-20261005.md (brief)", cutover)
    )
    sub = (
        "One-call / many-readers policy · RH quote ownership · cutover snapshot · "
        f"Built {_esc(now_pt)}"
    )
    return _page(
        "Architecture",
        tab_nav,
        sub,
        body,
        now_pt=now_pt,
        toc_links=[
            ("#query-architecture-one-call-many-readers", "Query architecture"),
            ("#query-ownership-notes", "Ownership notes"),
            ("#cutover-status-2026-10-05-pt", "Cutover status"),
            ("setup.html", "Setup page →"),
            ("data-sources.html", "Data sources →"),
        ],
    )


def build_setup_html(tab_nav: str | None = None, *, now_pt: Optional[str] = None) -> str:
    now_pt = now_pt or datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT")
    tab_nav = tab_nav or make_tab_nav("setup.html")
    setup = _read(ROOT / "docs" / "SETUP-VS-PRODUCTION.md")
    api = _read(ROOT / "docs" / "API-INVENTORY.md")
    cutover = _cutover_brief()
    body = (
        _section("docs/SETUP-VS-PRODUCTION.md", setup)
        + "<hr/>"
        + _section("docs/API-INVENTORY.md", api)
        + "<hr/>"
        + _section("CUTOVER-20261005.md (brief)", cutover)
    )
    sub = (
        "What is local vs published production · API inventory · cutover snapshot · "
        f"Built {_esc(now_pt)}"
    )
    return _page(
        "Setup vs production",
        tab_nav,
        sub,
        body,
        now_pt=now_pt,
        toc_links=[
            ("#setup-vs-production-what-is-real", "Setup vs production"),
            ("#api-inventory-what-the-desk-actually-uses", "API inventory"),
            ("#cutover-status-2026-10-05-pt", "Cutover status"),
            ("architecture.html", "Architecture page →"),
            ("data-sources.html", "Data sources →"),
        ],
    )


if __name__ == "__main__":
    dash = Path(__file__).resolve().parent
    (dash / "architecture.html").write_text(build_architecture_html())
    (dash / "setup.html").write_text(build_setup_html())
    print("wrote", dash / "architecture.html")
    print("wrote", dash / "setup.html")
