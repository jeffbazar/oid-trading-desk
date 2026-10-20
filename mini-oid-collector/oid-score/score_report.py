#!/usr/bin/env python3
"""Score accuracy report + re-scoring / ablation (research only).

  score_report.py                         # all logged live rows, logged scores
  score_report.py --mode backfill         # backfill rows only (mode=all for both)
  score_report.py --date 2026-10-19       # one session
  score_report.py --config alt.json       # re-score logged history with an alternate config
  score_report.py --ablate                # drop one input at a time, report change by horizon
Writes ~/oid-data/score/reports/summary-<date|all>-<mode>[-<cfg>].json (+ latest-summary.json for the daily job).

Metrics per horizon: n; hit = share of nonzero scores whose forward return had the same sign;
edge_bps = mean(sign(score) * ret) in basis points; corr = Pearson(raw, ret);
by bucket -3..+3: n, avg ret (bps), hit (nonzero buckets), avg MFE/MAE in the bucket's direction, wall/flip touch rates.
"""
import argparse, copy, json, math, statistics as stt
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import score_lib as L

HORIZONS = ["5m", "15m", "30m", "60m", "120m", "close", "next_open"]


def jl(p):
    out = []
    try:
        for ln in Path(p).read_text().splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    except OSError:
        pass
    return out


def load(mode, date):
    rows, outs = {}, defaultdict(dict)
    pats = {"live": ["scores-*.jsonl"], "backfill": ["backfill-scores-*.jsonl"], "all": ["scores-*.jsonl", "backfill-scores-*.jsonl"]}[mode]
    for pat in pats:
        for sp in sorted(L.OUT.glob(pat)):
            if mode == "live" and sp.name.startswith("backfill-"):
                continue
            if date and not sp.stem.endswith(date.replace("-", "")):
                continue
            for r in jl(sp):
                if r.get("trigger") != "badge":
                    rows[r["id"]] = r
            for o in jl(sp.with_name(sp.name.replace("scores-", "outcomes-"))):
                outs[o["id"]][o["h"]] = o
    return rows, outs


def sgn(x):
    return (x > 0) - (x < 0)


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    try:
        return round(stt.correlation(xs, ys), 3)
    except Exception:
        mx, my = stt.mean(xs), stt.mean(ys)
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3) if sx and sy else None


def metrics(pairs):
    """pairs: [(score, raw, outcome)] for one horizon."""
    nz = [(s, o["ret_pct"]) for s, _, o in pairs if s]
    hit = round(sum(1 for s, r in nz if sgn(r) == sgn(s)) / len(nz), 3) if nz else None
    edge = round(stt.mean(sgn(s) * r for s, r in nz) * 100, 2) if nz else None
    corr = pearson([raw for _, raw, _ in pairs], [o["ret_pct"] for _, _, o in pairs])
    return {"n": len(pairs), "n_nonzero": len(nz), "hit": hit, "edge_bps": edge, "corr_raw": corr}


def bucket_table(pairs):
    B = defaultdict(list)
    for s, raw, o in pairs:
        B[s].append(o)
    out = {}
    for s in range(-3, 4):
        os_ = B.get(s) or []
        if not os_:
            continue
        rets = [o["ret_pct"] for o in os_]
        d = {"n": len(os_), "avg_ret_bps": round(stt.mean(rets) * 100, 2)}
        if s:
            d["hit"] = round(sum(1 for r in rets if sgn(r) == sgn(s)) / len(rets), 3)
        else:
            d["avg_abs_ret_bps"] = round(stt.mean(abs(r) for r in rets) * 100, 2)
        if "up_pct" in os_[0]:
            fav = [(o["up_pct"] if s >= 0 else -o["dn_pct"]) for o in os_]
            adv = [(o["dn_pct"] if s >= 0 else -o["up_pct"]) for o in os_]
            d["avg_mfe_bps"], d["avg_mae_bps"] = round(stt.mean(fav) * 100, 2), round(stt.mean(adv) * 100, 2)
            for k in ("cw", "pw", "gf"):
                t = [o["touch"][k] for o in os_ if k in (o.get("touch") or {})]
                if t:
                    d[f"touch_{k}"] = round(sum(t) / len(t), 3)
        out[str(s)] = d
    return out


def analyze(rows, outs, cfg=None):
    """cfg=None -> logged scores; else re-score every row under cfg."""
    sc = {}
    for i, r in rows.items():
        if cfg is None:
            sc[i] = (r["score"], r["raw"])
        else:
            raw, s, _ = L.rescore(r, cfg)
            sc[i] = (s, raw)
    res = {"overall": {}, "buckets": {}, "by_ticker": {}, "by_slot": {}, "by_trigger": {}}
    for h in HORIZONS:
        pairs = [(sc[i][0], sc[i][1], outs[i][h]) for i in rows if h in outs.get(i, {})]
        if not pairs:
            continue
        res["overall"][h] = metrics(pairs)
        res["buckets"][h] = bucket_table(pairs)
        for key, fld in (("by_ticker", "sym"), ("by_slot", "slot"), ("by_trigger", "trigger")):
            G = defaultdict(list)
            for i in rows:
                if h in outs.get(i, {}):
                    G[rows[i].get(fld)].append((sc[i][0], sc[i][1], outs[i][h]))
            res[key][h] = {str(k): metrics(v) for k, v in sorted(G.items(), key=lambda kv: str(kv[0]))}
    res["score_dist"] = {str(s): sum(1 for v in sc.values() if v[0] == s) for s in range(-3, 4)}
    return res


def ablation(rows, outs, base_cfg):
    base = analyze(rows, outs, base_cfg)["overall"]
    out = {"base": base, "drop": {}}
    for name in base_cfg["components"]:
        if not base_cfg["components"][name].get("enabled", True):
            continue
        c = copy.deepcopy(base_cfg)
        c["components"][name]["enabled"] = False
        c["config_version"] = f"{base_cfg['config_version']}-no_{name}"
        ov = analyze(rows, outs, c)["overall"]
        d = {}
        for h, m in ov.items():
            b = base.get(h) or {}
            d[h] = {**m, "d_hit": None if m["hit"] is None or b.get("hit") is None else round(m["hit"] - b["hit"], 3),
                    "d_edge_bps": None if m["edge_bps"] is None or b.get("edge_bps") is None else round(m["edge_bps"] - b["edge_bps"], 2),
                    "d_corr": None if m["corr_raw"] is None or b.get("corr_raw") is None else round(m["corr_raw"] - b["corr_raw"], 3)}
        out["drop"][name] = d
    return out


def fmt(res, abl=None, title=""):
    lines = [title]
    lines.append("horizon   n  nz   hit   edge_bps  corr")
    for h, m in res["overall"].items():
        lines.append(f"{h:<8}{m['n']:>4}{m['n_nonzero']:>4}  {m['hit'] if m['hit'] is not None else '-':>5}  {m['edge_bps'] if m['edge_bps'] is not None else '-':>8}  {m['corr_raw'] if m['corr_raw'] is not None else '-'}")
    lines.append("score dist: " + json.dumps(res["score_dist"]))
    for h in ("30m", "close"):
        if h in res["buckets"]:
            lines.append(f"buckets @{h}: " + "  ".join(f"{k}: n{v['n']} {v['avg_ret_bps']}bps" + (f" hit{v['hit']}" if 'hit' in v else '') for k, v in res["buckets"][h].items()))
    if abl:
        lines.append("ablation (drop one input; delta hit / delta edge_bps vs base):")
        hs = list(abl["base"].keys())
        lines.append("drop      " + "".join(f"{h:>16}" for h in hs))
        for name, d in abl["drop"].items():
            lines.append(f"{name:<10}" + "".join(f"{(str(d[h]['d_hit']) + '/' + str(d[h]['d_edge_bps'])) if h in d else '-':>16}" for h in hs))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="live", choices=["live", "backfill", "all"])
    ap.add_argument("--date")
    ap.add_argument("--config", help="alternate config to re-score history with")
    ap.add_argument("--ablate", action="store_true")
    ap.add_argument("--daily", action="store_true", help="also write latest-summary.json")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    rows, outs = load(a.mode, a.date)
    cfg = L.load_config(a.config) if a.config else None
    base_cfg = cfg or L.load_config()
    res = analyze(rows, outs, cfg)
    abl = ablation(rows, outs, base_cfg) if a.ablate else None
    now = datetime.now(L.PT)
    doc = {"generated_pt": now.strftime("%Y-%m-%d %I:%M %p PT"), "mode": a.mode, "date": a.date or "all",
           "scored_with": base_cfg["config_version"] if cfg else "logged", "n_rows": len(rows),
           "n_outcome_rows": sum(len(v) for v in outs.values()),
           "caveat": "tiny sample - research only, not a trading signal" if len(rows) < 2000 else None,
           "result": res, "ablation": abl}
    rd = L.OUT / "reports"
    rd.mkdir(parents=True, exist_ok=True)
    tag = f"{(a.date or 'all').replace('-', '')}-{a.mode}" + (f"-{base_cfg['config_version']}" if cfg else "") + ("-ablate" if a.ablate else "")
    p = rd / f"summary-{tag}.json"
    p.write_text(json.dumps(doc, indent=1))
    if a.daily:
        (rd / "latest-summary.json").write_text(json.dumps(doc, indent=1))
    if not a.quiet:
        print(fmt(res, abl, f"OID direction score report · mode={a.mode} · date={a.date or 'all'} · scored_with={doc['scored_with']} · rows={len(rows)}"))
        print("->", p)


if __name__ == "__main__":
    main()
