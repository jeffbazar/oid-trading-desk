"""Research only: robustness of read-through tradeability results.
Variants: full; ex-20 macro-shock sessions; ex-16 (drop only the 16 certain ones, keep the 4 uncertain);
out-of-sample (link + betas fit on events before 2025-10-21, tested on events from 2025-10-21 on).
Event-clustered stats: average within each event first, then across events (t = mean / (sd/sqrt(n_events))).
Inputs: readthrough-20261021.json (events), readthrough-data-20261021.json, macro_shock_exclusions (Research Bot).
Output: ~/oid-data/patterns/readthrough-robust-20261021.json"""
import json, math, csv, statistics as st
from collections import defaultdict
from pathlib import Path
P = Path.home() / "oid-data/patterns"
X = json.loads((P / "readthrough-data-20261021.json").read_text())
RT = json.loads((P / "readthrough-20261021.json").read_text())
EV = RT["events"]; tiers = X["tiers"]
D = {s: {b[0]: b for b in bs} for s, bs in X["daily"].items()}
F30 = X["first30"]; O, C = 1, 4
TWIN = {"GOOG": "GOOGL", "GOOGL": "GOOG"}
SH = list(csv.DictReader(open(P / "macro_shock_exclusions_2024-10_2026-10.csv")))
UNCERTAIN = {"2026-03-11", "2026-03-26", "2026-10-08", "2026-10-21"}  # 2 "confirm date", 1 secondary source, 1 overlaps tonight's earnings
EX20 = {d for r in SH for d in r["sessions_to_exclude"].split(";")}
EX16 = {d for r in SH if r["shock_date"] not in UNCERTAIN for d in r["sessions_to_exclude"].split(";")}
def r(s, d0, f0, d1, f1):
    a, b = D[s].get(d0), D[s].get(d1)
    if not a or not b: return None
    x = b[f1] / a[f0] - 1
    return None if abs(x) > 0.6 else x
def obs(e, p):
    co, cc = r(p, e["d0"], C, e["d1"], O), r(p, e["d0"], C, e["d1"], C)
    if co is None or cc is None: return None
    f = (F30.get(e["d1"]) or {}).get(p); o1 = D[p][e["d1"]][O]
    return {"co": co, "cc": cc, "oc": D[p][e["d1"]][C] / o1 - 1, "m30": (f[3] / o1 - 1) if f else None, "nd": r(p, e["d1"], C, e["d2"], C)}
peers = sorted(s for s in D if s != "SPY")
OB = {}
for i, e in enumerate(EV):
    for p in peers:
        if p == e["bw"] or TWIN.get(e["bw"]) == p or tiers.get(p) != "core": continue
        o = obs(e, p)
        if o: OB[(i, p)] = o
def ols(x, y):
    if len(x) < 3: return None
    mx, my = st.mean(x), st.mean(y); sxx = sum((a - mx) ** 2 for a in x); syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0: return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    return b, my - b * mx, b * math.sqrt(sxx / syy)
sg = lambda x: 1 if x > 0 else -1
def run(train, test, loo):
    """train/test: sets of event idx. link peers + betas from train; if loo, drop the test event itself from the fit."""
    link = {}
    for bw in {EV[i]["bw"] for i in test}:
        cs = []
        for p in peers:
            idx = [i for i in train if EV[i]["bw"] == bw and (i, p) in OB]
            if len(idx) < 8: continue
            f = ols([EV[i]["cc"] for i in idx], [OB[(i, p)]["cc"] for i in idx])
            if f: cs.append((p, f[2]))
        link[bw] = [p for p, _ in sorted(cs, key=lambda t: -t[1])[:10]]
    rows = []
    for i in test:
        e = EV[i]
        for p in link.get(e["bw"], []):
            if (i, p) not in OB: continue
            idx = [k for k in train if EV[k]["bw"] == e["bw"] and (k, p) in OB and not (loo and k == i)]
            f = ols([EV[k]["co"] for k in idx], [OB[(k, p)]["co"] for k in idx])
            if not f: continue
            o = OB[(i, p)]
            rows.append(dict(o, ev=i, bw_co=e["co"], implied=f[1] + f[0] * e["co"]))
    return rows
def stat(rows, fn):
    """per-obs mean bp, n obs; event-clustered mean bp, n events, t."""
    per = defaultdict(list)
    for x in rows:
        v = fn(x)
        if v is not None: per[x["ev"]].append(v)
    allv = [v for vs in per.values() for v in vs]
    if not allv: return {"n_obs": 0, "n_ev": 0}
    em = [st.mean(vs) for vs in per.values()]
    t = (st.mean(em) / (st.stdev(em) / math.sqrt(len(em)))) if len(em) > 2 and st.stdev(em) > 0 else None
    return {"obs_bp": round(st.mean(allv) * 1e4, 1), "n_obs": len(allv), "ev_bp": round(st.mean(em) * 1e4, 1), "n_ev": len(em),
            "t": round(t, 2) if t is not None else None, "rate": round(sum(v > 0 for v in allv) / len(allv), 3)}
def metrics(rows):
    G = [x for x in rows if abs(x["co"]) >= 0.01]
    U = [x for x in rows if abs(x["implied"]) >= 0.01 and sg(x["co"]) == sg(x["implied"]) and abs(x["co"]) < 0.75 * abs(x["implied"])]
    Ov = [x for x in rows if abs(x["implied"]) >= 0.01 and sg(x["co"]) == sg(x["implied"]) and abs(x["co"]) > 1.25 * abs(x["implied"])]
    dn = [x for x in rows if x["bw_co"] <= -0.04]; up = [x for x in rows if x["bw_co"] >= 0.04]
    m = lambda k: (lambda x: x[k])
    return {
        "gap_hold_ge1pct": {"m30": stat(G, lambda x: sg(x["co"]) * x["m30"] if x["m30"] is not None else None),
                            "oc": stat(G, lambda x: sg(x["co"]) * x["oc"]), "nd": stat(G, lambda x: sg(x["co"]) * x["nd"] if x["nd"] is not None else None)},
        "underreact_catchup": {"m30": stat(U, lambda x: sg(x["implied"]) * x["m30"] if x["m30"] is not None else None),
                               "oc": stat(U, lambda x: sg(x["implied"]) * x["oc"]), "nd": stat(U, lambda x: sg(x["implied"]) * x["nd"] if x["nd"] is not None else None)},
        "overreact_continue": {"oc": stat(Ov, lambda x: sg(x["implied"]) * x["oc"]), "nd": stat(Ov, lambda x: sg(x["implied"]) * x["nd"] if x["nd"] is not None else None)},
        "bw_down_ge4": {"gap": stat(dn, m("co")), "m30": stat(dn, lambda x: x["m30"]), "oc": stat(dn, m("oc")), "nd": stat(dn, lambda x: x["nd"])},
        "bw_up_ge4": {"gap": stat(up, m("co")), "m30": stat(up, lambda x: x["m30"]), "oc": stat(up, m("oc")), "nd": stat(up, lambda x: x["nd"])}}
allI = set(range(len(EV)))
hit = lambda S: {i for i in allI if EV[i]["d1"] in S or EV[i]["d2"] in S}
h20, h16 = hit(EX20), hit(EX16)
CUT = "2025-10-21"
tr = {i for i in allI if EV[i]["d1"] < CUT}; te = allI - tr
V = {"full": run(allI, allI, True), "ex20": run(allI - h20, allI - h20, True), "ex16": run(allI - h16, allI - h16, True),
     "oos_train_pre_2025-10-21": run(tr, tr, True), "oos_test_from_2025-10-21": run(tr, te, False)}
out = {"excluded_events_ex20": sorted((EV[i]["bw"], EV[i]["d1"]) for i in h20), "excluded_events_ex16": sorted((EV[i]["bw"], EV[i]["d1"]) for i in h16),
       "uncertain": sorted(UNCERTAIN), "n_events": {"full": len(allI), "ex20": len(allI - h20), "ex16": len(allI - h16), "train": len(tr), "test": len(te)},
       "variants": {k: metrics(v) for k, v in V.items()}}
(P / "readthrough-robust-20261021.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: out[k] for k in ("excluded_events_ex20", "excluded_events_ex16", "n_events")}))
for blk in ["bw_down_ge4", "gap_hold_ge1pct", "underreact_catchup", "overreact_continue", "bw_up_ge4"]:
    print("\n==", blk)
    for k, v in out["variants"].items():
        print(" %-26s" % k, " | ".join("%s %s/%s ev %s (t %s, ne %s, no %s)" % (w, s.get("obs_bp"), "", s.get("ev_bp"), s.get("t"), s.get("n_ev"), s.get("n_obs")) for w, s in v[blk].items()))
