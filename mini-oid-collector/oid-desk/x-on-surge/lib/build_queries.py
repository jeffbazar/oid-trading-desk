#!/usr/bin/env python3
"""Build X recent-search queries per ticker from query_map.json. Prints length check. No API calls."""
import json, sys
M=json.load(open(__file__.rsplit('/',1)[0]+'/query_map.json'))
SUFFIX="-is:retweet -is:nullcast lang:en"   # -is:reply optional: see design s1.3
LIMIT=512
def entry(sym):
    e=M['tickers'].get(sym) or M['mini_extra_22'].get(sym)
    if e and e.get('mode')=='alias': return entry(e['of'])
    return sym, e
def build(sym, use_optional=False):
    sym,e=entry(sym)
    tags=["$"+sym]+e.get('extra_cashtags',[])
    core=" OR ".join(tags)
    kw=list(e.get('kw',[]))+(e.get('optional_kw',[]) if use_optional else [])
    mode=e['mode']
    if mode=='cashtag_only' and not (use_optional and kw): q=f"({core})"
    elif mode=='cashtag_plus' or (mode=='cashtag_only'): q=f"({core} OR {' OR '.join(kw)})"
    else:
        ctx=e.get('ctx',M['CTX'])
        q=f"({core} OR (({' OR '.join(kw)}) ({' OR '.join(ctx)})))"
    neg=" ".join("-"+n for n in e.get('neg',[]))
    q=f"{q} {neg} {SUFFIX}".replace("  "," ")
    return q
if __name__=="__main__":
    syms=list(M['tickers'])+[k for k in M['mini_extra_22'] if not k.startswith('_')]
    worst=0
    for s in syms:
        q=build(s); worst=max(worst,len(q))
        print(f"{s:5} {len(q):3}  {q}")
    print("max len", worst, "limit", LIMIT)
