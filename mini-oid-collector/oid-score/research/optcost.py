"""Options-cost study for 1m higher_low / lower_high (shadow research; read-only on live data).
Writes ~/oid-data/patterns/optcost-20261021.json (+ setups jsonl). No orders, no trading changes."""
import bisect, gzip, json, math, sys, statistics as st
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo
H = Path.home()
sys.path.insert(0, str(H / "oid-score"))
import patterns as PT, pattern_io as IO
PTZ = ZoneInfo("America/Los_Angeles")
PATS = {("higher_low", "1m", 1), ("lower_high", "1m", -1)}
LIVE_DAY = "2026-10-21"
snap = json.loads((H / "oid-data/patterns/opt-cost-snap-20261021.json").read_text())["by_sym"]

# ---------- setups
setups = []
for ln in open(H / "oid-data/patterns/backtest-grades.jsonl"):
    r = json.loads(ln)
    if (r["pattern"], r["interval"], r["direction"]) in PATS:
        r["src"] = "bt"; setups.append(r)
recs = []
for p in sorted((IO.ARCH / "patterns" / f"date={LIVE_DAY}").glob("part-patterns-live-*.jsonl")):
    for ln in p.read_text().splitlines():
        try: x = json.loads(ln)
        except Exception: continue
        if x.get("mode") == "live" and x.get("state") == "triggered" and (x["pattern"], x["interval"], x["direction"]) in PATS:
            recs.append(x)
seen = set(); live_trg = []
for x in sorted(recs, key=lambda x: x["ts"]):
    if x["det_id"] in seen: continue
    seen.add(x["det_id"]); live_trg.append(x)
uni = {s: stv for s, _, stv in IO.universe()}
bars = {}
def b1_of(sym):
    if sym not in bars:
        h = IO.hist_1m(sym, uni.get(sym))
        if not h or h[-1][6] < LIVE_DAY:
            h = [b for b in h if b[6] < LIVE_DAY] + IO.day_1m(sym, LIVE_DAY, uni.get(sym), live_only=True)
        bars[sym] = h
    return bars[sym]
for x in live_trg:
    g = PT.grade(x, b1_of(x["ticker"]))
    if not g: continue
    r = {"ticker": x["ticker"], "pattern": x["pattern"], "interval": "1m", "direction": x["direction"], "ts": x["ts"],
         "px": x["px"], "key_levels": x["key_levels"], "atr_bar": x.get("atr_bar"), "src": "live", **g}
    setups.append(r)
n_rej = defaultdict(int)
S = []
for r in setups:
    if r["outcome"] == "rejected_wrong_side":
        n_rej[(r["src"], r["pattern"])] += 1; continue
    if not r.get("final"): continue
    S.append(r)

# ---------- context data
walls = defaultdict(list)
for f in sorted((H / "oid-data/walls-history").glob("walls-*.jsonl")):
    for ln in f.read_text().splitlines():
        try: w = json.loads(ln)
        except Exception: continue
        if w.get("cw") or w.get("pw"): walls[w["sym"]].append((w["as_of"], w.get("cw"), w.get("pw")))
for v in walls.values(): v.sort()
cp = defaultdict(list)  # sym -> [(t, cp15, cp60)]
for f in sorted((H / "oid-optflow/data/cp-history").glob("2026-*.jsonl*")):
    op = gzip.open if f.suffix == ".gz" else open
    with op(f, "rt") as fh:
        for ln in fh:
            try: x = json.loads(ln)
            except Exception: continue
            if x.get("hdr"): continue
            for s, u in (x.get("u") or {}).items():
                a, b = (u.get("15") or [None])[0], (u.get("60") or [None])[0]
                cp[s].append((x["t"], a, b))
score = defaultdict(list)
for f in sorted((IO.ARCH / "score_features").glob("date=*/part-score-*core-1.jsonl")):
    for ln in f.read_text().splitlines():
        try: x = json.loads(ln)
        except Exception: continue
        if x.get("profile") == "core" and x.get("score") is not None: score[x["symbol"]].append((x["t"], x["score"]))
for d in (cp, score): [v.sort(key=lambda x: x[0]) for v in d.values()]
_TC = {}
def at(series, t, maxage):
    if not series: return None
    k = id(series)
    if k not in _TC: _TC[k] = [x[0] for x in series]
    j = bisect.bisect_right(_TC[k], t) - 1
    if j < 0 or t - series[j][0] > maxage: return None
    return series[j]

# ---------- per setup features + outcome path
def pct(xs, q):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * q; f = math.floor(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)
med_snap = {}
for side in "CP":
    vals = [v[f"w1{side}"] for v in snap.values() if v.get(f"w1{side}") and v[f"w1{side}"]["spread_bp_und"] is not None]
    med_snap[side] = {k: st.median([x[k] for x in vals if x.get(k) is not None]) for k in ("spread_bp_und", "spread_pct_mid")}
    med_snap[side]["prem_bp"] = st.median([x["mid"] / snap[s]["spot"] * 1e4 for s, v in snap.items() for x in [v.get(f"w1{side}")] if x])
    med_snap[side]["theta_bp_min"] = st.median([abs(x["theta"]) / 390 / snap[s]["spot"] * 1e4 for s, v in snap.items()
                                                for x in [v.get(f"w1{side}")] if x and x.get("theta")])
    med_snap[side]["iv"] = st.median([x["iv"] for v in snap.values() for x in [v.get(f"w1{side}")] if x and x.get("iv")])
T_YRS = 2 / 365
rows = []
for r in S:
    sym, d, e, ts = r["ticker"], r["direction"], r["px"], r["ts"]
    b1 = b1_of(sym)
    i0 = bisect.bisect_left([b[0] for b in b1], ts) if False else None
    tlist = bars.setdefault("_t_" + sym, [b[0] for b in b1])
    i0 = bisect.bisect_left(tlist, ts)
    seg = b1[i0:i0 + 30]
    if not seg: continue
    best, tbest = 0.0, 0
    for j, b in enumerate(seg):
        f = ((b[2] - e) if d > 0 else (e - b[3])) / e * 1e4
        if f > best: best, tbest = f, j + 1
    G, I = r["key_levels"]["target"], r["key_levels"]["invalidation"]
    mins = r.get("minutes_to_outcome") or len(seg)
    if r["outcome"] == "target_hit": move = (G - e) * d / e * 1e4
    else:
        k = min(len(seg), max(1, int(round(mins)))) - 1
        move = (seg[k][4] - e) * d / e * 1e4
    ib = i0 - 1  # break bar = the bar whose close triggered
    rv = None
    if ib >= 20:
        vs = [b[5] for b in b1[ib - 20:ib] if b[5]]
        if len(vs) >= 5 and st.mean(vs) > 0: rv = b1[ib][5] / st.mean(vs)
    tr5 = tr15 = None
    if ib >= 15 and b1[ib - 15][6] == b1[ib][6]:
        tr15 = (b1[ib][4] - b1[ib - 15][4]) * d > 0
        tr5 = (b1[ib][4] - b1[ib - 5][4]) * d > 0
    dt = datetime.fromtimestamp(ts - 60, PTZ); hm = dt.hour * 60 + dt.minute
    tod = "a 6:30-6:35" if hm < 395 else "b 6:35-9:00" if hm < 540 else "c 9:00-11:00" if hm < 660 else "d 11:00-13:00"
    w = at(walls.get(sym, []), ts, 3 * 3600)
    room = None
    if w:
        lvl = w[1] if d > 0 else w[2]
        if lvl: room = (lvl - e) * d / e * 1e4
    c = at(cp.get(sym, []), ts, 60)
    cpa = None
    if c:
        v = c[2] if c[2] is not None else c[1]
        if v is not None: cpa = (v > 1.10) if d > 0 else (v < 0.91)
    sc = at(score.get(sym, []), ts, 120)
    sca = None if sc is None else (sc[1] * d > 0)
    side = "C" if d > 0 else "P"
    o = (snap.get(sym) or {}).get(f"w1{side}")
    sp = o["spread_bp_und"] if o else med_snap[side]["spread_bp_und"]
    th = (abs(o["theta"]) / 390 / snap[sym]["spot"] * 1e4) if (o and o.get("theta")) else med_snap[side]["theta_bp_min"]
    iv = (o.get("iv") if o else None) or med_snap[side]["iv"]
    prem = (o["mid"] / snap[sym]["spot"] * 1e4) if o else med_snap[side]["prem_bp"]
    gam = lambda x_bp: 0.5 * 0.3989 * (x_bp / 1e4) ** 2 / (iv * math.sqrt(T_YRS)) * 1e4 if iv else 0.0
    opt = 0.5 * move + (gam(move) if move > 0 else -gam(move)) * 0 + (0.5 * 0.3989 * (move / 1e4) ** 2 / (iv * math.sqrt(T_YRS)) * 1e4 if iv else 0) - sp - th * mins
    opt_best = 0.5 * best + gam(best) - sp - th * max(tbest, 1)
    rows.append({"src": r["src"], "ticker": sym, "pattern": r["pattern"], "dir": d, "date": dt.strftime("%Y-%m-%d"), "tod": tod,
                 "hit": r["outcome"] == "target_hit", "outcome": r["outcome"], "mins": mins, "move_bp": round(move, 2),
                 "best_bp": round(best, 2), "t_best": tbest, "rr": r.get("rr"), "rvol": rv, "tr5": tr5, "tr15": tr15,
                 "wall_room_bp": room, "cp_agree": cpa, "score_agree": sca, "spread_bp": sp, "theta_bp_min": th, "prem_bp": prem,
                 "opt_bp": round(opt, 2), "opt_pct_prem": round(opt / prem, 4) if prem else None, "opt_best_bp": round(opt_best, 2),
                 "snap": "ticker" if o else "median"})

def summ(rs):
    if not rs: return {"n": 0}
    n = len(rs); bst = [x["best_bp"] for x in rs]; op = [x["opt_bp"] for x in rs]; pp = [x["opt_pct_prem"] for x in rs if x["opt_pct_prem"] is not None]
    return {"n": n, "hit": round(sum(x["hit"] for x in rs) / n, 4), "best_p50": round(pct(bst, .5), 1), "best_p75": round(pct(bst, .75), 1),
            "best_p90": round(pct(bst, .9), 1), "ge30": round(sum(b >= 30 for b in bst) / n, 4), "ge50": round(sum(b >= 50 for b in bst) / n, 4),
            "ge100": round(sum(b >= 100 for b in bst) / n, 4), "move_mean": round(st.mean(x["move_bp"] for x in rs), 2),
            "opt_mean_bp": round(st.mean(op), 2), "opt_med_bp": round(pct(op, .5), 2), "opt_mean_pct_prem": round(st.mean(pp), 4) if pp else None,
            "opt_win": round(sum(o > 0 for o in op) / n, 4), "opt_best_mean_bp": round(st.mean(x["opt_best_bp"] for x in rs), 2),
            "spread_med_bp": round(pct([x["spread_bp"] for x in rs], .5), 2), "theta_med_bp_min": round(pct([x["theta_bp_min"] for x in rs], .5), 3),
            "mins_med": pct([x["mins"] for x in rs], .5), "low_n": n < 30}
out = {"med_snap": med_snap, "n_rejected": {f"{a}|{b}": v for (a, b), v in n_rej.items()}, "base": {}, "gate2": {}, "subsets": {}}
for lab, filt in (("all", lambda x: True), ("bt", lambda x: x["src"] == "bt"), ("live", lambda x: x["src"] == "live")):
    for pat in ("higher_low", "lower_high", "both"):
        rs = [x for x in rows if filt(x) and (pat == "both" or x["pattern"] == pat)]
        out["base"][f"{lab}|{pat}"] = summ(rs)
G = {"a wall room>=50bp": lambda x: x["wall_room_bp"] is not None and x["wall_room_bp"] >= 50,
     "b C/P agrees": lambda x: x["cp_agree"] is True,
     "c rvol>=2x": lambda x: x["rvol"] is not None and x["rvol"] >= 2,
     "d 5m+15m trend agrees": lambda x: x["tr5"] is True and x["tr15"] is True,
     "e ex first5 & 9-11": lambda x: x["tod"] in ("b 6:35-9:00", "d 11:00-13:00")}
cov = {"a wall room>=50bp": lambda x: x["wall_room_bp"] is not None, "b C/P agrees": lambda x: x["cp_agree"] is not None,
       "c rvol>=2x": lambda x: x["rvol"] is not None, "d 5m+15m trend agrees": lambda x: x["tr5"] is not None, "e ex first5 & 9-11": lambda x: True}
for pat in ("both", "higher_low", "lower_high"):
    P = [x for x in rows if pat == "both" or x["pattern"] == pat]
    res = {"gate1 only": dict(summ(P), covered=len(P))}
    for k, f in G.items():
        C = [x for x in P if cov[k](x)]
        res[k] = dict(summ([x for x in C if f(x)]), covered=len(C), covered_base=summ(C).get("opt_mean_bp"))
    for (k1, f1), (k2, f2) in combinations(G.items(), 2):
        C = [x for x in P if cov[k1](x) and cov[k2](x)]
        res[f"{k1[0]}+{k2[0]}"] = dict(summ([x for x in C if f1(x) and f2(x)]), covered=len(C), covered_base=summ(C).get("opt_mean_bp"))
    res["d' score agrees"] = dict(summ([x for x in P if x["score_agree"] is True]), covered=sum(x["score_agree"] is not None for x in P))
    out["gate2"][pat] = res
P = rows
by = defaultdict(list)
for x in P: by[("tod", x["tod"])].append(x)
for x in P:
    rv = x["rvol"]; by[("rvol", "na" if rv is None else "<1" if rv < 1 else "1-2" if rv < 2 else "2-3" if rv < 3 else ">=3")].append(x)
    by[("score_agree", str(x["score_agree"]))].append(x); by[("cp_agree", str(x["cp_agree"]))].append(x)
    wr = x["wall_room_bp"]; by[("wall_room", "na" if wr is None else "<=0" if wr <= 0 else "0-50" if wr < 50 else "50-100" if wr < 100 else ">=100")].append(x)
    by[("ticker", x["ticker"])].append(x)
for k, rs in by.items(): out["subsets"]["|".join(k)] = summ(rs)
(H / "oid-data/patterns/optcost-20261021.json").write_text(json.dumps(out, indent=1))
with open(H / "oid-data/patterns/optcost-setups-20261021.jsonl", "w") as fh:
    for x in rows: fh.write(json.dumps(x) + "\n")
print("setups", len(rows), "rejected", dict(out["n_rejected"]), "snap tickers", len(snap))
