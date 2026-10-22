"""Research only: bellwether earnings read-through map. Output ~/oid-data/patterns/readthrough-20261021.json"""
import json, math, statistics as st, bisect
from collections import defaultdict
from pathlib import Path
H = Path.home(); P = H / "oid-data/patterns"
X = json.loads((P / "readthrough-data-20261021.json").read_text())
ev = json.loads((P / "bw-earnings.json").read_text())
BW = ["LRCX","AMAT","KLAC","ASML","TSM","MU","NVDA","AMD","AVGO","META","MSFT","GOOG","AMZN","ORCL","SMCI"]
D = {s: {b[0]: b for b in bs} for s, bs in X["daily"].items()}
days = sorted(D["SPY"])
F30 = X["first30"]; tiers = X["tiers"]
peers = sorted(s for s in D if s not in ("SPY",))
TWIN = {"GOOG": "GOOGL", "GOOGL": "GOOG"}
def r(s, d0, f0, d1, f1):
    a, b = D[s].get(d0), D[s].get(d1)
    if not a or not b: return None
    x = b[f1] / a[f0] - 1
    return None if abs(x) > 0.6 else x  # data-artifact guard (e.g. CORZ relisting 1/2024: +7,290%)
O, C = 1, 4
events = []
for bw in BW:
    for e in ev.get(bw, []):
        d = e["date"]
        if d >= "2026-10-21": continue
        j = bisect.bisect_left(days, d)
        if j >= len(days) - 2 or j < 1: continue
        if days[j] != d: cands = [j]
        elif e.get("time") == "premarket": cands = [j]
        elif e.get("time") == "postmarket": cands = [j + 1]
        else: cands = [j, j + 1]
        best = None
        for k in cands:
            if k + 1 >= len(days): continue
            g = r(bw, days[k - 1], C, days[k], O)
            if g is not None and (best is None or abs(g) > abs(best[1])): best = (k, g)
        if not best: continue
        k = best[0]; d0, d1, d2 = days[k - 1], days[k], days[k + 1]
        events.append({"bw": bw, "date": d, "time": e.get("time"), "d0": d0, "d1": d1, "d2": d2,
                       "co": best[1], "cc": r(bw, d0, C, d1, C), "oc": r(bw, d1, O, d1, C), "nd": r(bw, d1, C, d2, C)})
def peer_obs(e, p):
    co, cc = r(p, e["d0"], C, e["d1"], O), r(p, e["d0"], C, e["d1"], C)
    if co is None or cc is None: return None
    f = (F30.get(e["d1"]) or {}).get(p)
    o1 = D[p][e["d1"]][O]
    return {"co": co, "cc": cc, "oc": D[p][e["d1"]][C] / o1 - 1, "m30": (f[3] / o1 - 1) if f else None, "nd": r(p, e["d1"], C, e["d2"], C),
            "spy_cc": r("SPY", e["d0"], C, e["d1"], C)}
OBS = defaultdict(dict)  # (bw, peer) -> {event idx: obs}
for i, e in enumerate(events):
    for p in peers:
        if p == e["bw"] or TWIN.get(e["bw"]) == p: continue
        o = peer_obs(e, p)
        if o: OBS[(e["bw"], p)][i] = o
def ols(x, y):
    n = len(x)
    if n < 3: return None
    mx, my = st.mean(x), st.mean(y); sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0: return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx; al = my - b * mx
    syy = sum((c - my) ** 2 for c in y)
    rho = b * math.sqrt(sxx / syy) if syy > 0 else None
    res = [c - (al + b * a) for a, c in zip(x, y)]
    sd = math.sqrt(sum(z * z for z in res) / (n - 2)) if n > 2 else None
    return b, al, rho, sd
MAP = defaultdict(dict)
for (bw, p), ob in OBS.items():
    idx = sorted(ob)
    for w in ("co", "cc"):
        x = [events[i][w] for i in idx]; y = [ob[i][w] for i in idx]
        f = ols(x, y)
        if not f: continue
        hit = sum((a > 0) == (c > 0) for a, c in zip(x, y) if a != 0) / len(x)
        MAP[bw].setdefault(p, {})[w] = {"slope": round(f[0], 3), "alpha": round(f[1], 4), "corr": round(f[2], 3) if f[2] is not None else None,
                                         "hit": round(hit, 3), "n": len(x), "resid_sd": round(f[3], 4) if f[3] else None}
# ---- tradeability on linked peers (top 10 by cc corr with n>=8, per bellwether), leave-one-out beta for "implied"
LINK = {}
for bw in BW:
    c = [(p, v["cc"]["corr"]) for p, v in MAP[bw].items() if v.get("cc") and v["cc"]["n"] >= 8 and v["cc"]["corr"] is not None
         and tiers.get(p) == "core"]  # linked = core (curated AI/semis) names only; avoids spurious wide-list matches
    LINK[bw] = [p for p, _ in sorted(c, key=lambda t: -t[1])[:10]]
rows = []
for i, e in enumerate(events):
    for p in LINK[e["bw"]]:
        ob = OBS[(e["bw"], p)]
        if i not in ob: continue
        idx = [k for k in ob if k != i]
        f = ols([events[k]["co"] for k in idx], [ob[k]["co"] for k in idx])
        if not f: continue
        o = ob[i]; imp = f[1] + f[0] * e["co"]
        rows.append(dict(o, bw=e["bw"], peer=p, date=e["d1"], bw_co=e["co"], implied=imp, gap_minus_imp=o["co"] - imp))
def mean_bp(xs): xs = [x for x in xs if x is not None]; return (round(st.mean(xs) * 1e4, 1), len(xs)) if xs else (None, 0)
def rate(xs): xs = [x for x in xs if x is not None]; return (round(sum(x > 0 for x in xs) / len(xs), 3), len(xs)) if xs else (None, 0)
sg = lambda x: 1 if x > 0 else -1
T = {}
G = [x for x in rows if abs(x["co"]) >= 0.01]
T["gap_hold_ge1pct"] = {"n": len(G), "m30_signed_bp": mean_bp([sg(x["co"]) * x["m30"] if x["m30"] is not None else None for x in G]),
    "m30_hold_rate": rate([sg(x["co"]) * x["m30"] if x["m30"] is not None else None for x in G]),
    "oc_signed_bp": mean_bp([sg(x["co"]) * x["oc"] for x in G]), "oc_hold_rate": rate([sg(x["co"]) * x["oc"] for x in G]),
    "nd_signed_bp": mean_bp([sg(x["co"]) * x["nd"] if x["nd"] is not None else None for x in G]), "nd_hold_rate": rate([sg(x["co"]) * x["nd"] if x["nd"] is not None else None for x in G])}
# under/over reaction vs LOO beta-implied: does the day move toward the implied level?
f = ols([-x["gap_minus_imp"] for x in rows], [x["oc"] for x in rows])
f30 = ols([-x["gap_minus_imp"] for x in rows if x["m30"] is not None], [x["m30"] for x in rows if x["m30"] is not None])
under = [x for x in rows if abs(x["implied"]) >= 0.01 and sg(x["co"]) == sg(x["implied"]) and abs(x["co"]) < abs(x["implied"]) * 0.75]
over = [x for x in rows if abs(x["implied"]) >= 0.01 and sg(x["co"]) == sg(x["implied"]) and abs(x["co"]) > abs(x["implied"]) * 1.25]
T["vs_implied"] = {"n": len(rows), "oc_on_shortfall_slope": round(f[0], 3), "oc_on_shortfall_corr": round(f[2], 3),
    "m30_on_shortfall_slope": round(f30[0], 3), "m30_on_shortfall_corr": round(f30[2], 3),
    "underreact_n": len(under), "underreact_oc_toward_implied_bp": mean_bp([sg(x["implied"]) * x["oc"] for x in under]),
    "underreact_m30_toward_bp": mean_bp([sg(x["implied"]) * x["m30"] if x["m30"] is not None else None for x in under]),
    "underreact_nd_toward_bp": mean_bp([sg(x["implied"]) * x["nd"] if x["nd"] is not None else None for x in under]),
    "overreact_n": len(over), "overreact_oc_toward_implied_bp": mean_bp([-sg(x["implied"]) * x["oc"] for x in over]),
    "overreact_m30_bp": mean_bp([-sg(x["implied"]) * x["m30"] if x["m30"] is not None else None for x in over]),
    "overreact_nd_bp": mean_bp([-sg(x["implied"]) * x["nd"] if x["nd"] is not None else None for x in over]),
    "gap_over_implied_median": round(st.median([x["co"] / x["implied"] for x in rows if abs(x["implied"]) >= 0.01]), 3)}
big = [x for x in rows if abs(x["bw_co"]) >= 0.04]
T["bw_move_ge4pct_linked"] = {"n_obs": len(big), "n_events": len({(x["bw"], x["date"]) for x in big}),
    "peer_gap_signed_bp": mean_bp([sg(x["bw_co"]) * x["co"] for x in big]),
    "peer_m30_signed_bp": mean_bp([sg(x["bw_co"]) * x["m30"] if x["m30"] is not None else None for x in big]),
    "peer_oc_signed_bp": mean_bp([sg(x["bw_co"]) * x["oc"] for x in big]), "peer_oc_same_dir_rate": rate([sg(x["bw_co"]) * x["oc"] for x in big]),
    "peer_nd_signed_bp": mean_bp([sg(x["bw_co"]) * x["nd"] if x["nd"] is not None else None for x in big]),
    "peer_nd_same_dir_rate": rate([sg(x["bw_co"]) * x["nd"] if x["nd"] is not None else None for x in big])}
for d in (1, -1):
    b2 = [x for x in big if sg(x["bw_co"]) == d]
    T[f"bw_{'up' if d > 0 else 'down'}_ge4pct_linked"] = {"n_obs": len(b2), "n_events": len({(x["bw"], x["date"]) for x in b2}),
        "peer_gap_bp": mean_bp([x["co"] for x in b2]), "peer_oc_bp": mean_bp([x["oc"] for x in b2]), "peer_nd_bp": mean_bp([x["nd"] for x in b2]),
        "peer_m30_bp": mean_bp([x["m30"] for x in b2])}
# all peers (not only linked) for +-4% bellwether moves
allbig = []
for i, e in enumerate(events):
    if abs(e["co"]) < 0.04: continue
    for p in peers:
        o = OBS.get((e["bw"], p), {}).get(i)
        if o: allbig.append((sg(e["co"]), o))
T["bw_move_ge4pct_all_peers"] = {"n_obs": len(allbig), "peer_gap_signed_bp": mean_bp([s * o["co"] for s, o in allbig]),
    "peer_oc_signed_bp": mean_bp([s * o["oc"] for s, o in allbig]), "peer_nd_signed_bp": mean_bp([s * o["nd"] if o["nd"] is not None else None for s, o in allbig])}
# per bellwether: bellwether's own follow-through
T["bw_self"] = {bw: {"n": len([e for e in events if e["bw"] == bw]), "med_abs_co_bp": round(st.median(abs(e["co"]) for e in events if e["bw"] == bw) * 1e4),
                     "oc_signed_bp": mean_bp([sg(e["co"]) * e["oc"] for e in events if e["bw"] == bw])} for bw in BW}
# ---- tonight: LRCX after hours
S = X["snap"]
def ah(s):
    v = S.get(s) or {}
    if not v.get("last") or not v.get("close") or not (v.get("bar_t") or "").startswith("2026-10-21"): return None
    if (v.get("last_t") or "") < "2026-10-21T20:00": return None
    x = v["last"] / v["close"] - 1
    return None if abs(x) < 1e-9 else x  # last print == close: no real extended-hours trade
lr = ah("LRCX")
TON = []
for p, v in MAP["LRCX"].items():
    c = v.get("co")
    if not c or c["n"] < 8: continue
    imp = c["alpha"] + c["slope"] * lr if lr is not None else None
    a = ah(p)
    z = (a - imp) / c["resid_sd"] if (a is not None and imp is not None and c["resid_sd"]) else None
    TON.append({"peer": p, "tier": tiers.get(p), "slope_co": c["slope"], "corr_co": c["corr"], "n": c["n"], "implied": imp, "actual_ah": a,
                "diff": (a - imp) if a is not None else None, "z": z,
                "flag": None if z is None else ("overshot (fell more than implied)" if z < -1 else "undershot / held up" if z > 1 else "in line")})
TON.sort(key=lambda t: -(t["corr_co"] or 0))
out = {"events": events, "n_events": len(events), "map": MAP, "linked": LINK, "trade": T, "tonight": {"lrcx_ah": lr, "rows": TON,
       "lrcx_snap": S.get("LRCX")}, "n_rows_linked": len(rows)}
(P / "readthrough-20261021.json").write_text(json.dumps(out, indent=1))
print("events", len(events), "linked rows", len(rows), "LRCX AH", lr)
print(json.dumps(T, indent=1))
