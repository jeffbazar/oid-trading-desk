# Render direction-analysis-results.md from direction-analysis-results.json (+ fade-robustness.json, replay-drop xcheck)
import json, os, sys
from pathlib import Path
D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.path.expanduser("~/oid-data/score/direction-analysis"))
R = json.load(open(D / "direction-analysis-results.json"))
RB = json.load(open(D / "fade-robustness.json")) if (D / "fade-robustness.json").exists() else {}
xp = D / "replay-drop" / "xcheck-20261023-drop-trend.json"
XC = json.load(open(xp)) if xp.exists() else None
L, P = R["live 10/21-23"], R["replay 10/19-20"]
V = R["variants"]
o = []; w = o.append
def pct(x): return "–" if x is None else f"{x*100:.1f}%"
def s4(v): return f"{v['n']} / {pct(v['hit'])} / {v['mean_bp']:+.2f} / {v['total_bp']:+.0f}"
HZ = ("5m", "15m", "30m")

w("# Live direction score — why it loses (research only, no live changes)\n")
w(f"Generated from `direction-analysis-results.json` (config {R.get('config')}). Live window 10/21–23/2026 (live mode), replay 10/19–20 (replay mode); "
  f"57 core names minus CBRS/DRAM/SKHY/SPCX (no 200-day SMA) — same trade definition as the ma200-gate job: first snapshot of each non-zero score run, "
  f"non-overlapping per name per horizon, return = sign × forward return (gross, bp). No stop/target exists in the live score.\n")
w("Reconstruction: score rebuilt from logged component c/q with `score_lib.combine` semantics matches the logged score on " + ", ".join(f"{d} {v['recomputed_score_matches_logged']*100:.0f}% of {v['rows']} rows" for d, v in R["reconstruction"].items()) + ".\n")

b15, b30 = L["baselines"]["15m"], L["baselines"]["30m"]; p15 = P["baselines"]["15m"]
lg = {k: v for k, v in L["lag"].items()}
F1 = V[R["selection"]["chosen"]]
w("## Summary of findings\n")
w(f"- **Losses are long calls on the live days.** 15m: long calls {s4(b15['long_calls'])} vs short calls {s4(b15['short_calls'])}; 30m: long {s4(b30['long_calls'])} vs short {s4(b30['short_calls'])}. "
  f"But on the 10/19–20 replay days short calls lost more (15m short {s4(p15['short_calls'])}, long {s4(p15['long_calls'])}), so the problem is not 'longs in a down tape' — it is the direction call itself.")
w(f"- **The score is anti-predictive, not just bad on down days.** Inverse score at 15m: live {s4(b15['inverse_score'])}, replay {s4(p15['inverse_score'])}; it beats short-all on the replay days ({s4(p15['short_all'])}). Score is negative at 15m on 4 of 5 days (only 10/22 positive).")
w(f"- **Misses are 'right then reversed', not 'small'.** At 15m, right-but-small is only {pct(L['outcomes']['15m']['all']['cost5bp']['right-but-small']['share'])} of trades; wrong trades that first moved ≥5 bp our way carry {pct(L['outcomes']['15m']['all']['cost5bp']['wrong: right-then-reversed (MFE>=thr)']['share_of_negative_bp'])} of negative bp (≈{pct(L['outcomes']['15m']['all']['0.25atr_h']['wrong: right-then-reversed (MFE>=thr)']['share_of_negative_bp'])} with an ATR-scaled threshold).")
w(f"- **Mechanism = chasing (momentum calls into mean reversion).** Trend/volume/market components flip only after a move has already happened (15m pre-flip move in the flip direction: trend {pct(lg['trend']['pre15m_move_in_flip_dir_bp']['hit'])} / {lg['trend']['pre15m_move_in_flip_dir_bp']['mean_bp']:+.1f} bp, volume {pct(lg['volume']['pre15m_move_in_flip_dir_bp']['hit'])} / {lg['volume']['pre15m_move_in_flip_dir_bp']['mean_bp']:+.1f} bp, market {pct(lg['market']['pre15m_move_in_flip_dir_bp']['hit'])} / {lg['market']['pre15m_move_in_flip_dir_bp']['mean_bp']:+.1f} bp) and the next 15m goes the other way (post-15m mean {lg['trend']['post15m']['mean_bp']:+.2f}, {lg['volume']['post15m']['mean_bp']:+.2f}, {lg['market']['post15m']['mean_bp']:+.2f} bp). "
  f"On live trades corr(trailing 15m return, forward signed return) = {L['signatures']['15m'].get('corr_trailing15m_vs_forward')} at 15m. Live longs after a ≥20 bp 15m rise: {s4(L['signatures']['15m']['long']['after 15m rise >=+20bp'])}; longs above the session open: {s4(L['signatures']['15m']['long']['above session open'])}. Flow flips show no lead or lag (pre/post ≈ 0).")
w(f"- **Regimes:** losses concentrate in the high-ATR% tercile (live 15m {s4(L['regimes']['15m']['ATR% tercile: high']['all'])}), in long calls below the 20/50-day SMA (most longs: {s4(L['signatures']['15m']['long']['below 20d SMA'])}), and in AI-infra/optical/semis groups. Near-vs-far 200-day is not a driver (≈8% of trades). VIX range 16.7–19.5 is too narrow to say anything about VIX.")
w(f"- **No single component is the culprit:** every component's own sign hits < 50% at 15m live except market (≈50%); dominance on losers ≈ dominance on winners for all six; no drop-one variant is positive on any split at 15m.")
w(f"- **Proposal (one change): fade the score — trade the opposite of its sign (F1).** Fit 10/21–22 15m {s4(F1['fit 10/21-22']['15m']['score'])}; test 10/23 {s4(F1['test 10/23']['15m']['score'])}; replay 10/19–20 (incl. up day 10/20) {s4(F1['replay 10/19-20']['15m']['score'])}. Short-all on the same trades: fit {s4(V['live (recomputed)']['fit 10/21-22']['15m']['short_all'])}, test {s4(V['live (recomputed)']['test 10/23']['15m']['short_all'])}, replay {s4(V['live (recomputed)']['replay 10/19-20']['15m']['short_all'])}. "
  f"Net of 5 bp the 15m edge is thin (fit {F1['fit 10/21-22']['15m']['score']['net5_mean_bp']}, test {F1['test 10/23']['15m']['score']['net5_mean_bp']}, replay {F1['replay 10/19-20']['15m']['score']['net5_mean_bp']} bp) and 5m is negative net. "
  "It was added after seeing the inverse baseline, so it is NOT a blind holdout; a clean validation needs the next 5+ sessions untouched (shadow-only). F2 (invert only trend/volume/market) is the more surgical version, positive on all three splits at 15m and 30m but smaller (5m fit ≈ 0). F1 hit rates are only ~50–54%: the gain comes from avoiding the large adverse moves after chased entries, not from a higher hit rate.")
w("")
w("## Definitions\n")
w("```\n" + (R["definitions"] if isinstance(R["definitions"], str) else json.dumps(R["definitions"], indent=1)).strip() + "\n```\n")
w("Outcome buckets requested: wrong (d<=0) split into right-then-reversed (MFE >= threshold) and never-right; right-but-small (0<d<threshold); right (d>=threshold).\n")

w("## 1. Outcome split (live 10/21–23)\n")
w("Threshold = 5 bp (cost) unless noted. 'Share neg' = share of all negative bp.\n")
w("| h | side | trades | total bp | wrong % | right-then-reversed % (share neg) | never-right % (share neg) | right-but-small % (bp) | right % (bp) | med MFE / MAE |")
w("|---|---|---|---|---|---|---|---|---|---|")
for hz in HZ:
    for side in ("all", "long", "short"):
        x = L["outcomes"][hz][side]; c = x["cost5bp"]
        rr, nr = c["wrong: right-then-reversed (MFE>=thr)"], c["wrong: never right (MFE<thr)"]
        w(f"| {hz} | {side} | {x['trades']} | {x['total_bp']:+.0f} | {pct(c['wrong']['share'])} | {pct(rr['share'])} ({pct(rr['share_of_negative_bp'])}) | "
          f"{pct(nr['share'])} ({pct(nr['share_of_negative_bp'])}) | {pct(c['right-but-small']['share'])} ({c['right-but-small']['total_bp']:+.0f}) | "
          f"{pct(c['right']['share'])} ({c['right']['total_bp']:+.0f}) | {x['median_mfe_bp']} / {x['median_mae_bp']} |")
w("\nWith the 0.25×ATR-to-horizon threshold, right-then-reversed share of negative bp (all): " +
  ", ".join(f"{hz} {pct(L['outcomes'][hz]['all']['0.25atr_h']['wrong: right-then-reversed (MFE>=thr)']['share_of_negative_bp'])}" for hz in HZ) +
  "; the rest never reached the ATR threshold.\n")

w("## 2. Baselines on the same trades (n / hit / mean bp / total bp)\n")
for lab, S in (("live 10/21–23", L), ("replay 10/19–20", P)):
    w(f"**{lab}**\n"); w("| h | score | inverse score | short-all | long calls only | short calls only |"); w("|---|---|---|---|---|---|")
    for hz in HZ:
        b = S["baselines"][hz]; w(f"| {hz} | {s4(b['score'])} | {s4(b['inverse_score'])} | {s4(b['short_all'])} | {s4(b['long_calls'])} | {s4(b['short_calls'])} |")
    w("")
w("Per day, 15m (mean bp): \n"); w("| day | SPY o→c | VIX | score | inverse | short-all | long calls | short calls |"); w("|---|---|---|---|---|---|---|---|")
for S in (P, L):
    for d, b in S["baselines_by_day"]["15m"].items():
        spy = R["index_day"].get(d, {}).get("SPY", {}).get("open_to_close_pct")
        w(f"| {d} | {spy if spy is not None else '–'} | {R['vix'].get(d, {}).get('Close', '–')} | {b['score']['mean_bp']:+.2f} | {b['inverse_score']['mean_bp']:+.2f} | {b['short_all']['mean_bp']:+.2f} | "
          f"{b['long_calls']['mean_bp']:+.2f} (n {b['long_calls']['n']}) | {b['short_calls']['mean_bp']:+.2f} (n {b['short_calls']['n']}) |")
w("")

w("## 3. Regimes (15m; mean bp, n; L = long calls, S = short calls)\n")
for lab, S in (("live 10/21–23", L), ("replay 10/19–20", P)):
    w(f"**{lab}**\n"); w("| bucket | all n / hit / mean / total | L mean (n) | S mean (n) | share of neg bp |"); w("|---|---|---|---|---|")
    for k, v in S["regimes"]["15m"].items():
        a = v["all"]; w(f"| {k} | {a['n']} / {pct(a['hit'])} / {a['mean_bp']:+.2f} / {a['total_bp']:+.0f} | {v['long']['mean_bp']:+.2f} ({v['long']['n']}) | {v['short']['mean_bp']:+.2f} ({v['short']['n']}) | {pct(v['share_of_negative_bp'])} |")
    w("")
w("'name day up/down' uses the name's own close vs open (known only after the close — descriptive, not tradable). ATR% tercile cuts (bp): " + str(R["atr_pct_tercile_cuts_bp"]) + ".\n")

w("## 4. Components (live, 15m)\n")
c = L["components"]["15m"]; cp = P["components"]["15m"]
w("| comp | own-sign n / hit / mean bp | agrees w/ trade | dominant on losers | dominant on winners | replay own-sign hit / mean |"); w("|---|---|---|---|---|---|")
for k in c["own_sign_hit"]:
    v = c["own_sign_hit"][k]; vp = cp["own_sign_hit"][k]
    w(f"| {k} | {v['n']} / {pct(v['hit'])} / {v['mean_bp']:+.2f} | {pct(c['agrees_with_trade_sign'][k])} | {pct(c['dominant_on_losers'].get(k))} | {pct(c['dominant_on_winners'].get(k))} | {pct(vp['hit'])} / {vp['mean_bp']:+.2f} |")
w("\nDrop-one (offline recompute: component removed from numerator and denominator, as `SF.ablate`/`--drop` does), 15m mean bp:\n")
w("| variant | fit 10/21–22 | test 10/23 | replay 10/19–20 | live 10/21–23 |"); w("|---|---|---|---|---|")
for k in ["live (recomputed)"] + [k for k in V if k.startswith("drop")]:
    w(f"| {k} | " + " | ".join(f"{V[k][l]['15m']['score']['mean_bp']:+.2f} (n {V[k][l]['15m']['score']['n']})" for l in ("fit 10/21-22", "test 10/23", "replay 10/19-20", "live 10/21-23")) + " |")
w("")
if XC:
    w(f"Cross-check vs the real `score_replay_changes.py 2026-10-23 --drop trend` (rebuilds inputs from raw data): at {XC['rows']} logged snapshots the replay's score equals the offline drop-trend score {pct(XC['exact_match'])} of the time and has the same sign {pct(XC['sign_match'])} — the gap is replay input reconstruction (replay vs live inputs), not combine semantics. The replay script only emits episodes/changes, not labelled trades, so the offline recompute is used for P&L.\n")

w("## 5. Failure signatures (15m; n / hit / mean / total)\n")
for lab, S in (("live 10/21–23", L), ("replay 10/19–20", P)):
    g = S["signatures"]["15m"]; g3 = S["signatures"]["30m"]
    w(f"**{lab}** — corr(trailing 15m return, forward signed return) on trades: 15m {g.get('corr_trailing15m_vs_forward')} (n {g.get('n_corr')}), 30m {g3.get('corr_trailing15m_vs_forward')}\n")
    w("| condition | long calls | short calls |"); w("|---|---|---|")
    for k in g["long"]:
        w(f"| {k} | {s4(g['long'][k])} | {s4(g['short'].get(k, {'n':0,'hit':None,'mean_bp':0,'total_bp':0}))} |")
    w("")
w("**Component lag test** (no pattern inputs feed the live score, so lag is tested on components): each crossing of a component's c through ±0.2; 'pre' = the 15m move before the flip in the flip direction, 'post' = the move after, in the flip direction.\n")
w("| set | comp | flips | pre-15m: % in flip dir / mean bp | post 5m mean | post 15m hit / mean | post 30m mean |"); w("|---|---|---|---|---|---|---|")
for lab, S in (("live", L), ("replay", P)):
    for k, v in S["lag"].items():
        w(f"| {lab} | {k} | {v['flips']} | {pct(v['pre15m_move_in_flip_dir_bp']['hit'])} / {v['pre15m_move_in_flip_dir_bp']['mean_bp']:+.2f} | {v['post5m']['mean_bp']:+.2f} | {pct(v['post15m']['hit'])} / {v['post15m']['mean_bp']:+.2f} | {v['post30m']['mean_bp']:+.2f} |")
w("")

w("## 6. Candidate changes — fit 10/21–22, test 10/23, replay 10/19–20 (n / hit / mean bp / total bp)\n")
sel = R["selection"]
w(f"Selection rule (in code): {sel['rule']}. Chosen: **{sel['chosen']}**. Caveat: {sel.get('caveat')}\n")
for hz in ("15m", "30m", "5m"):
    w(f"**{hz}**\n"); w("| variant | fit 10/21–22 | test 10/23 | replay 10/19–20 |"); w("|---|---|---|---|")
    for k in V:
        if k.startswith("drop"): continue
        w(f"| {k} | " + " | ".join(s4(V[k][l][hz]['score']) for l in ("fit 10/21-22", "test 10/23", "replay 10/19-20")) + " |")
    w("| short-all (same trades as live) | " + " | ".join(s4(V['live (recomputed)'][l][hz]['short_all']) for l in ("fit 10/21-22", "test 10/23", "replay 10/19-20")) + " |")
    w("")
ch = V[sel["chosen"]]
w("Chosen variant per day (15m mean bp): " + ", ".join(f"{d} {ch[d]['15m']['score']['mean_bp']:+.2f}" for d in ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23")) + "\n")
w("Net of 5 bp/trade (chosen): " + "; ".join(f"{l} " + ", ".join(f"{hz} {ch[l][hz]['score'].get('net5_mean_bp')}" for hz in HZ) for l in ("fit 10/21-22", "test 10/23", "replay 10/19-20")) + "\n")
if RB:
    w("**Robustness of the fade (F1)** — clustered by symbol-day (does NOT account for cross-name correlation within a day):\n")
    w("| set | n | mean | median | 5% trimmed mean | t (sym-day cluster) | top-5 names share of total | names positive |"); w("|---|---|---|---|---|---|---|---|")
    for k, v in RB.items():
        w(f"| {k} | {v['n']} | {v['mean']:+.2f} | {v['median']:+.2f} | {v['trim5_mean']:+.2f} | {v['t_cluster']} | {pct(v['top5_share_of_total'])} | {v['names_positive']} |")
    w("")

w("## Caveats\n")
for c_ in [
    "Five sessions total, only one clear index down day (10/22 SPY o→c −0.31%, QQQ −1.28%); 10/23 gapped down then was flat intraday; 10/21 and 10/20 were up days. Any 'down-day' conclusion rests on ~1 day.",
    "Trades are strongly cross-sectionally correlated (57 names, mostly semis/AI infra, move together) and overlap in time; per-trade t-stats overstate significance. The effective sample is closer to 5 days than ~2,000 trades.",
    "Returns are gross snapshot-to-horizon; no stop/target exists, so MFE/MAE buckets describe path, not a tradable exit. Net-of-5bp is shown where relevant.",
    "10/19–20 are replay-mode scores (inputs rebuilt from recorded data), 10/21–23 are live-mode logged scores.",
    "Industry groups are a hand map (score_features.sector is null for core).",
    "F1/F2 were added to the candidate list after the inverse-score baseline had been seen on all five days, so their 'test' and 'replay' columns are not a blind holdout. The blind candidates (P1–P3, single-component inverts, late-entry gates) all stayed negative out of sample.",
]: w(f"- {c_}")
(D / "direction-analysis-results.md").write_text("\n".join(o) + "\n")
print("wrote", D / "direction-analysis-results.md", len(o), "lines")
