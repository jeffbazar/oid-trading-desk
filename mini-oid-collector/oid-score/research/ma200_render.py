import json,sys
def G(s):
    return "n 0" if not s or not s.get("n") else f"{s['n']:,} / {s['hit']*100:.1f}% / {s['mean_bp']:+.2f} / {s['total_bp']:+,.0f}"
R=json.load(open(sys.argv[1]))
def f(s):
    if not s or not s.get("n"): return "n 0"
    return f"{s['n']:,} | {s['hit']*100:.1f}% | {s['mean_bp']:+.2f} | {s['total_bp']:+,.0f}"
L=[f"# 200-day SMA regime gate — live direction score replay ({R['version']})","",
   f"SMA source: {R['sma_source']}. Cross-check vs the mini's Alpaca bars_1d (core names, no split): {R['sma_crosscheck_vs_mini_alpaca_bars_1d']}.","",
   "Buckets on |px/SMA200-1| at the row: pinned <1%, near 1-2%, off >2%. Trades = non-overlapping first snapshot of each same-sign score run per symbol per horizon. bp = directional move to the horizon (no stop/target).",""]
for S in R["sets"]:
    tag=f"{S['profile']} {S['mode']} {S['days'][0]}..{S['days'][-1]}"
    P=S["pooled"]
    L+=[f"## {tag} — {P['names']} names, {P['rows']:,} rows",""]
    L+=["### (a)/(b) 15s rows with score≠0 by bucket","","| hz | bucket | rows | row share | miss share | hit | mean bp |","|---|---|---|---|---|---|---|"]
    for hz in ("5m","15m","30m"):
        for b in ("pinned<1%","near1-2%","off>2%"):
            s=P["rows_by_bucket"][hz][b]
            if s.get("n"): L.append(f"| {hz} | {b} | {s['n']:,} | {s['row_share']*100:.1f}% | {s['miss_share']*100:.1f}% | {s['hit']*100:.1f}% | {s['mean_bp']:+.2f} |")
        for b in ("with 200d side","against 200d side"):
            s=P["rows_by_bucket"][hz][b]
            if s.get("n"): L.append(f"| {hz} | {b} | {s['n']:,} | | | {s['hit']*100:.1f}% | {s['mean_bp']:+.2f} |")
    L+=["","### (c) trades (non-overlapping) — n | hit | mean bp | total bp","","| hz | gate | trades | hit | mean bp | total bp | % removed | short-all same trades hit/mean | long-all hit/mean |","|---|---|---|---|---|---|---|---|---|"]
    for hz in ("5m","15m","30m"):
        for g in ("no gate","gate: drop pinned<1%","gate: drop <2%"):
            s=P["trades"][hz][g]; sh=s["short_all_same_trades"]; lo=s["long_all_same_trades"]
            rm=s.get("pct_trades_removed"); 
            L.append(f"| {hz} | {g} | {f(s)} | {'' if rm is None else f'{rm*100:.1f}%'} | {sh.get('hit',0)*100:.1f}% / {sh.get('mean_bp',0):+.2f} | {lo.get('hit',0)*100:.1f}% / {lo.get('mean_bp',0):+.2f} |")
        for b in ("only pinned<1%","only near1-2%","only off>2%"):
            L.append(f"| {hz} | {b} | {f(P['trades'][hz][b])} | | | |")
    L+=["","### by day — trades: n / hit / mean bp / total bp","","| day | hz | no gate | drop <1% | drop <2% | names pinned/near/off |","|---|---|---|---|---|---|"]
    for d,a in S["by_day"].items():
        for hz in ("5m","15m","30m"):
            t=a["trades"][hz]
            L.append(f"| {d} | {hz} | {G(t['no gate'])} | {G(t['gate: drop pinned<1%'])} | {G(t['gate: drop <2%'])} | {a['bucket_mix_names']} |")
    if S.get("holds_scorecard_def"):
        L+=["","### scorecard holds (episodes, start-to-stop gain)","","| gate | holds | hit | mean bp | total bp | share | miss share |","|---|---|---|---|---|---|---|"]
        for g,s in S["holds_scorecard_def"].items():
            L.append(f"| {g} | {f(s)} | {s['share_of_holds']*100:.1f}% | {s['miss_share']*100:.1f}% |")
        for d,h in S["holds_by_day"].items():
            L.append(f"| {d}: no gate ; drop<1% ; drop<2% | {G(h['no gate'])} ; {G(h['gate: drop pinned<1%'])} ; {G(h['gate: drop <2%'])} | | | | | |")
    L.append("")
open(sys.argv[2],"w").write("\n".join(L)+"\n"); print("\n".join(L))
