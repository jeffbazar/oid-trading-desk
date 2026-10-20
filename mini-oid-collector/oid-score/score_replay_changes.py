#!/usr/bin/env python3
"""Replay a session's score changes from logged data, every --step seconds (default 5), to test/measure change logging.

  score_replay_changes.py 2026-10-20 [--step 5] [--out DIR]

Fast inputs re-evaluated every step: price (5 s SIP bar close), 1-min bars (VWAP/trend/volume, closed bars only),
SPY/QQQ tape, options aggressor C/P (optflow cp-history, 15 s samples), momentum state (events file).
Slow inputs (walls/flip, VIX) are held from the last logged 15-min score row at or before each step.
No lookahead: every input is taken at or before the step time. Score math = score_lib (unchanged).
Output (derived, overwritten): ~/oid-data/score/replay-YYYYMMDD/{changes,episodes}-YYYYMMDD.jsonl + summary.json
"""
import argparse, json, shutil, time
from collections import Counter
from datetime import datetime
from pathlib import Path
import score_lib as L
import score_engine as E
import score_changes as SC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--step", type=float, default=5.0)
    ap.add_argument("--out")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = L.load_config(a.config)
    date, d = a.date, a.date.replace("-", "")
    out = Path(a.out) if a.out else L.OUT / f"replay-{d}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    c0 = time.process_time()
    S = SC.Sources(date)
    syms = sorted(s for s in S.rows if s not in set(cfg.get("exclude") or []))
    bars1m = {s: L.load_day_bars(s, date) for s in set(syms) | set(SC.INDEX)}
    atr = {s: L.daily_atr(s, date)[0] for s in bars1m}
    ring = SC.Ring(trim=SC.RING_S)
    trk = SC.Tracker(out, mode="replay", persist=False, band=float((cfg.get("changes") or {}).get("buffer_band", SC.BUFFER_BAND)))
    ptr = {s: 0 for s in S.bars}
    t_first = min(r["t"] for v in S.rows.values() for r in v)
    t_end = SC.session_end_t(date)
    t = t_first
    steps = 0
    load_s = time.process_time() - c0
    c1 = time.process_time()
    pass_cpu = []
    while t <= t_end + 0.001:
        p0 = time.process_time()
        new = []
        for s, bl in S.bars.items():
            i = ptr[s]
            while i < len(bl) and bl[i][1] <= t + 0.001:
                ring.add(s, bl[i])
                new.append((s, bl[i]))
                i += 1
            ptr[s] = i
        trk.bars(new)
        snap_spy = S.snap("SPY", t) or {}
        mx = ((snap_spy.get("comps") or {}).get("market") or {}).get("x") or {}
        vix = {k: mx[k] for k in ("vix", "vix_ref", "vix_ref_kind", "vix_chg_pct", "vix_age_s", "vix_stale") if k in mx} or None
        mkt = E.market_inputs(t, date, cfg, bars1m, atr, vix)
        for s in syms:
            lb = ring.last(s, t)
            snap = S.snap(s, t)
            if not lb or not snap or not atr.get(s):
                continue
            px = lb[5]
            walls = S.walls_from_snap(snap, t, cfg)
            flow_ctx, flow_score = S.flow_at(s, t)
            if flow_score is None:
                fl = (snap.get("comps") or {}).get("flow") or {}
                flow_score = fl if (fl.get("f") or {}).get("src") == "uw" else None
            row = E.make_row(s, t, float(px), date, cfg, bars1m.get(s), atr.get(s), walls, flow_score, mkt, "replay", "fast")
            ctx = SC.build_ctx(s, t, px, atr.get(s), flow_ctx, lb[7], walls, S.mom_at(s, t), ring)
            trk.observe(date, t, s, px, row, ctx, cfg["config_version"])
        pass_cpu.append(time.process_time() - p0)
        steps += 1
        t += a.step
    px_end = {s: (ring.last(s, t_end) or [None] * 6)[5] for s in syms}
    trk.close_all(t_end, "session_end", px_by=px_end)
    cpu = time.process_time() - c1
    # summary
    ch = [json.loads(x) for x in (out / f"changes-{d}.jsonl").open()]
    ep = [json.loads(x) for x in (out / f"episodes-{d}.jsonl").open()]
    real = [c for c in ch if c["prev_score"] is not None]
    bfile = out / f"episodes-buffered-{d}.jsonl"
    beps = [json.loads(x) for x in bfile.open()] if bfile.exists() else []
    hours = (t_end - t_first) / 3600.0
    per = Counter(c["sym"] for c in real)
    vals = sorted(per.get(s, 0) / hours for s in syms)
    med = vals[len(vals) // 2] if vals else None
    durs = sorted(e["duration_s"] for e in ep)
    dn = sorted(e["duration_s"] for e in ep if e["stop_reason"] == "score_change")
    summ = {"date": date, "step_s": a.step, "symbols": len(syms), "steps": steps, "window_pt": [L.pt_str(t_first), L.pt_str(t_end)],
            "hours": round(hours, 2), "changes_rows": len(ch), "score_changes": len(real), "episodes": len(ep),
            "changes_per_ticker_hour": {"mean": round(len(real) / max(1, len(syms)) / hours, 1), "median": round(med, 1) if med is not None else None,
                                        "max": [per.most_common(1)[0][0], round(per.most_common(1)[0][1] / hours, 1)] if per else None,
                                        "min": round(vals[0], 1) if vals else None},
            "episode_duration_s": {"median_all": durs[len(durs) // 2] if durs else None, "median_closed_by_change": dn[len(dn) // 2] if dn else None,
                                   "share_under_30s": round(sum(1 for x in dn if x < 30) / len(dn), 3) if dn else None,
                                   "share_under_60s": round(sum(1 for x in dn if x < 60) / len(dn), 3) if dn else None},
            "buffered_shadow": {"band": trk.band, "episodes": len(beps),
                                "changes_per_ticker_hour_mean": round((len(beps) - len(syms)) / max(1, len(syms)) / hours, 1) if beps else None,
                                "median_duration_s": sorted(e["duration_s"] for e in beps)[len(beps) // 2] if beps else None,
                                "note": "comparison-only shadow; raw score is primary"},
            "by_symbol_per_hour": {s: round(per.get(s, 0) / hours, 1) for s in syms},
            "cpu_s": {"load": round(load_s, 2), "replay_total": round(cpu, 2),
                      "per_pass_ms_median": round(sorted(pass_cpu)[len(pass_cpu) // 2] * 1000, 2) if pass_cpu else None}}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps({k: v for k, v in summ.items() if k != "by_symbol_per_hour"}, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
