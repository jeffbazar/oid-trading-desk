#!/usr/bin/env python3
"""CCI-breakout filter: desk relevance (2026-10-25, research only). 61 core names, archived Alpaca 5m RTH bars
(~/oid-data/archive/parquet/bars_5m, 2025-10-20..2026-10-23, 255 sessions) + the 1h Alpaca bars fetched for this study.
Event: 5m close breaks above the highest high of the prior N 5m bars (N = 12/24/48 = 1h/2h/4h), from 10:00 ET on.
Long, entry at that bar's close; forward return to the close 15/30/60 min later, same RTH session only (no stop, gross).
Non-overlapping per symbol and horizon. Filters use bars before the signal bar:
  CCI5m  = Lowest(CCI(27), 18) < -100 on 5m bars (continuous RTH series)
  CCI60m = the post's rule on completed RTH 60m bars (bars starting 09:00-15:00 ET)
  RSI5m-cal = Lowest(RSI(14),18) on 5m below the quantile that passes as many bars as CCI5m (generic-pullback control)
Day-clustered t for (filtered - complement) uses per-day mean differences."""
import json, math, statistics, sys, bisect
from datetime import datetime, timezone
from pathlib import Path
import duckdb
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cci_lib as X
H = Path.home(); ROOT = H / "oid-data/score/cci-breakout-filter"
con = duckdb.connect()
rows = con.sql(f"""select symbol, bar_start_ns, open, high, low, close from read_parquet('{H}/oid-data/archive/parquet/bars_5m/*/*.parquet', hive_partitioning=true)
                  where session='rth' and high is not null and low is not null and close is not null and close > 0 order by symbol, bar_start_ns""").fetchall()
by = {}
for s, ns, o, h, l, c in rows: by.setdefault(s, []).append((datetime.fromtimestamp(ns / 1e9, timezone.utc), o, h, l, c))
HZ = {"15m": 3, "30m": 6, "60m": 12}
ev = {}  # (N, hz) -> list of (date, ret_bp, cci5, cci60, rsical)
for s, b in by.items():
    T = [x[0] for x in b]; Hh = [x[2] for x in b]; Ll = [x[3] for x in b]; Cc = [x[4] for x in b]
    loc = [t.astimezone(X.ET) for t in T]; dkey = [t.date() for t in loc]
    c27 = X.cci(Hh, Ll, Cc, 27); f5 = X.lowest_lt(c27, 18, -100)
    p = sum(f5) / len(f5)
    r = X.rsi(Cc, 14); lr = [None] * len(r)
    for i in range(18, len(r)):
        w = r[i - 18:i]; lr[i] = None if any(v is None for v in w) else min(w)
    vv = sorted(x for x in lr if x is not None); q = vv[int(p * len(vv))]; fr = [x is not None and x < q for x in lr]
    f60 = [False] * len(T)
    hf = ROOT / "bars/1h" / f"{s}.csv"
    if hf.exists():
        P = X.prep_intraday(X.load_csv(hf), "eq_rth")
        c60 = X.cci(P["H"], P["L"], P["C"], 27); m60 = X.lowest_lt(c60 + [None], 18, -100)  # m60[k]: bars <= k-1
        ends = [t.timestamp() + 3600 for t in P["T"]]
        for i, t in enumerate(T):
            k = bisect.bisect_right(ends, t.timestamp())  # number of 60m bars completed by the 5m bar's start
            f60[i] = m60[k] if k < len(m60) else False
    for N in (12, 24, 48):
        for hz, m in HZ.items():
            last = -10**9
            for i in range(N, len(Cc) - m):
                if loc[i].hour < 10: continue
                if dkey[i + m] != dkey[i]: continue
                if i - last < m: continue
                if Cc[i] > max(Hh[i - N:i]):
                    ev.setdefault((N, hz), []).append((str(dkey[i]), 1e4 * (Cc[i + m] / Cc[i] - 1), f5[i], f60[i], fr[i], s)); last = i
def summ(x):
    if not x: return {"n": 0}
    return {"n": len(x), "mean_bp": statistics.mean(x), "hit": sum(v > 0 for v in x) / len(x), "median_bp": statistics.median(x)}
def clus_t(a, b):
    da, db = {}, {}
    for d, r in a: da.setdefault(d, []).append(r)
    for d, r in b: db.setdefault(d, []).append(r)
    diffs = [statistics.mean(da[d]) - statistics.mean(db[d]) for d in da if d in db]
    if len(diffs) < 5: return None, len(diffs)
    sd = statistics.stdev(diffs); return (statistics.mean(diffs) / (sd / math.sqrt(len(diffs))) if sd > 0 else None), len(diffs)
out = {"definitions": __doc__, "n_symbols": len(by), "results": {}}
for (N, hz), E in sorted(ev.items()):
    r = {"all": summ([e[1] for e in E])}
    for j, nm in ((2, "CCI5m"), (3, "CCI60m"), (4, "RSI5m-cal")):
        a = [(e[0], e[1]) for e in E if e[j]]; b = [(e[0], e[1]) for e in E if not e[j]]
        t, nd = clus_t(a, b)
        r[nm] = {"pass": summ([x[1] for x in a]), "fail": summ([x[1] for x in b]), "pass_share": len(a) / len(E), "day_cluster_t_pass_minus_fail": t, "n_days": nd}
    out["results"][f"N{N}_{hz}"] = r
(ROOT / "desk-relevance.json").write_text(json.dumps(out, indent=1))
for k, r in out["results"].items():
    print(k, "all", round(r["all"]["mean_bp"], 2), r["all"]["n"], *[f"{nm}: pass {r[nm]['pass']['mean_bp']:.2f} (n {r[nm]['pass']['n']}) fail {r[nm]['fail']['mean_bp']:.2f} t {r[nm]['day_cluster_t_pass_minus_fail'] or 0:.2f}" for nm in ("CCI5m", "CCI60m", "RSI5m-cal")])
