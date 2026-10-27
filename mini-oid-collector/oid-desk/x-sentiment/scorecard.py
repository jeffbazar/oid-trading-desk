"""Daily SHADOW scorecard for the X sentiment feed: do sentiment swings / chatter spikes lead or lag price?
Prices: collector 1m SIP bars (~/oid-desk/desk/cache/bars/store/live/<SYM>-1m-<YYYYMMDD>.jsonl).
Horizons: 5m, 15m, 30m forward (the minute-scale end of the score label horizons; sentiment is sampled every 5-15 min).
Lead test: sign(sentiment change) vs forward return. Lag test: same sign vs the PRIOR 15m return (did tone just follow price?).
Chatter test: rows with chatter_z >= 2 -> forward |move| vs that ticker's median |move|, and direction by net sign.
Writes scorecard-YYYYMMDD.md/.json next to the feed. Never feeds the live score."""
import datetime as dt, json, statistics
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HZ = [5, 15, 30]
SWING = 0.25
ZSPIKE = 2.0


def load_bars(sym, ymd):
    p = Path.home() / f"oid-desk/desk/cache/bars/store/live/{sym}-1m-{ymd}.jsonl"
    bars = {}
    if not p.exists(): return []
    for line in open(p):
        try:
            b = json.loads(line); t = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).timestamp()
            bars[t] = float(b["c"])           # last write per minute wins
        except Exception: pass
    return sorted(bars.items())


def px_at(bars, t):
    """close of the last bar that ENDED at or before t (bar start + 60 <= t)."""
    best = None
    for s, c in bars:
        if s + 60 <= t: best = c
        else: break
    return best


def ret_bp(a, b):
    return None if (a is None or b is None or a == 0) else (b / a - 1) * 1e4


def pct(h, n):
    return f"{100*h/n:.0f}% ({h}/{n})" if n else "n/a"


def corr(x, y):
    if len(x) < 8: return None
    try: return round(statistics.correlation(x, y), 3)
    except Exception: return None


def run(args, cfg, DATA, OUT):
    ymd = args.date or dt.datetime.now(PT).strftime("%Y%m%d")
    src = OUT / f"{ymd}.jsonl"
    rows = []
    if src.exists():
        for line in open(src):
            try:
                r = json.loads(line)
                if r.get("status") == "ok" and r.get("tier") != "manual": rows.append(r)
            except Exception: pass
    by = {}
    for r in rows: by.setdefault(r["sym"], []).append(r)
    lead = {h: [0, 0] for h in HZ}; lag = [0, 0]; spike = {h: [0, 0, []] for h in HZ}
    xs = {h: [] for h in HZ}; ys = {h: [] for h in HZ}; px_, py_ = [], []
    nsw = 0
    for sym, rs in by.items():
        rs.sort(key=lambda r: r["t"]); bars = load_bars(sym, ymd)
        if not bars: continue
        moves = [abs(ret_bp(bars[i][1], bars[i + 15][1]) or 0) for i in range(0, max(0, len(bars) - 15), 5)]
        med = statistics.median(moves) if moves else None
        prev = None
        for r in rs:
            t = r["t"]; p0 = px_at(bars, t)
            fwd = {h: ret_bp(p0, px_at(bars, t + 60 * h)) for h in HZ}
            back = ret_bp(px_at(bars, t - 900), p0)
            ne = r.get("net_ewma")
            if prev is not None and ne is not None and prev.get("net_ewma") is not None:
                d = ne - prev["net_ewma"]
                for h in HZ:
                    if fwd[h] is not None: xs[h].append(d); ys[h].append(fwd[h])
                if back is not None: px_.append(d); py_.append(back)
                if abs(d) >= SWING:
                    nsw += 1; sgn = 1 if d > 0 else -1
                    for h in HZ:
                        if fwd[h] not in (None, 0.0): lead[h][1] += 1; lead[h][0] += (fwd[h] * sgn > 0)
                    if back not in (None, 0.0): lag[1] += 1; lag[0] += (back * sgn > 0)
            z = r.get("chatter_z")
            if z is not None and z >= ZSPIKE:
                sgn = 1 if (r.get("net") or 0) > 0 else -1 if (r.get("net") or 0) < 0 else 0
                for h in HZ:
                    if fwd[h] is None: continue
                    spike[h][2].append(abs(fwd[h]) / med if med else None)
                    if sgn and fwd[h] != 0: spike[h][1] += 1; spike[h][0] += (fwd[h] * sgn > 0)
            prev = r
    res = {"date": ymd, "rows": len(rows), "tickers": len(by), "swings": nsw, "swing_threshold": SWING, "z_spike": ZSPIKE,
           "lead_hit": {h: lead[h] for h in HZ}, "lag_hit_prior15m": lag,
           "corr_lead": {h: corr(xs[h], ys[h]) for h in HZ}, "corr_lag_prior15m": corr(px_, py_),
           "spike_dir_hit": {h: spike[h][:2] for h in HZ},
           "spike_move_vs_median": {h: (round(statistics.median([v for v in spike[h][2] if v is not None]), 2)
                                        if [v for v in spike[h][2] if v is not None] else None) for h in HZ},
           "shadow": True}
    L = [f"# X sentiment shadow scorecard, {ymd[:4]}-{ymd[4:6]}-{ymd[6:]}", "",
         "SHADOW ONLY: this feed does not touch the live direction score, orders or alerts.", "",
         f"Rows graded: {len(rows)} across {len(by)} tickers. Sentiment swings (|change in smoothed net| >= {SWING}): {nsw}.", "",
         "## Does a sentiment swing come before the move? (lead)", "| horizon | swing direction right | corr(change in net, fwd return) |", "|---|---|---|"]
    for h in HZ: L.append(f"| {h}m | {pct(*lead[h])} | {res['corr_lead'][h]} |")
    L += ["", "## Or after it? (lag)", f"Swing matched the PRIOR 15m move: {pct(*lag)}; corr(change in net, prior 15m return) = {res['corr_lag_prior15m']}.",
          "If the lag numbers beat the lead numbers, chatter is following price, not leading it.", "",
          f"## Chatter spikes (chatter_z >= {ZSPIKE})", "| horizon | direction right (by net sign) | median fwd move vs typical |", "|---|---|---|"]
    for h in HZ: L.append(f"| {h}m | {pct(*spike[h][:2])} | {res['spike_move_vs_median'][h] if res['spike_move_vs_median'][h] is not None else 'n/a'}x |")
    L += ["", "Coin flip is 50%. Needs ~2 weeks of shadow days before any of this can be trusted."]
    (OUT / f"scorecard-{ymd}.json").write_text(json.dumps(res, indent=1, default=str))
    (OUT / f"scorecard-{ymd}.md").write_text("\n".join(L) + "\n")
    print(f"scorecard {ymd}: rows={len(rows)} swings={nsw} -> {OUT / f'scorecard-{ymd}.md'}")
    return 0
