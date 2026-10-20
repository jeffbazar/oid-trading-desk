"""Data Sources tab + front-page alarm banner for the production SPA (Jeffrey 2026-10-10).

Injected by scripts/package_prod_dist.py. Data: snapshot.source_status (from
dashboard/source_status.py -> market-data/latest/source-status.json). Status only, never quotes.
"""
from __future__ import annotations

NAV_LINK = ('<a href="#sources" data-view="sources"><span>06</span>Data Sources'
            '<b class="src-badge" id="src-badge" hidden></b></a>')

SRC_JS = r"""function srcAge(s){if(s==null||!(s>=0))return '—';if(s<90)return Math.round(s)+'s';if(s<5400)return Math.floor(s/60)+'m';if(s<172800)return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m';return Math.floor(s/86400)+'d '+Math.floor((s%86400)/3600)+'h';}
function srcStatus(){return state.snapshot&&state.snapshot.source_status;}
function srcSelfStale(S){const age=Date.now()/1000-(+S.written_epoch||0);return age>(S.session==='rth'?900:7800)?age:0;}
function srcBadgePaint(){const b=document.getElementById('src-badge');const S=srcStatus();if(!b)return;if(!S){b.hidden=true;return;}const A=S.alarm||{};const n=(A.red||[]).length+(A.amber||[]).length;b.hidden=!n;b.textContent=n;b.className='src-badge '+(A.level||'');}
function sourceAlarm(){const S=srcStatus();if(!S)return '';const A=S.alarm||{};const lvl=A.level||'green';const self=srcSelfStale(S);const known=(A.known_missing||[]).length;
const ago=srcAge(Date.now()/1000-(+S.written_epoch||0));
const list=a=>(a||[]).map(r=>`<li><strong>${esc(r.feed)}</strong> <span class="src-pill ${r.status==='Down'?'down':'stale'}">${esc(r.status)}</span> <small>${esc(r.detail)}</small></li>`).join('');
const knownTxt=known?`<span class="src-known">${known} known gap${known>1?'s':''} (not built / needs purchase)</span>`:'';
if(lvl==='green'&&!self)return `<button class="src-alarm green" data-goto="sources" title="Open the Data Sources tab"><span class="src-dot"></span><strong>All expected data feeds are live</strong><small>checked ${esc(S.as_of_pt)} (${ago} ago) · ${esc((S.session||'').toUpperCase())}</small>${knownTxt}<span class="src-go">Data Sources →</span></button>`;
const cls=lvl==='red'?'red':'amber';
const head=lvl==='red'?`${(A.red||[]).length} feed${(A.red||[]).length>1?'s':''} down`+((A.amber||[]).length?` · ${(A.amber||[]).length} stale`:''):lvl==='amber'?`${(A.amber||[]).length} feed${(A.amber||[]).length>1?'s':''} stale`:'Feed status check is late';
return `<div class="src-alarm ${self&&lvl==='green'?'amber':cls}" data-goto="sources" role="alert" title="Open the Data Sources tab"><div class="src-alarm-head"><span class="src-dot"></span><strong>Data alarm · ${esc(head)}</strong><small>checked ${esc(S.as_of_pt)} (${ago} ago)</small>${knownTxt}<span class="src-go">Data Sources →</span></div>
${self?`<div class="src-self">The status check itself is ${srcAge(self)} old: the box watchdog or publish may have stalled.</div>`:''}<ul>${list(A.red)}${list(A.amber)}</ul></div>`;}
function renderSources(){const S=srcStatus();if(!S)return heading('DESK / DATA SOURCES','Data Sources','Feed status not published yet.')+'<section class="section"><div class="empty">source-status.json not in this snapshot.</div></section>';
const now=Date.now()/1000;const C=S.counts||{};
const tone=r=>r.tone||'missing';
const miniCls=m=>/^Yes/.test(m||'')?'y':/^(Partial|Mini)/.test(m||'')?'p':'n';
const sig=r=>(r.signals||[]).length?`<details class="src-sig"><summary>${(r.signals||[]).length} check${(r.signals||[]).length>1?'s':''}</summary><ul>${(r.signals||[]).map(s=>`<li><span class="src-pill ${s.state==='ok'?'live':s.state==='stale'?'stale':s.state==='absent'?'missing':'down'}">${esc(s.state)}</span> <strong>${esc(s.label)}</strong>${s.required===false?' <small>(secondary)</small>':''} <small>${esc(s.detail||'')}${s.ts_pt?' · '+esc(s.ts_pt):''}${s.file?' · '+esc(s.file):''}${s.writer_error?' · writer error: '+esc(s.writer_error):''}</small></li>`).join('')}</ul></details>`:'<small>configured</small>';
const rows=(S.rows||[]).map(r=>{const age=r.last_update_epoch?now-r.last_update_epoch:null;return `<tr class="src-row ${tone(r)}"><td class="numeric">${r.n}</td><td><strong>${esc(r.feed)}</strong>${r.risk?`<small>risk: ${esc(r.risk)}</small>`:''}</td><td><small style="font-size:12px;color:var(--ink)">${esc(r.uses_now)}</small></td><td><small style="font-size:12px;color:var(--ink)">${esc(r.source)}</small></td><td class="src-mini ${miniCls(r.mini)}">${esc(r.mini)}</td><td><span class="src-pill ${tone(r)}">${esc(r.status)}</span>${r.known?'<small>known gap · no alarm</small>':''}<small>${esc(r.detail||'')}</small></td><td class="numeric">${r.last_update_epoch?`<strong data-src-ts="${r.last_update_epoch}">${srcAge(age)}</strong><small>${esc(r.last_update_pt||'')}</small>`:'—'}</td><td>${sig(r)}</td></tr>`;}).join('');
const m=(k,c)=>`<span class="src-pill ${c}">${esc(k)} ${C[k]||0}</span>`;
if(!window.__srcTick){window.__srcTick=setInterval(()=>{document.querySelectorAll('[data-src-ts]').forEach(el=>{el.textContent=srcAge(Date.now()/1000-(+el.dataset.srcTs));});},15000);}
return heading('DESK / DATA SOURCES','Data Sources','Every feed the desk trades on, checked automatically: file freshness vs TTL, running collectors, Mac mini link and FlashAlpha quota.')
+sourceAlarm()
+`<div class="src-counts">${m('Live','live')}${m('Stale-risk','risk')}${m('Stale','stale')}${m('Down','down')}${m('Missing','missing')}${m('Needs purchase','purchase')}<small>Last checked ${esc(S.as_of_pt)} · session ${esc((S.session||'').toUpperCase())} · ${esc(S.cadence||'')}</small></div>`
+`<section class="section"><div class="table-scroll"><table class="src-table"><thead><tr><th>#</th><th>Feed</th><th>What the desk uses now</th><th>Source</th><th>From Mac mini?</th><th>Status</th><th>Age · last update</th><th>Checks</th></tr></thead><tbody>${rows}</tbody></table></div>
<div class="section-body source-notes"><p><strong>Alarm rules.</strong> Red = a feed that should be live is down (file missing or far past its TTL in market hours, collector process dead, Mac mini unreachable, FlashAlpha quota exhausted), or a known gap that had been Live and dropped. Amber = past TTL. Known gaps (Missing / Needs purchase) are counted but never alarm until they have been Live once. Outside RTH, last-session carry (e.g. Friday's close) counts as Live.</p>
<p>${Object.entries(S.legend||{}).map(([k,v])=>`<strong>${esc(k)}</strong>: ${esc(v)}`).join(' · ')}</p>
<p>Status only: this page never shows live option (OPRA) or equity quotes. Mac mini = Alpaca SIP + OPRA collector over Tailscale. Config: ${esc(S.config||'')} · writer ${esc(S.writer||'')} · JSON: data/source-status.json · research / paper only.</p></div></section>`;}
""" + "\n"

SRC_CSS = r"""
/* Data Sources tab + front-page alarm (2026-10-10) */
.src-badge{display:inline-block;min-width:18px;margin-left:6px;padding:0 5px;border-radius:9px;font-size:11px;line-height:18px;text-align:center;color:#fff;background:#b08900}
.src-badge.red{background:#c0392b}
.src-badge[hidden]{display:none}
.src-alarm{display:block;width:100%;text-align:left;margin:0 0 16px;padding:10px 14px;border-radius:8px;border:1px solid;cursor:pointer;font:inherit}
.src-alarm.green{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#eef8f2;border-color:#b9e3c9;color:#145c35;padding:7px 14px}
.src-alarm.amber{background:#fff7dc;border-color:#e8c766;color:#6b5200}
.src-alarm.red{background:#fdecea;border-color:#e59a92;color:#8c1d13}
.src-alarm-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.src-alarm small{opacity:.8}
.src-alarm ul{margin:6px 0 0 18px;padding:0;font-size:13px;line-height:1.5}
.src-alarm li small{opacity:.85}
.src-self{font-size:13px;margin-top:4px}
.src-dot{width:10px;height:10px;border-radius:50%;background:currentColor;display:inline-block;flex:none}
.src-alarm.green .src-dot{background:#1e9e57}.src-alarm.amber .src-dot{background:#d4a017}.src-alarm.red .src-dot{background:#d03b30;animation:srcpulse 1.4s infinite}
@keyframes srcpulse{50%{opacity:.35}}
.src-known{font-size:12px;padding:1px 8px;border-radius:9px;background:rgba(0,0,0,.06)}
.src-go{margin-left:auto;font-weight:600;font-size:13px}
.src-pill{display:inline-block;padding:1px 8px;border-radius:9px;font-size:12px;font-weight:600;white-space:nowrap}
.src-pill.live{background:#d1f2e0;color:#16733f}.src-pill.risk{background:#fbf3d5;color:#8a6d00}.src-pill.stale{background:#ffe9a8;color:#7a5a00}
.src-pill.down{background:#f8d7d5;color:#a82a20}.src-pill.missing{background:#ececec;color:#555}.src-pill.purchase{background:#e7dcf7;color:#6a32b0}
.src-counts{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.src-counts small{margin-left:6px;color:var(--muted)}
.src-table td{vertical-align:top}
.src-table td small{display:block;margin-top:3px}
.src-row.live td:first-child{box-shadow:inset 4px 0 0 #1e9e57}.src-row.risk td:first-child{box-shadow:inset 4px 0 0 #d4b44a}
.src-row.stale td:first-child{box-shadow:inset 4px 0 0 #e0a800}.src-row.stale{background:#fffaf0}
.src-row.down td:first-child{box-shadow:inset 4px 0 0 #d03b30}.src-row.down{background:#fff3f2}
.src-row.missing td:first-child{box-shadow:inset 4px 0 0 #aaa}.src-row.purchase td:first-child{box-shadow:inset 4px 0 0 #7b3fc4}
.src-mini{font-weight:600;font-size:12px}.src-mini.y{color:#0a6ed1}.src-mini.p{color:#7a5a00}.src-mini.n{color:#777;font-weight:400}
.src-sig summary{cursor:pointer;font-size:12px}.src-sig ul{margin:4px 0 0 14px;padding:0;font-size:12px;line-height:1.45}
"""


def inject_js(app_js: str) -> tuple[str, str]:
    reps = [
        ("changes:'Changes & provenance'};", "changes:'Changes & provenance',sources:'Data Sources'};"),
        ("{desk:renderDesk,evidence:renderEvidence,journal:renderJournal,bots:renderBots,changes:renderChanges}",
         "{desk:renderDesk,evidence:renderEvidence,journal:renderJournal,bots:renderBots,changes:renderChanges,sources:renderSources}"),
        ("(state.view==='desk'?'':keyTickerTape())", "(state.view==='desk'?sourceAlarm():state.view==='sources'?'':keyTickerTape())"),
    ]
    for a, _ in reps:
        if a not in app_js:
            return app_js, f"WARN source-status anchor missing: {a[:40]}"
    for a, b in reps:
        app_js = app_js.replace(a, b, 1)
    anchor = "function render(){if(!state.snapshot)return;"
    if anchor not in app_js:
        return app_js, "WARN render anchor missing"
    app_js = app_js.replace(anchor, SRC_JS + anchor + "try{srcBadgePaint();}catch(e){}", 1)
    return app_js, "ok"
