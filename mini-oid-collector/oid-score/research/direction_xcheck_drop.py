# Cross-check: offline drop-trend recompute vs score_replay_changes.py --drop trend (10/23), score at each logged snapshot
import json, bisect, collections, os, sys
sys.path.insert(0, os.path.expanduser("~/oid-score/research"))
import direction_analysis as DA
p = os.path.expanduser("~/oid-data/score/direction-analysis/replay-drop/20261023-drop-trend/changes-20261023.jsonl")
ch = collections.defaultdict(list)
for ln in open(p):
    j = json.loads(ln)
    if j.get("kind") == "score_change": ch[j["sym"]].append((j["t"], j["score"]))
for v in ch.values(): v.sort()
rows = DA.load("2026-10-23", "live")
n = same = same_sign = 0
for r in rows:
    s = ch.get(r["symbol"])
    if not s: continue
    i = bisect.bisect_right([a for a, _ in s], r["t"] + 0.01) - 1
    if i < 0: continue
    rep = s[i][1]; off = DA.recompute(r, drop=("trend",))
    n += 1; same += rep == off; same_sign += ((rep > 0) - (rep < 0)) == ((off > 0) - (off < 0))
out = {"rows": n, "exact_match": round(same / n, 4), "sign_match": round(same_sign / n, 4)}
print(out)
json.dump(out, open(os.path.expanduser("~/oid-data/score/direction-analysis/replay-drop/xcheck-20261023-drop-trend.json"), "w"))
