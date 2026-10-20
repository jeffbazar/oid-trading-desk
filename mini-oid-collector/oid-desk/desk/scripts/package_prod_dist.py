#!/usr/bin/env python3
"""Package the redesign SPA + local snapshot for production here.now publish (swift-dune).

Copies public UI, embeds static data (snapshot/registry/changes/reviews/prompts),
strips REVIEW chrome, and labels the host as the production OID desk.
Classic dashboard HTML is import input only (not published as site root).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from typing import Optional
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import perf_strip  # noqa: E402  performance strip at top of page (Jeffrey 2026-10-09)
import source_status_spa  # noqa: E402  Data Sources tab + front-page alarm (Jeffrey 2026-10-10)

PROMPTS = {
    "rose": "01-rose-trader-prompt.txt",
    "hal": "02-hal-trader-prompt.txt",
    "macro": "03-macro-bot-prompt.txt",
    "chart": "04-chart-bot-prompt.txt",
    "news": "05-news-alerts-bot-prompt.txt",
}

PROD_INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#08776c"><meta name="description" content="OID paper trading desk: published evidence, trader reviews, source coverage and operating guides.">
  <title>OID · Trading desk</title><link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="styles.css?v={css_v}">
</head>
<body>
  <a class="skip" href="#content">Skip to workspace</a>
  <section class="perf-strip" id="perf-strip" aria-label="Performance totals">{perf_html}</section>
  <div class="mode-bar"><strong>RESEARCH / PAPER</strong><span>Production OID desk · published snapshot</span><a href="#desk">Daily desk</a></div>
  <div class="app">
    <aside class="sidebar">
      <a class="brand" href="#desk"><span class="brand-mark">O</span><span>OID<small>Trading desk</small></span></a>
      <div class="nav-label">WORKSPACE</div>
      <nav aria-label="Main navigation">
        <a href="#desk" data-view="desk" aria-current="page"><span>01</span>Daily desk</a>
        <a href="#evidence" data-view="evidence"><span>02</span>Evidence</a>
        <a href="#journal" data-view="journal"><span>03</span>Trade journal</a>
        <a href="#bots" data-view="bots"><span>04</span>Bot operations</a>
        <a href="#changes" data-view="changes"><span>05</span>Changes</a>
        {src_nav}
      </nav>
      <div class="sidebar-bottom"><span class="dot"></span> Production OID desk<small id="connection-state">Loading production snapshot…</small><button class="text-button" data-action="clocks">Source clocks ↗</button></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><div><span class="muted">Workspace</span><span class="crumb-sep">/</span><strong id="view-name">Daily desk</strong></div><div class="topbar-right"><span id="snapshot-label">Loading snapshot</span><button class="secondary small" data-action="sync" id="sync-button" title="Re-fetch published snapshot (cache-busted)">Refresh snapshot</button></div></header>
      <main id="content" tabindex="-1"><div class="loading">Loading the published desk…</div></main>
      <footer><span>OID · paper decisions and evidence</span><button class="text-button" data-action="clocks">Observation time ≠ page build ≠ review time ↗</button></footer>
    </div>
  </div>
  <dialog id="modal" aria-labelledby="modal-title"><div class="dialog-head"><h2 id="modal-title">Details</h2><button class="icon-button" data-action="close-modal" aria-label="Close details">×</button></div><div id="modal-content"></div></dialog>
  <div class="toast" id="toast" role="status" aria-live="polite" hidden></div>
  <script type="module" src="app.js?v={js_v}"></script>
</body>
</html>
"""



def _inject_static_poll(app_js: str) -> str:
    """Production SPA previously loaded snapshot once and never re-fetched.

    Classic Live Book meta-refreshed every 60s; redesign static boot returned early.
    Inject: cache-bust snapshot fetches, 60s poll while tab visible, Sync reloads snapshot.
    """
    # Cache-bust static asset fetches (CDN max-age=3600 on *.json otherwise sticks).
    old_fetch = "const res=await fetch(target,{cache:'no-store'});"
    new_fetch = (
        "const bust=target+(target.includes('?')?'&':'?')+'t='+Date.now();"
        "const res=await fetch(bust,{cache:'no-store'});"
    )
    if old_fetch not in app_js:
        raise RuntimeError('static fetch anchor missing')
    app_js = app_js.replace(old_fetch, new_fetch, 1)

    # Replace early-return boot with poll (toast once, then quiet reloads).
    old_boot = (
        "if(STATIC_REVIEW){$('#connection-state').textContent='Production snapshot · published desk';"
        "toast('Production OID desk · published snapshot.');return;}"
    )
    new_boot = (
        "if(STATIC_REVIEW){"
        "$('#connection-state').textContent='Production snapshot · auto-refresh 60s';"
        "toast('Production OID desk · published snapshot.');"
        "const poll=async()=>{if(document.hidden)return;try{const changed=await load();"
        "if(changed){$('#connection-state').textContent='Production snapshot · updated';"
        "toast('Published snapshot updated.');}"
        "else{$('#connection-state').textContent='Production snapshot · auto-refresh 60s';}"
        "}catch(e){$('#connection-state').textContent='Snapshot refresh failed · retained data';}};"
        "setInterval(poll,60000);return;}"
    )
    if old_boot not in app_js:
        raise RuntimeError('static boot anchor missing after label rewrite')
    app_js = app_js.replace(old_boot, new_boot, 1)

    # Sync button: re-fetch published snapshot (no local API on static host).
    old_sync = (
        "function sync(){if(STATIC_REVIEW){toast('Snapshot refresh is via desk rebuild → import → publish (swift-dune).');return;}"
    )
    # sync may be async function
    if old_sync not in app_js:
        old_sync = (
            "async function sync(){if(STATIC_REVIEW){toast('Snapshot refresh is via desk rebuild → import → publish (swift-dune).');return;}"
        )
        new_sync = (
            "async function sync(){if(STATIC_REVIEW){const button=$('#sync-button');"
            "if(button){button.disabled=true;button.textContent='Refreshing…';}"
            "try{const changed=await load();"
            "toast(changed?'Published snapshot updated.':'Still on latest published snapshot.');"
            "$('#connection-state').textContent=changed?'Production snapshot · updated':'Production snapshot · auto-refresh 60s';"
            "}catch(e){toast('Refresh failed: '+e.message);}finally{"
            "if(button){button.disabled=false;button.textContent='Refresh snapshot';}}return;}"
        )
    else:
        new_sync = (
            "function sync(){if(STATIC_REVIEW){(async()=>{const button=$('#sync-button');"
            "if(button){button.disabled=true;button.textContent='Refreshing…';}"
            "try{const changed=await load();"
            "toast(changed?'Published snapshot updated.':'Still on latest published snapshot.');"
            "$('#connection-state').textContent=changed?'Production snapshot · updated':'Production snapshot · auto-refresh 60s';"
            "}catch(e){toast('Refresh failed: '+e.message);}finally{"
            "if(button){button.disabled=false;button.textContent='Refresh snapshot';}}})();return;}"
        )
    if old_sync not in app_js:
        raise RuntimeError('static sync anchor missing')
    app_js = app_js.replace(old_sync, new_sync, 1)

    # Enable Sync button in packaged index is separate; also unlock if present in JS-built chrome.
    app_js = app_js.replace(
        'disabled title="Refresh via rebuild → import → publish on the desk">Publish refresh only</button>',
        'title="Re-fetch published snapshot (cache-busted)">Refresh snapshot</button>',
    )
    return app_js


def build_prod_app_js(review_app: str, public_app: str) -> str:
    """Prefer review-dist static plumbing (already proven), rewrite REVIEW → production labels.

    Falls back to public-only if review-dist is missing.
    """
    if "STATIC_REVIEW" in review_app and "STATIC_MAP" in review_app:
        text = review_app
        replacements = [
            ("/* STATIC REVIEW BUILD — read-only here.now publish; production bold-tulip untouched */\nconst STATIC_REVIEW = true;",
             "/* STATIC PRODUCTION BUILD — here.now swift-dune-cs3e (OID desk) */\nconst STATIC_HOST = true;\nconst STATIC_REVIEW = true; /* alias: static host read-only plumbing */"),
            ("Static REVIEW site is read-only (no local API writes).",
             "Production static host is read-only (refresh via desk publish)."),
            ("Static REVIEW has no endpoint for ",
             "Production static host has no endpoint for "),
            ("REVIEW asset missing (",
             "Production asset missing ("),
            ("REVIEW static snapshot · read-only",
             "Production snapshot · published desk"),
            ("Sync disabled on static REVIEW host. Production bold-tulip was not touched.",
             "Snapshot refresh is via desk rebuild → import → publish (swift-dune)."),
            ("REVIEW site · production bold-tulip unchanged.",
             "Production OID desk · published snapshot."),
            ("document.title='OID · REVIEW · '+labels[state.view];",
             "document.title='OID · '+labels[state.view];"),
            ("New local workspace · original production remains unchanged",
             "Production OID desk · redesign SPA on swift-dune"),
            ("Source: bold-tulip-nejq.here.now · seven HTML pages and the published Peanut JSON feed.",
             "Snapshot imported from local rebuilt classic dashboard pages · Peanut JSON included."),

            ("(STATIC_REVIEW?'REVIEW · ':'')+'Page built '",
             "(STATIC_REVIEW?'':'')+'Page built '"),
            ("disabled title=\"Sync disabled on static REVIEW host\">Sync disabled (REVIEW)</button>",
             "disabled title=\"Refresh via rebuild → import → publish on the desk\">Publish refresh only</button>"),
        ]
        for a, b in replacements:
            text = text.replace(a, b)
        # Ensure STATIC_HOST is used where STATIC_REVIEW alone gated sync/boot (already true via alias)
        if "const STATIC_HOST" not in text:
            text = text.replace("const STATIC_REVIEW = true;", "const STATIC_HOST = true;\nconst STATIC_REVIEW = true;", 1)
        text = _inject_static_poll(text)
        return text

    raise RuntimeError("review-dist app.js with STATIC_REVIEW expected for packaging")


def copy_downloads(root: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    mapping = [
        (root / "docs" / "00-source-and-cadence-guide.txt", "00-source-and-cadence-guide.txt"),
        (root / "docs" / "API.md", "API.md"),
        (root / "docs" / "production-audit.md", "production-audit.md"),
        (root / "docs" / "trader-alignment-and-goals.txt", "trader-alignment-and-goals.txt"),
    ]
    for src, name in mapping:
        if src.is_file():
            shutil.copy2(src, dest / name)
    for filename in PROMPTS.values():
        src = root / "prompts" / filename
        if src.is_file():
            shutil.copy2(src, dest / filename)
    csv_path = dest / "trades.csv"
    if not csv_path.exists():
        csv_path.write_text("id,symbol,contract,status\n", encoding="utf-8")


def write_prompt_json(root: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for bot, filename in PROMPTS.items():
        src = root / "prompts" / filename
        text = src.read_text(encoding="utf-8") if src.is_file() else f"(missing {filename})"
        (dest / f"{bot}.json").write_text(
            json.dumps({"bot": bot, "filename": filename, "text": text}, ensure_ascii=False),
            encoding="utf-8",
        )



# --- Chart Bot plain-English reads (2026-10-07, Jeffrey) ---------------------------------
# Evidence -> Chart banner shows the newest read from chart-bot/observations/reads/index.json
# (snapshot.chart_reads, injected below); older reads are archived newest-first under it.
CHART_BANNER_OLD = (
    "${state.topic==='chart'?'<div class=\"notice info\"><div><strong>Daily chart snapshot · forecasts unavailable</strong>"
    "<small>Production computed split-adjusted daily structure for 37 symbols. No weekday chart collector is installed.</small>"
    "</div></div>':''}"
)
CHART_BANNER_NEW = "${state.topic==='chart'?chartReadBanner()+chartSetups4hSection()+chartLevelsSection():''}"
CHART_BANNER_FN = (
    "function chartReadBanner(){const rs=(state.snapshot&&state.snapshot.chart_reads)||[];"
    "const para=r=>(r.paragraphs||[]).map(x=>`<p style=\"margin:6px 0 0;font-size:13px;line-height:1.5;color:var(--text,#1d2b26)\">"
    "${x.lead?`<strong>${esc(x.lead)}</strong> `:''}${esc(x.body)}</p>`).join('');"
    "if(!rs.length)return '<div class=\"notice info\"><div><strong>Chart read not published yet</strong>"
    "<small>Forecasts unavailable · soft observation only · never elevates</small></div></div>';"
    "const l=rs[0],old=rs.slice(1);"
    "return `<div class=\"notice info chart-read\" style=\"display:block\"><div><strong style=\"font-size:14px\">Latest chart read — ${esc(l.title)}</strong>${para(l)}"
    "<small style=\"margin-top:8px\">Forecasts unavailable · soft observation only · never elevates · Chart Bot daily routine (Robinhood daily bars, CB-DAILY-V1)</small></div></div>`"
    "+(old.length?`<section class=\"section chart-reads-archive\"><div class=\"section-head\"><h2>Earlier chart reads</h2><small>${old.length} archived · newest first</small></div>"
    "<div class=\"section-body source-notes\">${old.map(r=>`<details><summary>${esc(r.title)}</summary>${para(r)}</details>`).join('')}</div></section>`:'');}\n"
)


def inject_chart_reads_js(app_js: str) -> tuple[str, str]:
    if CHART_BANNER_OLD not in app_js:
        return app_js, "WARN chart banner anchor missing; chart reads banner not injected"
    app_js = app_js.replace(CHART_BANNER_OLD, CHART_BANNER_NEW, 1)
    anchor = "function renderEvidence(){"
    if anchor not in app_js:
        raise RuntimeError("renderEvidence anchor missing for chartReadBanner injection")
    app_js = app_js.replace(anchor, CHART_BANNER_FN + CHART_LEVELS_FN + CHART_SETUPS4H_FN + anchor, 1)
    return app_js, "ok"


# 2026-10-08: Evidence -> Company map notice reflects Customer/Supplier Bot edges from the map page
# (dashboard/map_page.py <- supply-chain/supply-chain.db). Replaces the static "relationships not populated" banner.
MAP_NOTICE_OLD = (
    "${state.topic==='map'?'<div class=\"notice info\"><div><strong>Company identities available · relationships not populated</strong>"
    "<small>Preserves the production Map; reported news exposure appears in the context panel.</small></div></div>':''}"
)
MAP_NOTICE_NEW = "${state.topic==='map'?mapEvidenceNotice():''}"
MAP_NOTICE_FN = (
    "function mapEvidenceNotice(){const rel=sections('map').find(s=>/^Relationships$/i.test(s.title||''));"
    "const n=((rel&&rel.rows)||[]).filter(r=>!isPlaceholder(r)).length;"
    "if(!n)return '<div class=\"notice info\"><div><strong>Company identities available · relationships not populated</strong>"
    "<small>Empty edges are unknown exposure, not a failed fetch. Reported news exposure appears in the context panel.</small></div></div>';"
    "return `<div class=\"notice info\"><div><strong>Customer/Supplier map · ${n} evidenced edges · soft only</strong>"
    "<small>Customer/Supplier Bot · primary documents / issuer statements only (Evidence column links the source; inspect a row for the full record). "
    "Anything not listed is unknown exposure, not zero. Revenue share null unless disclosed. GOOG Class C only. Never elevates a trade.</small></div></div>`;}\n"
)


def inject_map_notice_js(app_js: str) -> tuple[str, str]:
    if MAP_NOTICE_OLD not in app_js:
        return app_js, "WARN map notice anchor missing; static map banner kept"
    app_js = app_js.replace(MAP_NOTICE_OLD, MAP_NOTICE_NEW, 1)
    anchor = "function renderEvidence(){"
    if anchor not in app_js:
        return app_js, "WARN renderEvidence anchor missing for map notice"
    app_js = app_js.replace(anchor, MAP_NOTICE_FN + anchor, 1)
    return app_js, "ok"


def load_chart_reads(root: Path) -> list[dict]:
    import importlib.util
    path = root / "chart-bot" / "chart_reads.py"
    if not path.is_file():
        return []
    spec = importlib.util.spec_from_file_location("chart_reads", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reads = mod.load_reads()
    for r in reads:
        r["title"] = mod.title_for(r)
        r.pop("text", None)
    return reads

# --- Chart Bot Levels & Patterns (CB-LEVELS-V1, 2026-10-08, Jeffrey) ------------------------
# snapshot.chart_levels = slim copy of chart-bot/levels/latest/levels.json; PNGs -> dist/levels/img/.
CHART_LEVELS_FN = (
    "function chartLevelsSection(){const L=state.snapshot&&state.snapshot.chart_levels;if(!L||!(L.names||[]).length)return '';"
    "const f=v=>v==null?'—':(+v>=1000?(+v).toLocaleString(undefined,{maximumFractionDigits:0}):(+v).toFixed(2));"
    "const pc=st=>/broken/.test(st)?'negative':/extended|premium/.test(st)?'warning':/buy zone|pullback|deep/.test(st)?'':'neutral';"
    "const z=b=>b?`${f(b.lo)}–${f(b.hi)}`:'—';"
    "const rows=L.names.map(n=>`<tr><td><strong>${esc(n.symbol)}</strong><small>${f(n.close)}</small></td>"
    "<td><span class=\"pill ${pc(n.stance)}\">${esc(n.stance)}</span><small>CB-DAILY ${esc(n.trend||'—')}</small></td>"
    "<td class=\"numeric\">${(n.r||[]).map(f).join(' / ')||'—'}</td><td class=\"numeric\">${(n.s||[]).map(f).join(' / ')||'—'}</td>"
    "<td class=\"numeric\">${z(n.buy)}${n.pull?`<small>pullback ${z(n.pull)}</small>`:''}</td><td class=\"numeric\">${f(n.inv)}</td>"
    "<td class=\"numeric\">${f(n.sma200w)}</td><td>${esc(n.pattern||'—')}</td></tr>`).join('');"
    "const cards=L.names.map(n=>`<details><summary><strong>${esc(n.symbol)}</strong> · ${esc(n.stance)} · ${esc(n.pattern||'')}</summary>"
    "<p style=\"color:var(--ink);font-size:12px;line-height:1.6\">${esc(n.read)}</p>"
    "${n.img?`<a href=\"${esc(n.img)}\" target=\"_blank\" rel=\"noopener\"><img loading=\"lazy\" src=\"${esc(n.img)}\" alt=\"${esc(n.symbol)} weekly and daily levels chart\" style=\"width:100%;max-width:1100px;border-radius:6px;margin-top:8px;background:#0e1512\"></a>`:''}</details>`).join('');"
    "return `<section class=\"section chart-levels\" style=\"margin-bottom:18px\"><div class=\"section-head\"><h2>Levels &amp; patterns</h2>"
    "<small>${esc(L.config_version)} · as of ${esc(L.as_of_session)} close · computed ${esc(L.calculated_at_pt||'')}<br>soft stance labels · not orders · never elevates</small></div>"
    "<div class=\"section-body\"><p style=\"font-size:12px;line-height:1.6\">${esc(L.summary||'')}</p></div>"
    "<div class=\"table-scroll\"><table><thead><tr><th>Name</th><th>Stance</th><th>Resistance</th><th>Support</th><th>Buy zone (0.5–0.618)</th><th>Invalidation</th><th>200-wk MA</th><th>Pattern</th></tr></thead><tbody>${rows}</tbody></table></div>"
    "<div class=\"section-body source-notes\"><p style=\"margin-top:12px\">Per-name reads and annotated charts (weekly ~3y + daily ~9mo). Click to expand.</p>${cards}"
    "<p>${esc(L.method_note||'')}</p></div></section>`;}\n"
)


CHART_SETUPS4H_FN = 'function chartSetups4hSection(){const S=state.snapshot&&state.snapshot.chart_setups_4h;if(!S||!(S.names||[]).length)return \'\';const f=v=>v==null?\'—\':(+v>=1000?(+v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}):(+v).toFixed(2));const pc=st=>/breakdown|downtrend/.test(st)?\'negative\':/breakout|impulse up|uptrend/.test(st)?\'\':/consolidation/.test(st)?\'warning\':\'neutral\';const tl=a=>(a||[]).slice(0,3).map(f).join(\' / \')||\'—\';const dn=a=>(a||[]).slice(0,3).map(t=>`${esc(t.label)} ${f(t.price)}`).join(\' / \')||\'—\';const gx=o=>{if(!o)return \'—\';const t=(o.gex||[]).slice(0,3).map(g=>`${g.k} (+$${g.m}M)`).join(\', \');return (t||\'\')+(o.cw!=null?`${t?\'; \':\'\'}call wall ${o.cw}`:\'\')+(o.pw!=null?` · put wall ${o.pw}`:\'\')+(o.flip!=null?` · flip ${f(o.flip)}`:\'\')||\'—\';};const iv=o=>o&&o.iv30!=null?`${(o.iv30*100).toFixed(1)}% (${esc(o.ivt||\'?\')}${o.cov?\'\':\', outside UW coverage list\'})`:\'—\';const best=new Set(S.best||[]);const rows=S.names.map(n=>`<tr><td><strong>${esc(n.symbol)}</strong>${best.has(n.symbol)?\' <span class="pill">top</span>\':\'\'}<small>${f(n.spot)}${n.live?\' live\':\'\'}</small></td><td><span class="pill ${pc(n.stage)}">${esc(n.stage)}</span><small>score ${n.score}</small></td><td class="numeric">${n.box?`${f(n.box.bottom)}–${f(n.box.top)}<small>${n.box.sessions} sess</small>`:\'—\'}</td><td class="numeric">${f(n.vah)} / ${f(n.poc)} / ${f(n.val)}</td><td class="numeric">&gt; ${f(n.bull)}<small>${tl(n.bull_t)}${n.main?` → ${f(n.main)}`:\'\'}</small></td><td class="numeric">&lt; ${f(n.bear)}<small>${dn(n.bear_t)}</small></td><td class="numeric">${n.vr==null?\'—\':n.vr.toFixed(2)}</td><td><small>${gx(n.opt)}</small></td></tr>`).join(\'\');const lvl=n=>`<table style="font-size:12px;margin-top:8px"><tbody><tr><td>Stage / score</td><td>${esc(n.stage)} · ${n.score}</td><td>SMA50 / SMA200 (4h)</td><td class="numeric">${f(n.sma50)} / ${f(n.sma200)}</td></tr><tr><td>Box</td><td class="numeric">${n.box?`${f(n.box.bottom)}–${f(n.box.top)} (${n.box.sessions} sessions, ${n.box.height_atr}× ATR)`:\'—\'}</td><td>VAH / POC / VAL (30 sess)</td><td class="numeric">${f(n.vah)} / ${f(n.poc)} / ${f(n.val)}</td></tr><tr><td>Support zone</td><td class="numeric">${n.sup?`${f(n.sup[0])}–${f(n.sup[1])}`:\'—\'}</td><td>Trendline</td><td>${esc(n.tl||\'—\')}</td></tr><tr><td>Impulse</td><td>${esc(n.imp||\'—\')}</td><td>Up/down vol</td><td class="numeric">${n.vr==null?\'—\':n.vr.toFixed(2)}</td></tr><tr><td>Bull trigger → targets</td><td class="numeric">&gt; ${f(n.bull)} (${esc(n.bull_b||\'\')}) → ${tl(n.bull_t)}${n.main?` → range high ${f(n.main)}`:\'\'}</td><td>Bear trigger → downside</td><td class="numeric">&lt; ${f(n.bear)} (${esc(n.bear_b||\'\')}) → ${dn(n.bear_t)}</td></tr><tr><td>Options (soft)</td><td colspan="3">${gx(n.opt)} · IV30 ${iv(n.opt)}</td></tr></tbody></table>`;const cards=S.names.map(n=>`<details><summary><strong>${esc(n.symbol)}</strong> · ${esc(n.stage)} · score ${n.score} · bull &gt; ${f(n.bull)} · bear &lt; ${f(n.bear)}</summary><p style="color:var(--ink);font-size:12px;line-height:1.6">${esc(n.read)}</p>${lvl(n)}${n.img?`<a href="${esc(n.img)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(n.img)}" alt="${esc(n.symbol)} 4-hour setup chart" style="width:100%;max-width:1100px;border-radius:6px;margin-top:8px;background:#fff;border:1px solid #ddd"></a>`:\'\'}</details>`).join(\'\');return `<section class="section chart-setups-4h" style="margin-bottom:18px"><div class="section-head"><h2>4-hour setups</h2><small>${esc(S.config_version)} · as of ${esc(S.as_of_pt||\'\')}${S.live?\' (last 4h bar live)\':\'\'} · CoinForge-style · soft research only · not orders · never elevates</small></div><div class="section-body"><p style="font-size:12px;line-height:1.6"><strong>Desk summary.</strong> ${esc(S.summary||\'\')}</p></div><div class="table-scroll"><table><thead><tr><th>Name</th><th>Stage</th><th>Box</th><th>VAH / POC / VAL</th><th>Bull trigger → targets</th><th>Bear trigger → downside</th><th>Up/down vol</th><th>Options (FlashAlpha)</th></tr></thead><tbody>${rows}</tbody></table></div><div class="section-body source-notes"><p style="margin-top:12px">Per-name 4h reads, level tables and charts. Click to expand.</p>${cards}<p>${esc(S.method_note||\'\')}</p></div></section>`;}\n'


def load_focus_watch(root: Path, data_dir: Path) -> Optional[dict]:
    """5s spot-vs-wall focus watch (Jeffrey 2026-10-09): slim readings + today's events into the
    snapshot and data/focus-watch.json. Data only (no SPA section yet). Never breaks the publish."""
    try:
        src = root / "cache" / "focus-watch.json"
        if not src.is_file():
            return None
        w = json.loads(src.read_text(encoding="utf-8"))
        evp = root / "cache" / "focus-watch-events.jsonl"
        evs = []
        if evp.is_file():
            for line in evp.read_text(encoding="utf-8").splitlines()[-200:]:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("session_date") == w.get("session_date"):
                    evs.append({k: e.get(k) for k in ("ts_pt", "symbol", "event", "severity", "level",
                                                     "level_price", "spot", "note")})
        slim = {"as_of_pt": w.get("as_of_pt"), "state": w.get("state"), "session": w.get("session"),
                "focus_symbols": w.get("focus_symbols"),
                "readings": {s: {"spot": r.get("spot"), "flags": r.get("flags"), "seats": r.get("seats"),
                                 "levels": [{k: l.get(k) for k in ("name", "price", "dist", "dist_pct", "side")}
                                            for l in r.get("levels") or []],
                                 "last_5m_close": ((r.get("bar5") or {}).get("last_close") or {}).get("c"),
                                 "rvol": r.get("rvol")}
                             for s, r in (w.get("readings") or {}).items()},
                "events": evs[-40:], "mandate": "research/paper only - alerts, never orders"}
        (data_dir / "focus-watch.json").write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
        return slim
    except Exception:  # noqa: BLE001
        return None


def load_intraday_bars(root: Path, data_dir: Path) -> Optional[dict]:
    """5m/15m bars + RVOL (quotes/mini_bars.py, Jeffrey 2026-10-10): per-name session RVOL + last bars into
    the snapshot and data/intraday-bars.json. Equities only, source tagged (alpaca-sip | rh). Data only
    (no SPA section yet). Never breaks the publish."""
    try:
        src = root / "cache" / "bars" / "summary.json"
        if not src.is_file():
            return None
        rec = json.loads(src.read_text(encoding="utf-8"))
        keep = ("session_date", "source", "prior_sessions", "session_volume", "session_rvol", "rvol_label",
                "recent30_rvol", "last_bar_et", "last_bar_pt", "last_close", "last_bar_rvol", "stale")
        bar = ("et", "pt", "o", "h", "l", "c", "v", "bar_rvol", "cum_rvol", "src", "partial")
        slim = {"as_of_pt": rec.get("generated_pt"), "session": rec.get("session"), "primary": rec.get("primary"),
                "fallback": rec.get("fallback"), "mini_ok": (rec.get("mini") or {}).get("ok"),
                "symbols": {s: {**{k: v.get(k) for k in keep},
                                "last5": {k: (v.get("last5") or {}).get(k) for k in bar} if v.get("last5") else None,
                                "last15": {k: (v.get("last15_complete") or {}).get(k) for k in bar} if v.get("last15_complete") else None}
                            for s, v in (rec.get("symbols") or {}).items()},
                "rule": "wall break = 5m close through + next 15m close holds + break-bar RVOL >= 1.5 (quotes/mini_bars.py break)",
                "mandate": "research/paper only - not an order"}
        (data_dir / "intraday-bars.json").write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
        return slim
    except Exception:  # noqa: BLE001
        return None


def load_chart_setups_4h(root: Path, dist: Path) -> Optional[dict]:
    """Slim 4h-setups payload for the SPA; copies PNGs into dist/setups_4h/img/."""
    latest = root / "chart-bot" / "setups_4h" / "latest"
    src = latest / "setups.json"
    if not src.is_file():
        return None
    d = json.loads(src.read_text(encoding="utf-8"))
    img_out = dist / "setups_4h" / "img"
    img_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dist / "setups_4h" / "setups.json")
    order = {s: i for i, s in enumerate((d.get("desk_summary") or {}).get("best") or [])}
    rows = sorted(d.get("names") or [], key=lambda n: (order.get(n["symbol"], 99), -(n.get("setup_score") or 0), n["symbol"]))
    names, live = [], False
    for n in rows:
        sym = n["symbol"]
        png = latest / "img" / f"{sym}.png"
        img = None
        if png.is_file():
            shutil.copy2(png, img_out / f"{sym}.png")
            img = f"setups_4h/img/{sym}.png?v={_asset_bust(png.read_bytes())}"
        vp = n.get("volume_profile") or {}
        op = n.get("options") or {}
        ivd = op.get("iv") or {}
        imp = n.get("impulse")
        tlr = n.get("trendline")
        live = live or bool(n.get("last_bar_live"))
        names.append({
            "symbol": sym, "spot": n.get("spot"), "live": n.get("last_bar_live"), "stage": n.get("stage"),
            "score": n.get("setup_score"), "sma50": n.get("sma50"), "sma200": n.get("sma200"),
            "box": n.get("box"), "vah": vp.get("vah"), "poc": vp.get("poc"), "val": vp.get("val"),
            "sup": [n["support_zone"]["lo"], n["support_zone"]["hi"]] if n.get("support_zone") else None,
            "tl": (f"{tlr['dir']} {tlr['p0']}→{tlr['p1']}, now ~{tlr['now']} ({tlr['quality']})" if tlr else None),
            "imp": (f"{imp['chg_pct']:+.2f}% / {imp['chg']:+,.2f} ({imp['p0']}→{imp['p1']})" if imp else None),
            "vr": n.get("vol_ratio_up_down"),
            "bull": n.get("bull_trigger"), "bull_b": n.get("bull_trigger_basis"), "bull_t": n.get("bull_targets"),
            "main": n.get("main_target"), "bear": n.get("bear_trigger"), "bear_b": n.get("bear_trigger_basis"),
            "bear_t": n.get("bear_targets"),
            "opt": {"gex": [{"k": f"{t['strike']:g}", "m": round(t["net_gex"] / 1e6)} for t in (op.get("top_pos_gex_above") or [])[:4]],
                    "cw": op.get("call_wall"), "pw": op.get("put_wall"),
                    "flip": op.get("gamma_flip"), "iv30": ivd.get("iv30"), "ivt": ivd.get("trend_1w"),
                    "cov": ivd.get("uw_coverage_listed")},
            "read": n.get("read"), "img": img,
        })
    ds = d.get("desk_summary") or {}
    return {
        "config_version": d.get("config_version"), "as_of_pt": d.get("as_of_pt"), "live": live,
        "summary": ds.get("text"), "best": ds.get("best"), "weakest": ds.get("weakest"),
        "method_note": "Method: Robinhood 30-minute regular-session split-adjusted bars aggregated to TradingView-style 4h "
                       "(09:30–13:30 / 13:30–16:00 ET; last bar marked live). SMA50/200 on 4h closes; box = longest recent "
                       "6–40-bar window within min(4×ATR, 9%); volume profile from 30m bars over 30 sessions (70% value area); "
                       "support = clustered fractal lows; fib = impulse 1.272/1.618 extensions + 0.618/0.71/0.786 retracement of "
                       "the prior down-leg; up/down volume since box start. Options: FlashAlpha get_gex/get_levels, UW screener IV30 "
                       "(soft color). Full method: chart-bot/SETUPS_4H.md · JSON: setups_4h/setups.json.",
        "names": names,
    }


def load_chart_levels(root: Path, dist: Path) -> Optional[dict]:
    """Slim levels payload for the SPA; copies PNGs into dist/levels/img/."""
    latest = root / "chart-bot" / "levels" / "latest"
    src = latest / "levels.json"
    if not src.is_file():
        return None
    d = json.loads(src.read_text(encoding="utf-8"))
    img_out = dist / "levels" / "img"
    img_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dist / "levels" / "levels.json")
    names = []
    for n in d.get("names") or []:
        sym = n["symbol"]
        png = latest / "img" / f"{sym}.png"
        img = None
        if png.is_file():
            shutil.copy2(png, img_out / f"{sym}.png")
            img = f"levels/img/{sym}.png?v={_asset_bust(png.read_bytes())}"
        fib = n.get("fib") or {}
        pats = [p["name"] + (f" ({p['confidence']})" if p.get("confidence") not in (None, "n/a") else "")
                for p in (n.get("patterns") or []) if p.get("name") != "no clean pattern"]
        names.append({
            "symbol": sym, "close": n.get("close"), "stance": n.get("stance"),
            "trend": n.get("daily_trend_cb_daily_v1"),
            "r": [x["price"] for x in (n.get("sr") or {}).get("resistance", [])[:2]],
            "s": [x["price"] for x in (n.get("sr") or {}).get("support", [])[:2]],
            "buy": fib.get("buy_zone"), "pull": n.get("pullback_zone"),
            "inv": n.get("invalidation"), "sma200w": n.get("sma200_weekly"),
            "pattern": pats[0] if pats else "no clean pattern",
            "read": n.get("read"), "img": img,
        })
    return {
        "config_version": d.get("config_version"), "as_of_session": d.get("as_of_session"),
        "calculated_at_pt": d.get("calculated_at_pt"),
        "summary": (d.get("desk_summary") or {}).get("text"),
        "method_note": "Method: Robinhood weekly + daily split-adjusted bars only. Weekly zigzag pivots; S/R = clustered fractal pivots "
                       "(weekly + daily, ATR tolerance); buy zone = 0.5–0.618 retracement of the major cycle swing (104-wk high vs lowest low "
                       "in the 78 wks before it); pullback zone = same on the latest weekly zigzag up-leg; channel = 90-day log-linear "
                       "regression with 10/90% residual rails; invalidation = latest confirmed daily zigzag swing low. No Elliott Wave. "
                       "Full JSON: levels/levels.json.",
        "names": names,
    }


# --- Whale Flow (CB-WHALE-V1, 2026-10-09, Jeffrey) -------------------------------------------
# Evidence -> "Whale flow" tab. Data: chart-bot/whale-flow/latest/summary.json written by
# chart-bot/whale-flow/whale_flow.py (UW flow-alerts collector, 60s RTH). Soft research only.
WHALE_FN = r"""function whaleFlowSection(){const W=state.snapshot&&state.snapshot.whale_flow;
if(!W)return '<section class="section"><div class="empty">Whale flow not collected yet.</div></section>';
if(!window.__wfWired){window.__wfWired=1;window.__wfMin=window.__wfMin||0;
document.addEventListener('click',e=>{const b=e.target.closest('[data-wf-min],[data-wf-tk]');if(!b)return;e.preventDefault();e.stopPropagation();
if(b.dataset.wfMin!=null)window.__wfMin=+b.dataset.wfMin;if(b.dataset.wfTk!=null)state.ticker=b.dataset.wfTk;updateRoute();render();},true);
setInterval(()=>{document.querySelectorAll('[data-wf-ts]').forEach(el=>{const s=(Date.now()-Date.parse(el.dataset.wfTs))/1000;el.textContent=wfAgo(s);
const tr=el.closest('tr');if(tr){tr.classList.toggle('wf-recent',s<900);}});},15000);}
const m=v=>{v=+v||0;const a=Math.abs(v);return (v<0?'−':'')+'$'+(a>=1e6?(a/1e6).toFixed(2)+'M':a>=1e3?(a/1e3).toFixed(0)+'K':a.toFixed(0));};
const n2=v=>v==null?'—':(+v>=1000?(+v).toLocaleString(undefined,{maximumFractionDigits:0}):(+v).toFixed(2).replace(/\.00$/,''));
const lp=l=>`<span class="pill ${l==='bullish'?'':l==='bearish'?'negative':'neutral'}">${esc(l)}</span>`;
const tk=state.ticker,mn=window.__wfMin||0;const fl=a=>(a||[]).filter(r=>(!tk||r.ticker===tk)&&(+r.premium>=mn));
const now=Date.now();const age=r=>(now-Date.parse(r.created_at))/1000;
const big=r=>+r.premium>=(/^(SPY|QQQ)$/.test(r.ticker)?(W.big_etf_min||5e6):(W.big_min||1e6));
const sty=r=>{const rec=age(r)<900;return `class="${rec?'wf-recent':''}" style="${big(r)?'box-shadow:inset 4px 0 0 #c9861a;':''}"`;};
const ctr=r=>`${esc((r.type||'').toUpperCase().slice(0,1))} ${n2(r.strike)}<small>${esc(r.expiry)}${r.dte==null?'':' · '+r.dte+'d'}</small>`;
const row=r=>`<tr ${sty(r)}><td class="numeric"><strong>${esc(r.time_pt)}</strong><small data-wf-ts="${esc(r.created_at)}">${wfAgo(age(r))}</small></td><td><strong>${esc(r.ticker)}</strong><small>spot ${n2(r.spot)}</small></td>
<td>${ctr(r)}</td><td>${esc(r.side)}<small>${esc(r.kind)}${r.combo?' · other leg: '+esc(r.combo):''}</small></td><td class="numeric">${(+r.size).toLocaleString()} @ ${n2(r.price)}</td>
<td class="numeric">${big(r)?'<strong style="color:#a8650a">'+m(r.premium)+'</strong>':m(r.premium)}</td><td>${(r.badge||(r.opening?'opening':'size ≤ OI'))==='opening'?'<span class="pill">opening</span>':(r.badge==='likely closing'?'<span class="pill neutral">likely closing</span>':'<span class="pill neutral" style="opacity:.75">size ≤ OI</span>')}<small>${(+r.size).toLocaleString()} vs OI ${(+r.oi||0).toLocaleString()}</small></td>
<td>${lp(r.lean)}</td><td><small>${(r.tags||[]).map(esc).join(' · ')||'—'}</small></td></tr>`;
const th='<thead><tr><th>Time PT</th><th>Ticker</th><th>Contract</th><th>Side / type</th><th>Size @ px</th><th>Premium</th><th>Opening / closing</th><th>Lean</th><th>vs our levels (soft)</th></tr></thead>';
const tape=fl(W.tape||W.newest).slice(0,60),top=fl(W.top).slice(0,25);
const n15=(W.tape||[]).filter(r=>age(r)<900&&(!tk||r.ticker===tk)).length;
const chips=[0,250000,1000000,5000000].map(v=>`<button class="${mn===v?'active':''}" aria-pressed="${mn===v}" data-wf-min="${v}">${v?'≥ '+m(v):'All sizes'}</button>`).join('');
const tchips=['',...(W.tickers||[]).slice(0,14).map(b=>b.ticker)].map(t=>`<button class="${(tk||'')===t?'active':''}" data-wf-tk="${t}">${t||'All tickers'}</button>`).join('');
const ts=(W.tickers||[]).filter(b=>!tk||b.ticker===tk).map(b=>`<tr><td><strong>${esc(b.ticker)}</strong><small>spot ${n2(b.spot)}</small></td><td class="numeric">${b.n}</td>
<td class="numeric">${esc(b.last_pt||'—')}<small data-wf-ts="${esc(b.last||'')}">${b.last?wfAgo((now-Date.parse(b.last))/1000):''}</small></td><td class="numeric"><small>${esc(b.first_pt||'—')}</small></td>
<td class="numeric">${m(b.call_prem)}</td><td class="numeric">${m(b.put_prem)}</td><td class="numeric">${m(b.bull_prem)}</td><td class="numeric">${m(b.bear_prem)}</td>
<td class="numeric">${m(b.net_dir_prem)}</td><td class="numeric"><small>${m(b.closing_prem||0)}</small></td><td>${lp(b.lean)}</td></tr>`).join('');
return `<style>.wf-recent td{background:rgba(8,119,108,.09)}.wf-chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.wf-chips button{font-size:12px;padding:3px 9px;border-radius:999px;border:1px solid var(--line,#ccd);background:transparent;cursor:pointer}.wf-chips button.active{background:#08776c;color:#fff;border-color:#08776c}</style>
<div class="notice info"><div><strong>Whale flow · ${esc(W.session_date)} · as of ${esc(W.as_of_pt)} (<span data-wf-ts="${esc(W.as_of_iso||'')}">${W.as_of_iso?wfAgo((now-Date.parse(W.as_of_iso))/1000):''}</span>) · ${W.count} trades · ${m(W.total_prem)} premium · ${W.big_count||0} big</strong>
<small>Last trade ${esc(W.last_trade_pt||'—')}. ${n15} in the last 15 min (shaded). Gold bar = big trade (≥ ${m(W.big_min||1e6)}, SPY/QQQ ≥ ${m(W.big_etf_min||5e6)}). Directional premium: bullish ${m(W.bull_prem)} vs bearish ${m(W.bear_prem)}; ${m(W.closing_prem||0)} of non-opening bid-side sales is labelled likely closing / overwrite (grey) and excluded from lean. Wall tags carry the FlashAlpha reading time (@HH:MM). Collector polls every ~60s in RTH; page republishes ≤ every 5 min, so the page can trail live trades by up to ~6 min. Soft research only · not orders · never elevates.</small></div></div>
<section class="section" style="margin-bottom:18px"><div class="section-head"><h2>Live tape · newest first</h2><small>${tape.length} shown${tk?' · '+esc(tk):''}${mn?' · ≥ '+m(mn):''} · times PT · "ago" updates in your browser</small></div>
<div class="section-body"><div class="wf-chips">${chips}</div><div class="wf-chips">${tchips}</div></div>
<div class="table-scroll"><table>${th}<tbody>${tape.map(row).join('')||'<tr><td colspan="9" class="empty">No trades match.</td></tr>'}</tbody></table></div></section>
<section class="section" style="margin-bottom:18px"><div class="section-head"><h2>Ticker summary</h2><small>sorted by total premium · lean = net bullish vs bearish directional premium (±20% band = mixed)</small></div>
<div class="table-scroll"><table><thead><tr><th>Ticker</th><th>Trades</th><th>Last trade PT</th><th>First PT</th><th>Call prem</th><th>Put prem</th><th>Bullish prem</th><th>Bearish prem</th><th>Net</th><th>Likely closing (excluded)</th><th>Lean</th></tr></thead><tbody>${ts||'<tr><td colspan="11" class="empty">No trades.</td></tr>'}</tbody></table></div></section>
<section class="section"><div class="section-head"><h2>Biggest whale trades today</h2><small>ranked by premium · top ${top.length}</small></div>
<div class="table-scroll"><table>${th}<tbody>${top.map(row).join('')||'<tr><td colspan="9" class="empty">No trades match.</td></tr>'}</tbody></table></div>
<div class="section-body source-notes"><p>${esc(W.method_note||'')}</p><p>${esc(W.source||'')} · daily log chart-bot/whale-flow/${esc(W.session_date)}/trades.jsonl · big-trade queue big_trades.jsonl · JSON: data/whale-flow.json</p></div></section>`;}
function wfAgo(s){if(!(s>=0))return '';if(s<60)return 'just now';if(s<3600)return Math.floor(s/60)+' min ago';const h=Math.floor(s/3600);return h+'h '+Math.floor((s%3600)/60)+'m ago';}
""".replace("\n", "") + "\n"


def inject_whale_js(app_js: str) -> tuple[str, str]:
    a1, b1 = "topics={chart:'Chart',", "topics={chart:'Chart',whale:'Whale flow',"
    a2 = "else if(state.topic==='macro'){body=macroEvidence();}"
    b2 = "else if(state.topic==='whale'){body=whaleFlowSection();}" + a2
    anchor = "function renderEvidence(){"
    if a1 not in app_js or a2 not in app_js or anchor not in app_js:
        return app_js, "WARN whale anchors missing; tab not added"
    app_js = app_js.replace(a1, b1, 1).replace(a2, b2, 1)
    app_js = app_js.replace("state.topic!=='news'&&state.topic!=='macro'?", "state.topic!=='news'&&state.topic!=='macro'&&state.topic!=='whale'?", 1)
    app_js = app_js.replace(anchor, WHALE_FN + anchor, 1)
    return app_js, "ok"


def load_whale_flow(root: Path, data_dir: Path) -> Optional[dict]:
    try:
        src = root / "chart-bot" / "whale-flow" / "latest" / "summary.json"
        if not src.is_file():
            return None
        w = json.loads(src.read_text(encoding="utf-8"))
        (data_dir / "whale-flow.json").write_text(json.dumps(w, ensure_ascii=False), encoding="utf-8")
        return w
    except Exception:  # noqa: BLE001  never break the publish
        return None


def load_source_status(root: Path, data_dir: Path) -> Optional[dict]:
    """Recompute data-source status on every publish (dashboard/source_status.py) and ship it as
    snapshot.source_status + data/source-status.json. Status/ages only, never quotes. Never breaks the publish."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("source_status", root / "dashboard" / "source_status.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out = mod.compute()
    except Exception:  # noqa: BLE001  fall back to the last computed file
        try:
            out = json.loads((root / "market-data" / "latest" / "source-status.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    try:
        (data_dir / "source-status.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def _asset_bust(raw: bytes) -> str:
    """Short content hash for cache-busting query strings on static assets."""
    return hashlib.sha256(raw).hexdigest()[:12]


def package(root: Path, dist: Path) -> dict:
    root = root.resolve()
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)

    public = root / "public"
    review_app_path = Path("/workspace/oid-trading-desk-review-dist/app.js")
    review_app = review_app_path.read_text(encoding="utf-8") if review_app_path.is_file() else ""
    public_app = (public / "app.js").read_text(encoding="utf-8")

    shutil.copy2(public / "styles.css", dist / "styles.css")
    with open(dist / "styles.css", "a", encoding="utf-8") as fh:
        fh.write(perf_strip.PERF_CSS)
        fh.write(source_status_spa.SRC_CSS)
    shutil.copy2(public / "favicon.svg", dist / "favicon.svg")
    app_text = build_prod_app_js(review_app, public_app)
    app_text, chart_reads_js = inject_chart_reads_js(app_text)
    app_text, map_notice_js = inject_map_notice_js(app_text)
    app_text, whale_js = inject_whale_js(app_text)
    app_text, perf_js = perf_strip.inject_js(app_text)
    app_text, src_js = source_status_spa.inject_js(app_text)
    try:
        perf = perf_strip.compute(root)
        perf_html = perf_strip.render_html(perf)
    except Exception as exc:  # noqa: BLE001  never break the publish over the strip
        perf, perf_html = None, f"<small>Performance totals unavailable ({type(exc).__name__})</small>"
    (dist / "app.js").write_text(app_text, encoding="utf-8")
    # Content-hash bust: here.now caches /app.js and /styles.css for up to 1h (+SWR)
    # despite _headers. Fresh index.html (no-cache) points at new ?v= URLs each publish.
    js_v = _asset_bust(app_text.encode("utf-8"))
    css_v = _asset_bust((dist / "styles.css").read_bytes())
    (dist / "index.html").write_text(
        PROD_INDEX_TEMPLATE.format(js_v=js_v, css_v=css_v, perf_html=perf_html,
                                   src_nav=source_status_spa.NAV_LINK if src_js == "ok" else ""),
        encoding="utf-8",
    )

    data = dist / "data"
    data.mkdir()
    snapshot_src = root / "data" / "snapshot.json"
    if not snapshot_src.is_file():
        raise FileNotFoundError("Missing data/snapshot.json — run import --local-dashboard first")
    snap_out = json.loads(snapshot_src.read_text(encoding="utf-8"))
    snap_out["chart_reads"] = load_chart_reads(root)
    snap_out["chart_levels"] = load_chart_levels(root, dist)
    snap_out["chart_setups_4h"] = load_chart_setups_4h(root, dist)
    snap_out["focus_watch"] = load_focus_watch(root, data)
    snap_out["intraday_bars"] = load_intraday_bars(root, data)
    snap_out["whale_flow"] = load_whale_flow(root, data)
    snap_out["performance"] = perf
    snap_out["source_status"] = load_source_status(root, data)
    if perf is not None:
        (data / "performance.json").write_text(json.dumps(perf, ensure_ascii=False), encoding="utf-8")
    (data / "snapshot.json").write_text(json.dumps(snap_out, ensure_ascii=False), encoding="utf-8")
    shutil.copy2(root / "docs" / "source-registry.json", data / "registry.json")
    shutil.copy2(root / "docs" / "changes.json", data / "changes.json")
    (data / "reviews.json").write_text(json.dumps({"reviews": [], "next_cursor": None}), encoding="utf-8")
    write_prompt_json(root, data / "prompts")

    copy_downloads(root, dist / "downloads")
    prompts_dir = dist / "prompts"
    prompts_dir.mkdir()
    for filename in PROMPTS.values():
        src = root / "prompts" / filename
        if src.is_file():
            shutil.copy2(src, prompts_dir / filename)

    (dist / "README-PROD.txt").write_text(
        "OID Trading Desk — PRODUCTION publish (swift-dune-cs3e)\n"
        "Redesign SPA + local snapshot. bold-tulip-nejq is frozen (do not update).\n"
        "\n"
        "CACHE NOTE (2026-10-07):\n"
        "here.now / Cloudflare serves app.js and styles.css with\n"
        "  Cache-Control: public, max-age=3600, stale-while-revalidate=86400\n"
        "even when dist-prod/_headers requests no-cache. _headers IS honored\n"
        "for index.html and /data/* (those already return no-cache).\n"
        "Hard guarantee: index.html references app.js?v=<content-hash> and\n"
        "styles.css?v=<content-hash> so each publish forces a new asset URL.\n"
        "Do not remove the ?v= bust from package_prod_dist.py.\n",
        encoding="utf-8",
    )
    # Ask CDN/edge to keep desk assets fresh. here.now currently ignores _headers
    # for /app.js and /styles.css (still max-age=3600+SWR); index.html + /data/*
    # do honor no-cache. Query-string bust in index.html is the hard guarantee.
    (dist / "_headers").write_text(
        "/data/*\n"
        "  Cache-Control: no-cache, no-store, must-revalidate\n"
        "/app.js\n"
        "  Cache-Control: no-cache, no-store, must-revalidate\n"
        "/styles.css\n"
        "  Cache-Control: no-cache, no-store, must-revalidate\n"
        "/index.html\n"
        "  Cache-Control: no-cache, no-store, must-revalidate\n"
        "/\n"
        "  Cache-Control: no-cache, no-store, must-revalidate\n",
        encoding="utf-8",
    )

    snap = json.loads(snapshot_src.read_text(encoding="utf-8"))
    return {
        "dist": str(dist),
        "snapshot_id": snap.get("snapshot_id"),
        "open_rose": len(snap.get("positions", {}).get("rose", [])),
        "open_hal": len(snap.get("positions", {}).get("hal", [])),
        "asset_bust": {"app.js": js_v, "styles.css": css_v},
        "chart_reads": {"count": len(snap_out.get("chart_reads") or []), "js": chart_reads_js},
        "chart_levels": {"count": len((snap_out.get("chart_levels") or {}).get("names") or []),
                         "as_of": (snap_out.get("chart_levels") or {}).get("as_of_session")},
        "chart_setups_4h": {"count": len((snap_out.get("chart_setups_4h") or {}).get("names") or []),
                            "as_of": (snap_out.get("chart_setups_4h") or {}).get("as_of_pt")},
        "whale_flow": {"js": whale_js, "count": (snap_out.get("whale_flow") or {}).get("count"),
                       "as_of": (snap_out.get("whale_flow") or {}).get("as_of_pt")},
        "source_status": {"js": src_js, "level": ((snap_out.get("source_status") or {}).get("alarm") or {}).get("level"),
                          "as_of": (snap_out.get("source_status") or {}).get("as_of_pt")},
        "performance": {"js": perf_js, "desk": (perf or {}).get("desk"), "as_of": (perf or {}).get("as_of_pt")},
        "files": sorted(p.name for p in dist.iterdir()),
    }


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=root / "dist-prod")
    args = parser.parse_args(argv)
    info = package(root, args.dist)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
