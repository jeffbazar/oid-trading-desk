"""CCI-breakout research (2026-10-25, Jeffrey): read-only Alpaca SIP bar fetch for the 61 core names.
1Hour bars (all sessions 04:00-20:00 ET, adjustment=all) and 1Day bars since 2016-01-01, via optflow's REST helper
(keys never printed). Output: ~/oid-data/score/cci-breakout-filter/bars/{1h,1d}/SYM.csv (t_utc,o,h,l,c,v)."""
import sys, time, gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path.home() / "oid-optflow")); sys.path.insert(0, str(Path.home() / "oid-score"))
import optflow as OF
import pattern_io as IO
H = Path.home(); OUT = H / "oid-data/score/cci-breakout-filter/bars"
syms = [s for s, t, _ in IO.universe() if t == "core"]
END = "2026-10-24T00:00:00Z"
def get(p):
    for k in range(6):
        try: return OF._get("/v2/stocks/bars", p)
        except Exception: time.sleep(2 + 3 * k)
    raise RuntimeError("fetch failed")
def bars(ch, tf, start):
    out = {}; tok = None
    while True:
        p = {"symbols": ",".join(ch), "timeframe": tf, "start": start, "end": END, "limit": 10000, "feed": "sip", "adjustment": "all"}
        if tok: p["page_token"] = tok
        d = get(p)
        for s, bs in (d.get("bars") or {}).items(): out.setdefault(s, []).extend([(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in bs])
        tok = d.get("next_page_token")
        if not tok: return out
def job(arg):
    s, tf, d = arg
    f = OUT / d / f"{s}.csv"
    if f.exists(): return s, tf, -1
    r = bars([s], tf, "2016-01-01T00:00:00Z").get(s, [])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("t,o,h,l,c,v\n" + "".join(f"{t},{o},{h},{l},{c},{v}\n" for t, o, h, l, c, v in r))
    return s, tf, len(r)
t0 = time.time()
jobs = [(s, "1Day", "1d") for s in syms] + [(s, "1Hour", "1h") for s in syms]
with ThreadPoolExecutor(4) as ex:
    for s, tf, n in ex.map(job, jobs): print(s, tf, n, f"{time.time()-t0:.0f}s", flush=True)
print("done", len(syms), f"{time.time()-t0:.0f}s")
