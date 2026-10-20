#!/usr/bin/env python3
"""Build map.html from the supply-chain SQLite identity store. No invented edges."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "supply-chain" / "supply-chain.db"
FUNDS = {"SPY", "QQQ", "SMH", "EWY"}


def _esc(s: Any) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _load():
    if not DB.exists():
        return [], [], []
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        select e.legal_name, e.country, e.listing_status, e.notes,
               i.ticker, i.share_class, i.exchange
        from entities e
        join instruments i on i.entity_id = e.entity_id
        order by i.ticker
        """
    ).fetchall()
    rels = con.execute(
        """
        select r.edge_type, r.relationship_certainty, r.product_scope,
               r.commitment_stage, r.disclosure_category, r.last_verified_at,
               a.legal_name as from_name, b.legal_name as to_name,
               c.evidence_status, c.locator, c.source_url, c.excerpt
        from relationships r
        join entities a on a.entity_id = r.from_entity_id
        join entities b on b.entity_id = r.to_entity_id
        left join claims c on c.claim_id = coalesce(
            r.supporting_claim_id,
            (select rc.claim_id from relationship_claims rc
              where rc.relationship_id = r.relationship_id and rc.role = 'primary' limit 1))
        order by a.legal_name, r.edge_type, b.legal_name
        """
    ).fetchall()
    sources = con.execute(
        "select source_id, provider, status, last_success_at from sources order by source_id"
    ).fetchall()
    con.close()
    return rows, rels, sources


def build_html(tab_nav: str, now_pt: str | None = None) -> str:
    now_pt = now_pt or datetime.now(PT).strftime("%Y-%m-%d %-I:%M %p PT")
    rows, rels, sources = _load()
    companies = [r for r in rows if r["ticker"] not in FUNDS]
    funds = [r for r in rows if r["ticker"] in FUNDS]

    def name_rows(items):
        out = []
        for r in items:
            note = r["notes"] or ""
            flag = ""
            if "ticker-only" in note:
                flag = "Legal name not verified"
            elif r["exchange"] == "UNVERIFIED":
                flag = "Exchange not verified"
            out.append(
                "<tr>"
                f"<td class='num'>{_esc(r['ticker'])}</td>"
                f"<td>{_esc(r['legal_name'])}</td>"
                f"<td>{_esc(r['share_class'] or '—')}</td>"
                f"<td>{_esc(r['country'] or '—')}</td>"
                f"<td class='notes'>{_esc(flag or '—')}</td>"
                "</tr>"
            )
        return "\n".join(out) or "<tr><td colspan='5' class='empty'>None</td></tr>"

    def _evidence_cell(r) -> str:
        label = " · ".join(x for x in (r["evidence_status"] or r["disclosure_category"], r["locator"]) if x) or "—"
        tip = f" title=\"{_esc(r['excerpt'])}\"" if r["excerpt"] else ""
        if r["source_url"]:
            return f"<td class='notes'{tip}><a href=\"{_esc(r['source_url'])}\" target=\"_blank\" rel=\"noopener\">{_esc(label)}</a></td>"
        return f"<td class='notes'{tip}>{_esc(label)}</td>"

    if rels:
        rel_html = "\n".join(
            "<tr>"
            f"<td>{_esc(r['from_name'])}</td>"
            f"<td>{_esc(r['edge_type'])}</td>"
            f"<td>{_esc(r['to_name'])}</td>"
            f"<td>{_esc(r['relationship_certainty'])}</td>"
            f"<td>{_esc(r['commitment_stage'] or '—')}</td>"
            f"<td class='notes'>{_esc(r['product_scope'] or '—')}</td>"
            + _evidence_cell(r)
            + f"<td class='num'>{_esc(r['last_verified_at'] or '—')}</td>"
            "</tr>"
            for r in rels
        )
        rel_lead = (f"{len(rels)} evidenced edges (primary documents / issuer statements). "
                    "Anything not listed is unknown exposure, not zero; revenue share stays null unless disclosed.")
    else:
        rel_html = "<tr><td colspan='8' class='empty'>No evidenced edges. An empty map is not a failed fetch.</td></tr>"
        rel_lead = "No evidenced customer, supplier, or project edges."

    src_html = "\n".join(
        "<tr>"
        f"<td class='num'>{_esc(s['source_id'])}</td>"
        f"<td>{_esc(s['provider'])}</td>"
        f"<td>{_esc(s['status'])}</td>"
        f"<td>{_esc(s['last_success_at'] or '—')}</td>"
        "</tr>"
        for s in sources
    ) or "<tr><td colspan='4' class='empty'>No source registry</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="300"/>
<title>OID · Map</title>
<style>
:root{{
  --bg:#070b10; --panel:#0e141c; --line:#1a2533;
  --text:#e8eef7; --muted:#7f91a8; --accent:#4da3ff;
  --good:#3dd68c; --warn:#f0b429;
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
td.num{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
td.notes,.empty{{font-size:.78rem;color:var(--muted);line-height:1.35}}
.callout{{margin:14px 0;padding:12px 14px;border:1px solid #5a4a1e;border-radius:12px;background:#1a160c;color:var(--warn);font-size:.9rem}}
footer{{margin-top:20px;color:var(--muted);font-size:.8rem;line-height:1.45}}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>Map · customers and suppliers</h1>
<div class="sub">Tech and chip play identity · Built {_esc(now_pt)} · {len(companies)} companies, {len(funds)} funds, {len(rels)} edges</div>
<div class="callout">{_esc(rel_lead)} Soft color only. This does not open a seat, and it is not a live graph.</div>

<h2>Relationships</h2>
<div class="table-wrap"><table>
<thead><tr><th>From</th><th>Edge</th><th>To</th><th>Certainty</th><th>Stage</th><th>Scope</th><th>Evidence</th><th>Verified</th></tr></thead>
<tbody>
{rel_html}
</tbody></table></div>

<h2>Companies</h2>
<div class="table-wrap"><table>
<thead><tr><th>Ticker</th><th>Name</th><th>Share class</th><th>Country</th><th>Gap</th></tr></thead>
<tbody>
{name_rows(companies)}
</tbody></table></div>

<h2>Funds</h2>
<p class="sub">These are funds, not operating companies. They are not demand.</p>
<div class="table-wrap"><table>
<thead><tr><th>Ticker</th><th>Name</th><th>Share class</th><th>Country</th><th>Gap</th></tr></thead>
<tbody>
{name_rows(funds)}
</tbody></table></div>

<h2>Sources</h2>
<div class="table-wrap"><table>
<thead><tr><th>Id</th><th>Provider</th><th>Status</th><th>Last success</th></tr></thead>
<tbody>
{src_html}
</tbody></table></div>

<footer>
Research / paper only. One Alphabet entity; GOOG is Class C and GOOGL is not listed. Empty edges stay empty until a filing or issuer statement supports them. The suppressed hypothetical capex example is not shown as a company event.
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    nav = '<div class="tabs"><a href="index.html">Blotter</a><a href="data-sources.html">Data sources</a><a href="trader-intel.html">Trader intel</a><a href="catalysts.html">Events</a><a href="soft-grader.html">Soft Grader</a><a href="news-archive.html">News Archive</a><a class="active" href="map.html">Map</a><a href="chart.html">Chart</a></div>'
    out = Path(__file__).resolve().parent / "map.html"
    out.write_text(build_html(nav))
    print("wrote", out)
