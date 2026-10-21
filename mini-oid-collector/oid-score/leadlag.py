#!/usr/bin/env python3
"""LEADLAG (2026-10-21): leader -> follower lead-lag detector. SHADOW ONLY (never feeds a live score, an alert or a trade).

An extension of the shadow pattern detector (patterns.py, Field Guide 34; this is Field Guide 35). When a LEADER ticker
fires a directional pattern event (breakout, breakdown, failed_breakout = wall/level rejection, failed_breakdown, gap
fill, vwap_loss, vwap_reclaim) the detector logs the expected move of each of its mapped FOLLOWERS: direction (leader
direction x sign of their correlation), expected lag, horizon, and a probability = the raw hit rate of the same
(pattern, interval, direction, relationship bucket) in the out-of-sample backtest, with its n. The live hit rate takes
over once live n >= 20 (both kept).

  leadlag.py build [--split 0.6]   (needs numpy: ~/oid-score/venv-leadlag/bin/python; nightly com.oid.desk.leadlag-build)
      1) MAP: 1-min RTH log returns of every tracked ticker (core + Sector watch bar stores; IBIT = BTC proxy) on the
         minute grid (last price carried within a session, never across the overnight) ->
         per pair: c5 = 5-min return correlation, c(k) = corr(r_leader[t], r_follower[t+k]) for k = 0..10 min,
         best lag, lead_t (sum of c(1..10) vs its null s.e.), asym_t (A->B minus B->A), beta5, n.
         Followers of A = |c5| >= 0.30 and lagged correlation not against c5, ranked by |c5| + 0.05 * lead_t.
         -> ~/oid-data/patterns/leadlag-map.json
      2) BACKTEST (out-of-sample): map rebuilt on the first 60% of sessions only; every leader event in the last 40%
         (same pattern engines as live) x its followers -> follower log return from the event bar's close over the
         horizon (1m events 15 min, 5m 30 min, 30m 60 min); hit = follower moved the predicted way (> 0 bp).
         Also an in-sample run (full map, all sessions) for comparison.
         -> ~/oid-data/patterns/leadlag-rates.json "backtest" (oos) / "backtest_insample"
  leadlag.py daemon               live (launchd com.oid.desk.leadlag): each 1-min bar close +25 s in RTH, reads the new
      triggered leader events from today's pattern archive (written by com.oid.desk.patterns), logs predictions to
      ~/oid-data/archive/leadlag/date=D/part-leadlag-live-<n>.jsonl and rewrites ~/oid-data/patterns/leadlag-live.json
      (active predictions per follower; read by score_features shadow fields and the live page Lead-lag column).
  leadlag.py grade [--days 10]    nightly, called from pattern_learn.py grade (com.oid.desk.pattern-grade 1:50 PM PT):
      labels every live prediction -> archive leadlag_labels/date=D/; live rates -> leadlag-rates.json "live";
      scorecard ~/oid-data/patterns/leadlag-scorecard-<D>.{md,json}; one row in ~/oid-data/score/experiments.jsonl
Kill switch: touch ~/oid-data/patterns/leadlag-disabled. No paid calls, no network, no orders, no alerts.
"""
import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / "oid-score"))
import patterns as PT  # noqa: E402
import pattern_io as IO  # noqa: E402
import score_lib as L  # noqa: E402

LL_VERSION = "ll-v1-20261021"
PDIR = IO.PDIR
MAP = PDIR / "leadlag-map.json"
RATES = PDIR / "leadlag-rates.json"
LIVE = PDIR / "leadlag-live.json"
GUIDE_COPY = Path.home() / "oid-live-page/guide/ll/leadlag-live.json"   # served read-only at /guide/ll/ (no livepage restart)
EXP = Path.home() / "oid-data/score/experiments.jsonl"
EVT = {"breakout", "breakdown", "failed_breakout", "failed_breakdown", "gap_up", "gap_down", "vwap_reclaim", "vwap_loss"}
HZ = {"1m": 15, "5m": 30, "30m": 60}          # follower horizon (minutes) by leader event interval
MAXLAG = 10
C5_MIN = 0.30
TOPK_MAP = 12
TOPK_LIVE = 8
BTC_PROXY = "IBIT"
KIND = {"breakout": "breakout", "breakdown": "breakdown", "failed_breakout": "rejection", "failed_breakdown": "rejection",
        "gap_up": "gap_fill", "gap_down": "gap_fill", "vwap_reclaim": "vwap", "vwap_loss": "vwap"}


def rel_bucket(c5):
    a = abs(c5 or 0)
    return ("c50" if a >= 0.5 else "c30") + ("" if (c5 or 0) >= 0 else "neg")


def rate_key(pattern, iv, d, rel):
    return f"{pattern}|{iv}|{d:+d}|{rel}"


def pair_key(a, b, d, iv):
    return f"{a}>{b}|{'up' if d > 0 else 'dn'}|{iv}"


def sectors():
    out = {}
    for f in ("sectors.json", "wide-sectors.json"):
        try:
            d = json.loads((Path.home() / "oid-live-page" / f).read_text())
            for g in d.get("groups") or []:
                for s in g.get("tickers") or []:
                    out.setdefault(s, g.get("name") or g.get("id"))
        except Exception:
            pass
    return out


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def atomic(p, doc, indent=None):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=indent, separators=None if indent else (",", ":")))
    tmp.replace(p)


# ================================================================== BUILD (numpy)
def load_bars(uni):
    bars = {}
    for sym, tier, store in uni:
        try:
            b = IO.hist_1m(sym, store)
        except Exception:
            b = []
        if b:
            bars[sym] = b
    return bars


def build_matrix(bars, sessions_keep):
    import numpy as np
    syms = sorted(bars)
    keep = set(sessions_keep)
    grid = sorted({b[0] for s in syms for b in bars[s] if b[6] in keep})
    gi = {t: i for i, t in enumerate(grid)}
    sess = {}
    for s in syms:
        for b in bars[s]:
            if b[6] in keep:
                sess[b[0]] = b[6]
    sd = np.array([sess[t] for t in grid])
    P = np.full((len(grid), len(syms)), np.nan)
    for j, s in enumerate(syms):
        for b in bars[s]:
            i = gi.get(b[0])
            if i is not None and b[4]:
                P[i, j] = b[4]
    # carry the last price forward within a session only; first bar of each session has no return
    R = np.full_like(P, np.nan)
    bounds = []
    st = 0
    for i in range(1, len(grid) + 1):
        if i == len(grid) or sd[i] != sd[st]:
            bounds.append((st, i))
            st = i
    Pf = P.copy()
    for a, z in bounds:
        blk = Pf[a:z]
        for i in range(1, z - a):
            m = np.isnan(blk[i])
            blk[i, m] = blk[i - 1, m]
        with np.errstate(invalid="ignore", divide="ignore"):
            R[a + 1:z] = np.log(blk[1:] / blk[:-1])
    # winsorize at 6 sd per ticker (halts / bad prints)
    sdv = np.nanstd(R, axis=0)
    sdv[~np.isfinite(sdv) | (sdv == 0)] = 1.0
    R = np.clip(R, -6 * sdv, 6 * sdv)
    return syms, grid, sd, bounds, Pf, R


def pair_stats(R, bounds):
    import numpy as np
    N = R.shape[1]
    M = (~np.isnan(R)).astype(float)
    X = np.nan_to_num(R)
    X2 = X * X
    acc = {k: [np.zeros((N, N)) for _ in range(6)] for k in range(0, MAXLAG + 1)}
    for a, z in bounds:
        for k in range(0, MAXLAG + 1):
            if z - a - 1 <= k:
                continue
            x1, x2 = X[a + 1:z - k], X[a + 1 + k:z]
            m1, m2 = M[a + 1:z - k], M[a + 1 + k:z]
            A = acc[k]
            A[0] += m1.T @ m2
            A[1] += x1.T @ m2
            A[2] += m1.T @ x2
            A[3] += x1.T @ x2
            A[4] += (x1 * x1).T @ m2
            A[5] += m1.T @ (x2 * x2)

    def corr(A):
        n, sx, sy, sxy, sxx, syy = A
        with np.errstate(invalid="ignore", divide="ignore"):
            c = (n * sxy - sx * sy) / np.sqrt((n * sxx - sx * sx) * (n * syy - sy * sy))
        return np.nan_to_num(c), n
    C = {}
    n0 = None
    for k in range(0, MAXLAG + 1):
        C[k], nk = corr(acc[k])
        if k == 0:
            n0 = nk
    # 5-min returns (sum of the 1-min log returns in each ET 5-min bucket, per session)
    rows5 = []
    for a, z in bounds:
        for s in range(a + 1, z, 5):
            blk = R[s:min(s + 5, z)]
            ok = (~np.isnan(blk)).any(axis=0)
            v = np.nansum(blk, axis=0)
            v[~ok] = np.nan
            rows5.append(v)
    R5 = np.array(rows5)
    M5 = (~np.isnan(R5)).astype(float)
    X5 = np.nan_to_num(R5)
    n5 = M5.T @ M5
    sx, sy = X5.T @ M5, M5.T @ X5
    sxy = X5.T @ X5
    sxx, syy = (X5 * X5).T @ M5, M5.T @ (X5 * X5)
    with np.errstate(invalid="ignore", divide="ignore"):
        c5 = np.nan_to_num((n5 * sxy - sx * sy) / np.sqrt((n5 * sxx - sx * sx) * (n5 * syy - sy * sy)))
        vx = (n5 * sxx - sx * sx)
        beta = np.nan_to_num((n5 * sxy - sx * sy) / vx)   # follower (col) on leader (row)
    return C, n0, c5, n5, beta


def make_map(bars, sessions_keep, secs):
    import numpy as np
    syms, grid, sd, bounds, Pf, R = build_matrix(bars, sessions_keep)
    C, n0, c5, n5, beta = pair_stats(R, bounds)
    N = len(syms)
    S_ab = sum(C[k] for k in range(1, MAXLAG + 1))       # row leads col
    lagged = np.stack([C[k] for k in range(1, MAXLAG + 1)])  # (10, N, N)
    m = {}
    for i, a in enumerate(syms):
        cand = []
        for j, b in enumerate(syms):
            if i == j or n0[i, j] < 500:
                continue
            n = float(n0[i, j])
            se = math.sqrt(MAXLAG / n)
            sgn = 1.0 if c5[i, j] >= 0 else -1.0
            lead_t = float(sgn * S_ab[i, j] / se)
            asym_t = float(sgn * (S_ab[i, j] - S_ab[j, i]) / math.sqrt(2 * MAXLAG / n))
            kbest = int(np.argmax(sgn * lagged[:, i, j])) + 1
            d = {"f": b, "c5": round(float(c5[i, j]), 3), "c0_1m": round(float(C[0][i, j]), 3),
                 "lag_min": kbest, "c_lag": round(float(lagged[kbest - 1, i, j]), 4),
                 "c_lags": [round(float(lagged[k, i, j]), 4) for k in range(MAXLAG)],
                 "lead_t": round(lead_t, 2), "asym_t": round(asym_t, 2), "beta5": round(float(beta[i, j]), 3),
                 "n_1m": int(n), "n_5m": int(n5[i, j]), "same_sector": bool(secs.get(a) and secs.get(a) == secs.get(b))}
            cand.append(d)
        pairs = sorted(cand, key=lambda d: -abs(d["c5"]))[:25]
        fol = [d for d in cand if abs(d["c5"]) >= C5_MIN and d["lead_t"] > -2.0]
        for d in fol:
            d["rank"] = round(abs(d["c5"]) + 0.05 * max(0.0, d["lead_t"]) + (0.03 if d["same_sector"] else 0), 4)
        fol = sorted(fol, key=lambda d: -d["rank"])[:TOPK_MAP]
        m[a] = {"sector": secs.get(a), "followers": fol, "pairs": pairs}
    # reverse index: leaders of each ticker (the tickers whose follower list includes it)
    for a, v in m.items():
        for d in v["followers"]:
            m[d["f"]].setdefault("leaders", []).append({"l": a, **{k: d[k] for k in ("c5", "lag_min", "c_lag", "lead_t", "asym_t", "n_1m", "same_sector", "rank")}})
    for v in m.values():
        v["leaders"] = sorted(v.get("leaders", []), key=lambda d: -d["rank"])[:TOPK_MAP]
    return m, syms, grid, sd, Pf


def leader_events(uni, bars, start):
    """Same engines as live: every TRIGGERED leader event in sessions >= start (warm-up = earlier sessions)."""
    ev = []
    for sym, tier, store in uni:
        b1 = bars.get(sym)
        if not b1:
            continue
        atr_d = IO.daily_atr([b for b in b1 if b[6] < start])
        for iv in PT.IV_MIN:
            e = PT.Engine(sym, iv, atr_d)
            for b in (b1 if iv == "1m" else PT.roll(b1, iv)):
                for r in e.step(b):
                    if b[6] >= start and r["state"] == "triggered" and r["pattern"] in EVT and r.get("direction"):
                        ev.append({"ticker": sym, "ts": r["ts"], "interval": iv, "pattern": r["pattern"],
                                   "direction": r["direction"], "date": b[6]})
    return ev


def follow_outcomes(events, mp, syms, grid, sd, Pf, topk):
    import numpy as np
    col = {s: j for j, s in enumerate(syms)}
    gi = {t: i for i, t in enumerate(grid)}
    out = []
    for e in events:
        i = gi.get(e["ts"] - 60)          # the 1-min bar that closes at the event time
        if i is None:
            continue
        H = HZ[e["interval"]]
        z = i
        while z + 1 < len(grid) and sd[z + 1] == sd[i] and z - i < H:
            z += 1
        if z == i:
            continue
        ja = col.get(e["ticker"])
        for d in (mp.get(e["ticker"]) or {}).get("followers", [])[:topk]:
            j = col.get(d["f"])
            if j is None:
                continue
            p0, p1 = Pf[i, j], Pf[z, j]
            if not (np.isfinite(p0) and np.isfinite(p1)) or p0 <= 0:
                continue
            fd = e["direction"] * (1 if d["c5"] >= 0 else -1)
            path = Pf[i:z + 1, j]
            sgn = fd * np.log(path / p0) * 1e4
            sgn = np.nan_to_num(sgn)
            k_pk = int(np.argmax(sgn))
            pre = Pf[max(i - 15, 0), j]
            pre_bp = float(fd * math.log(p0 / pre) * 1e4) if (np.isfinite(pre) and pre > 0 and sd[max(i - 15, 0)] == sd[i]) else None
            la0, la1 = Pf[i, ja], Pf[z, ja]
            out.append({"leader": e["ticker"], "follower": d["f"], "pattern": e["pattern"], "interval": e["interval"],
                        "direction": e["direction"], "f_dir": fd, "rel": rel_bucket(d["c5"]), "c5": d["c5"],
                        "fwd_bp": float(sgn[-1]), "mfe_bp": float(sgn.max()), "min_to_peak": k_pk, "minutes": z - i,
                        "pre15_bp": pre_bp, "leader_fwd_bp": float(e["direction"] * math.log(la1 / la0) * 1e4)
                        if (np.isfinite(la0) and np.isfinite(la1) and la0 > 0) else None, "date": e["date"]})
    return out


def agg_outcomes(outs, by_pair=False):
    agg = {}
    for o in outs:
        ks = [rate_key(o["pattern"], o["interval"], o["direction"], o["rel"])]
        if by_pair:
            ks = [pair_key(o["leader"], o["follower"], o["direction"], o["interval"])]
        for k in ks:
            a = agg.setdefault(k, {"n": 0, "hit": 0, "_bp": [], "_pk": [], "_lead": []})
            a["n"] += 1
            a["hit"] += o["fwd_bp"] > 0
            a["_bp"].append(o["fwd_bp"])
            a["_pk"].append(o["min_to_peak"])
            if o.get("leader_fwd_bp") is not None:
                a["_lead"].append(o["leader_fwd_bp"] > 0)
    med = lambda xs: (sorted(xs)[len(xs) // 2] if xs else None)
    for a in agg.values():
        a["rate"] = round(a["hit"] / a["n"], 4) if a["n"] else None
        bp = a.pop("_bp")
        a["mean_bp"] = round(sum(bp) / len(bp), 1) if bp else None
        a["med_bp"] = round(med(bp), 1) if bp else None
        a["med_min_to_peak"] = med(a.pop("_pk"))
        ld = a.pop("_lead")
        a["leader_follow_through"] = round(sum(ld) / len(ld), 4) if ld else None
        a["low_n"] = a["n"] < 20
    return dict(sorted(agg.items()))


def build(a):
    t0 = time.time()
    uni = IO.universe()
    bars = load_bars(uni)
    secs = sectors()
    allsess = sorted({b[6] for v in bars.values() for b in v})
    IO.log(f"leadlag build: {len(bars)} tickers, {len(allsess)} sessions {allsess[0]}..{allsess[-1]}")
    mp, syms, grid, sd, Pf = make_map(bars, allsess, secs)
    IO.log(f"full map in {time.time() - t0:.0f} s")
    doc = {"ll_version": LL_VERSION, "built_pt": IO.pt_str(time.time()), "shadow_only": True,
           "sessions": [allsess[0], allsess[-1]], "n_sessions": len(allsess), "n_tickers": len(syms),
           "btc_proxy": BTC_PROXY if BTC_PROXY in bars else None,
           "method": "1-min RTH log returns (last price carried within a session, winsorized 6 sd) on the minute grid. c5 = 5-min "
                     "return correlation (the relationship); c_lags[k-1] = corr(leader r[t], follower r[t+k]) for k=1..10 min; lag_min = "
                     "the k with the strongest same-sign lagged corr; lead_t = sum of c(1..10) (signed by c5) / sqrt(10/n); asym_t = "
                     "(leader->follower minus follower->leader) / sqrt(20/n). Followers: |c5| >= 0.30, lead_t > -2, ranked by "
                     "|c5| + 0.05*max(0, lead_t) + 0.03 same sector. pairs = top 25 by |c5| (any lag).",
           "by_ticker": mp}
    atomic(MAP, doc)
    # ---- out-of-sample backtest: map from the first split of sessions, events in the rest
    cut = allsess[max(3, int(len(allsess) * a.split))]
    early = [s for s in allsess if s < cut]
    mp_oos, syms_o, grid_o, sd_o, Pf_o = make_map(bars, early, secs)
    ev_oos = leader_events(uni, bars, cut)
    IO.log(f"oos: map on {early[0]}..{early[-1]}, {len(ev_oos)} leader events from {cut} ({time.time() - t0:.0f} s)")
    _, syms2, grid2, sd2, Pf2 = None, syms, grid, sd, Pf      # price paths: full grid (event bars are in it)
    outs = follow_outcomes(ev_oos, mp_oos, syms2, grid2, sd2, Pf2, TOPK_LIVE)
    # ---- in-sample: full map, every event after the 2 warm-up sessions
    ev_all = leader_events(uni, bars, allsess[2])
    outs_is = follow_outcomes(ev_all, mp, syms, grid, sd, Pf, TOPK_LIVE)
    rd = jload(RATES, {}) or {}
    rd.update(ll_version=LL_VERSION, built_pt=IO.pt_str(time.time()),
              method=("hit = follower log return from the leader event bar's close over the horizon (1m event 15 min, 5m 30 min, "
                      "30m 60 min, cut at the session close) in the predicted direction (> 0 bp); predicted direction = leader event "
                      "direction x sign(c5). Keys: pattern|interval|leader direction|bucket (c50 = |c5| >= 0.5, c30 = 0.30-0.50, "
                      "neg = inverse). backtest = OUT-OF-SAMPLE (follower map from sessions before " + cut + ", events " + cut +
                      " on); backtest_insample = full map, every event after 2 warm-up sessions. Top 8 followers per event. "
                      "Coin-flip reference = 50%. Raw rates, not calibrated."),
              oos_split=cut, oos_map_sessions=[early[0], early[-1]], oos_event_sessions=[cut, allsess[-1]],
              backtest=agg_outcomes(outs), backtest_insample=agg_outcomes(outs_is),
              backtest_pairs=agg_outcomes(outs_is, by_pair=True),
              n_events_oos=len(ev_oos), n_preds_oos=len(outs), n_events_insample=len(ev_all), n_preds_insample=len(outs_is))
    rd.setdefault("live", {})
    atomic(RATES, rd, indent=1)
    tot = lambda ag: (sum(v["n"] for v in ag.values()), sum(v["hit"] for v in ag.values()))
    n1, h1 = tot(rd["backtest"])
    n2, h2 = tot(rd["backtest_insample"])
    IO.log(f"leadlag rates: oos n={n1} hit={h1 / max(n1, 1):.1%}; in-sample n={n2} hit={h2 / max(n2, 1):.1%}; "
           f"{time.time() - t0:.0f} s -> {MAP.name}, {RATES.name}")


# ================================================================== LIVE (stdlib only)
def prob_for(rd, pattern, iv, d, rel, leader, follower):
    k = rate_key(pattern, iv, d, rel)
    pk = pair_key(leader, follower, d, iv)
    bt = ((rd or {}).get("backtest") or {}).get(k) or {}
    lv = ((rd or {}).get("live") or {}).get(k) or {}
    bp = ((rd or {}).get("backtest_pairs") or {}).get(pk) or {}
    ex = {"prob_backtest": bt.get("rate"), "n_backtest": bt.get("n"), "prob_live": lv.get("rate"), "n_live": lv.get("n"),
          "prob_pair_insample": bp.get("rate"), "n_pair_insample": bp.get("n"), "rate_key": k}
    if lv.get("n", 0) >= 20:
        return lv["rate"], "live", lv["n"], ex
    if bt.get("n"):
        return bt["rate"], "backtest_oos" + (" (n<20 low sample)" if bt["n"] < 20 else ""), bt["n"], ex
    return None, "no samples", 0, ex


def wall_tag(px, d, w):
    if not w or not px:
        return None
    cw, pw = w.get("cw"), w.get("pw")
    if cw:
        x = (px - cw) / cw * 100
        if d < 0 and -1.0 <= x <= 0.3:
            return {"tag": "call_wall_rejection", "wall": cw, "dist_pct": round(x, 2)}
        if d > 0 and 0 < x <= 1.0:
            return {"tag": "call_wall_breakout", "wall": cw, "dist_pct": round(x, 2)}
    if pw:
        x = (px - pw) / pw * 100
        if d > 0 and -0.3 <= x <= 1.0:
            return {"tag": "put_wall_bounce", "wall": pw, "dist_pct": round(x, 2)}
        if d < 0 and -1.0 <= x < 0:
            return {"tag": "put_wall_breakdown", "wall": pw, "dist_pct": round(x, 2)}
    return None


def bar_close_at(bars, ts):
    """close of the last 1-min bar that closed at or before ts (bars from L.load_day_bars) -> (px, bar_close_ts)"""
    best = None
    for b in bars:
        t = b.get("ts")
        if t is not None and t + 60 <= ts + 1:
            best = b
    return (best["c"], best["ts"] + 60) if best else (None, None)


class Live:
    def __init__(self, date):
        self.date = date
        self.uni = {s: st for s, _, st in IO.universe()}
        self.off = {}
        self.preds = []
        self.seen = set()
        d = IO.ARCH / "leadlag" / f"date={date}"
        for p in d.glob("part-leadlag-live-*.jsonl"):
            for ln in p.read_text().splitlines():
                try:
                    r = json.loads(ln)
                    self.seen.add(r["pred_id"])
                    self.preds.append(r)
                except Exception:
                    pass
        self.writer = LLWriter("live")
        self.mp_m = self.rd_m = None
        self.mp, self.rd = {}, {}

    def _reload(self):
        for attr, p in (("mp", MAP), ("rd", RATES)):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if getattr(self, attr + "_m") != m:
                d = jload(p)
                if d is not None:
                    setattr(self, attr, d.get("by_ticker", d) if attr == "mp" else d)
                    setattr(self, attr + "_m", m)

    def new_events(self):
        out = []
        d = IO.ARCH / "patterns" / f"date={self.date}"
        for p in sorted(d.glob("part-patterns-live-*.jsonl")):
            o = self.off.get(p.name, 0)
            with open(p) as fh:
                fh.seek(o)
                chunk = fh.read()
            if not chunk:
                continue
            last_nl = chunk.rfind("\n")
            if last_nl < 0:
                continue
            self.off[p.name] = o + len(chunk[:last_nl + 1].encode())
            for ln in chunk[:last_nl + 1].splitlines():
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("state") == "triggered" and r.get("pattern") in EVT and r.get("direction") and r.get("mode") == "live":
                    out.append(r)
        return out

    def pass_(self, now):
        self._reload()
        evs = self.new_events()
        if not evs or not self.mp:
            self.write_live(now)
            return 0
        try:
            walls = L.walls_from_files()
        except Exception:
            walls = {}
        cache = {}

        def bars_of(s):
            if s not in cache:
                try:
                    cache[s] = L.load_day_bars(s, self.date, store=self.uni.get(s), hist_fallback=False)
                except Exception:
                    cache[s] = []
            return cache[s]
        recs = []
        for e in evs:
            lead = e["ticker"]
            fol = (self.mp.get(lead) or {}).get("followers") or []
            if not fol:
                continue
            wt = wall_tag(e.get("px"), e["direction"], walls.get(lead))
            for d in fol[:TOPK_LIVE]:
                f = d["f"]
                pid = f"{e['det_id']}>{f}"
                if pid in self.seen:
                    continue
                fd = e["direction"] * (1 if d["c5"] >= 0 else -1)
                rel = rel_bucket(d["c5"])
                p, src, n, ex = prob_for(self.rd, e["pattern"], e["interval"], e["direction"], rel, lead, f)
                px, pxt = bar_close_at(bars_of(f), e["ts"])
                H = HZ[e["interval"]]
                r = {"pred_id": pid, "ts": e["ts"], "t_pt": IO.pt_str(e["ts"]), "date": self.date, "leader": lead,
                     "follower": f, "pattern": e["pattern"], "kind": KIND.get(e["pattern"]), "interval": e["interval"],
                     "direction": e["direction"], "f_dir": fd, "rel": rel, "c5": d["c5"], "lag_min": d["lag_min"],
                     "c_lag": d["c_lag"], "lead_t": d["lead_t"], "same_sector": d.get("same_sector"),
                     "horizon_min": H, "expires_ts": e["ts"] + H * 60, "leader_px": e.get("px"),
                     "leader_det_id": e["det_id"], "wall": wt, "f_px0": px, "f_px0_bar_close_ts": pxt,
                     "f_px0_stale_s": round(e["ts"] - pxt, 1) if pxt else None,
                     "prob_est": p, "prob_source": src, "prob_n": n, **{k: v for k, v in ex.items() if v is not None},
                     "logged_ts": round(now, 1), "catchup": now - e["ts"] > 150, "mode": "live",
                     "ll_version": LL_VERSION}
                self.seen.add(pid)
                recs.append(r)
        self.writer.write(self.date, recs)
        self.preds += recs
        self.write_live(now)
        return len(recs)

    def write_live(self, now):
        act = [r for r in self.preds if r["ts"] <= now < r["expires_ts"]]
        by = {}
        for r in act:
            by.setdefault(r["follower"], []).append(r)
        out = {}
        for f, rs in by.items():
            net = sum(r["f_dir"] * (r["prob_est"] if r["prob_est"] is not None else 0.5) for r in rs)
            sig = 1 if net > 0 else -1 if net < 0 else 0
            same = [r for r in rs if r["f_dir"] == sig] or rs
            top = sorted(same, key=lambda r: (r["prob_est"] if r["prob_est"] is not None else -1, r["ts"]), reverse=True)[0]
            out[f] = {"signal": sig, "prob": top["prob_est"], "n": top["prob_n"], "src": top["prob_source"],
                      "leader": top["leader"], "pattern": top["pattern"], "iv": top["interval"], "lag_min": top["lag_min"],
                      "c5": top["c5"], "wall": (top.get("wall") or {}).get("tag"), "ts": top["ts"], "t_pt": top["t_pt"],
                      "expires_pt": IO.pt_str(top["expires_ts"]), "n_active": len(rs),
                      "n_up": sum(1 for r in rs if r["f_dir"] > 0), "n_dn": sum(1 for r in rs if r["f_dir"] < 0)}
        evs = {}
        for r in self.preds[-400:]:
            x = evs.setdefault(r["leader_det_id"], {"leader": r["leader"], "pattern": r["pattern"], "iv": r["interval"],
                                                     "dir": r["direction"], "t_pt": r["t_pt"], "ts": r["ts"],
                                                     "wall": (r.get("wall") or {}).get("tag"), "followers": []})
            x["followers"].append({"f": r["follower"], "dir": r["f_dir"], "prob": r["prob_est"], "n": r["prob_n"],
                                   "lag": r["lag_min"]})
        doc = {"as_of": round(now, 1), "as_of_pt": IO.pt_str(now), "mode": "live", "ll_version": LL_VERSION,
               "shadow_only": True, "note": "shadow only: never feeds a live score, an alert or a trade",
               "n_followers": len(out), "by_sym": out,
               "recent_events": sorted(evs.values(), key=lambda x: -x["ts"])[:30]}
        atomic(LIVE, doc)
        try:
            atomic(GUIDE_COPY, doc)
        except Exception:
            pass


class LLWriter(IO.Writer):
    def _open(self, day):
        d = IO.ARCH / "leadlag" / f"date={day}"
        d.mkdir(parents=True, exist_ok=True)
        seqs = [int(p.stem.rsplit("-", 1)[1]) for p in d.glob("part-leadlag-live-*.jsonl") if p.stem.rsplit("-", 1)[1].isdigit()]
        self.path = d / f"part-leadlag-live-{(max(seqs) + 1) if seqs else 1}.jsonl"
        self.day = day


def rth(now):
    d = datetime.fromtimestamp(now, IO.PTZ)
    return d.weekday() < 5 and (6, 30) <= (d.hour, d.minute) <= (13, 5)


def daemon(a):
    IO.log(f"leadlag daemon up ({LL_VERSION})")
    lv, stats, last_log = None, {"preds": 0, "passes": 0, "errors": 0}, 0
    while True:
        now = time.time()
        if (PDIR / "leadlag-disabled").exists():
            time.sleep(30)
            continue
        if not rth(now) and not a.force:
            if lv is not None:
                IO.log(f"session over: {stats}")
                lv.write_live(now)
                lv = None
            time.sleep(30)
            continue
        date = a.date or datetime.fromtimestamp(now, IO.ET).strftime("%Y-%m-%d")
        try:
            if lv is None or lv.date != date:
                lv = Live(date)
                stats = {"preds": 0, "passes": 0, "errors": 0}
                IO.log(f"day {date}: {len(lv.seen)} predictions already archived")
            t0 = time.time()
            n = lv.pass_(now)
            stats["preds"] += n
            stats["passes"] += 1
            stats["ms"] = round((time.time() - t0) * 1000, 1)
            if n or now - last_log > 900:
                IO.log(f"pass: {n} new predictions ({stats})")
                last_log = now
        except Exception as e:
            stats["errors"] += 1
            IO.log(f"pass error: {type(e).__name__}: {e}")
        if a.once:
            return 0
        nxt = (int(time.time()) // 60 + 1) * 60 + 25
        time.sleep(max(1.0, nxt - time.time()))


# ================================================================== GRADE (stdlib only)
def grade(a):
    t0 = time.time()
    root = IO.ARCH / "leadlag"
    days = sorted(p.name[5:] for p in root.glob("date=*"))[-a.days:]
    uni = {s: st for s, _, st in IO.universe()}
    cache = {}

    def bars_of(s, day):
        k = (s, day)
        if k not in cache:
            try:
                cache[k] = L.load_day_bars(s, day, store=uni.get(s), hist_fallback=True)
            except Exception:
                cache[k] = []
        return cache[k]
    allp = []
    for day in days:
        labs = []
        for p in sorted((root / f"date={day}").glob("part-leadlag-live-*.jsonl")):
            for ln in p.read_text().splitlines():
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                fb = bars_of(r["follower"], day)
                p0, t0b = bar_close_at(fb, r["ts"])
                p1, t1b = bar_close_at(fb, r["expires_ts"])
                lb = bars_of(r["leader"], day)
                l0, _ = bar_close_at(lb, r["ts"])
                l1, _ = bar_close_at(lb, r["expires_ts"])
                last_close = (fb[-1]["ts"] + 60) if fb else 0
                final = bool(fb) and (last_close >= r["expires_ts"] or time.time() > r["expires_ts"] + 3600)
                lab = {"label_id": r["pred_id"] + ":live", "pred_id": r["pred_id"], "date": day, "leader": r["leader"],
                       "follower": r["follower"], "pattern": r["pattern"], "interval": r["interval"],
                       "direction": r["direction"], "f_dir": r["f_dir"], "rel": r["rel"], "c5": r["c5"],
                       "prob_est": r.get("prob_est"), "prob_source": r.get("prob_source"), "wall": (r.get("wall") or {}).get("tag"),
                       "catchup": r.get("catchup"), "ll_version": r.get("ll_version"), "graded_pt": IO.pt_str(time.time())}
                if p0 and p1 and t1b and t1b > t0b:
                    fwd = r["f_dir"] * math.log(p1 / p0) * 1e4
                    lab.update(fwd_bp=round(fwd, 1), outcome="hit" if fwd > 0 else "miss", final=final,
                               minutes=round((t1b - t0b) / 60, 1),
                               leader_fwd_bp=round(r["direction"] * math.log(l1 / l0) * 1e4, 1) if (l0 and l1) else None)
                else:
                    lab.update(outcome="no_bars", final=final)
                labs.append(lab)
        d = IO.ARCH / "leadlag_labels" / f"date={day}"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "part-leadlag-grader-1.jsonl", "w") as fh:
            for x in labs:
                fh.write(json.dumps({k: v for k, v in x.items() if v is not None}, separators=(",", ":")) + "\n")
    outs = []
    for p in sorted((IO.ARCH / "leadlag_labels").glob("date=*/part-leadlag-grader-1.jsonl")):
        for ln in p.read_text().splitlines():
            x = json.loads(ln)
            if x.get("final") and x.get("outcome") in ("hit", "miss"):
                outs.append({"leader": x["leader"], "follower": x["follower"], "pattern": x["pattern"], "interval": x["interval"],
                             "direction": x["direction"], "rel": x["rel"], "fwd_bp": x["fwd_bp"], "min_to_peak": None,
                             "leader_fwd_bp": x.get("leader_fwd_bp"), "date": x["date"]})
    rd = jload(RATES, {}) or {}
    for o in outs:
        o["min_to_peak"] = 0
    rd["live"] = agg_outcomes(outs)
    for v in rd["live"].values():
        v.pop("med_min_to_peak", None)
    rd["live_built_pt"] = IO.pt_str(time.time())
    atomic(RATES, rd, indent=1)
    D = days[-1] if days else "none"
    today = [o for o in outs if o["date"] == D]
    ag = agg_outcomes(today)
    bt = rd.get("backtest") or {}
    card = {"date": D, "days_graded": days, "ll_version": LL_VERSION, "graded_pt": IO.pt_str(time.time()),
            "today": ag, "live_keys": len(rd["live"]), "live_n_total": sum(v["n"] for v in rd["live"].values()),
            "today_n": len(today), "today_hit": sum(1 for o in today if o["fwd_bp"] > 0)}
    atomic(PDIR / f"leadlag-scorecard-{D}.json", card, indent=1)
    md = [f"# Lead-lag scorecard {D} (shadow, {LL_VERSION})", "",
          f"Graded {IO.pt_str(time.time())}. Days: {', '.join(days) or 'none'}. Hit = follower moved the predicted way "
          "(log return > 0 bp) from the leader event bar's close to the end of the horizon. Coin flip = 50%.", "",
          f"Today: n={card['today_n']} hit={card['today_hit']}"
          + (f" ({card['today_hit'] / card['today_n']:.1%})" if card["today_n"] else ""), "",
          "| key (pattern / iv / leader dir / bucket) | n | hit | live rate | mean bp | backtest oos rate (n) |", "|---|---|---|---|---|---|"]
    for k, v in sorted(ag.items(), key=lambda kv: -kv[1]["n"]):
        b = bt.get(k) or {}
        md.append(f"| {k.replace('|', ' / ')} | {v['n']} | {v['hit']} | {v['rate']:.1%} | {v['mean_bp']} | "
                  f"{(b.get('rate') or 0):.1%} ({b.get('n', 0)}) |")
    (PDIR / f"leadlag-scorecard-{D}.md").write_text("\n".join(md) + "\n")
    row = {"id": f"leadlag-scorecard-{D}", "kind": "leadlag_scorecard", "date": D, "created_pt": IO.pt_str(time.time()),
           "ll_version": LL_VERSION, "shadow_only": True, "summary": {"n": card["today_n"], "hit": card["today_hit"]},
           "live_rates": {k: {"n": v["n"], "rate": v["rate"]} for k, v in rd["live"].items()},
           "files": [str(PDIR / f"leadlag-scorecard-{D}.md")]}
    try:  # RRFIX 10/21: one row per id, a rerun replaces the earlier row instead of appending a duplicate
        from pattern_learn import exp_upsert
        exp_upsert(row)
    except ImportError:
        with open(EXP, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    IO.log(f"leadlag graded {len(days)} days in {time.time() - t0:.1f} s: today n={card['today_n']} hit={card['today_hit']}; "
           f"live keys {len(rd['live'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--split", type=float, default=0.6)
    d = sp.add_parser("daemon")
    d.add_argument("--once", action="store_true")
    d.add_argument("--force", action="store_true", help="test: run outside RTH")
    d.add_argument("--date")
    g = sp.add_parser("grade")
    g.add_argument("--days", type=int, default=10)
    a = ap.parse_args()
    {"build": build, "daemon": daemon, "grade": grade}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
