#!/usr/bin/env python3
"""PATTERNS (2026-10-21): backtest base rates, replays and the nightly grader for the shadow pattern detector.

  pattern_learn.py backtest [--min-sessions 2]   every stored 1-min session of every tracked ticker through the same
        engines -> grade each TRIGGERED detection on 1-min bars (target before a closing invalidation, within the horizon)
        -> ~/oid-data/patterns/base-rates.json  "backtest": {pattern|interval|direction: n, target_hit, rate, ...}
  pattern_learn.py replay --date YYYY-MM-DD      one day through the engines (warmed on the sessions before it) ->
        archive patterns/date=D/part-patterns-replay-1.jsonl (mode=replay), counts per pattern and a sample
        [--live-json] also writes live.json (mode=replay; score_features ignores non-live files)
  pattern_learn.py grade [--days 10]             nightly (launchd com.oid.desk.pattern-grade, weekdays 1:50 PM PT):
        label every detection of the last N archive days (target_hit / invalidated / expired / not_triggered, minutes
        to outcome, MFE/MAE) -> archive pattern_labels/date=D/part-pattern-grader-1.jsonl; live hit rates (final labels,
        mode=live) -> base-rates.json "live" (prob_est switches to live once n >= 20; both kept);
        scorecard ~/oid-data/patterns/scorecard-<D>.{md,json}; one row appended to ~/oid-data/score/experiments.jsonl
Shadow only; research/paper only; no orders; no paid calls.
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path.home() / "oid-score"))
import patterns as PT  # noqa: E402
import pattern_io as IO  # noqa: E402

EXP = Path.home() / "oid-data/score/experiments.jsonl"


def exp_upsert(row):
    """RRFIX 10/21: one experiments.jsonl row per id. A rerun replaces the earlier row for the same id (atomic rewrite)
    instead of appending a duplicate; rows with other ids are kept byte-for-byte."""
    keep = []
    if EXP.exists():
        for ln in EXP.read_text().splitlines():
            if not ln.strip():
                continue
            try:
                if json.loads(ln).get("id") == row["id"]:
                    continue
            except Exception:
                pass
            keep.append(ln)
    keep.append(json.dumps(row))
    EXP.parent.mkdir(parents=True, exist_ok=True)
    tmp = EXP.with_name("." + EXP.name + ".tmp")
    tmp.write_text("\n".join(keep) + "\n")
    tmp.replace(EXP)


def triggered_of(recs):
    """records -> {det_id: (first record, triggered record or None, last record)}"""
    by = {}
    for r in recs:
        x = by.setdefault(r["det_id"], [r, None, r])
        if r["state"] == "triggered" and x[1] is None:
            x[1] = r
        x[2] = r
    return by


def backtest(a):
    t0 = time.time()
    uni = IO.universe()
    graded, counts, sessions = [], Counter(), set()
    for j, (sym, tier, store) in enumerate(uni):
        b1 = IO.hist_1m(sym, store)
        if not b1:
            continue
        ss = sorted({b[6] for b in b1})
        sessions |= set(ss)
        if len(ss) <= a.min_sessions:
            continue
        start = ss[a.min_sessions]
        atr_d = IO.daily_atr([b for b in b1 if b[6] < start])
        recs = []
        for iv in PT.IV_MIN:
            e = PT.Engine(sym, iv, atr_d)
            for b in (b1 if iv == "1m" else PT.roll(b1, iv)):
                out = e.step(b)
                if b[6] >= start:
                    recs += out
        for det_id, (first, trg, last) in triggered_of(recs).items():
            counts[(first["pattern"], first["interval"], first["direction"], "detected")] += 1
            if trg and trg["direction"]:
                counts[(first["pattern"], first["interval"], first["direction"], "triggered")] += 1
                graded.append((trg, PT.grade(trg, b1)))
        if j % 25 == 0:
            IO.log(f"backtest {j + 1}/{len(uni)} {sym}: {len(graded)} graded so far ({time.time() - t0:.0f} s)")
    agg = PT.aggregate(graded)
    for k, v in agg.items():
        v["n_detected"] = counts.get((v["pattern"], v["interval"], v["direction"], "detected"), 0)
        v["n_triggered"] = counts.get((v["pattern"], v["interval"], v["direction"], "triggered"), 0)
    doc = IO.rates() or {}
    doc.update(detector_version=PT.DETECTOR_VERSION, built_pt=IO.pt_str(time.time()),
               method="every stored 1-min session of the core + Sector watch bar stores through the live engines (first "
                      f"{a.min_sessions} sessions per ticker = warm-up); a TRIGGERED detection is graded on 1-min bars from "
                      "the trigger bar's close: target touched first = hit; a 1-min close beyond invalidation = invalidated; "
                      "else expired at the horizon. rate = target_hit / n (n = final grades). In-sample for every replayed day.",
               backtest_sessions=[min(sessions), max(sessions)] if sessions else None, backtest_tickers=len(uni),
               backtest=agg)
    doc.setdefault("live", {})
    IO.PDIR.mkdir(parents=True, exist_ok=True)
    IO.RATES.write_text(json.dumps(doc, indent=1))
    IO.log(f"base rates: {len(agg)} keys from {len(graded)} graded detections, {len(uni)} tickers, "
           f"{doc['backtest_sessions']} in {time.time() - t0:.0f} s -> {IO.RATES}")
    top = sorted(agg.values(), key=lambda v: -v["n"])[:12]
    for v in top:
        print(f"  {v['pattern']:<20} {v['interval']:>3} {v['direction']:+d}  n={v['n']:<5} hit {v['rate']:.1%}  "
              f"med {v['med_min_to_hit']} min to hit")


def replay(a):
    t0 = time.time()
    D = a.date
    uni = IO.universe()
    rd = IO.rates()
    ctx = IO.ReplayCtx(D)
    w = IO.Writer("replay")
    engs, allr = {}, []
    for sym, tier, store in uni:
        h = IO.hist_1m(sym, store, before=D)
        if not h:
            continue
        eng = IO.warm(sym, h)
        b1 = IO.day_1m(sym, D, store, live_only=False)
        out = []
        for iv, e in eng.items():
            for b in (b1 if iv == "1m" else PT.roll(b1, iv)):
                out += e.step(b)
        for r in out:
            IO.enrich(r, rd, ctx, "replay")
        out.sort(key=lambda r: r["ts"])
        allr += out
        engs[sym] = eng
    allr.sort(key=lambda r: (r["ts"], r["ticker"]))
    w.write(D, allr)
    if a.live_json:
        IO.write_live(engs, rd, time.time(), mode="replay", note=f"replay of {D} (end-of-day state); the live daemon overwrites this at 6:30 AM PT")
    st = Counter(r["state"] for r in allr)
    ids = triggered_of(allr)
    per = Counter((v[0]["pattern"]) for v in ids.values())
    per_iv = Counter((v[0]["pattern"], v[0]["interval"]) for v in ids.values())
    trig = Counter(v[0]["pattern"] for v in ids.values() if v[1])
    summ = {"date": D, "tickers": len(engs), "records": len(allr), "detections": len(ids), "states": dict(st),
            "by_pattern": {p: {"detections": n, "triggered": trig.get(p, 0),
                               "by_interval": {iv: per_iv.get((p, iv), 0) for iv in PT.IV_MIN if per_iv.get((p, iv))}}
                           for p, n in per.most_common()},
            "secs": round(time.time() - t0, 1), "file": str(w.path)}
    (IO.PDIR / f"replay-{D}-summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    ex = [r for r in allr if r["state"] == "triggered" and r["direction"] and r["interval"] == "5m"][:1]
    if ex:
        print("SAMPLE", json.dumps(ex[0], indent=1))


def load_recs(day):
    out = []
    for p in sorted((IO.ARCH / "patterns" / f"date={day}").glob("part-patterns-*.jsonl")):
        for ln in p.read_text().splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def grade(a):
    t0 = time.time()
    days = sorted(p.name[5:] for p in (IO.ARCH / "patterns").glob("date=*"))[-a.days:]
    uni = {s: st for s, _, st in IO.universe()}
    bars = {}

    def b1_of(sym):
        if sym not in bars:
            st = uni.get(sym)
            h = IO.hist_1m(sym, st)
            last = h[-1][6] if h else ""
            import datetime as _dt
            today = _dt.datetime.now(IO.ET).strftime("%Y-%m-%d")
            if today > last:
                h += IO.day_1m(sym, today, st, live_only=True)
            bars[sym] = h
        return bars[sym]
    allg = defaultdict(list)
    for day in days:
        recs = load_recs(day)
        labs = []
        for mode in ("live", "replay"):
            for det_id, (first, trg, last) in triggered_of([r for r in recs if r.get("mode") == mode]).items():
                lab = {"label_id": det_id + ":" + mode, "det_id": det_id, "mode": mode, "date": day, "ticker": first["ticker"],
                       "interval": first["interval"], "pattern": first["pattern"], "direction": first["direction"],
                       "detected_ts": first["ts"], "prob_est": (trg or first).get("prob_est"),
                       "prob_source": (trg or first).get("prob_source"), "confidence_raw": first.get("confidence_raw"),
                       "detector_version": first.get("detector_version"), "graded_pt": IO.pt_str(time.time())}
                if not first["direction"]:
                    lab.update(outcome="context", final=True)
                elif not trg:
                    lab.update(outcome="not_triggered", final=last["state"] in ("failed", "expired"), last_state=last["state"])
                else:
                    g = PT.grade(trg, b1_of(first["ticker"]))
                    lab.update(g or {"outcome": "pending", "final": False})
                    lab["triggered_ts"] = trg["ts"]
                    if g:
                        allg[mode].append((trg, g))
                labs.append(lab)
        d = IO.ARCH / "pattern_labels" / f"date={day}"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "part-pattern-grader-1.jsonl", "w") as fh:
            for x in labs:
                fh.write(json.dumps({k: v for k, v in x.items() if v is not None}, separators=(",", ":")) + "\n")
    # live rates over ALL label files (final, mode=live)
    live_g = []
    for p in sorted((IO.ARCH / "pattern_labels").glob("date=*/part-pattern-grader-1.jsonl")):
        for ln in p.read_text().splitlines():
            x = json.loads(ln)
            if x.get("mode") == "live" and x.get("final") and x.get("outcome") in ("target_hit", "invalidated", "expired", "rejected_wrong_side"):
                live_g.append(({"pattern": x["pattern"], "interval": x["interval"], "direction": x["direction"],
                                "vol_confirm": None}, x))
    doc = IO.rates() or {}
    doc["live"] = PT.aggregate(live_g)
    doc["live_built_pt"] = IO.pt_str(time.time())
    IO.RATES.write_text(json.dumps(doc, indent=1))
    rep = {m: PT.aggregate(g) for m, g in allg.items()}
    D = days[-1] if days else "none"
    card = {"date": D, "days_graded": days, "detector_version": PT.DETECTOR_VERSION, "graded_pt": IO.pt_str(time.time()),
            "by_mode": rep, "live_rates_keys": len(doc["live"]),
            "live_n_total": sum(v["n"] for v in doc["live"].values())}
    (IO.PDIR / f"scorecard-{D}.json").write_text(json.dumps(card, indent=1))
    md = [f"# Pattern scorecard {D} (shadow, {PT.DETECTOR_VERSION})", "",
          f"Graded {IO.pt_str(time.time())}. Days: {', '.join(days)}. Triggered detections only; hit = target touched before "
          "a 1-min close beyond invalidation, within the horizon. RRFIX 10/21: setups whose target sits on the wrong side of entry "
          "(gap past the trigger) or whose entry is already beyond invalidation are rejected and excluded. med R:R = median "
          "|target-entry| / |entry-invalidation|; breakeven = 1/(1+R:R); 1:1 rate = same bars with target = entry +/- stop "
          "distance. Backtest rates are in base-rates.json (not regraded tonight).", ""]
    bt = doc.get("backtest") or {}
    for m, ag in rep.items():
        md += [f"## {m}", "", "| pattern | iv | dir | n | hit | live/replay rate | med R:R | breakeven | 1:1 rate (n) | rejected wrong side | backtest rate (n) | med min to hit |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in sorted(ag.items(), key=lambda kv: -kv[1]["n"]):
            b = bt.get(k) or {}
            md.append(f"| {v['pattern']} | {v['interval']} | {v['direction']:+d} | {v['n']} | {v['target_hit']} | "
                      f"{v['rate']:.1%} | {v.get('med_rr') if v.get('med_rr') is not None else '—'} | "
                      f"{(format(v['breakeven'], '.1%') if v.get('breakeven') is not None else '—')} | "
                      f"{(format(v['rate_1r'], '.1%') if v.get('rate_1r') is not None else '—')} ({v.get('n_1r', 0)}) | "
                      f"{v.get('n_rejected_wrong_side', 0)} | {(b.get('rate') or 0):.1%} ({b.get('n', 0)}) | {v['med_min_to_hit']} |")
        md.append("")
    (IO.PDIR / f"scorecard-{D}.md").write_text("\n".join(md))
    row = {"id": f"pattern-scorecard-{D}", "kind": "pattern_scorecard", "date": D, "created_pt": IO.pt_str(time.time()),
           "detector_version": PT.DETECTOR_VERSION, "shadow_only": True,
           "summary": {m: {"n": sum(v["n"] for v in ag.values()), "hit": sum(v["target_hit"] for v in ag.values())}
                       for m, ag in rep.items()},
           "live_rates": {k: {"n": v["n"], "rate": v["rate"], "med_rr": v.get("med_rr"), "rate_1r": v.get("rate_1r"),
                              "n_1r": v.get("n_1r")} for k, v in doc["live"].items()},
           "grader": "rrfix-20261021: wrong-side targets rejected; 1:1 secondary grade",
           "files": [str(IO.PDIR / f"scorecard-{D}.md")]}
    exp_upsert(row)
    IO.log(f"graded {len(days)} days in {time.time() - t0:.1f} s: " +
           ", ".join(f"{m} n={row['summary'][m]['n']} hit={row['summary'][m]['hit']}" for m in row["summary"]) +
           f"; live keys {len(doc['live'])}")
    try:  # LEADLAG (10/21): grade the shadow leader -> follower predictions in the same nightly job
        import leadlag
        leadlag.grade(argparse.Namespace(days=a.days))
    except Exception as e:
        IO.log(f"leadlag grade failed: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("backtest")
    b.add_argument("--min-sessions", type=int, default=2)
    r = sp.add_parser("replay")
    r.add_argument("--date", required=True)
    r.add_argument("--live-json", action="store_true")
    g = sp.add_parser("grade")
    g.add_argument("--days", type=int, default=10)
    g.add_argument("--weekdays-only", action="store_true")
    a = ap.parse_args()
    if a.cmd == "grade" and a.weekdays_only and time.localtime().tm_wday >= 5:
        return 0
    {"backtest": backtest, "replay": replay, "grade": grade}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
