#!/usr/bin/env python3
"""Backfill score rows for a past session from logged 1-min bars (clearly labeled mode=backfill).

  score_backfill.py 2026-10-19 [--config path]

Limits (recorded in every row as flags): walls/flip come from the newest cached FlashAlpha snapshot
(lookahead=True when that snapshot is later than the score time); options-aggressor flow and VIX history
are not logged intraday, so those inputs are missing (q=0); UW market tide uses only points <= t.
Output: ~/oid-data/score/backfill-scores-YYYYMMDD.jsonl (overwritten each run; it is derived data).
"""
import argparse, json, urllib.request
from datetime import datetime
import score_lib as L
import score_engine as E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = L.load_config(a.config)
    date = a.date
    try:
        with urllib.request.urlopen(L.STATE_URL, timeout=5) as r:
            syms = [x["sym"] for x in json.loads(r.read())["rows"] if x.get("kind") != "ext"]
    except Exception:
        syms = sorted(p.name.split("-1m-")[0] for p in (L.STORE / "live").glob(f"*-1m-{date.replace('-', '')}.jsonl"))
    syms = [s for s in syms if s not in set(cfg.get("exclude") or [])]
    W = L.walls_from_files()
    bars = {s: L.load_day_bars(s, date) for s in set(syms) | {"SPY", "QQQ"}}
    atr = {s: L.daily_atr(s, date)[0] for s in bars}
    rows = []
    sched = E.schedule(cfg, date)
    # vol_surge events of that date from the trigger engine (via the live page state, if still listed)
    evs = []
    try:
        with urllib.request.urlopen(L.STATE_URL, timeout=5) as r:
            for e in (json.loads(r.read()).get("vol_surge") or {}).get("events") or []:
                if str(e.get("engine_pt") or "").startswith(date):
                    t = datetime.strptime(e["engine_pt"].replace(" PT", ""), "%Y-%m-%d %I:%M:%S %p").replace(tzinfo=L.PT).timestamp()
                    evs.append((t, e))
    except Exception:
        pass
    jobs = [(t, hm, trig, None) for t, hm, trig in sched] + [(t, datetime.fromtimestamp(t, L.PT).strftime("%H:%M"), "vol_surge", e) for t, e in evs]
    for t, hm, trig, ev in sorted(jobs, key=lambda j: j[0]):
        mkt = E.market_inputs(t, date, cfg, bars, atr, None)
        for s in syms:
            if ev and s != ev.get("symbol"):
                continue
            b = bars.get(s) or []
            closed = [x for x in b if x["ts"] + 60 <= t + 1]
            if not closed or not atr.get(s):
                continue
            px = closed[-1]["c"]
            w = W.get(s)
            walls = None
            if w:
                walls = dict(w, as_of_pt=L.pt_str(w["t"]), age_s=round(t - w["t"]), stale=(t - w["t"]) > cfg["staleness"]["walls_stale_s"],
                             lookahead=w["t"] > t)
                if walls["lookahead"]:
                    walls["stale"] = False
            evd = {k: ev.get(k) for k in ("engine_pt", "level", "level_price", "dir", "rvol_1m", "vol_60s", "dry_run")} if ev else None
            rows.append(E.make_row(s, t, px, date, cfg, b, atr[s], walls, None, mkt, "backfill", trig, slot=hm, event=evd,
                                   extra={"backfill_note": "walls from latest cached snapshot (lookahead flag); no flow/VIX history"}))
    p = L.OUT / f"backfill-scores-{date.replace('-', '')}.jsonl"
    L.OUT.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    from collections import Counter
    print(f"backfill {date}: {len(rows)} rows, {len(set(r['sym'] for r in rows))} symbols, slots {len(sched)}, vol_surge events {len(evs)} -> {p}")
    print("score distribution:", dict(sorted(Counter(r["score"] for r in rows).items())))


if __name__ == "__main__":
    main()
