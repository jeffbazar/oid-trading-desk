# Robustness of F1 (fade) on 15m/30m: median, 5% trimmed mean, cluster(symbol-day) SE, top-name concentration
import json, os, sys, statistics as S, collections, math
sys.path.insert(0, os.path.expanduser("~/oid-score/research"))
import direction_analysis as DA
days = {"fit 10/21-22": ["2026-10-21", "2026-10-22"], "test 10/23": ["2026-10-23"], "replay 10/19-20": ["2026-10-19", "2026-10-20"]}
data = {d: DA.load(d, "live" if d >= "2026-10-21" else "replay") for v in days.values() for d in v}
out = {}
for lab, ds in days.items():
    rows = [r for d in ds for r in data[d]]
    for r in rows: r["fade"] = -DA.recompute(r)
    for h in (900, 1800):
        tr = DA.trades(rows, h, "fade")
        xs = [DA.d_of(r, s, h) for r, s in tr]
        xs = [x for x in xs if x is not None]
        n = len(xs); m = sum(xs) / n
        k = int(0.05 * n); tm = S.mean(sorted(xs)[k:n - k])
        cl = collections.defaultdict(list)
        for (r, s) in tr:
            x = DA.d_of(r, s, h)
            if x is not None: cl[(r["symbol"], r["date"])].append(x)
        se = math.sqrt(sum((sum(v) - len(v) * m) ** 2 for v in cl.values())) / n
        byname = collections.Counter()
        for (r, s) in tr:
            x = DA.d_of(r, s, h)
            if x is not None: byname[r["symbol"]] += x
        top = byname.most_common(5); tot = sum(xs)
        pos_names = sum(1 for v in byname.values() if v > 0)
        out[f"{lab} {h//60}m"] = {"n": n, "mean": round(m, 2), "median": round(S.median(xs), 2), "trim5_mean": round(tm, 2),
            "cluster_se_symday": round(se, 2), "t_cluster": round(m / se, 2), "n_clusters": len(cl),
            "top5_names_bp": [(a, round(b)) for a, b in top], "top5_share_of_total": round(sum(b for _, b in top) / tot, 2) if tot else None,
            "total_ex_top5": round(tot - sum(b for _, b in top)), "names_positive": f"{pos_names}/{len(byname)}"}
        print(lab, h // 60, out[f"{lab} {h//60}m"])
json.dump(out, open(os.path.expanduser("~/oid-data/score/direction-analysis/fade-robustness.json"), "w"), indent=1)
