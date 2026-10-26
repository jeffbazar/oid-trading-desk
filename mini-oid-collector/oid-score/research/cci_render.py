#!/usr/bin/env python3
"""Render CCI-breakout-filter result JSONs into REPORT.md (research only)."""
import json, sys
from pathlib import Path
R = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "oid-data/score/cci-breakout-filter"
ORDER = ["nq_60m_yahoo", "qqq_60m_ext", "qqq_60m_rth", "core_60m_rth", "nq_1d", "ndx_1d", "qqq_1d", "core_1d"]
CMP = ["CCI27_lo18<-100 (post)", "NOT CCI (complement)", "RSI14_lo18 calibrated", "min(close-SMA20)/ATR lo18 calibrated",
       "pullback depth (36h high - 18 low)/ATR calibrated", "close<SMA20 in last 18", "RSI14_lo18<30"]
f = lambda x, d=2: "–" if x is None else (f"{x:,.{d}f}" if isinstance(x, (int, float)) else str(x))
p = lambda x: "–" if x is None else f"{100*x:.0f}%"
L = ["# CCI breakout filter test — results tables", ""]
for k in ORDER:
    fp = R / "results" / f"{k}.json"
    if not fp.exists(): L += [f"## {k}: not run", ""]; continue
    r = json.loads(fp.read_text()); bc = r["base_case"]
    syms = r["bars"]; s0 = next(iter(syms.values()))
    L += [f"## {k} — {r['desc']}", f"Symbols {len(syms)}; first {s0['first'][:10]} last {s0['last'][:10]} (first symbol); cost {r['cost_bp']} bp/trade; IS/OOS cut {r['cut']}; "
          f"CCI pass rate {f(s0['cci_pass_rate'],2)}; family {r['family_size']}; runtime {r['runtime_s']} s", "",
          f"Base case `{r['base_case_def']}` (returns in bp net of cost)", "",
          "| | trades | win | avg bp | net bp | maxDD bp | net/DD |", "|---|---|---|---|---|---|---|"]
    for nm in ["base", "cci", "not_cci"] + [c for c in CMP[2:] if c in bc]:
        s = bc[nm]; L.append(f"| {nm} | {s['n']} | {p(s.get('win'))} | {f(s.get('avg'))} | {f(s.get('net'),0)} | {f(s.get('dd'),0)} | {f(s.get('pdd'))} |")
    for lab, key in (("base", "base_is_oos"), ("cci", "cci_is_oos")):
        a, b = bc[key]; L.append(f"| {lab} IS / OOS | {a['n']} / {b['n']} | | {f(a.get('avg'))} / {f(b.get('avg'))} | {f(a.get('net'),0)} / {f(b.get('net'),0)} | | {f(a.get('pdd'))} / {f(b.get('pdd'))} |")
    L.append(f"\nWelch t (CCI-pass vs CCI-fail trades): {f(bc.get('welch_t_cci_vs_notcci'))}")
    if "base_usd" in bc:
        L.append(f"USD (1 NQ, $20/pt, 1.25 pt cost): base avg ${f(bc['base_usd']['avg_trade_usd'],0)} net ${f(bc['base_usd']['net_usd'],0)} net/DD {f(bc['base_usd']['net_over_dd'])}; "
                 f"CCI avg ${f(bc['cci_usd']['avg_trade_usd'],0)} net ${f(bc['cci_usd']['net_usd'],0)} net/DD {f(bc['cci_usd']['net_over_dd'])}")
    L += ["", "Family (post-style metrics; all / IS / OOS)", "",
          "| filter | variants | net improved | avg improved | avg ≥+22% (of profitable) | bounce | median Δavg bp | median kept |", "|---|---|---|---|---|---|---|---|"]
    for c in CMP:
        if c not in r["family"]: continue
        d = r["family"][c]; g = lambda m, fn=p: " / ".join(fn(d[sp].get(m)) for sp in ("all", "is", "oos"))
        L.append(f"| {c} | {d['all'].get('n_variants')} | {g('pct_net_improved')} | {g('pct_avg_improved')} | {g('pct_avg_up22_of_profitable')} | {g('bounce_index')} | {g('median_davg_bp', f)} | {p(d['all'].get('median_trade_retention'))} |")
    rs = r.get("random_summary")
    if rs:
        L += ["", "Random filters (same keep rate) — net-improved share: mean / max over seeds; CCI percentile rank among seeds", ""]
        for sp, v in rs.items():
            L.append(f"- {sp}: random mean {p(v['pct_net_improved_mean'])}, max {p(v['pct_net_improved_max'])}; random median Δavg mean {f(v['median_davg_bp_mean'])} bp, max {f(v['median_davg_bp_max'])} bp; CCI rank {f(v['cci_pct_net_improved_rank'])} (n={v['n_seeds']})")
    nb = {kk: v for kk, v in r["family"].items() if kk.startswith("NB ") or kk.startswith("NB")}
    if nb:
        ok = [v["all"] for v in nb.values() if v["all"].get("n_variants")]
        L += ["", f"Neighbourhood (CCI period × lookback × threshold, {len(ok)} settings, small grid): "
              f"{sum(v['pct_net_improved'] > .5 for v in ok)} improve net in >50% of variants; {sum(v['median_davg_bp'] > 0 for v in ok)} have median Δavg > 0; "
              f"OOS: {sum(v['oos'].get('pct_net_improved', 0) > .5 for v in nb.values())} >50% net, {sum((v['oos'].get('median_davg_bp') or 0) > 0 for v in nb.values())} Δavg>0"]
    L.append("")
dr = R / "desk-relevance.json"
if dr.exists():
    d = json.loads(dr.read_text())
    L += ["## Desk relevance — 5m breakouts on the core universe (archive 2025-10-20 → 2026-10-23, RTH, gross)", "",
          "| event / horizon | all n, avg bp | CCI5m pass vs fail (t) | CCI60m pass vs fail (t) | RSI5m-cal pass vs fail (t) |", "|---|---|---|---|---|"]
    for kk, v in d["results"].items():
        cell = lambda nm: f"{f(v[nm]['pass'].get('mean_bp'))} (n {v[nm]['pass']['n']}) vs {f(v[nm]['fail'].get('mean_bp'))} ({f(v[nm]['day_cluster_t_pass_minus_fail'])})"
        L.append(f"| {kk} | {v['all']['n']}, {f(v['all']['mean_bp'])} | {cell('CCI5m')} | {cell('CCI60m')} | {cell('RSI5m-cal')} |")
(R / "REPORT_tables.md").write_text("\n".join(L) + "\n"); print("\n".join(L))
