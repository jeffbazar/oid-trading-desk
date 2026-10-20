#!/usr/bin/env python3
"""Replay a session's LIGHT (Sector watch) score changes every --step seconds (default 5) from logged data.

  score_replay_wide.py 2026-10-20 [--step 5] [--out DIR]

Same profile/maths as score_wide.py (profiles.light). Inputs re-evaluated every step, all at or before the step time:
  price      = close of the last bar that ended at or before the step: wide 5 s RTH bars when the archive has them,
               else the wide store's 1-min bars (then the replay is effectively 1-minute resolution - flagged in summary.json)
  trend/volume from closed 1-min bars (wide store), ATR(14) from earlier sessions, 15-min rvol from the wide norms
  market     = SPY/QQQ closed 1-min bars (core store) + VIX held from the core's logged 15-min SPY row + UW tide
Output (derived, overwritten): ~/oid-data/score/replay-YYYYMMDD-wide/{changes-wide,episodes-wide,episodes-wide-buffered}-YYYYMMDD.jsonl
+ summary.json.  Research/log only.
"""
import argparse, json, shutil, time
from collections import Counter
from datetime import datetime
from pathlib import Path
import score_lib as L
import score_engine as E
import score_changes as SC
import score_wide as W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--step", type=float, default=5.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = L.load_config()
    P, paths = W.setup(cfg)
    date, d = a.date, a.date.replace("-", "")
    out = Path(a.out) if a.out else L.OUT / f"replay-{d}-wide"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    c0 = time.process_time()
    syms, sec = W.universe(P, paths)
    bars1m = {s: L.load_day_bars(s, date, store=paths["store"]) for s in syms}
    atr = {s: L.daily_atr(s, date, store=paths["store"])[0] for s in syms}
    L._HIST.clear()
    for s in SC.INDEX:
        bars1m[s] = L.load_day_bars(s, date)
        atr[s] = L.daily_atr(s, date)[0]
    gb, used = W.grading_bars(date, P, paths, syms)
    idx5 = SC.load_5s(date, only=set(SC.INDEX))
    allbars = {**{s: gb[s] for s in syms if gb.get(s)}, **idx5}
    S = SC.Sources(date, need_bars=False)
    ring = SC.Ring(trim=SC.RING_S)
    trk = SC.Tracker(out, mode="replay", persist=False, band=float((P.get("changes") or {}).get("buffer_band", SC.BUFFER_BAND)),
                     tag=P["profile"].get("file_tag", "wide"), tag_fn=W.tag_fn(P, sec))
    ptr = {s: 0 for s in allbars}
    t_open = datetime.strptime(date, "%Y-%m-%d").replace(hour=6, minute=30, tzinfo=L.PT).timestamp()
    t_end = SC.session_end_t(date)
    t = t_open + a.step
    steps = 0
    load_s = time.process_time() - c0
    c1 = time.process_time()
    pass_cpu = []
    while t <= t_end + 0.001:
        p0 = time.process_time()
        new = []
        for s, bl in allbars.items():
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
        mkt = E.market_inputs(t, date, P, bars1m, atr, vix)
        for s in syms:
            lb = ring.last(s, t)
            if not lb or not atr.get(s):
                continue
            px = lb[5]
            row = W.score_row(s, t, px, date, P, bars1m.get(s), atr.get(s), mkt, "replay")
            cx = W.ctx_for(s, t, px, atr.get(s), lb[7], ring, extra={"px_src": "5s_close" if (lb[1] - lb[0]) < 10 else "1m_close"})
            trk.observe(date, t, s, px, row, cx, P["config_version"])
        pass_cpu.append(time.process_time() - p0)
        steps += 1
        t += a.step
    px_end = {s: (ring.last(s, t_end) or [None] * 6)[5] for s in syms}
    trk.close_all(t_end, "session_end", px_by=px_end)
    cpu = time.process_time() - c1
    tag = P["profile"].get("file_tag", "wide")
    ch = [json.loads(x) for x in (out / f"changes-{tag}-{d}.jsonl").open()]
    ep = [json.loads(x) for x in (out / f"episodes-{tag}-{d}.jsonl").open()]
    real = [c for c in ch if c["prev_score"] is not None]
    hours = (t_end - t_open) / 3600.0
    scored = sorted({c["sym"] for c in ch})
    per = Counter(c["sym"] for c in real)
    vals = sorted(per.get(s, 0) / hours for s in scored)
    durs = sorted(e["duration_s"] for e in ep)
    big = Counter()
    for e in ep:
        if abs(e["score"]) >= 2:
            big[(e.get("sector") or "?", abs(e["score"]))] += 1
    summ = {"date": date, "profile": P["score_profile"], "config_version": P["config_version"], "inputs": sorted(W.enabled(P)),
            "step_s": a.step, "symbols_universe": len(syms), "symbols_scored": len(scored), "steps": steps,
            "price_bars": used, "resolution_note": ("1-minute: no wide 5 s RTH bars for this date, price/peak/trough from 1-min bars"
                                                    if used["5s"] == 0 else "5 s where available, 1-min fallback for the rest"),
            "window_pt": [L.pt_str(t_open), L.pt_str(t_end)], "hours": round(hours, 2),
            "changes_rows": len(ch), "score_changes": len(real), "episodes": len(ep),
            "changes_per_ticker_hour": {"mean": round(len(real) / max(1, len(scored)) / hours, 1),
                                        "median": round(vals[len(vals) // 2], 1) if vals else None},
            "episode_duration_s_median": durs[len(durs) // 2] if durs else None,
            "holds_by_score": dict(sorted(Counter(str(e["score"]) for e in ep).items())),
            "big_holds_by_sector": {f"{k[0]} | ±{k[1]}": v for k, v in sorted(big.items())},
            "cpu_s": {"load": round(load_s, 2), "replay_total": round(cpu, 2),
                      "per_pass_ms_median": round(sorted(pass_cpu)[len(pass_cpu) // 2] * 1000, 2) if pass_cpu else None}}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
