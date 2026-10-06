#!/usr/bin/env python3
"""Render architecture.html and setup.html with the blotter nav.

The live blotter already publishes these pages on
https://bold-tulip-nejq.here.now/. This module rebuilds them from the desk
markdown so the nav tabs stay on Architecture and Setup. It does not publish.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

NAV = (
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
)

PAGE_CSS = """
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
.table-wrap{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel);margin:0 0 16px}
table{width:100%;border-collapse:collapse;min-width:640px}
th,td{padding:8px 10px;text-align:left;font-size:.8rem;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.66rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}
footer{margin-top:28px;color:var(--muted);font-size:.8rem;line-height:1.45}
"""


def desk_root(root=None) -> Path:
    if root is not None:
        return Path(root).resolve()
    return Path(__file__).resolve().parents[1]


def nav_html(active: str) -> str:
    parts = ['<div class="tabs">']
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        parts.append(f'<a{cls} href="{html.escape(href, quote=True)}">{html.escape(label)}</a>')
    parts.append("</div>")
    return "".join(parts)


def inject_nav(page: str, active: str) -> str:
    """Replace an existing tab strip, or insert one at the start of body."""
    nav = nav_html(active)
    if 'class="tabs"' in page:
        return re.sub(r'<div class="tabs">.*?</div>', nav, page, count=1, flags=re.S)
    if "<body>" in page:
        return page.replace("<body>", "<body>" + nav, 1)
    return nav + page


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "section"


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=True)

    def link(match):
        label, url = match.group(1), match.group(2)
        safe = html.escape(url, quote=True)
        if url.startswith(("http://", "https://", "#", "/")) or url.endswith((".html", ".md")):
            return f'<a href="{safe}">{label}</a>'
        return match.group(0)

    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)
    return escaped


def _table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and set(re.sub(r"[:\- ]", "", "".join(cells))) == set():
            continue
        rows.append(cells)
    if not rows:
        return ""
    head = rows[0]
    body = rows[1:]
    html_rows = ["<thead><tr>" + "".join(f"<th>{_inline(cell)}</th>" for cell in head) + "</tr></thead>"]
    if body:
        html_rows.append("<tbody>")
        for row in body:
            html_rows.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
        html_rows.append("</tbody>")
    return '<div class="table-wrap"><table>' + "".join(html_rows) + "</table></div>"


def markdown_to_html(markdown: str) -> str:
    """Render the desk's markdown subset: headings, lists, tables, quotes, fences."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    blocks = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            fence = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                fence.append(lines[index])
                index += 1
            index += 1
            code = html.escape("\n".join(fence), quote=False)
            blocks.append(f"<pre><code>{code}</code></pre>")
            continue
        if line.startswith("|") and line.rstrip().endswith("|"):
            table = []
            while index < len(lines) and lines[index].startswith("|"):
                table.append(lines[index])
                index += 1
            blocks.append(_table(table))
            continue
        if line.startswith(">"):
            quote = []
            while index < len(lines) and lines[index].startswith(">"):
                quote.append(lines[index][1:].lstrip())
                index += 1
            blocks.append("<blockquote>" + _inline(" ".join(quote)) + "</blockquote>")
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            blocks.append(f'<h{level} id="{_slug(title)}">{_inline(title)}</h{level}>')
            index += 1
            continue
        if re.match(r"^[-*]\s+", line):
            items = []
            while index < len(lines) and re.match(r"^[-*]\s+", lines[index]):
                items.append(re.sub(r"^[-*]\s+", "", lines[index]))
                index += 1
            blocks.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s+", line):
            items = []
            while index < len(lines) and re.match(r"^\d+\.\s+", lines[index]):
                items.append(re.sub(r"^\d+\.\s+", "", lines[index]))
                index += 1
            blocks.append("<ol>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ol>")
            continue
        if not line.strip():
            index += 1
            continue
        para = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() and not _block_start(lines[index]):
            para.append(lines[index].strip())
            index += 1
        blocks.append("<p>" + _inline(" ".join(para)) + "</p>")
    return "\n".join(block for block in blocks if block)


def _block_start(line: str) -> bool:
    return bool(
        line.startswith("```")
        or line.startswith("|")
        or line.startswith(">")
        or line.startswith("#")
        or re.match(r"^[-*]\s+", line)
        or re.match(r"^\d+\.\s+", line)
    )


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        return f"# Missing {relative}\n\nThis source file is not in the desk tree.\n"
    return path.read_text(encoding="utf-8")


def _page(title: str, active: str, sections: list[tuple[str, str]], built_at: str) -> str:
    body = []
    for label, markdown in sections:
        body.append(f'<p class="src-chip"><code>{html.escape(label)}</code></p>')
        body.append(markdown_to_html(markdown))
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style>
</head><body><div class="wrap">
{nav_html(active)}
<div class="doc">
{''.join(body)}
</div>
<footer>
Research / paper only · Zero RH execution · Alert-only close language.
Sources stay in the desk tree; this page is a readable static mirror for bold-tulip.
Built {html.escape(built_at)}.
</footer>
</div></body></html>
"""


def render_architecture(root=None, built_at: str = "2026-10-05") -> str:
    base = desk_root(root)
    sections = [
        ("docs/QUERY-ARCHITECTURE.md", _read(base, "docs/QUERY-ARCHITECTURE.md")),
        ("market-data/QUERY-DEDUP.md", _read(base, "market-data/QUERY-DEDUP.md")),
        ("DUPLICATE-RH-QUOTES.md", _read(base, "DUPLICATE-RH-QUOTES.md")),
        ("CUTOVER-20261005.md", _read(base, "CUTOVER-20261005.md")),
    ]
    return _page("OID · Architecture", "architecture.html", sections, built_at)


def render_setup(root=None, built_at: str = "2026-10-05") -> str:
    base = desk_root(root)
    sections = [
        ("docs/SETUP-VS-PRODUCTION.md", _read(base, "docs/SETUP-VS-PRODUCTION.md")),
        ("docs/API-INVENTORY.md", _read(base, "docs/API-INVENTORY.md")),
        ("CUTOVER-20261005.md", _read(base, "CUTOVER-20261005.md")),
    ]
    return _page("OID · Setup vs production", "setup.html", sections, built_at)
