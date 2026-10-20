#!/usr/bin/env python3
"""X Summarizer prefilter, filter_version xf-v1.1. Emits rows that match SCHEMAS.md section 9 v1.1 (file as of 2026-10-18 18:08 PT).
v0.4: ETF ticker check passes on-topic macro / constituent posts (query_map ETF_TOPICS).
  to_posts_raw(...)     -> posts_raw rows, PK post_id (tailnet only, never published). First receipt wins; query_id/surge_id = first-sighting convenience.
  post_query_hits(...)  -> post_query_hits rows, PK (post_id, fetch_id); source of truth for links; rank 1-based; lead_s/leading/reused
  prefilter(...)        -> item_filter rows (one per post), incl. job_id + author_followers/following/tweet_count/account_age_days
Scope (v1.1 #4): spam + copy rings + the account rules only. Novelty / stale-story is the scorer's job (it has cluster_id).
Pure functions, stdlib only, no network. Two-stage use on the mini (design s1.2):
  stage 1 = prefilter(rows, sym, stage=1) on text only -> user_ids_to_lookup(...) -> GET /2/users (only survivors not in cache)
  stage 2 = fill author_* from the lookup/cache -> prefilter(rows, sym) final -> write item_filter, grader job for kept rows.
Drop-reason enum (v1.1): spam_cashtags promo new_account low_followers low_activity follow_farm ring blocklist lang irrelevant_collision (null = kept).
Tier enum (v1.1): T1 T2 T2b T3 T4 T5 / X. T2b = aggregators c=0.6. Thin accounts stay T5 with c=0.075. Every dropped row: tier X, c=0.
Fetching is OFF in this module (pure functions). The X key lives on the mini at ~/oid-data/secrets/X_BEARER_TOKEN; this file never reads it."""
import re, json, os, hashlib, time, datetime as dt
H=os.path.dirname(os.path.abspath(__file__))
TIERS=json.load(open(H+'/x-credibility-tiers.json')); BL=json.load(open(H+'/x-blocklist.json')); QM=json.load(open(H+'/query_map.json'))
SCHEMA_VERSION="v1.1"; FILTER_VERSION="xf-v1.1"; WRITER_RAW="x_on_surge@0.1"; WRITER_FILTER="x_prefilter@"+FILTER_VERSION
DROP_ENUM={"spam_cashtags","promo","new_account","low_followers","low_activity","follow_farm","ring","blocklist","lang","irrelevant_collision",None}
TIER_ENUM={"T1","T2","T2b","T3","T4","T5","X"}
BLOCK={b['handle'].lower() for b in BL['block']} if not os.environ.get('NO_BLOCKLIST') else set()
DOWN={b['handle'].lower() for b in BL['downgrade']}; MUTE={b['handle'].lower() for b in BL['pattern_mute']}
T1={h.lower():ts for h,ts in TIERS['T1_official']['handles'].items()}
T2={h.lower() for h in TIERS['T2_news_desks']['handles']+TIERS['T2_news_desks'].get('proposed_additions',[])}
T2B={h.lower() for h in TIERS['T2b_aggregators']['handles']}
T3={h.lower() for h in TIERS['T3_flow_and_analysts']['flow']+TIERS['T3_flow_and_analysts']['analysts_commentators']}
ALLOW=set(T1)|T2|T2B|T3
CFG=dict(max_cashtags=4, min_account_age_days=30, min_followers=50, min_tweet_count=20, farm_min_following=1000, farm_following_ratio=5,
         thin_followers=200, thin_age_days=180,
         ring_min_authors=3, ring_window_s=600, near_dup_jaccard=0.8, story_jaccard=0.6, langs_ok=("en","und","zxx","qme","qam"))
PROMO=re.compile(r"|".join([
 r"\bdiscord\b", r"\btelegram\b", r"t\.me/", r"\bwhatsapp\b", r"free (?:alerts?|trial|signals?|picks?)", r"\d+\s?% winner", r"\bwinners?\b.*\b(?:today|again|alert)",
 r"whale detected", r"link in (?:my )?bio", r"\bdm (?:me|for)\b", r"check (?:my )?pinned", r"join (?:our|my|the) (?:community|group|chat|room|server)",
 r"community exclusively", r"you should definitely pay att?ention", r"if you hold (?:any of )?the (?:aforementioned|following) stocks",
 r"watchlist is ready", r"locked in this week", r"high-growth potential", r"\b\d{2,4}x (?:gains?|potential|runner)", r"\bnext 100x\b",
 r"\bgiveaway\b", r"\bpromo code\b", r"\buse code\b", r"\bairdrop\b", r"\bpresale\b", r"\bvip (?:group|room|alerts?)\b", r"\bpaid group\b",
 r"sign up (?:now|today|here)", r"click (?:here|the link)", r"tap the link", r"🔗[:：]"]), re.I)
URL=re.compile(r"https?://\S+"); MENT=re.compile(r"@\w+"); CT=re.compile(r"\$([A-Za-z]{1,6})\b")

# ---------- time helpers (SCHEMAS s1: *_ns int64 UTC + *_iso RFC3339 Z, ns precision) ----------
def iso_to_ns(s):
    d=dt.datetime.fromisoformat(s.replace('Z','+00:00')); return int(d.timestamp())*1_000_000_000 + d.microsecond*1000
def ns_to_iso(ns): return dt.datetime.fromtimestamp(ns//1_000_000_000, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')+f".{ns%1_000_000_000:09d}Z"
def common(event_ns, ingest_ns, writer):
    return dict(schema_version=SCHEMA_VERSION, event_ts_ns=event_ns, event_ts_iso=ns_to_iso(event_ns) if event_ns is not None else None,
                ingest_ts_ns=ingest_ns, ingest_ts_iso=ns_to_iso(ingest_ns) if ingest_ns is not None else None, writer=writer)

# ---------- posts_raw ----------
def ticker_hits(text, syms):
    return [s for s in syms if kw_hit(s, text)]
def to_posts_raw(resp, query_id, surge_id, via, candidate_syms, ingest_ns=None, user_cache=None, fetch_id=None):
    """resp = X v2 search JSON (data + optional includes.users). user_cache: {author_id: user obj} for author_* fields when expansions are off.
    One row per post_id. query_id / surge_id / first_fetch_id = the fetch that first saw the post (post_query_hits is the source of truth).
    via: 'search' | 'builtin' ('stream' reserved for a later separate-app stream).
    symbols = matched tickers among candidate_syms (comma list, null if none)."""
    ingest_ns = ingest_ns if ingest_ns is not None else time.time_ns()
    U={u['id']:u for u in (resp.get('includes',{}) or {}).get('users',[])}
    if user_cache: U={**user_cache, **U}
    out=[]
    for p in resp.get('data',[]) or []:
        u=U.get(p.get('author_id')) or {}; pm=u.get('public_metrics') or {}; m=p.get('public_metrics') or {}
        text=(p.get('note_tweet') or {}).get('text') or p.get('text','')
        refs=p.get('referenced_tweets') or []; ent=p.get('entities') or {}
        cashtags=[c.get('tag','').upper() for c in ent.get('cashtags',[])] or sorted({c.upper() for c in CT.findall(text)})
        urls=[x.get('unwound_url') or x.get('expanded_url') or x.get('url') for x in ent.get('urls',[])] or URL.findall(text)
        hits=ticker_hits(text, candidate_syms)
        handle=u.get('username') or (p.get('url','').split('/')[3] if p.get('url','').count('/')>=4 else None)
        created_ns=iso_to_ns(p['created_at'])
        out.append(dict(post_id=p['id'], symbols=",".join(hits) if hits else None, query_id=query_id, surge_id=surge_id, via=via,
            author_id=p.get('author_id'), author_handle=handle,
            first_fetch_id=fetch_id,
            author_followers=pm.get('followers_count'), author_following=pm.get('following_count'), author_tweet_count=pm.get('tweet_count'),
            author_verified_type=u.get('verified_type'),
            author_created_ns=iso_to_ns(u['created_at']) if u.get('created_at') else None,
            created_ns=created_ns, created_iso=ns_to_iso(created_ns), text=text, lang=p.get('lang'),
            urls=json.dumps(urls), cashtags=json.dumps(cashtags), n_cashtags=len(set(cashtags)),
            is_reply=bool(p.get('in_reply_to_user_id')) or any(r.get('type')=='replied_to' for r in refs),
            is_quote=any(r.get('type')=='quoted' for r in refs), conversation_id=p.get('conversation_id'),
            like_count=m.get('like_count'), repost_count=m.get('retweet_count'), reply_count=m.get('reply_count'), quote_count=m.get('quote_count'),
            raw_json=json.dumps(p, ensure_ascii=False), **common(created_ns, ingest_ns, WRITER_RAW)))
    return out
def merge_posts_raw(existing, new_rows):
    """posts_raw is keyed per post_id: keep the first sighting, fill author_* if it arrived later (stage-2 lookup). Returns the merged dict."""
    for r in new_rows:
        o=existing.get(r['post_id'])
        if o is None: existing[r['post_id']]=r
        else:
            for k in ('author_followers','author_following','author_tweet_count','author_verified_type','author_created_ns','author_handle'):
                if o.get(k) is None and r.get(k) is not None: o[k]=r[k]
    return existing
def post_query_hits(resp, query_id, fetch_id, surge_id, fetch_start_ns, fire_ts_ns=None, reused=False, ingest_ns=None, writer=None):
    """SCHEMAS v1.1 link table, PK (post_id, fetch_id). rank = 1-based position in the result page. surge_id null for sweeps.
    lead_s = fire_ts - created_at (s, positive = post first); leading = lead_s >= 60; both null without a surge.
    reused = attached from a fetch <= 3 min old (x_fetch_status skipped:recent). event_ts = fetch start."""
    ingest_ns = ingest_ns if ingest_ns is not None else time.time_ns()
    out=[]
    for i,p in enumerate(resp.get('data',[]) or []):
        lead=(fire_ts_ns-iso_to_ns(p['created_at']))/1e9 if (fire_ts_ns is not None and surge_id) else None
        out.append(dict(post_id=p['id'], query_id=query_id, fetch_id=fetch_id, surge_id=surge_id, rank=i+1,
                        lead_s=(round(lead,3) if lead is not None else None), leading=(lead>=60 if lead is not None else None), reused=bool(reused),
                        **common(fetch_start_ns, ingest_ns, writer or WRITER_RAW)))
    return out

# ---------- text features ----------
def norm(t):
    t=URL.sub(" ",t); t=MENT.sub(" ",t); t=t.lower(); t=re.sub(r"[^\w\s$%.]"," ",t); return re.sub(r"\s+"," ",t).strip()
def shingles(t,k=3):
    w=norm(t).split(); return {" ".join(w[i:i+k]) for i in range(max(1,len(w)-k+1))}
def jac(a,b): return len(a&b)/len(a|b) if a and b else 0.0
def simhash64(t):
    v=[0]*64
    for s in shingles(t):
        h=int.from_bytes(hashlib.blake2b(s.encode(),digest_size=8).digest(),'big')
        for i in range(64): v[i]+= 1 if (h>>i)&1 else -1
    return f"{sum(1<<i for i in range(64) if v[i]>0):016x}"
def _etf_rx(sym):
    """ETF topic regex (v0.4): macro for broad index ETFs, constituents for sector ETFs. Terms starting uppercase match case-sensitively."""
    if sym not in _ETF_RX:
        grp=QM.get('ETF_TOPICS',{}).get('map',{}).get(sym)
        if not grp: _ETF_RX[sym]=None
        else:
            terms=[t for g in grp for t in QM['ETF_TOPICS']['groups'][g]]
            cs=[t for t in terms if t.startswith('\\') or t[:1].isupper()]
            ci=[t for t in terms if t not in cs]
            pat=lambda ts: r"(?<![\w$])(?:"+"|".join(ts)+r")(?!\w)"
            _ETF_RX[sym]=(re.compile(pat(cs)) if cs else None, re.compile(pat(ci), re.I) if ci else None)
    return _ETF_RX[sym]
_ETF_RX={}
def etf_topic_hit(sym, text):
    rx=_etf_rx(sym)
    return bool(rx) and any(r.search(text) for r in rx if r)
def kw_hit(sym, text):
    e=QM['tickers'].get(sym) or QM['mini_extra_22'].get(sym) or {}
    if etf_topic_hit(sym, text): return True     # v0.4: ETF on-topic macro / constituent posts are not collisions
    if e.get('mode')=='alias': return kw_hit(e['of'], text) or bool(re.search(r"\$"+re.escape(sym)+r"\b", text))
    if re.search(r"\$"+re.escape(sym)+r"\b", text): return True          # case-sensitive cashtag
    if e.get('mode')=='cashtag_only': return False
    if re.search(r"\b"+re.escape(sym)+r"\b", text): return True           # bare UPPERCASE ticker, non-ambiguous names only
    return any(re.search(r"\b"+re.escape(k.strip('"'))+r"\b", text, re.I) for k in e.get('kw',[]))

# ---------- tiers (enum T1..T5 / X; sub-tier weight carried in c) ----------
def tier(handle, sym, followers, vtype, created_ns, now_ns):
    h=(handle or '').lower()
    if h in BLOCK: return 'X',0.0
    if h in T1: return ('T1',1.0) if (sym in T1[h] or '_AI_LAB' in T1[h]) else ('T3',0.5)
    if h in T2: return 'T2',0.8
    if h in T2B: return 'T2b',0.6                   # v1.1: own tier
    if h in T3: return 'T3',0.5
    if h in DOWN: return 'T5',0.15
    age=(now_ns-created_ns)/86400e9 if created_ns else None; f=followers or 0
    if vtype in('business','government') or (vtype=='blue' and f>=10000 and (age or 0)>=365): return 'T4',0.3
    if followers is not None and age is not None and f<CFG['thin_followers'] and age<CFG['thin_age_days']: return 'T5',0.075   # thin
    return 'T5',0.15

# ---------- item_filter ----------
def user_ids_to_lookup(posts_raw_rows, sym, cache_ids=()):
    """After stage 1: author_ids of surviving, non-allowlisted posts that lack author data and aren't cached. Batch into one GET /2/users?ids= (<=100)."""
    keep=[r for r in prefilter(posts_raw_rows, sym, stage=1) if not r['dropped']]
    kept_ids={r['item_id'] for r in keep}
    return sorted({p['author_id'] for p in posts_raw_rows if 'x:'+p['post_id'] in kept_ids and p['author_followers'] is None
                   and (p['author_handle'] or '').lower() not in ALLOW and p['author_id'] not in set(cache_ids)})
def prefilter(posts_raw_rows, sym, now_ns=None, ingest_ns=None, stage=2, users=None, job_id=None):
    """users: {author_id: X user object} from the stage-2 lookup / 7-day cache, used when posts_raw author_* are still null.
    Missing user data -> the account rules that need it are skipped (never guessed). job_id is set on kept rows only (null if dropped)."""
    now_ns=now_ns or time.time_ns(); ingest_ns=ingest_ns if ingest_ns is not None else time.time_ns()
    users=users or {}
    rows=[]
    for p in posts_raw_rows:
        pm=(users.get(p.get('author_id')) or {}).get('public_metrics') or {}
        pick=lambda k,m: p.get(k) if p.get(k) is not None else pm.get(m)
        fol=pick('author_followers','followers_count'); following=pick('author_following','following_count'); tweets=pick('author_tweet_count','tweet_count')
        h=(p['author_handle'] or '').lower(); txt=p['text']
        tg,c=tier(p['author_handle'], sym, fol, p['author_verified_type'], p['author_created_ns'], now_ns)
        age=(now_ns-p['author_created_ns'])/86400e9 if p['author_created_ns'] else None
        reason=None
        if tg=='X': reason='blocklist'
        elif h not in ALLOW and not kw_hit(sym, txt): reason='irrelevant_collision'   # allowlisted wires/officials/T3 skip it: sweep posts carry macro/peer news; grader sets relevant
        elif p['lang'] and p['lang'] not in CFG['langs_ok']: reason='lang'
        elif h not in ALLOW:
            if p['n_cashtags']>CFG['max_cashtags']: reason='spam_cashtags'
            elif PROMO.search(txt): reason='promo'
            elif stage==2 and age is not None and age<CFG['min_account_age_days']: reason='new_account'
            elif stage==2 and fol is not None and fol<CFG['min_followers']: reason='low_followers'
            elif stage==2 and tweets is not None and tweets<CFG['min_tweet_count']: reason='low_activity'
            elif stage==2 and following is not None and fol is not None and following>=CFG['farm_min_following'] and following>=CFG['farm_following_ratio']*fol: reason='follow_farm'
        elif h in MUTE and PROMO.search(txt): reason='promo'
        rows.append(dict(item_id='x:'+p['post_id'], src='x', job_id=job_id, dropped=reason is not None, drop_reason=reason, cluster_id=None, cluster_rank=None,
                         simhash=simhash64(txt), credibility_tier=('X' if reason else tg), c=(0.0 if reason else c),
                         author_followers=fol, author_following=following, author_tweet_count=tweets,
                         author_account_age_days=(int(age) if age is not None else None), filter_version=FILTER_VERSION,
                         **common(p['created_ns'], ingest_ns, WRITER_FILTER),
                         _sh=shingles(txt), _h=h, _t=p['created_ns']))
    # copy-paste ring: >=3 distinct non-allowlisted authors, Jaccard>=0.8, within 10 min
    for a in rows:
        grp=[b for b in rows if jac(a['_sh'],b['_sh'])>=CFG['near_dup_jaccard'] and abs(a['_t']-b['_t'])<=CFG['ring_window_s']*1e9]
        au={b['_h'] for b in grp}
        if len(au)>=CFG['ring_min_authors'] and not (au & ALLOW):
            for b in grp:
                if b['drop_reason'] in (None,'promo','spam_cashtags','low_followers','new_account','low_activity','follow_farm'):
                    b.update(dropped=True, drop_reason='ring', credibility_tier='X', c=0.0)
    for r in rows:
        if r['dropped']: r['job_id']=None
    # same-story clusters among kept rows; cluster_id 'c-<simhash of rank-0 item>'; rank 0 = highest c, then earliest
    kept=sorted([r for r in rows if not r['dropped']], key=lambda r:(-r['c'], r['_t']))
    for r in kept:
        if r['cluster_id']: continue
        cid='c-'+r['simhash'][:8]; members=[o for o in kept if not o['cluster_id'] and (o is r or jac(r['_sh'],o['_sh'])>=CFG['story_jaccard'])]
        for o in members: o['cluster_id']=cid
        for i,o in enumerate(sorted(members, key=lambda r:(-r['c'], r['_t']))): o['cluster_rank']=i
    for r in rows:
        for k in ('_sh','_h','_t'): r.pop(k)
        assert r['drop_reason'] in DROP_ENUM and r['credibility_tier'] in TIER_ENUM
    return rows

if __name__=="__main__":
    import glob, collections
    tot=collections.Counter(); now=iso_to_ns('2026-10-18T00:00:00Z')
    os.makedirs(H+'/replays/schema', exist_ok=True)
    for f in sorted(g for g in glob.glob(H+'/replays/*.json')):
        d=json.load(open(f)); base=os.path.basename(f)[:-5]; sym=base.split('-')[0]
        qid=f"crowd:{sym}"; fid=f"x-search-replay-{base}"
        pr=to_posts_raw(d, query_id=qid, surge_id=None, via='builtin', candidate_syms=[sym], ingest_ns=now, fetch_id=fid)
        hits=post_query_hits(d, qid, fid, None, fetch_start_ns=now, ingest_ns=now)
        lookup=user_ids_to_lookup([{**p,'author_followers':None} for p in pr], sym)
        users={u['id']:u for u in (d.get('includes') or {}).get('users',[])}
        itf=prefilter(pr, sym, now_ns=now, ingest_ns=now, users=users, job_id=None)
        c=collections.Counter(r['drop_reason'] or 'KEPT' for r in itf); tot.update(c)
        print(base, dict(c), '| stage-1 users to look up:', len(lookup), 'of', len({p['author_id'] for p in pr}))
        with open(H+f'/replays/schema/{base}.posts_raw.jsonl','w') as w: [w.write(json.dumps(r,ensure_ascii=False)+"\n") for r in pr]
        with open(H+f'/replays/schema/{base}.item_filter.jsonl','w') as w: [w.write(json.dumps(r)+"\n") for r in itf]
        with open(H+f'/replays/schema/{base}.post_query_hits.jsonl','w') as w: [w.write(json.dumps(r)+"\n") for r in hits]
    print('TOTAL', dict(tot))
