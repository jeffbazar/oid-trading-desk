#!/usr/bin/env python3
"""Daily direction-score scorecard (research/log only - never places orders).

  daily_scorecard.py [YYYY-MM-DD] [--episodes PATH] [--source auto|episodes|scores]

Reads ~/oid-data/score/episodes-YYYYMMDD.jsonl (live v1.1 score holds). If that file is missing/empty it falls back to
holds rebuilt from scores-YYYYMMDD.jsonl (consecutive logged rows with the same score; timing only to the 15-min grid /
vol_surge rows), with peak/trough from 5 s SIP bars and context rebuilt from logged files at each hold's start.
Writes ~/oid-data/score/scorecard-YYYYMMDD.json and .md.

Per combo: holds, % that went with the score, median/mean gain bp (direction-signed, start->stop), mean peak (MFE)
and trough (MAE) bp in the score's direction, median hold seconds. Score 0 holds have no direction (gain columns blank).
"""
import argparse, json, statistics
from datetime import datetime
from pathlib import Path
import score_lib as L
import score_changes as SC

SURGE = 3.0


def holds_from_scores(date, cfg):
    S = SC.Sources(date)
    ring = SC.Ring(trim=None)
    for s, bl in S.bars.items():
        ring.b[s] = bl
    t_end = SC.session_end_t(date)
    eps = []
    for sym, rows in S.rows.items():
        if sym in set(cfg.get("exclude") or []):
            continue
        groups = []
        for r in rows:
            if groups and groups[-1][-1]["score"] == r["score"]:
                groups[-1].append(r)
            else:
                groups.append([r])
        bl = S.bars.get(sym) or []
        for i, g in enumerate(groups):
            r0 = g[0]
            t0, px0 = r0["t"], r0["px"]
            if i + 1 < len(groups):
                t1, px1, nxt, why = groups[i + 1][0]["t"], groups[i + 1][0]["px"], groups[i + 1][0]["score"], "score_change"
            else:
                lb = ring.last(sym, t_end)
                t1, px1, nxt, why = t_end, (lb[5] if lb else g[-1]["px"]), None, "session_end"
            inside = [b for b in bl if b[0] >= t0 - 0.001 and b[1] <= t1 + 0.001]
            hi = max([px0, px1] + [b[3] if b[3] is not None else b[5] for b in inside])
            lo = min([px0, px1] + [b[4] if b[4] is not None else b[5] for b in inside])
            d = SC.sgn(r0["score"])
            ret, pk, tr = SC.bp(px1, px0), SC.bp(hi, px0), SC.bp(lo, px0)
            walls = S.walls_from_snap(r0, t0, cfg)
            flow_ctx, _ = S.flow_at(sym, t0)
            fx = ((r0.get("comps") or {}).get("flow") or {}).get("x") or {}
            if fx.get("uw_lean"):
                flow_ctx["lean5" if fx.get("which") == "5m" else "lean15"] = fx.get("uw_lean")
            ctx = SC.build_ctx(sym, t0, px0, r0.get("atr"), flow_ctx, r0.get("rvol_1m"), walls, S.mom_at(sym, t0), ring)
            eps.append({"sym": sym, "score": r0["score"], "dir": d, "start_t": t0, "stop_t": t1, "duration_s": round(t1 - t0, 1),
                        "start_px": px0, "stop_px": px1, "ret_bp": ret, "gain_bp": round(ret * d, 2) if (d and ret is not None) else None,
                        "peak_bp": pk, "trough_bp": tr,
                        "mfe_bp": (pk if d > 0 else -tr if d < 0 else None) if None not in (pk, tr) else None,
                        "mae_bp": (tr if d > 0 else -pk if d < 0 else None) if None not in (pk, tr) else None,
                        "next_score": nxt, "stop_reason": why, "n_5s_bars": len(inside), "trigger_start": r0.get("trigger"),
                        "agree_start": SC.agree(r0["score"], ctx), "ctx_start": ctx})
    return eps


def load_episodes(p):
    out = []
    for ln in p.open():
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def stats(eps):
    n = len(eps)
    g = [e["gain_bp"] for e in eps if e.get("gain_bp") is not None]
    mf = [e["mfe_bp"] for e in eps if e.get("mfe_bp") is not None]
    ma = [e["mae_bp"] for e in eps if e.get("mae_bp") is not None]
    du = [e["duration_s"] for e in eps if e.get("duration_s") is not None]
    f = lambda xs, fn: (round(fn(xs), 1) + 0.0) if xs else None
    if n == 0:
        return {"holds": 0, "pct_with": None, "median_gain_bp": None, "mean_gain_bp": None, "mean_peak_bp": None, "mean_trough_bp": None, "median_hold_s": None}
    return {"holds": n, "pct_with": round(100.0 * sum(1 for x in g if x > 0) / len(g), 1) if g else None,
            "median_gain_bp": f(g, statistics.median), "mean_gain_bp": f(g, statistics.mean),
            "mean_peak_bp": f(mf, statistics.mean), "mean_trough_bp": f(ma, statistics.mean), "median_hold_s": f(du, statistics.median)}


def yn(v):
    return "missing" if v is None else ("yes" if v else "no")


def room_bucket(v):
    if v is None:
        return "missing"
    return "<0.25" if v < 0.25 else "0.25-1" if v <= 1.0 else ">1"


def stack(e):
    a = e.get("agree_start") or {}
    s, c, r = a.get("surge"), a.get("cp"), a.get("room_dir_atr")
    if s and c and r is not None and r > 0.5:
        return "yes (all three)"
    if s is None or c is None or r is None:
        return "no / missing input"
    return "no"


COMBOS = [
    ("score x surge (rvol_1m >= 3)", lambda e: yn((e.get("agree_start") or {}).get("surge"))),
    ("score x C/P agrees", lambda e: yn((e.get("agree_start") or {}).get("cp"))),
    ("score x wall room in score direction (ATR)", lambda e: room_bucket((e.get("agree_start") or {}).get("room_dir_atr"))),
    ("score x momentum state", lambda e: (e.get("agree_start") or {}).get("mom_state") or ((e.get("ctx_start") or {}).get("mom") or {}).get("state") or "missing"),
    ("score x surge x C/P agrees x room > 0.5 ATR", stack),
    ("score x stock tape agrees (own 60 s return)", lambda e: yn((e.get("agree_start") or {}).get("stock_tape_60"))),
    ("score x market agrees (SPY/QQQ 60 s return)", lambda e: yn((e.get("agree_start") or {}).get("market_60"))),
]


def build(eps):
    res = {"score_alone": {}, "combos": {}}
    for s in range(-3, 4):
        x = [e for e in eps if e["score"] == s]
        if x:
            res["score_alone"][str(s)] = stats(x)
    nz = [e for e in eps if e["score"] != 0]
    res["score_alone"]["all nonzero"] = stats(nz)
    for name, fn in COMBOS:
        groups = {}
        for e in nz:
            groups.setdefault(fn(e), []).append(e)
        c = {}
        for k in sorted(groups):
            g = groups[k]
            c[k] = {"all nonzero": stats(g)}
            for m in (1, 2, 3):
                gm = [e for e in g if abs(e["score"]) == m]
                if gm:
                    c[k][f"±{m}"] = stats(gm)
            for s in (-3, -2, -1, 1, 2, 3):
                gs = [e for e in g if e["score"] == s]
                if gs:
                    c[k][f"score {s:+d}"] = stats(gs)
        res["combos"][name] = c
    return res


def fmt(v):
    return "–" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def md(date, src, res, n, note):
    H = "| holds | % with score | median gain bp | mean gain bp | mean peak bp | mean trough bp | median hold s |"
    S = "|---:|---:|---:|---:|---:|---:|---:|"
    cols = ("holds", "pct_with", "median_gain_bp", "mean_gain_bp", "mean_peak_bp", "mean_trough_bp", "median_hold_s")
    line = lambda st: " | ".join(fmt(st[c]) for c in cols)
    out = [f"# Direction score scorecard — {date}", "", f"Source: **{src}** ({n} holds). {note}", "",
           "Gain = start-to-stop move in the score's direction. Peak/trough = best/worst move in the score's direction during the hold. "
           "±1/±2/±3 = score of that size in either direction, gains signed to the score. Score 0 has no direction, so its gain columns are blank. Times PT.", "", "## Score alone", "",
           "| score " + H, "|---" + S]
    for k, st in res["score_alone"].items():
        out.append(f"| {k} | {line(st)} |")
    for name, c in res["combos"].items():
        out += ["", f"## {name}", "", "| bucket | scores " + H, "|---|---" + S]
        for k, sub in c.items():
            for sk in ("all nonzero", "±1", "±2", "±3"):
                if sk in sub:
                    out.append(f"| {k} | {sk} | {line(sub[sk])} |")
    bv = res.get("buffered_vs_raw")
    out += ["", "## Buffered vs raw (comparison only — the raw score above is primary)", ""]
    if bv:
        r_, b_ = bv["raw_all_nonzero"], bv["buffered_all_nonzero"]
        out.append(f"Buffered shadow (band {bv['band']}): {b_['holds']} nonzero holds vs raw {r_['holds']}; % with score {fmt(b_['pct_with'])} vs {fmt(r_['pct_with'])}; "
                   f"median gain {fmt(b_['median_gain_bp'])} vs {fmt(r_['median_gain_bp'])} bp; mean gain {fmt(b_['mean_gain_bp'])} vs {fmt(r_['mean_gain_bp'])} bp; "
                   f"median hold {fmt(b_['median_hold_s'])} vs {fmt(r_['median_hold_s'])} s.")
    else:
        out.append("Buffered shadow not available for this source (it is only logged with live/replay episodes).")
    fw = res.get("secondary_fwd")
    out += ["", "## Secondary check: move 5 / 15 / 30 / 60 s after each change (nonzero scores, 5 s bar closes)", ""]
    if fw:
        out += ["| after | changes | % with score | % flat | median gain bp | mean gain bp |", "|---|---:|---:|---:|---:|---:|"]
        for h, st in fw["horizons"].items():
            out.append(f"| +{h} s | {fmt(st['n'])} | {fmt(st['pct_with'])} | {fmt(st['pct_flat'])} | {fmt(st['median_gain_bp'])} | {fmt(st['mean_gain_bp'])} |")
        out.append(f"Per-change rows: `{fw['file']}`.")
    else:
        out.append("Not available: needs a changes-YYYYMMDD.jsonl file (live/replay change log).")
    out += ["", "Per-score (±1/±2/±3 separately) breakdowns are in the .json."]
    return "\n".join(out) + "\n"


def fwd_secondary(date, d, tag, changes_p):
    """Secondary check: move +5/15/30/60 s after each score change, from 5 s bar closes (post-session).
    Writes changes-fwd-YYYYMMDD<tag>.jsonl next to the changes file; returns per-horizon stats for nonzero scores."""
    if changes_p is None or not changes_p.exists() or changes_p.stat().st_size == 0:
        return None
    ch = [c for c in load_episodes(changes_p) if c.get("kind") == "score_change"]
    if not ch:
        return None
    rows = SC.forward_moves(ch, SC.load_5s(date), t_end=SC.session_end_t(date))
    outp = changes_p.with_name(f"changes-fwd-{d}{tag}.jsonl")
    with outp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    res = {"file": outp.name, "changes": len(ch), "with_base_bar": sum(1 for r in rows if r.get("base_px") is not None), "horizons": {}}
    for h in SC.FWD_HORIZONS:
        g = [r["fwd"][str(h)]["gain_bp"] for r in rows if r["score"] and r["fwd"].get(str(h)) and r["fwd"][str(h)].get("gain_bp") is not None]
        res["horizons"][str(h)] = {"n": len(g), "pct_with": round(100.0 * sum(1 for x in g if x > 0) / len(g), 1) if g else None,
                                   "pct_flat": round(100.0 * sum(1 for x in g if x == 0) / len(g), 1) if g else None,
                                   "median_gain_bp": round(statistics.median(g), 1) + 0.0 if g else None,
                                   "mean_gain_bp": round(statistics.mean(g), 1) + 0.0 if g else None}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=datetime.now(L.PT).strftime("%Y-%m-%d"))
    ap.add_argument("--episodes")
    ap.add_argument("--source", default="auto", choices=["auto", "episodes", "scores"])
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    cfg = L.load_config()
    d = a.date.replace("-", "")
    p = Path(a.episodes) if a.episodes else L.OUT / f"episodes-{d}.jsonl"
    eps, src, note = [], None, ""
    if a.source in ("auto", "episodes") and p.exists() and p.stat().st_size > 0:
        eps, src = load_episodes(p), f"episodes ({p.name})"
        note = "Live score holds timed to the fast pass (~5 s)." if not a.episodes else f"Episodes from {p}."
    if not eps and a.source != "episodes":
        sp = L.OUT / f"scores-{d}.jsonl"
        if not sp.exists():
            print(f"no episodes or scores for {a.date}")
            return 1
        eps, src = holds_from_scores(a.date, cfg), f"scores fallback ({sp.name})"
        note = ("Holds rebuilt from logged score rows, so start/stop are only known to the 15-min grid (plus vol_surge rows); "
                "C/P from optflow cp-history, momentum from the events log, tapes from 5 s bars, all at each hold's start.")
    res = build(eps)
    # comparison-only: buffered shadow vs raw (raw stays the primary score)
    bp_ = None
    if src and src.startswith("episodes"):
        bp_ = p.with_name(p.name.replace("episodes-", "episodes-buffered-", 1))
    if bp_ is not None and bp_.exists() and bp_.stat().st_size > 0:
        beps = [e for e in load_episodes(bp_) if e.get("score") != 0]
        res["buffered_vs_raw"] = {"raw_all_nonzero": res["score_alone"]["all nonzero"], "buffered_all_nonzero": stats(beps),
                                  "band": (beps[0].get("buffered_band") if beps else None), "file": bp_.name}
    else:
        res["buffered_vs_raw"] = None
    chp = (p.with_name(p.name.replace("episodes-", "changes-", 1)) if (src and src.startswith("episodes")) else None)
    try:
        res["secondary_fwd"] = fwd_secondary(a.date, d, a.tag, chp)
    except Exception as ex:  # secondary check must never break the scorecard
        print(f"secondary fwd check failed: {ex}")
        res["secondary_fwd"] = None
    res.update({"date": a.date, "source": src, "n_holds": len(eps), "generated_pt": L.pt_str(datetime.now().timestamp()),
                "definitions": {"surge": "rvol_1m >= 3 at hold start", "cp_agrees": "aggressor C/P 1m (else 15s, else UW lean) on the score's side; C/P>1.10 call, <0.91 put",
                                "wall_room": "ATR from price to the call wall (score>0) or put wall (score<0) at hold start",
                                "stock_tape_agrees": "sign of the stock's own 60 s return (5 s bars) = score sign",
                                "market_agrees": "sign of mean SPY/QQQ 60 s return = score sign"}})
    base = L.OUT / f"scorecard-{d}{a.tag}"
    Path(str(base) + ".json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    Path(str(base) + ".md").write_text(md(a.date, src, res, len(eps), note), encoding="utf-8")
    print(f"scorecard {a.date}: {len(eps)} holds from {src} -> {base}.json/.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
