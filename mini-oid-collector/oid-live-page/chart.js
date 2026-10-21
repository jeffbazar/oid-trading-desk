/* OID live page CHART (2026-10-20). Click a ticker (core tile, table row, Sector watch row) -> price candles + volume,
   direction score lane (raw, step line, colored by score), C/P 15s / 1m lane, call wall / put wall / flip history.
   Data: /chart.json (read-only, built on the mini). Library: vendor/lightweight-charts (TradingView, Apache-2.0, local).
   Research only: no orders. Times shown in PT (daily bars by ET trading date). */
(function(){
'use strict';
const IVS=['15s','1m','5m','15m','1h','1d'],RNG=['1D','1W','1M','3M','YTD','1Y'];
const SCOL={'3':'#116329','2':'#2da44e','1':'#6fdd8b','0':'#8c959f','-1':'#ff8182','-2':'#fa4549','-3':'#a40e26'};
const POLL_MS=5000;
// MOMSTATE lane colors = the page's Momentum chip colors (ACCEL dark green, RESUME light green, DECEL amber, quiet grey)
const MOC={3:'#1a7f37',2:'#6fdd8b',1:'#d4a72c',0:'#d0d7de'},MON={3:'▲ ACCEL',2:'▲ RESUME',1:'DECEL',0:'quiet'};
// Right-side padding (Robinhood style): empty bars to the right of the latest candle so it clears the price-axis labels.
// PAD = default rightOffset in bars; fitted views (open, Reset, range buttons) use max(PAD, 8% of the bars shown) so the gap stays visible on long ranges.
const PAD=12,PAD_FRAC=0.08;
const padFor=n=>Math.max(PAD,Math.ceil(n*PAD_FRAC));
// FUTURE SPACE (10/20 6 PM): intraday charts always extend ~2 h of clock time past the latest candle. The space is made of
// invisible time-only points (whitespace) on their own hidden series, so the time axis prints future times and drag /
// trackpad pan move through it natively. Bars = 2 h / bar size (15s 480, 1m 120, 5m 24, 15m 8, 1h 2; ÷k when downsampled),
// never less than ~60 px so the candle clears the price labels. 1d: max(12 bars, 8%) of trading days (weekends skipped).
const FUT_S=7200,IVSEC={'15s':15,'1m':60,'5m':300,'15m':900,'1h':3600,'1d':86400},MIN_GAP_PX=60;
function futBars(){if(!D)return PAD;const n=D.bars.length;if(D.iv==='1d')return padFor(n);
 const step=IVSEC[D.iv]*(D.k||1),f=Math.max(1,Math.round(FUT_S/step));const w=Math.max(200,(($('chc')||{}).clientWidth||1200)-70);
 return Math.max(f,Math.ceil(MIN_GAP_PX*n/Math.max(100,w-MIN_GAP_PX)));}
// The hidden time-only points run further than the default view (max(future bars, 70% of the bars, 200)) so the axis keeps
// printing future times while you pan the latest candle toward the middle or past it.
function wsPoints(){if(!D||!D.bars.length)return [];const lt=D.bars[D.bars.length-1][0],F=Math.max(futBars(),Math.ceil(D.bars.length*0.7),200),out=[];
 if(D.iv==='1d'){let t=lt;while(out.length<F){t+=86400;const wd=new Date((t+off(t,'America/New_York'))*1000).getUTCDay();if(wd!==0&&wd!==6)out.push({time:ct(t)});}return out;}
 const step=IVSEC[D.iv]*(D.k||1);let prev=ct(lt);for(let j=1;j<=F;j++){let t=ct(lt+j*step);if(t<=prev)t=prev+step;out.push({time:t});prev=t;}return out;}
let K={sym:null,iv:'1m',rng:'1D',ext:1,box:false,fitw:0};
try{Object.assign(K,JSON.parse(localStorage.lvChart||'{}'));}catch(e){}
K.box=false;
let CH=null,S={},D=null,IDX=new Map(),TIMER=null,BUSY=false,OPEN=false,LIVEPL=[],REQ=0,LAST_INFO='';
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function save(){try{localStorage.lvChart=JSON.stringify({sym:K.sym,iv:K.iv,rng:K.rng,ext:K.ext,fitw:K.fitw?1:0});}catch(e){}}
// ---- time: lightweight-charts draws UTC; shift epoch seconds so the axis reads PT (daily bars: ET trading date)
const FMT={};
function fmtFor(tz){return FMT[tz]||(FMT[tz]=new Intl.DateTimeFormat('en-US',{timeZone:tz,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}));}
const OFFC={};
function off(t,tz){const k=tz+Math.floor(t/1800);if(k in OFFC)return OFFC[k];const p={};fmtFor(tz).formatToParts(new Date(t*1000)).forEach(x=>p[x.type]=x.value);
 const u=Date.UTC(+p.year,+p.month-1,+p.day,(+p.hour)%24,+p.minute,+p.second)/1000;return OFFC[k]=Math.round((u-Math.floor(t))/60)*60;}
function ct(t){return D&&D.iv==='1d'?t+off(t,'America/New_York'):t+off(t,'America/Los_Angeles');}
function ptLabel(t){if(D&&D.iv==='1d')return new Date(t*1000).toLocaleDateString('en-US',{timeZone:'America/New_York',weekday:'short',month:'numeric',day:'numeric',year:'numeric'})+' (ET date)';
 return new Date(t*1000).toLocaleString('en-US',{timeZone:'America/Los_Angeles',weekday:'short',month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit'})+' PT';}
function f2(x,n){return x==null?'—':(+x).toFixed(n==null?2:n);}
function fv(v){if(v==null)return '—';v=+v;return v>=1e6?(v/1e6).toFixed(2)+'M':v>=1e3?(v/1e3).toFixed(1)+'K':String(v);}
function fcp(x){return x==null?'—':x>=99?'∞':(+x).toFixed(2);}
// ---- modal
function ensureModal(){if($('chm'))return;const m=document.createElement('div');m.id='chm';m.hidden=true;m.innerHTML=`
<div class="chp" role="dialog" aria-label="Stock chart">
 <div class="chh"><b id="chsym"></b><span id="chtier" class="chtag"></span><span id="chlive"></span>
  <span class="chsp"></span><span class="chbtns" id="chiv"></span><span class="chbtns" id="chrng"></span>
  <label class="chx"><input type="checkbox" id="chext"> ext hrs</label>
  <button id="chfw" title="Fit walls: include call wall / put wall / flip in the price scale. Off (default) = the scale fits the candles; a wall outside the view shows as a labelled marker at the top or bottom edge">Fit walls</button><button id="chlh" title="Zoom to the last 60 minutes">Last hour</button><button id="chbox" title="Box zoom: drag across the chart to zoom (or hold Shift and drag)">⬚ Box zoom</button><button id="chctr" title="Put the latest candle in the middle (same zoom). Arrow keys ← → also pan">Center</button><button id="chreset" title="Reset zoom (whole range, with space right of the last candle)">Reset</button>
  <button id="chclose" title="Close (Esc)">✕</button></div>
 <div class="chbody"><div id="chc"></div><div id="chsel" hidden></div><div id="chtip" hidden></div><div id="chempty" hidden></div><div id="chedge"></div></div>
 <div class="chf" id="chfoot"></div></div>`;document.body.appendChild(m);
 m.addEventListener('click',e=>{if(e.target===m)closeChart();});
 $('chclose').onclick=closeChart;$('chreset').onclick=homeView;$('chctr').onclick=centerLast;
 $('chlh').onclick=lastHour;$('chfw').onclick=()=>{K.fitw=K.fitw?0:1;save();paintCtl();if(S.c){S.c.priceScale().applyOptions({autoScale:true});}edgesSoon();};$('chbox').onclick=()=>{K.box=!K.box;$('chbox').classList.toggle('on',K.box);if(CH)CH.applyOptions({handleScroll:{pressedMouseMove:!K.box}});};
 $('chext').onchange=e=>{K.ext=e.target.checked?1:0;save();load(true);};
 $('chiv').innerHTML=IVS.map(v=>`<button data-iv="${v}">${v}</button>`).join('');
 $('chrng').innerHTML=RNG.map(v=>`<button data-r="${v}">${v}</button>`).join('');
 $('chiv').onclick=e=>{const b=e.target.closest('button');if(!b)return;K.iv=b.dataset.iv;save();load(true);};
 $('chrng').onclick=e=>{const b=e.target.closest('button');if(!b)return;K.rng=b.dataset.r;save();load(true);};
 boxZoom();}
function paintCtl(){document.querySelectorAll('#chiv button').forEach(b=>b.classList.toggle('on',b.dataset.iv===K.iv));
 document.querySelectorAll('#chrng button').forEach(b=>b.classList.toggle('on',b.dataset.r===K.rng));$('chext').checked=!!K.ext;if($('chfw'))$('chfw').classList.toggle('on',!!K.fitw);$('chext').disabled=K.iv==='1d';}
function loadLib(){return window.LightweightCharts?Promise.resolve():new Promise((res,rej)=>{const s=document.createElement('script');s.src='vendor/lightweight-charts.standalone.production.js';s.onload=res;s.onerror=()=>rej(new Error('chart library failed to load'));document.head.appendChild(s);});}
window.openChart=function(sym){if(!sym)return;ensureModal();K.sym=String(sym).toUpperCase();save();OPEN=true;$('chm').hidden=false;document.body.classList.add('chopen');
 paintCtl();liveHead();loadLib().then(()=>load(true)).catch(e=>{$('chempty').hidden=false;$('chempty').textContent=e.message;});};
window.openLastChart=function(){openChart(K.sym||'NVDA');};
function closeChart(){OPEN=false;REQ++;if($('chedge'))$('chedge').innerHTML='';if($('chfoot'))$('chfoot').innerHTML='';if($('chm'))$('chm').hidden=true;document.body.classList.remove('chopen');clearTimeout(TIMER);TIMER=null;if(CH){CH.remove();CH=null;S={};}D=null;}
document.addEventListener('keydown',e=>{if(!OPEN)return;if(e.key==='Escape'){e.preventDefault();closeChart();return;}
 if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&!/INPUT|SELECT|TEXTAREA/.test((e.target&&e.target.tagName)||'')){e.preventDefault();panBy((e.key==='ArrowRight'?1:-1)*0.1);}});
// ---- pan helpers (zoom unchanged: the visible width in bars is kept exactly)
function panBars(d){if(!CH||!d)return;const ts=CH.timeScale(),r=ts.getVisibleLogicalRange();if(!r)return;ts.setVisibleLogicalRange({from:r.from+d,to:r.to+d});}
function panBy(frac){if(!CH)return;const r=CH.timeScale().getVisibleLogicalRange();if(r)panBars((r.to-r.from)*frac);}
function centerLast(){if(!CH||!D||!D.bars.length)return;const ts=CH.timeScale(),r=ts.getVisibleLogicalRange();if(!r)return;const h=(r.to-r.from)/2,c=D.bars.length-1;ts.setVisibleLogicalRange({from:c-h,to:c+h});}
// Mac trackpad: a two-finger sideways swipe is a wheel event with deltaX. The library would read its small deltaY as zoom
// (and its wheel-scroll is off), so sideways-dominant wheel events are taken here and pan; up/down wheel and pinch still zoom.
function wheelPan(){const el=$('chc');if(!el||el.dataset.wp)return;el.dataset.wp=1;
 el.addEventListener('wheel',e=>{if(!CH||e.ctrlKey)return;const ax=Math.abs(e.deltaX),ay=Math.abs(e.deltaY);const sx=e.shiftKey&&ax===0?e.deltaY:e.deltaX;
  if(!(ax>ay||(e.shiftKey&&ay>0)))return;e.preventDefault();e.stopPropagation();const ts=CH.timeScale(),r=ts.getVisibleLogicalRange();if(!r)return;
  const u=e.deltaMode===1?32:e.deltaMode===2?el.clientWidth:1;const bs=Math.max(0.05,(ts.width()||el.clientWidth)/(r.to-r.from));panBars(sx*u/bs);},{capture:true,passive:false});}
// ---- live header from the page's own stream (raw numbers, same as the tiles)
function rowOf(sym){try{if(typeof st!=='undefined'&&st&&st.rows){const r=st.rows.find(x=>x.sym===sym);if(r)return {k:'core',r};}}catch(e){}
 try{if(typeof WIDE!=='undefined'&&WIDE&&WIDE.groups){for(const g of WIDE.groups){const r=g.rows.find(x=>x.s===sym);if(r)return {k:'wide',r,g};}}}catch(e){}return null;}
function scChip(lab,s,raw){if(s==null)return '';const c=SCOL[String(s)]||'#8c959f';return `<span class="chsc" style="background:${c}">${lab}${s>0?'+':''}${s}<small> ${raw==null?'':(+raw).toFixed(2)}</small></span>`;}
function liveHead(){if(!OPEN)return;$('chsym').textContent=K.sym;const x=rowOf(K.sym);let h='';
 if(x&&x.k==='core'){const r=x.r;$('chtier').textContent='core';const rv=r.rvol!=null?r.rvol:r.day_rvol;
  h=`<b>${f2(r.last)}</b> <span class="${r.chg>0?'up':r.chg<0?'dn':''}">${r.chg==null?'':(r.chg>0?'+':'')+(+r.chg).toFixed(2)+'%'}</span> · rvol <b>${rv==null?'—':(+rv).toFixed(1)+'×'}</b>${r.hot?' <span class="chhot">SURGE</span>':''} ${r.score&&r.score.s!=null?scChip('Direction ',r.score.s,r.score.raw):''}`+
   `${r.af15?' · C/P 15s <b>'+fcp(r.af15.cp)+'</b>':''}${r.af60?' 1m <b>'+fcp(r.af60.cp)+'</b>':''}`;}
 else if(x){const r=x.r;$('chtier').textContent='Sector watch · '+(x.g.name||'');
  h=`<b>${f2(r.p)}</b> <span class="${r.c>0?'up':r.c<0?'dn':''}">${r.c==null?'':(r.c>0?'+':'')+(+r.c).toFixed(2)+'%'}</span> · rvol <b>${r.r!=null?(+r.r).toFixed(1)+'×':r.dr!=null?'d '+(+r.dr).toFixed(1)+'×':'—'}</b>${r.sg?' <span class="chhot">SURGE</span>':''} ${r.fs?scChip('Full ',r.fs.s,r.fs.raw):''} ${r.ls?scChip('Light ',r.ls.s,r.ls.raw):''}`+
   `${r.af15?' · C/P 15s <b>'+fcp(r.af15.cp)+'</b>':''}${r.af60?' 1m <b>'+fcp(r.af60.cp)+'</b>':''}`;}
 else $('chtier').textContent='';
 $('chlive').innerHTML=h;liveWalls(x);liveEdge();}
function curWalls(x){if(!x)return null;if(x.k==='core'){const w=x.r.walls;if(!w||!w.lv)return null;return {cw:w.lv.cw&&w.lv.cw.px,pw:w.lv.pw&&w.lv.pw.px,gf:w.lv.gf&&w.lv.gf.px,lab:w.as_of_pt,st:w.stale};}
 const w=x.r.w;if(!w)return null;return {cw:w.cw,pw:w.pw,gf:w.gf,lab:w.t,st:w.st};}
function liveWalls(x){if(!S.c)return;const w=curWalls(x);const key=JSON.stringify(w);if(key===LAST_INFO)return;LAST_INFO=key;
 LIVEPL.forEach(p=>{try{S.c.removePriceLine(p)}catch(e){}});LIVEPL=[];if(!w)return;
 const add=(px,col,t,ls)=>{if(px==null)return;LIVEPL.push(S.c.createPriceLine({price:+px,color:col,lineWidth:1,lineStyle:ls,axisLabelVisible:true,title:t}));};
 add(w.cw,'#1a7f37','call wall'+(w.st?' (stale)':''),2);add(w.pw,'#cf222e','put wall'+(w.st?' (stale)':''),2);add(w.gf,'#bf8700','flip'+(w.st?' (stale)':''),1);edgesSoon();}
// ---- WALL SCALE (10/20 6:30 PM): price scale fits the candles; walls are drawn but do not stretch the scale unless "Fit walls" is on.
function wallAuto(orig){return K.fitw?orig():null;}
function wallNow(){const w=curWalls(rowOf(K.sym));if(w&&(w.cw!=null||w.pw!=null||w.gf!=null))return w;if(!D||!D.walls)return null;
 for(let i=D.walls.length-1;i>=0;i--){const x=D.walls[i];if(x&&(x[0]!=null||x[1]!=null||x[2]!=null))return {cw:x[0],pw:x[1],gf:x[2],st:false};}return null;}
function candleAuto(orig){const r=orig();if(!K.fitw||!r||!r.priceRange)return r;const w=wallNow();if(!w)return r;
 const v=[w.cw,w.pw,w.gf].filter(x=>x!=null).map(Number);if(!v.length)return r;
 return {priceRange:{minValue:Math.min(r.priceRange.minValue,...v),maxValue:Math.max(r.priceRange.maxValue,...v)},margins:r.margins};}
let EDGE_RAF=0;function edgesSoon(){if(EDGE_RAF)return;EDGE_RAF=requestAnimationFrame(()=>{EDGE_RAF=0;edges();});}
function lastPx(){const x=rowOf(K.sym);if(x){const v=x.k==='core'?x.r.last:x.r.p;if(v!=null)return +v;}return D&&D.bars.length?+D.bars[D.bars.length-1][4]:null;}
function edges(){const box=$('chedge');if(!box)return;if(!CH||!S.c||!D||!D.bars.length){box.innerHTML='';return;}
 let ph=0,aw=0;try{ph=CH.panes()[0].getHeight();aw=CH.priceScale('right',0).width();}catch(e){}
 if(!ph){box.innerHTML='';return;}const top=S.c.coordinateToPrice(0),bot=S.c.coordinateToPrice(ph);if(top==null||bot==null){box.innerHTML='';return;}
 const w=wallNow()||{},sc=scnNow(),pl=patLevels();if(!wallNow()&&!sc&&!pl.length){box.innerHTML='';return;}const lp=lastPx();const up=[],dn=[];
 [['cw','call wall','#1a7f37'],['pw','put wall','#cf222e'],['gf','flip','#9a6700']].forEach(([k,nm,col])=>{const v=w[k];if(v==null)return;const px=+v;
  const d=lp?((px-lp)/lp*100):null;const lab=`${nm} ${px.toFixed(2)}${d==null?'':` (${d>=0?'+':'−'}${Math.abs(d).toFixed(1)}%)`}${w.st?' stale':''}`;
  if(px>top)up.push([px,`▲ ${lab}`,col]);else if(px<bot)dn.push([px,`▼ ${lab}`,col]);});
 scnLevels(sc).forEach(([px,t,col])=>{px=+px;const d=lp?((px-lp)/lp*100):null;const lab=`${t.replace(/ \(.*\)$/,'')} ${px.toFixed(2)}${d==null?'':` (${d>=0?'+':'−'}${Math.abs(d).toFixed(1)}%)`}`;
  if(px>top)up.push([px,`▲ ${lab}`,col]);else if(px<bot)dn.push([px,`▼ ${lab}`,col]);});  // CHARTSCN
 pl.forEach(([px,t,col])=>{px=+px;const d=lp?((px-lp)/lp*100):null;const lab=`${t.replace(/ \(.*\)$/,'')} ${px.toFixed(2)}${d==null?'':` (${d>=0?'+':'−'}${Math.abs(d).toFixed(1)}%)`}`;
  if(px>top)up.push([px,`▲ ${lab}`,col]);else if(px<bot)dn.push([px,`▼ ${lab}`,col]);});  // PATTERNS
 up.sort((a,b)=>a[0]-b[0]);dn.sort((a,b)=>b[0]-a[0]);
 box.innerHTML=up.map((x,j)=>`<div class="che" style="top:${4+j*19}px;right:${aw+8}px;color:${x[2]};border-color:${x[2]}" title="outside the visible price range; turn on Fit walls to include it">${esc(x[1])}</div>`).join('')+
  dn.map((x,j)=>`<div class="che" style="top:${ph-22-j*19}px;right:${aw+8}px;color:${x[2]};border-color:${x[2]}" title="outside the visible price range; turn on Fit walls to include it">${esc(x[1])}</div>`).join('');}
window.addEventListener('resize',()=>{if(OPEN)edgesSoon();});
// ---- data -> series
// ---- CHARTSCN (10/21): Chart Bot primary scenario (CB-SCN-V1, shadow): trigger / T1 / invalidation as thin dashed price lines.
// Price lines never enter autoscale (not even with Fit walls); levels off-screen get edge markers like the walls.
let SCNPL=[],SCN_KEY='';function scnNow(){return D&&D.scn&&D.scn.label?D.scn:null;}
function scnLevels(s){const o=[];if(!s)return o;const lab=String(s.label).replace(/_/g,' ').toLowerCase(),st=s.status?' · '+s.status:'';
 if(s.label==='RANGE_CHOP'){if(s.rhi!=null)o.push([s.rhi,'CB range high ('+lab+st+')','#8250df']);if(s.rlo!=null)o.push([s.rlo,'CB range low','#8250df']);return o;}
 if(s.trig!=null)o.push([s.trig,'CB trigger ('+lab+st+')','#8250df']);if(s.t1!=null)o.push([s.t1,'CB T1','#0969da']);if(s.inv!=null)o.push([s.inv,'CB invalidation','#57606a']);return o;}
function scnLines(){if(!S.c)return;const s=scnNow();const key=JSON.stringify(s);if(key===SCN_KEY)return;SCN_KEY=key;
 SCNPL.forEach(p=>{try{S.c.removePriceLine(p)}catch(e){}});SCNPL=[];
 scnLevels(s).forEach(([px,t,col])=>SCNPL.push(S.c.createPriceLine({price:+px,color:col,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:t})));edgesSoon();}
// ---- PATTERNS (10/21): shadow chart-pattern detector (pattern_daemon.py): markers, active-pattern tag (raw prob, source, n),
// dashed trigger / target / invalidation lines for the selected pattern (price lines: never in autoscale; edge markers when off-screen).
const PSHORT={range:'RNG',bull_flag:'FLAG',bear_flag:'FLAG',breakout:'BO',breakdown:'BD',failed_breakout:'FBO',failed_breakdown:'FBD',head_shoulders:'H&S',inv_head_shoulders:'iH&S',double_top:'DT',double_bottom:'DB',vwap_reclaim:'VWAP+',vwap_loss:'VWAP−',higher_low:'HL',lower_high:'LH',gap_up:'GAP',gap_down:'GAP'};
let PATPL=[],PAT_KEY='',PSEL=null,PIV={'1m':0,'5m':1,'30m':1};try{Object.assign(PIV,JSON.parse(localStorage.lvPatIv||'{}'))}catch(e){}
const pName=p=>String(p).replace(/_/g,' ');
function patDets(){return (D&&D.pat&&D.pat.dets)||[];}
function patActive(){return patDets().filter(x=>x.st==='forming'||x.st==='confirmed'||x.st==='triggered').sort((a,b)=>((b.d?1:0)-(a.d?1:0))||((b.prob==null?-1:b.prob)-(a.prob==null?-1:a.prob)));}
function patSel(){const a=patDets();if(PSEL){const x=a.find(y=>y.id===PSEL);if(x)return x;}return patActive().filter(x=>x.d)[0]||null;}
function patLevels(){const s=patSel();if(!s||!s.d)return [];const lab=`${pName(s.p)} ${s.iv}`;const o=[];
 if(s.trig!=null)o.push([s.trig,`PAT trigger (${lab} · ${s.st})`,'#bc4c00']);if(s.tgt!=null)o.push([s.tgt,'PAT target','#116329']);if(s.inv!=null)o.push([s.inv,'PAT invalidation','#82071e']);return o;}
function pProb(x){return x.prob==null?(x.d?'no rate yet':'context'):`${(x.prob*100).toFixed(1)}% raw (${x.src}${x.n!=null?' n='+x.n:''}${x.n!=null&&x.n<20?', n<20':''})`;}
function barIdx(t){const B=D.bars;let lo=0,hi=B.length-1,r=-1;while(lo<=hi){const m=(lo+hi)>>1;if(B[m][0]<=t){r=m;lo=m+1;}else hi=m-1;}return r;}
function patMarks(){if(!D||!D.bars.length)return [];const sel=patSel();const out=[];
 patDets().forEach(x=>{if(!x.d||!PIV[x.iv])return;const i=barIdx(x.t0-1);if(i<0)return;const up=x.d>0,isS=sel&&sel.id===x.id;
  out.push({time:ct(D.bars[i][0]),position:up?'belowBar':'aboveBar',shape:up?'arrowUp':'arrowDown',color:up?(isS?'#116329':'#2da44e'):(isS?'#82071e':'#cf222e'),size:isS?2:1,text:(PSHORT[x.p]||x.p)+' '+x.iv,id:x.id});});
 out.sort((a,b)=>a.time-b.time);return out;}
function patTag(){const bd=document.querySelector('#chm .chbody');if(!bd)return;let el=$('chpat');
 if(!el){el=document.createElement('div');el.id='chpat';bd.appendChild(el);el.addEventListener('click',e=>{const t=e.target.closest('[data-pid],[data-piv]');if(!t)return;
  if(t.dataset.piv){PIV[t.dataset.piv]=PIV[t.dataset.piv]?0:1;try{localStorage.lvPatIv=JSON.stringify(PIV)}catch(_){}}else PSEL=t.dataset.pid;PAT_KEY='';patDraw();edgesSoon();});}
 if(!D||!D.pat){el.innerHTML='<div class="pth">Patterns <span class="mut">(shadow) · no detections for this range</span></div>';return;}
 const act=patActive().slice(0,5),sel=patSel();
 el.innerHTML=`<div class="pth">Patterns <span class="mut">(shadow · ${esc(D.pat.src||'')})</span>${['1m','5m','30m'].map(v=>`<span class="ptiv${PIV[v]?' on':''}" data-piv="${v}" title="show ${v} markers">${v}</span>`).join('')}</div>`+
  (act.length?act.map(x=>`<div class="ptr${sel&&sel.id===x.id?' sel':''}" data-pid="${esc(x.id)}" title="${esc(`${pName(x.p)} ${x.iv} · ${x.st} · trigger ${x.trig??'—'} · target ${x.tgt??'—'} · invalidation ${x.inv??'—'} · confidence_raw ${x.conf??'—'} · prob = hit rate of triggered ${pName(x.p)} ${x.iv} (target before a closing invalidation), raw, not smoothed. Shadow only: not in any score or trade. Click to draw its lines.`)}">${x.d>0?'▲':x.d<0?'▼':'◆'} ${esc(pName(x.p))} ${x.iv} · ${esc(x.st)} · <b>${esc(pProb(x))}</b></div>`).join(''):'<div class="mut">no active pattern at the last bar</div>');}
function patDraw(){if(!S.c||!D)return;const L=window.LightweightCharts;
 try{if(!S.mk&&L.createSeriesMarkers)S.mk=L.createSeriesMarkers(S.c,[]);if(S.mk)S.mk.setMarkers(patMarks());}catch(e){}
 const lv=patLevels();const key=JSON.stringify(lv);if(key!==PAT_KEY){PAT_KEY=key;PATPL.forEach(p=>{try{S.c.removePriceLine(p)}catch(e){}});PATPL=[];
  lv.forEach(([px,t,col])=>PATPL.push(S.c.createPriceLine({price:+px,color:col,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:t})));}
 patTag();}
function patFoot(){const p=D&&D.pat;if(!p)return '<span class="mut">Patterns: none in this range</span>';return `<span title="shadow chart-pattern detector ${esc(p.version||'')}; never feeds a score or a trade">Patterns: ${(p.dets||[]).length} detections (${esc(p.src||'')}${p.dates&&p.dates.length?' · '+esc(p.dates.join(', ')):''})</span>`;}
function build(keep){LIVEB=null;const L=window.LightweightCharts;if(CH){CH.remove();CH=null;S={};}LIVEPL=[];LAST_INFO='';SCNPL=[];SCN_KEY='';PATPL=[];PAT_KEY='';S.mk=null;
 const el=$('chc');CH=L.createChart(el,{autoSize:true,layout:{background:{type:'solid',color:'#ffffff'},textColor:'#1f2328',fontSize:11,panes:{separatorColor:'#d0d7de',separatorHoverColor:'#afb8c1'}},
  grid:{vertLines:{color:'#f0f2f4'},horzLines:{color:'#f0f2f4'}},crosshair:{mode:0},rightPriceScale:{borderColor:'#d0d7de'},
  timeScale:{borderColor:'#d0d7de',timeVisible:D.iv!=='1d',secondsVisible:D.iv==='15s',rightOffset:PAD,fixLeftEdge:false,fixRightEdge:false,shiftVisibleRangeOnNewBar:true,lockVisibleTimeRangeOnResize:true},
  handleScroll:{mouseWheel:false,pressedMouseMove:!K.box,horzTouchDrag:true,vertTouchDrag:false},handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true},
  localization:{locale:'en-US'}});
 S.ws=CH.addSeries(L.LineSeries,{color:'rgba(0,0,0,0)',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,visible:true},0);
 S.c=CH.addSeries(L.CandlestickSeries,{upColor:'#1a7f37',downColor:'#cf222e',borderVisible:false,wickUpColor:'#1a7f37',wickDownColor:'#cf222e',priceLineVisible:true,autoscaleInfoProvider:candleAuto},0);
 S.c.priceScale().applyOptions({scaleMargins:{top:0.06,bottom:0.05}});
 S.cw=CH.addSeries(L.LineSeries,{color:'#1a7f37',lineWidth:2,lineType:1,lineStyle:0,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,title:'',autoscaleInfoProvider:wallAuto},0);
 S.pw=CH.addSeries(L.LineSeries,{color:'#cf222e',lineWidth:2,lineType:1,lineStyle:0,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,autoscaleInfoProvider:wallAuto},0);
 S.gf=CH.addSeries(L.LineSeries,{color:'#bf8700',lineWidth:1,lineType:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,autoscaleInfoProvider:wallAuto},0);
 S.v=CH.addSeries(L.HistogramSeries,{priceFormat:{type:'custom',formatter:fv,minMove:1},priceLineVisible:false,lastValueVisible:false},1);
 const fix={autoscaleInfoProvider:()=>({priceRange:{minValue:-3.3,maxValue:3.3}})};
 const kinds=Object.keys(D.score||{});S.sc={};
 kinds.forEach((k,i)=>{S.sc[k]=CH.addSeries(L.LineSeries,Object.assign({lineWidth:k==='light'?2:3,lineType:1,lineStyle:k==='light'?2:0,priceLineVisible:false,lastValueVisible:true,title:k==='core'?'Direction':k==='light'?'Light':'Full',
   priceFormat:{type:'price',precision:2,minMove:0.01}},fix),2);});
 const s0=S.sc[kinds[0]];if(s0){[0,2,-2].forEach(v=>s0.createPriceLine({price:v,color:v?'#d0d7de':'#8c959f',lineWidth:1,lineStyle:v?2:0,axisLabelVisible:false,title:v?(v>0?'+2':'-2'):''}));}
 S.hasMo=D.tier==='core';const CPP=S.hasMo?4:3;
 if(S.hasMo){S.mo=CH.addSeries(L.HistogramSeries,{priceLineVisible:false,lastValueVisible:false,base:0,title:'momentum',priceFormat:{type:'custom',formatter:()=>'',minMove:1},autoscaleInfoProvider:()=>({priceRange:{minValue:0,maxValue:1}})},3);}
 const hasCp=(D.cp||[]).some(x=>x&&(x[0]!=null||x[1]!=null));S.hasCp=hasCp;
 if(hasCp){S.cp15=CH.addSeries(L.LineSeries,{color:'#8250df',lineWidth:1,priceLineVisible:false,lastValueVisible:true,title:'C/P 15s',priceFormat:{type:'price',precision:2,minMove:0.01}},CPP);
  S.cp60=CH.addSeries(L.LineSeries,{color:'#0969da',lineWidth:2,priceLineVisible:false,lastValueVisible:true,title:'C/P 1m',priceFormat:{type:'price',precision:2,minMove:0.01}},CPP);
  S.cp60.priceScale().applyOptions({mode:1});S.cp60.createPriceLine({price:1,color:'#8c959f',lineWidth:1,lineStyle:2,axisLabelVisible:false,title:'1.0'});}
 const P=CH.panes();try{P[0].setStretchFactor(5);P[1].setStretchFactor(1.3);if(P[2])P[2].setStretchFactor(1.6);if(S.hasMo&&P[3])P[3].setStretchFactor(0.35);if(P[CPP])P[CPP].setStretchFactor(1.4);}catch(e){}
 CH.timeScale().subscribeVisibleLogicalRangeChange(edgesSoon);
 CH.subscribeCrosshairMove(tip);wheelPan();setData();if(keep)CH.timeScale().setVisibleLogicalRange(keep);else homeView();liveWalls(rowOf(K.sym));scnLines();patDraw();edgesSoon();setTimeout(()=>{if(window.chartAfterBuild)chartAfterBuild();},250);}
const cpv=x=>x==null?null:Math.max(0.05,Math.min(20,x));
function pts(i){const b=D.bars[i],t=ct(b[0]),o={};const fl=b[7];
 o.c=fl===2||fl===3?{time:t,open:b[1],high:b[2],low:b[3],close:b[4],color:'#afb8c1',wickColor:'#afb8c1'}:{time:t,open:b[1],high:b[2],low:b[3],close:b[4]};
 o.v={time:t,value:b[5],color:fl===3?'#d0d7de':(b[4]>=b[1]?'#1a7f3766':'#cf222e66')};
 const w=D.walls[i];o.cw=w&&w[0]!=null?{time:t,value:w[0]}:{time:t};o.pw=w&&w[1]!=null?{time:t,value:w[1]}:{time:t};o.gf=w&&w[2]!=null?{time:t,value:w[2]}:{time:t};
 o.sc={};for(const k in D.score){const s=D.score[k][i];o.sc[k]=s&&s[1]!=null?{time:t,value:+s[1],color:SCOL[String(s[0])]}:(s?{time:t,value:s[0],color:SCOL[String(s[0])]}:{time:t});}
 const m=(D.mom||[])[i];o.mo=m?{time:t,value:1,color:MOC[m[0]]}:{time:t};
 const c=D.cp[i];o.cp15=c&&c[0]!=null?{time:t,value:cpv(c[0])}:{time:t};o.cp60=c&&c[1]!=null?{time:t,value:cpv(c[1])}:{time:t};return o;}
function setData(){IDX=new Map();const A={c:[],v:[],cw:[],pw:[],gf:[],cp15:[],cp60:[],mo:[],sc:{}};for(const k in S.sc)A.sc[k]=[];
 for(let i=0;i<D.bars.length;i++){const o=pts(i);IDX.set(o.c.time,i);A.c.push(o.c);A.v.push(o.v);A.cw.push(o.cw);A.pw.push(o.pw);A.gf.push(o.gf);A.cp15.push(o.cp15);A.cp60.push(o.cp60);A.mo.push(o.mo);for(const k in S.sc)A.sc[k].push(o.sc[k]);}
 if(S.mo)S.mo.setData(A.mo);
 S.ws.setData(wsPoints());S.c.setData(A.c);S.v.setData(A.v);S.cw.setData(A.cw);S.pw.setData(A.pw);S.gf.setData(A.gf);for(const k in S.sc)S.sc[k].setData(A.sc[k]);if(S.hasCp){S.cp15.setData(A.cp15);S.cp60.setData(A.cp60);}
 $('chempty').hidden=D.bars.length>0;if(!D.bars.length)$('chempty').textContent=`No ${D.iv} bars stored for ${D.sym} in this range.`;}
// ---- LIVEEDGE (10/21): forming candle + last-price line tick from the live row (core: state.json last, 1 s; wide: 5 s),
// not only when a closed 1m bar lands. Display-only: never written into D.bars; dropped before every server delta/build.
const LIVESEC={'15s':15,'1m':60,'5m':300,'15m':900,'1h':3600};let LIVEB=null;
function livePx(){const x=rowOf(K.sym);if(!x)return null;const p=x.k==='core'?x.r.last:x.r.p;return p==null||!isFinite(+p)?null:+p;}
function liveDrop(){if(!LIVEB||!S.c||!D)return;const ex=LIVEB.extra;LIVEB=null;if(!ex)return;const a=[];for(let i=0;i<D.bars.length;i++)a.push(pts(i).c);S.c.setData(a);}
function liveEdge(){try{if(!OPEN||!D||!S.c||!D.bars.length||D.to!==D.today)return;const p=livePx();if(p==null)return;
 const sess=(typeof st!=='undefined'&&st)?st.session:null;if(!K.ext&&sess&&sess!=='RTH')return;
 const lb=D.bars[D.bars.length-1],now=Date.now()/1000;let t,o,h,l,extra;
 if(D.iv==='1d'){t=lb[0];o=lb[1];h=Math.max(lb[2],p);l=Math.min(lb[3],p);extra=false;}
 else{const step=(LIVESEC[D.iv]||60)*(D.k||1);if(now<lb[0]+step){t=lb[0];o=lb[1];h=Math.max(lb[2],p);l=Math.min(lb[3],p);extra=false;}
  else{t=lb[0]+step*Math.floor((now-lb[0])/step);if(LIVEB&&LIVEB.t===t){o=LIVEB.o;h=Math.max(LIVEB.h,p);l=Math.min(LIVEB.l,p);}else{o=LIVEB&&LIVEB.extra?LIVEB.c:lb[4];h=Math.max(o,p);l=Math.min(o,p);}extra=true;}}
 if(LIVEB&&LIVEB.t===t){h=Math.max(h,LIVEB.h);l=Math.min(l,LIVEB.l);}
 LIVEB={t,o,h,l,c:p,extra};S.c.update({time:ct(t),open:o,high:h,low:l,close:p});edgesSoon();}catch(e){console.warn('liveEdge',e);}}
setInterval(liveEdge,1000);window.chartLive=()=>LIVEB;
function applyDelta(n){// n = reply with bars from `since` (inclusive): replace the last bar, append new ones
 liveDrop();const t0=n.bars.length?n.bars[0][0]:null;if(t0==null){liveEdge();return;}
 // live edge = the latest candle is on screen. Then new bars scroll the view by the same count (candle keeps its spot, padding kept);
 // otherwise (panned/zoomed into history) the view is restored exactly, no snap back.
 const ts=CH.timeScale(),vr=ts.getVisibleLogicalRange(),n0=D.bars.length,atEdge=!vr||vr.to>=n0-1.5;let j=D.bars.length-1;while(j>=0&&D.bars[j][0]>=t0)j--;
 const keep=j+1;D.bars=D.bars.slice(0,keep).concat(n.bars);D.walls=D.walls.slice(0,keep).concat(n.walls);D.cp=D.cp.slice(0,keep).concat(n.cp);D.mom=(D.mom||[]).slice(0,keep).concat(n.mom||n.bars.map(()=>null));
 for(const k in D.score)D.score[k]=D.score[k].slice(0,keep).concat((n.score||{})[k]||n.bars.map(()=>null));
 D.wall_events=n.wall_events;D.scn=n.scn;scnLines();D.pat=n.pat;D.gen_ms=n.gen_ms;D.notes=n.notes;D.sources=n.sources;D.n_total=n.n_total;
 const add=D.bars.length-n0,nr=vr?(atEdge?{from:vr.from+add,to:vr.to+add}:{from:vr.from,to:vr.to}):null;
 const hadCp=S.hasCp,nowCp=n.cp.some(x=>x&&(x[0]!=null||x[1]!=null));if(nowCp&&!hadCp){build(nr);return;}
 for(let i=keep;i<D.bars.length;i++){const o=pts(i);IDX.set(o.c.time,i);S.c.update(o.c);S.v.update(o.v);S.cw.update(o.cw);S.pw.update(o.pw);S.gf.update(o.gf);for(const k in S.sc)S.sc[k].update(o.sc[k]);if(S.hasCp){S.cp15.update(o.cp15);S.cp60.update(o.cp60);}if(S.mo)S.mo.update(o.mo);}
 S.ws.setData(wsPoints());if(nr)ts.setVisibleLogicalRange(nr);patDraw();LIVEB=null;liveEdge();edgesSoon();}
function foot(ms,kb,live){const d=D;if(!d)return;const av=d.avail||{};const ivn=d.k>1?`1 bar = ${d.k} × ${d.iv}`:d.iv;
 const sc=Object.entries(d.sources.score||{}).map(([k,v])=>`${(window.scoreName?window.scoreName(k):({core:'Direction',light:'Light',full:'Full'})[k])}: ${v.length?v.join('; '):'none'}`).join(' · ');
 $('chfoot').innerHTML=`<span><b>${esc(d.sym)}</b> ${esc(ivn)} · ${esc(d.range)} = ${esc(d.from)} → ${esc(d.to)} · ${d.n_total} bars · ${esc(d.iv)} stored since <b>${esc(av[d.iv]||'?')}</b></span>`+
  (d.notes||[]).map(x=>`<span class="chnote">${esc(x)}</span>`).join('')+
  `<span>bars: ${esc((d.sources.bars||[]).join(', '))}</span><span>score: ${esc(sc)}</span><span>C/P: ${esc((d.sources.cp||[]).join(', ')||'none')}</span><span>momentum: ${esc((d.sources.mom||[]).join('; ')||'no history in this range')}</span><span>walls: ${esc((d.sources.walls||[]).join(', ')||'none')} (${(d.wall_events||[]).length} level changes)</span>`+
  (d.scn?`<span title="Chart Bot CB-SCN-V1 primary, shadow only. calibrated_score runs hot on primaries (~44% est vs ~36% realized)">Chart Bot: ${esc(String(d.scn.label).replace(/_/g,' ').toLowerCase())} ${d.scn.score!=null?Math.round(d.scn.score*100)+'%':''} · ${esc(d.scn.status||'?')} (${esc(d.scn.status_src)}${d.scn.status_asof?', '+esc(d.scn.status_asof):''}) · run ${esc(d.scn.run||'?')}${(d.scn.alts||[]).length?' · alts: '+d.scn.alts.map(a=>esc(String(a.label).replace(/_/g,' ').toLowerCase())+' '+esc(a.status||'?')).join(', '):''}</span>`/*CBSTATUS*/:'<span class="mut">Chart Bot: no scenario for this ticker</span>')+patFoot()+
  `<span class="mut">${live?'live · ':''}server ${d.gen_ms} ms · ${ms} ms · ${kb} KB · ${new Date().toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles'})} PT · drag / two-finger swipe / ← → = pan (axis runs ~2 h past the last candle) · Center = latest candle in the middle · wheel up/down or pinch = zoom · auto-follow only at the live edge · Shift+drag or ⬚ = box zoom · Esc closes</span>`;}
function url(since){return `chart.json?sym=${encodeURIComponent(K.sym)}&iv=${K.iv}&range=${K.rng}&ext=${K.ext}`+(since!=null?`&since=${since}`:'');}
function load(full){if(!OPEN||!window.LightweightCharts)return;clearTimeout(TIMER);paintCtl();const my=++REQ;const t0=performance.now();
 const since=(!full&&D&&D.bars.length)?D.bars[D.bars.length-1][0]:null;BUSY=true;
 fetch(url(since),{cache:'no-store'}).then(r=>r.text().then(tx=>({ok:r.ok,tx}))).then(({ok,tx})=>{if(my!==REQ||!OPEN)return;const d=JSON.parse(tx);
  if(!ok)throw new Error(d.error||'error');const ms=Math.round(performance.now()-t0),kb=(tx.length/1024).toFixed(0);
  if(full||!D||d.k!==D.k||d.iv!==D.iv||d.range!==D.range||d.from!==D.from){D=d;$('chempty').hidden=true;build();}else applyDelta(d);
  foot(ms,kb,d.to===d.today);}).catch(e=>{$('chempty').hidden=false;$('chempty').textContent='Chart data error: '+e.message;})
 .finally(()=>{BUSY=false;if(my===REQ&&OPEN){const live=D&&D.to===D.today;TIMER=setTimeout(()=>{liveHead();edgesSoon();load(false);},live?POLL_MS:60000);}});}
// ---- crosshair tooltip
function tip(p){const el=$('chtip');if(!p||p.time==null||!D){el.hidden=true;return;}const i=IDX.get(p.time);if(i==null){el.hidden=true;return;}
 if(!p.point){const x=CH.timeScale().timeToCoordinate(p.time),y=S.c.priceToCoordinate(D.bars[i][4]);if(x==null||y==null){el.hidden=true;return;}p={time:p.time,point:{x,y}};}
 const b=D.bars[i],w=D.walls[i],c=D.cp[i];let h=`<div class="tt">${esc(ptLabel(b[0]))}${D.k>1?' <small>('+D.k+'×'+D.iv+')</small>':''} <small>${{p:'pre',r:'',a:'post'}[b[6]]||''}</small></div>`+
  `<div>O <b>${f2(b[1])}</b> H <b>${f2(b[2])}</b> L <b>${f2(b[3])}</b> C <b>${f2(b[4])}</b></div><div>Vol <b>${fv(b[5])}</b>${b[7]===2?' <small class="mut">priced from 5 s VWAP</small>':b[7]===3?' <small class="mut">no trades</small>':''}</div>`;
 for(const k in D.score){const s=D.score[k][i];const lab=(window.scoreName?window.scoreName(k):({core:'Direction',light:'Light',full:'Full'})[k]);
  h+=s?`<div>${lab} <b style="color:${SCOL[String(s[0])]}">${s[0]>0?'+':''}${s[0]}</b> raw <b>${s[1]==null?'—':(+s[1]).toFixed(3)}</b>${s[2]!==s[3]?` <small>range in bar ${s[3]>0?'+':''}${s[3]}…${s[2]>0?'+':''}${s[2]}</small>`:''}${s[4]?` <small>${s[4]} change${s[4]>1?'s':''}</small>`:''}<br><small class="mut">since ${esc(ptLabel(s[5]).replace(/^\w+ /,''))}</small></div>`:`<div>${lab} <span class="mut">— (no score: outside regular hours or not stored)</span></div>`;}
 if(S.hasMo){const m=(D.mom||[])[i];h+=m?`<div>Momentum <b style="color:${m[0]===2?'#1a7f37':m[0]===0?'#6e7781':MOC[m[0]]}">${MON[m[0]]}</b>${m[1]?` <small>since ${esc(new Date(m[1]*1000).toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles'}))} PT</small>`:''}${m[2]?` <small>${m[2]} change${m[2]>1?'s':''} in bar</small>`:''}</div>`:'<div>Momentum <span class="mut">— (no momentum history for this bar: engine runs in regular hours; history starts 10/20)</span></div>';}
 else h+='<div>Momentum <span class="mut">— (momentum engine covers core names only)</span></div>';
 h+=c?`<div>C/P 15s <b>${fcp(c[0])}</b>${c[2]!=null?' <small>'+c[2]+' prints</small>':''} · 1m <b>${fcp(c[1])}</b>${c[3]!=null?' <small>'+c[3]+' prints</small>':''}</div>`:(S.hasCp?'<div>C/P <span class="mut">—</span></div>':'');
 h+=w?`<div><span style="color:#1a7f37">call wall <b>${f2(w[0])}</b></span> · <span style="color:#cf222e">put wall <b>${f2(w[1])}</b></span> · <span style="color:#9a6700">flip <b>${f2(w[2])}</b></span></div>`:'<div class="mut">walls: none known at this bar</div>';
 el.innerHTML=h;el.hidden=false;const box=$('chc').getBoundingClientRect();const x=p.point.x,y=p.point.y;const tw=el.offsetWidth,th=el.offsetHeight;
 el.style.left=Math.max(4,Math.min(box.width-tw-60,x+16>box.width-tw-60?x-tw-16:x+16))+'px';el.style.top=Math.max(4,Math.min(box.height-th-4,y-th/2))+'px';}
// ---- zoom helpers
function lastHour(){if(!CH||!D||!D.bars.length)return;const n=D.bars.length,lt=D.bars[n-1][0];let i=n-1;while(i>0&&D.bars[i-1][0]>=lt-3600)i--;CH.timeScale().setVisibleLogicalRange({from:i-0.5,to:n-1+futBars()});}
// default view: whole range plus right padding (open, Reset, range / interval buttons). One time scale for all panes, so volume/score/C/P follow.
function homeView(){if(!CH||!D)return;const n=D.bars.length;if(!n){CH.timeScale().fitContent();return;}CH.timeScale().setVisibleLogicalRange({from:-0.5,to:n-1+futBars()});}
function boxZoom(){const body=document.querySelector('#chm .chbody');let x0=null;const sel=$('chsel');
 const start=e=>{if(!CH)return;if(!(K.box||e.shiftKey)||e.button!==0)return;e.stopPropagation();e.preventDefault();const r=$('chc').getBoundingClientRect();x0=e.clientX-r.left;sel.hidden=false;sel.style.left=x0+'px';sel.style.width='0px';};
 body.addEventListener('mousedown',start,true);body.addEventListener('pointerdown',e=>{if(K.box||e.shiftKey)e.stopPropagation();},true);
 window.addEventListener('mousemove',e=>{if(x0==null)return;const r=$('chc').getBoundingClientRect();const x=Math.max(0,Math.min(r.width,e.clientX-r.left));sel.style.left=Math.min(x0,x)+'px';sel.style.width=Math.abs(x-x0)+'px';});
 window.addEventListener('mouseup',e=>{if(x0==null)return;const r=$('chc').getBoundingClientRect();const x1=Math.max(0,Math.min(r.width,e.clientX-r.left));sel.hidden=true;const a=Math.min(x0,x1),b=Math.max(x0,x1);x0=null;
  if(b-a<6||!CH)return;const ts=CH.timeScale();const la=ts.coordinateToLogical(a),lb=ts.coordinateToLogical(b);if(la!=null&&lb!=null&&lb>la)ts.setVisibleLogicalRange({from:la,to:lb});});}
// ---- deep link: #chart=SYM[/iv][/range][/lh][/tip]  (lh = zoom to last hour, tip = show the tooltip at the last bar)
let HASHOPT={};
function fromHash(){const h=decodeURIComponent(location.hash||'');const m=h.match(/chart=([A-Za-z0-9.\-]+)((?:\/[A-Za-z0-9]+)*)/);if(!m)return;
 HASHOPT={};(m[2]||'').split('/').filter(Boolean).forEach(x=>{if(IVS.includes(x))K.iv=x;else if(RNG.includes(x))K.rng=x;else HASHOPT[x]=1;});openChart(m[1]);}
window.chartEdges=()=>[...document.querySelectorAll('#chedge .che')].map(e=>e.textContent);
window.chartDebug=()=>({range:CH&&CH.timeScale().getVisibleLogicalRange(),pad:D&&CH?+(CH.timeScale().getVisibleLogicalRange().to-(D.bars.length-1)).toFixed(2):null,n:D&&D.bars.length,first:D&&D.bars.length&&D.bars[0][0],last:D&&D.bars.length&&D.bars[D.bars.length-1][0]});
window.chartAfterBuild=function(){if(HASHOPT.lh)lastHour();if(HASHOPT.tip&&CH&&D&&D.bars.length){const i=Math.max(0,D.bars.length-1-(HASHOPT.lh?8:Math.floor(D.bars.length/3)));const b=D.bars[i];
 try{CH.setCrosshairPosition(b[4],ct(b[0]),S.c);}catch(e){}}};
if(document.readyState==='complete')setTimeout(fromHash,300);else window.addEventListener('load',()=>setTimeout(fromHash,300));
window.addEventListener('hashchange',fromHash);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&OPEN&&!BUSY)load(false);});
})();
