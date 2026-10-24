#!/usr/bin/env python3
"""SHADOW-PAT (2026-10-24, Jeffrey "refactor our scores based on this"): pattern-evidence SHADOW of the direction score.

RESEARCH / SHADOW ONLY. Never imported by score_daemon.py / score_wide.py, never writes latest*.json, changes-*.jsonl,
episodes-*.jsonl or anything a live alert, trade or order reads. Reads archives only.

What the shadow changes vs the live score (v1.2-20261022, components flip/walls/volume/flow/trend/market):
  * The live score has NO pattern input (1m higher low / lower high etc. are only logged as shadow features
    pat_* in score_features), so "drop the 1m patterns" is already true; the shadow adds nothing from 1m.
  * Adds ONE extra component "patterns" (weight W, default 0.75) that is present only while an edge pattern is
    live on that ticker (triggered, not yet completed/failed/expired, same session), so it never dilutes names with
    no live pattern (same rule as the news add-one test):
        c_pat = clamp( sum_i dir_i * k_i , -1, 1 )
        k_i   = min(1, max(EV_R_i, 0) * n_i/(n_i+K) / REF)      K = 50 (shrinkage), REF = 0.15 R
        EV_R  = p_hit * medRR - (1 - p_hit)  (expired counted as a loss), from live pattern_labels on the FIT days
    Candidates: 30m breakdown, 30m failed_breakout, 5m head_shoulders, 5m gap_up (fade, dir -1).
    Patterns with n < 20 on the fit days are tracked (logged) with k = 0. Everything else (all 1m, flags, VWAP
    reclaim/loss, 5m higher low, double bottoms ...) gets k = 0.
  * Re-combine exactly like score_lib.combine (missing = shrink, den = sum of enabled weights):
        num = raw/4.5 * den ;  raw' = clamp(4.5 * (num + W*c_pat)/(den + W), -3, 3) ; score' = round half away
    (raw is clamped at +-3 in the logs, so for |raw| = 3 rows num is a lower bound; noted in the report.)
  * Setups the grader rejects at trigger time (target on the wrong side of entry / entry beyond invalidation) are
    skipped; that is knowable at the trigger, so no look-ahead. Outcomes are NEVER used to choose which live rows
    get a pattern (only the terminal record's timestamp ends the window, which is known at that time).

  shadow_patterns.py replay --fit 2026-10-21,2026-10-22 --test 2026-10-23 [--profile core] [--weight 0.75]
  shadow_patterns.py weights --fit 2026-10-21,2026-10-22,2026-10-23        -> prints / writes the weight table
  shadow_patterns.py live                                                  -> SHADOW logger daemon (separate process)
Outputs: ~/oid-data/score/shadow-patterns/ (replay-*.json/.md, weights-*.json, shadow-YYYYMMDD.jsonl)
"""
import argparse
import bisect
import collections
import datetime as dt
import glob
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

HOME = Path.home()
DATA = Path(os.environ.get("OID_DATA_ROOT", str(HOME / "oid-data"))).expanduser()
AR = DATA / "archive"
OUT = DATA / "score" / "shadow-patterns"
EXP = DATA / "score" / "experiments.jsonl"
VERSION = "shadowpat-v1-20261024"
CANDIDATES = [("breakdown", "30m"), ("failed_breakout", "30m"), ("head_shoulders", "5m"), ("gap_up", "5m")]
TRACK_ONLY_IV = ("30m",)          # any other 30m pattern: tracked, unweighted
K_SHRINK, REF_R, MIN_N = 50.0, 0.15, 20
GAIN, MAXABS = 4.5, 3.0           # score-config scale.gain 1.5 * max_abs 3
DEN = {"core": 4.75, "wide_full": 4.75, "light": 2.5}
HZ = (300, 900, 1800)
TERMINAL = ("completed", "failed", "expired")
try:
    from zoneinfo import ZoneInfo
    PTZ = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PTZ = None


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def session_end(date):
    d = dt.datetime.strptime(date, "%Y-%m-%d").replace(hour=13, minute=0, tzinfo=PTZ)
    return d.timestamp()


# ------------------------------------------------------------------ weights from pattern_labels
def edge_table(fit_days, mode="live"):
    acc = collections.defaultdict(lambda: {"n": 0, "hit": 0, "rr": []})
    for d in fit_days:
        for p in glob.glob(str(AR / "pattern_labels" / f"date={d}" / "part-pattern-grader-*.jsonl")):
            for line in open(p):
                r = json.loads(line)
                if r.get("mode") != mode or not r.get("final") or r.get("outcome") not in ("target_hit", "invalidated", "expired"):
                    continue
                a = acc[(r["pattern"], r["interval"], r["direction"])]
                a["n"] += 1
                a["hit"] += r["outcome"] == "target_hit"
                if r.get("rr") is not None:
                    a["rr"].append(r["rr"])
    out = {}
    for (pat, iv, d), a in acc.items():
        n = a["n"]
        p = a["hit"] / n if n else 0.0
        rr = statistics.median(a["rr"]) if a["rr"] else None
        ev = (p * rr - (1 - p)) if rr is not None else None
        cand = (pat, iv) in CANDIDATES
        shr = (max(ev, 0.0) * n / (n + K_SHRINK)) if (ev is not None) else 0.0
        k = min(1.0, shr / REF_R) if (cand and n >= MIN_N and ev is not None and ev > 0) else 0.0
        role = ("weighted" if k > 0 else ("candidate_no_edge" if cand and n >= MIN_N else
                ("tracked_small_n" if (cand or iv in TRACK_ONLY_IV) and n < MIN_N else
                 ("tracked" if iv in TRACK_ONLY_IV else "zero"))))
        out[f"{pat}|{iv}"] = {"pattern": pat, "iv": iv, "dir": d, "n": n, "hit": a["hit"], "p": round(p, 4),
                              "med_rr": round(rr, 3) if rr is not None else None,
                              "breakeven": round(1 / (1 + rr), 4) if rr else None,
                              "ev_r": round(ev, 4) if ev is not None else None, "shrunk": round(shr, 4),
                              "k": round(k, 4), "role": role}
    return out


# ------------------------------------------------------------------ pattern windows from the pattern archive
def rejected_at_trigger(r):
    kl = r.get("key_levels") or {}
    px, tg, inv, d = r.get("px"), kl.get("target"), kl.get("invalidation"), r.get("direction")
    if px is None or tg is None or d is None:
        return True
    if d * (tg - px) <= 0:
        return True
    if inv is not None and d * (px - inv) <= 0:
        return True
    return False


def windows_from_records(recs, date, weights, tracked_ivs=TRACK_ONLY_IV):
    """recs: pattern archive records (any order). -> {sym: [(t0, t1, dir, k, key, det_id)]} for weighted + tracked."""
    trig, term = {}, {}
    for r in recs:
        st, did = r.get("state"), r.get("det_id")
        if st == "triggered" and did not in trig:
            trig[did] = r
        elif st in TERMINAL:
            term[did] = min(term.get(did, 9e18), float(r["ts"]))
    se = session_end(date)
    out = collections.defaultdict(list)
    for did, r in trig.items():
        key = f"{r['pattern']}|{r['interval']}"
        w = weights.get(key) or {}
        k = w.get("k", 0.0)
        if k <= 0 and r["interval"] not in tracked_ivs and (r["pattern"], r["interval"]) not in CANDIDATES:
            continue
        if rejected_at_trigger(r):
            continue
        t0 = float(r["ts"])
        t1 = min(term.get(did, se), se)
        if t1 <= t0:
            continue
        out[r["ticker"]].append((t0, t1, int(r["direction"]), float(k), key, did))
    for s in out:
        out[s].sort()
    return out


def load_recs(date, mode):
    recs = []
    for p in sorted(glob.glob(str(AR / "patterns" / f"date={date}" / f"part-patterns-{mode}-*.jsonl"))):
        for line in open(p):
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def c_pat_at(wins, t):
    c, active, tracked = 0.0, [], []
    for (t0, t1, d, k, key, did) in wins:
        if t0 > t:
            break
        if t < t1:
            if k > 0:
                c += d * k
                active.append(key)
            else:
                tracked.append(key)
    return max(-1.0, min(1.0, c)), active, tracked


def shadow_raw(raw, cp, den, w):
    if raw is None:
        return None, None
    if not cp:
        r2 = raw
    else:
        num = raw / GAIN * den
        r2 = max(-MAXABS, min(MAXABS, GAIN * (num + w * cp) / (den + w)))
    s2 = int(math.copysign(math.floor(abs(r2) + 0.5), r2)) if r2 else 0
    return round(r2, 3), s2


# ------------------------------------------------------------------ replay
def load_snaps(date, profile, smode="live"):
    import duckdb
    cols = ["symbol", "t", "raw", "score", "px", "atr"] + [f"h{h}_{x}" for h in HZ for x in ("ret_bp", "full", "mae_bp", "mfe_bp")]
    q = (f"select {', '.join(cols)} from read_parquet('{AR}/parquet/score_labels/date={date}/*.parquet') "
         f"where kind='snap' and mode='{smode}' and profile='{profile}' order by symbol, t")
    con = duckdb.connect()
    rel = con.execute(q)
    names = [d[0] for d in rel.description]
    return [dict(zip(names, row)) for row in rel.fetchall()]


def metrics(rows, skey):
    out = {}
    for h in HZ:
        xs = []
        for r in rows:
            s = r[skey]
            ret = r.get(f"h{h}_ret_bp")
            if not s or ret is None or not r.get(f"h{h}_full"):
                continue
            d = 1 if s > 0 else -1
            dm = d * ret
            atr_bp = (r["atr"] / r["px"] * 1e4) if (r.get("atr") and r.get("px")) else None
            xs.append((dm, dm / atr_bp if atr_bp else None))
        n = len(xs)
        if not n:
            out[f"{h // 60}m"] = {"n": 0}
            continue
        atrs = [a for _, a in xs if a is not None]
        out[f"{h // 60}m"] = {"n": n, "hit": round(sum(1 for dm, _ in xs if dm > 0) / n, 4),
                              "mean_bp": round(sum(dm for dm, _ in xs) / n, 2),
                              "median_bp": round(statistics.median(dm for dm, _ in xs), 2),
                              "mean_atr": round(sum(atrs) / len(atrs), 4) if atrs else None}
    return out


def replay_day(date, profile, weights, w, pat_mode, smode="live"):
    snaps = load_snaps(date, profile, smode)
    wins = windows_from_records(load_recs(date, pat_mode), date, weights)
    den = DEN[profile]
    by_sym = collections.defaultdict(list)
    for r in snaps:
        by_sym[r["symbol"]].append(r)
    act_ct = collections.Counter()
    for sym, rows in by_sym.items():
        ws = wins.get(sym, [])
        for r in rows:
            cp, act, trk = c_pat_at(ws, r["t"])
            r["cp"] = cp
            r["active"] = act
            r["shadow_raw"], r["shadow_score"] = shadow_raw(r["raw"], cp, den, w)
            r["clamped_in"] = r["raw"] is not None and abs(r["raw"]) >= MAXABS
            for a in act:
                act_ct[a] += 1
    snaps = [r for r in snaps if r["raw"] is not None]
    for r in snaps:
        r["short"] = -1          # control: "short everything" (all weighted edge patterns are bearish)
    pat = [r for r in snaps if r["cp"]]
    chg = [r for r in pat if r["shadow_score"] != r["score"]]
    flip = [r for r in chg if r["score"] and r["shadow_score"] and (r["score"] > 0) != (r["shadow_score"] > 0)]
    res = {"date": date, "profile": profile, "pattern_mode": pat_mode, "score_mode": smode, "snaps": len(snaps),
           "pattern_windows": sum(1 for s in wins.values() for x in s if x[3] > 0),
           "tracked_windows": sum(1 for s in wins.values() for x in s if x[3] == 0),
           "rows_pattern_active": len(pat), "rows_score_changed": len(chg), "rows_sign_flipped": len(flip),
           "rows_clamped_raw_with_pattern": sum(1 for r in pat if r["clamped_in"]),
           "active_by_pattern": dict(act_ct),
           "all": {"live": metrics(snaps, "score"), "shadow": metrics(snaps, "shadow_score")},
           "pattern_rows": {"live": metrics(pat, "score"), "shadow": metrics(pat, "shadow_score")},
           "changed_rows": {"live": metrics(chg, "score"), "shadow": metrics(chg, "shadow_score")},
           "control_short": {"all": metrics(snaps, "short"), "pattern_rows": metrics(pat, "short"),
                             "changed_rows": metrics(chg, "short")}}
    return res


def fmt_m(m):
    if not m.get("n"):
        return "n 0"
    return f"n {m['n']:,} · hit {m['hit'] * 100:.1f}% · mean {m['mean_bp']:+.2f} bp · med {m['median_bp']:+.2f} bp · {m['mean_atr']:+.4f} ATR"


def cmd_weights(a):
    fit = a.fit.split(",")
    wt = edge_table(fit, a.pattern_mode)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"weights-{fit[0]}_{fit[-1]}.json"
    p.write_text(json.dumps({"version": VERSION, "fit_days": fit, "K": K_SHRINK, "REF_R": REF_R, "MIN_N": MIN_N,
                             "weights": wt}, indent=1))
    for k, v in sorted(wt.items(), key=lambda kv: -kv[1]["k"]):
        if v["role"] != "zero":
            print(k, v)
    log("weights ->", p)
    return wt


def cmd_replay(a):
    fit = a.fit.split(",")
    tests = a.test.split(",")
    wt = edge_table(fit, "live")
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"version": VERSION, "fit_days": fit, "test_days": tests, "profile": a.profile, "weight": a.weight,
           "weights": {k: v for k, v in wt.items() if v["role"] != "zero"}, "days": []}
    for d in tests:
        mode = "live" if glob.glob(str(AR / "patterns" / f"date={d}" / "part-patterns-live-*.jsonl")) else "replay"
        log("replay", d, a.profile, "patterns:", mode)
        res["days"].append(replay_day(d, a.profile, wt, a.weight, mode, "live" if mode == "live" else "replay"))
    # pooled
    rm = all(x["score_mode"] == "live" for x in res["days"])
    tag = ("" if rm else "replaymode-") + f"{a.profile}-w{a.weight}-fit{fit[0][5:]}_{fit[-1][5:]}-test{'_'.join(x[5:] for x in tests)}"
    p = OUT / f"replay-{tag}.json"
    p.write_text(json.dumps(res, indent=1))
    L = [f"# Shadow pattern score replay {tag}", "", f"version {VERSION}; fit days {', '.join(fit)}; test days {', '.join(tests)}; "
         f"profile {a.profile}; pattern weight W {a.weight}. Rows = 15 s live score snapshots with full label windows; score 0 rows excluded.", "",
         "## Weights (fit days)", "", "| pattern | iv | dir | n | hit | med R:R | breakeven | EV R | shrunk | k | role |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(res["weights"].items(), key=lambda kv: (-kv[1]["k"], kv[0])):
        L.append(f"| {v['pattern']} | {v['iv']} | {v['dir']:+d} | {v['n']} | {v['p'] * 100:.1f}% | {v['med_rr']} | "
                 f"{(v['breakeven'] or 0) * 100:.1f}% | {v['ev_r']} | {v['shrunk']} | {v['k']} | {v['role']} |")
    for r in res["days"]:
        L += ["", f"## {r['date']} (patterns: {r['pattern_mode']}, score rows: {r['score_mode']})", "",
              f"snaps {r['snaps']:,}; weighted pattern windows {r['pattern_windows']}; tracked windows {r['tracked_windows']}; "
              f"rows with a weighted pattern live {r['rows_pattern_active']:,}; integer score changed {r['rows_score_changed']:,}; "
              f"sign flipped {r['rows_sign_flipped']:,}; |raw|=3 rows with pattern {r['rows_clamped_raw_with_pattern']}", ""]
        for grp in ("all", "pattern_rows", "changed_rows"):
            for hz in ("5m", "15m", "30m"):
                L.append(f"- {grp} {hz}: live {fmt_m(r[grp]['live'][hz])} | shadow {fmt_m(r[grp]['shadow'][hz])} | short-all control {fmt_m(r['control_short'][grp][hz])}")
    (OUT / f"replay-{tag}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    log("replay ->", p)
    return res


# ------------------------------------------------------------------ live shadow logger (separate process)
def cmd_live(a):
    """Every POLL s: read new score_features snapshot rows (core) and new pattern archive records (tail, byte offsets),
    compute the shadow score, append rows to shadow-YYYYMMDD.jsonl. Reads files only; never touches the scorer."""
    poll = a.poll
    OUT.mkdir(parents=True, exist_ok=True)
    wpath = Path(a.weights_file).expanduser()
    state = {"date": None}

    def reset(date):
        wt = json.loads(wpath.read_text())["weights"]
        state.update({"date": date, "wt": wt, "off": {}, "recs": [], "latest": {}, "wins": {}, "n": 0,
                      "out": open(OUT / f"shadow-{date.replace('-', '')}.jsonl", "a")})
        log("live shadow day", date, "weights", wpath.name)

    def tail(p):
        off = state["off"].get(p, 0)
        try:
            sz = os.path.getsize(p)
        except OSError:
            return []
        if sz < off:
            off = 0
        if sz == off:
            return []
        with open(p, "rb") as fh:
            fh.seek(off)
            buf = fh.read()
        cut = buf.rfind(b"\n") + 1
        state["off"][p] = off + cut
        out = []
        for line in buf[:cut].splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    while True:
        now = time.time()
        date = dt.datetime.fromtimestamp(now, PTZ).strftime("%Y-%m-%d")
        if os.path.exists(DATA / "score" / "shadow-patterns" / "disabled"):
            time.sleep(60)
            continue
        if state["date"] != date:
            if state.get("out"):
                state["out"].close()
            reset(date)
        new_p = []
        for p in sorted(glob.glob(str(AR / "patterns" / f"date={date}" / "part-patterns-live-*.jsonl"))):
            new_p += tail(p)
        if new_p:
            state["recs"] += new_p
            state["wins"] = windows_from_records(state["recs"], date, state["wt"])
        rows = []
        for p in sorted(glob.glob(str(AR / "score_features" / f"date={date}" / "part-*.jsonl"))):
            rows += tail(p)
        n = 0
        for r in rows:
            if r.get("profile") != "core" or r.get("mode") != "live" or r.get("raw") is None:
                continue
            cp, act, trk = c_pat_at(state["wins"].get(r["symbol"], []), float(r["t"]))
            r2, s2 = shadow_raw(r["raw"], cp, DEN["core"], a.weight)
            o = {"v": VERSION, "sym": r["symbol"], "t": r["t"], "t_pt": dt.datetime.fromtimestamp(float(r["t"]), PTZ).strftime("%H:%M:%S"),
                 "px": r.get("px"), "live_score": r.get("score"), "live_raw": r["raw"], "c_pat": round(cp, 4),
                 "w_pat": a.weight, "shadow_raw": r2, "shadow_score": s2, "active": act, "tracked": trk,
                 "snap_id": r.get("snap_id"), "settings_version": r.get("settings_version")}
            state["out"].write(json.dumps(o, separators=(",", ":")) + "\n")
            n += 1
        if n:
            state["out"].flush()
            state["n"] += n
        if int(now) % 900 < poll:
            log(f"shadow rows today {state['n']}, pattern recs {len(state['recs'])}, live windows "
                f"{sum(1 for s in state['wins'].values() for x in s if x[0] <= now < x[1])}")
        time.sleep(poll)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("weights")
    x.add_argument("--fit", required=True)
    x.add_argument("--pattern-mode", default="live")
    x = sp.add_parser("replay")
    x.add_argument("--fit", required=True)
    x.add_argument("--test", required=True)
    x.add_argument("--profile", default="core", choices=sorted(DEN))
    x.add_argument("--weight", type=float, default=0.75)
    x = sp.add_parser("live")
    x.add_argument("--weights-file", default=str(OUT / "weights-2026-10-21_2026-10-23.json"))
    x.add_argument("--weight", type=float, default=0.75)
    x.add_argument("--poll", type=int, default=15)
    a = ap.parse_args()
    {"weights": cmd_weights, "replay": cmd_replay, "live": cmd_live}[a.cmd](a)


if __name__ == "__main__":
    main()
