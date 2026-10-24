#!/usr/bin/env python3
"""DIRECTION-ANALYSIS (2026-10-24, Jeffrey): research-only. Why does the LIVE direction score (score_lib.combine, v1.2-20261022)
lose on 10/21-23? Reads archives only; nothing live is touched.

Inputs  score_labels (kind=snap, core, 15 s rows; h300/h900/h1800 ret/mfe/mae labels)  joined 1:1 on (symbol, t) with
        score_features (same snapshot: per-component c/q, trend_vwap_atr, trend_ret_atr, ...);
        bars_1d (Alpaca session open/close), bars_5m (lower highs / higher lows);
        ~/oid-data/score/ma200-gate/sma200.json (200-day SMA) and direction-analysis/daily_ctx.json (20/50-day SMA, VIX, SPY/QQQ day).
Trade = same definition as ma200-gate: first 15 s snapshot of a same-sign nonzero score run per symbol per day (run ends at 0,
sign flip or >60 s gap); NON-OVERLAPPING per horizon (a run start is taken only if >= horizon after the last taken trade on
that symbol). d = sign(score) * forward return (bp) to the horizon, final labels only. No stop/target.
Outcome buckets (per horizon): wrong d<=0; right-small 0<d<5 bp (cost proxy); right d>=5 bp. Alt threshold 0.25 x ATR-to-horizon
(ATR_bp x sqrt(h/390 min)). "right-then-reversed" = wrong but MFE >= threshold; "never right" = wrong and MFE < threshold.
Variants (drop-one, proposal) recompute raw/score per row from the LOGGED c and q with score_lib.combine semantics
(a disabled component leaves num and den), then re-derive trades from the new score series.
"""
import collections, json, math, os, statistics, sys
from pathlib import Path
import duckdb
sys.path.insert(0, str(Path.home() / "oid-score"))
import score_lib as L

D = Path.home() / "oid-data"
OUT = D / "score" / "direction-analysis"
PQ = D / "archive" / "parquet"
HZ = (300, 900, 1800)
COMPS = L.COMPONENTS
CFG = L.load_config()
W = {k: float(v.get("weight", 1.0)) for k, v in CFG["components"].items() if k in COMPS}
SMA = json.load(open(D / "score" / "ma200-gate" / "sma200.json"))["by_date"]
DCTX = json.load(open(OUT / "daily_ctx.json"))
FIT, TEST = ["2026-10-21", "2026-10-22"], ["2026-10-23"]
LIVE = ["2026-10-21", "2026-10-22", "2026-10-23"]
REPLAY = ["2026-10-19", "2026-10-20"]
COST = 5.0
GROUP = {}
for g, ss in {"ETF broad/intl": "DIA QQQ RSP SPY TQQQ VTV VUG EWY", "Semis + semi ETFs": "NVDA AMD AVGO ARM INTC QCOM TSM MRVL ALAB CRDO SMH SOXX",
              "Semi equipment": "AMAT ASML KLAC LRCX", "Analog semis": "ADI ON TXN", "Memory/storage": "MU SNDK STX WDC",
              "Optical/networking": "AAOI COHR LITE ANET GLW KEYS", "AI infra/neocloud/power/miners": "CRWV NBIS IREN WULF BE VRT SMCI DELL",
              "Megacap/software/internet": "AAPL AMZN GOOG GOOGL META MSFT NFLX ORCL PLTR INTU TSLA", "Other": "MH"}.items():
    for s in ss.split():
        GROUP[s] = g


def load(date, mode):
    lc = "l.symbol, l.t, l.score, l.raw, l.px, l.atr, " + ", ".join(f"l.h{h}_ret_bp, l.h{h}_full, l.h{h}_mfe_bp, l.h{h}_mae_bp" for h in HZ)
    fc = ", ".join(f"f.{c}_c, f.{c}_q" for c in COMPS) + ", f.trend_vwap_atr, f.trend_ret_atr, f.raw as f_raw, f.score as f_score"
    q = (f"select {lc}, {fc} from read_parquet('{PQ}/score_labels/date={date}/*.parquet') l join "
         f"read_parquet('{PQ}/score_features/date={date}/*.parquet') f on l.symbol=f.symbol and abs(l.t-f.t)<0.01 "
         f"and f.profile='core' and f.mode='{mode}' where l.kind='snap' and l.profile='core' and l.mode='{mode}' order by l.symbol, l.t")
    c = duckdb.connect()
    r = c.execute(q); names = [x[0] for x in r.description]; fetched = r.fetchall()
    o = {s: (op, cl) for s, op, cl in c.execute(f"select symbol, open, close from read_parquet('{PQ}/bars_1d/**/*.parquet', hive_partitioning=1) where trade_date='{date}'").fetchall()}
    b5 = collections.defaultdict(list)
    for s, e, hi, lo in c.execute(f"select symbol, bar_end_ns/1e9, high, low from read_parquet('{PQ}/bars_5m/**/*.parquet', hive_partitioning=1) "
                                  f"where date='{date}' and high is not null and low is not null order by symbol, bar_end_ns").fetchall():
        b5[s].append((e, hi, lo))
    rows = []
    ptr = collections.defaultdict(int)
    for v in fetched:
        x = dict(zip(names, v)); s = x["symbol"]
        sm = (SMA[date].get(s) or {}).get("sma200")
        if not sm or not x["px"]:
            continue
        x["date"] = date; x["dist200"] = x["px"] / sm - 1
        dc = DCTX["by_date"][date].get(s) or {}
        x["sma20"], x["sma50"] = dc.get("sma20"), dc.get("sma50")
        x["open"], x["close"] = o.get(s, (None, None))
        bl = b5.get(s) or []
        i = ptr[s]
        while i < len(bl) and bl[i][0] <= x["t"] + 0.001:
            i += 1
        ptr[s] = i
        last = bl[max(0, i - 3):i]
        x["lower_highs"] = len(last) == 3 and last[2][1] < last[1][1] < last[0][1]
        x["higher_lows"] = len(last) == 3 and last[2][2] > last[1][2] > last[0][2]
        x["atr_bp"] = x["atr"] / x["px"] * 1e4 if x["atr"] else None
        rows.append(x)
    # trailing 15m return from the row's own px series (15 s grid)
    by = collections.defaultdict(list)
    for x in rows:
        by[x["symbol"]].append(x)
    for s, rs in by.items():
        j = 0
        for x in rs:
            while j < len(rs) and rs[j]["t"] < x["t"] - 900 - 7:
                j += 1
            p = rs[j] if rs[j]["t"] <= x["t"] - 900 + 7 else None
            x["back900_bp"] = (x["px"] / p["px"] - 1) * 1e4 if p else None
    return rows


def recompute(x, drop=(), invert=(), zero=()):
    num = den = 0.0
    for c in COMPS:
        if c in drop:
            continue
        q, cv = x.get(f"{c}_q"), x.get(f"{c}_c")
        den += W[c]
        if q is None or cv is None or c in zero:
            continue
        num += W[c] * q * (-cv if c in invert else cv)
    mx = CFG["scale"].get("max_abs", 3)
    raw = L.clamp(mx * CFG["scale"].get("gain", 1.5) * (num / den if den else 0.0), -mx, mx)
    return int(math.copysign(math.floor(abs(raw) + 0.5), raw)) if raw else 0


def trades(rows, h, key="score"):
    taken = []
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["symbol"], r["date"])].append(r)
    for k, rs in by.items():
        ps, pt, lt = 0, None, -1e18
        for r in rs:
            sc = r[key]; sg = (sc > 0) - (sc < 0)
            if sg != 0 and (sg != ps or (pt is not None and r["t"] - pt > 60)):
                if r["t"] >= lt + h:
                    taken.append((r, sg)); lt = r["t"]
            ps, pt = sg, r["t"]
    return [(r, sg) for r, sg in taken if r.get(f"h{h}_full") and r.get(f"h{h}_ret_bp") is not None]


def st(xs):
    n = len(xs)
    if not n:
        return {"n": 0}
    return {"n": n, "hit": round(sum(v > 0 for v in xs) / n, 4), "mean_bp": round(sum(xs) / n, 2), "total_bp": round(sum(xs), 1),
            "net5_mean_bp": round(sum(xs) / n - COST, 2)}


def d_of(r, sg, h):
    return sg * r[f"h{h}_ret_bp"]


def thr_atr(r, h):
    return 0.25 * r["atr_bp"] * math.sqrt(h / 23400) if r.get("atr_bp") else None


def outcome_table(tr, h):
    """tr: list of (row, sign). buckets by side."""
    res = {}
    for side, f in (("all", lambda s: True), ("long", lambda s: s > 0), ("short", lambda s: s < 0)):
        sel = [(r, s) for r, s in tr if f(s)]
        tot = sum(d_of(r, s, h) for r, s in sel)
        neg = sum(min(0, d_of(r, s, h)) for r, s in sel)
        out = {"trades": len(sel), "total_bp": round(tot, 1), "sum_negative_bp": round(neg, 1), "mean_bp": round(tot / len(sel), 2) if sel else None}
        for tname, tf in (("cost5bp", lambda r: COST), ("0.25atr_h", lambda r: thr_atr(r, h))):
            B = collections.defaultdict(list)
            for r, s in sel:
                d = d_of(r, s, h); th = tf(r) or COST
                mfe = r.get(f"h{h}_mfe_bp")
                if d <= 0:
                    B["wrong"].append(d)
                    B["wrong: right-then-reversed (MFE>=thr)" if (mfe is not None and mfe >= th) else "wrong: never right (MFE<thr)"].append(d)
                elif d < th:
                    B["right-but-small"].append(d)
                else:
                    B["right"].append(d)
            o = {}
            for b in ("wrong", "wrong: right-then-reversed (MFE>=thr)", "wrong: never right (MFE<thr)", "right-but-small", "right"):
                xs = B.get(b, [])
                o[b] = {"n": len(xs), "share": round(len(xs) / len(sel), 4) if sel else None, "total_bp": round(sum(xs), 1),
                        "mean_bp": round(sum(xs) / len(xs), 2) if xs else None,
                        "share_of_negative_bp": round(sum(xs) / neg, 4) if neg and b.startswith("wrong") else None,
                        "net_of_5bp_total": round(sum(xs) - COST * len(xs), 1)}
            out[tname] = o
        mf = [r.get(f"h{h}_mfe_bp") for r, s in sel if r.get(f"h{h}_mfe_bp") is not None]
        ma = [r.get(f"h{h}_mae_bp") for r, s in sel if r.get(f"h{h}_mae_bp") is not None]
        out["median_mfe_bp"] = round(statistics.median(mf), 1) if mf else None
        out["median_mae_bp"] = round(statistics.median(ma), 1) if ma else None
        res[side] = out
    return res


def tercile_cuts(vals):
    v = sorted(vals)
    return v[len(v) // 3], v[2 * len(v) // 3]


def regimes(tr, h, cuts):
    def add(R, k, r, s):
        R.setdefault(k, {"long": [], "short": [], "all": []})
        d = d_of(r, s, h)
        R[k]["all"].append(d); R[k]["long" if s > 0 else "short"].append(d)
    R = {}
    for r, s in tr:
        dt = r["date"]; spy = DCTX["index_day"][dt]["SPY"]["open_to_close_pct"]
        add(R, f"day {dt} (SPY o->c {spy:+.2f}%, VIX close {DCTX['vix'][dt]['Close']})", r, s)
        if r["open"] and r["close"]:
            add(R, "name day: " + ("up (close>open)" if r["close"] > r["open"] else "down (close<=open)"), r, s)
            add(R, "entry px vs session open: " + ("above" if r["px"] > r["open"] else "below/at"), r, s)
        va = r.get("trend_vwap_atr")
        if va is not None:
            add(R, "entry px vs VWAP: " + ("above" if va > 0 else "below/at"), r, s)
        if r.get("atr_bp"):
            a = r["atr_bp"]; add(R, "ATR% tercile: " + ("low" if a < cuts[0] else "mid" if a < cuts[1] else "high"), r, s)
        add(R, "200d: " + ("near <2%" if abs(r["dist200"]) < 0.02 else "far >=2%"), r, s)
        add(R, "sector: " + GROUP.get(r["symbol"], "Other"), r, s)
    out = {}
    tot_neg = sum(min(0, d_of(r, s, h)) for r, s in tr); n_all = len(tr)
    for k, v in sorted(R.items()):
        e = {side: st(v[side]) for side in ("all", "long", "short")}
        e["trade_share"] = round(len(v["all"]) / n_all, 4)
        e["share_of_negative_bp"] = round(sum(min(0, x) for x in v["all"]) / tot_neg, 4) if tot_neg else None
        e["short_all_same"] = st([-sg * x for sg, x in zip([1] * 0, [])]) if False else None
        out[k] = e
    return out


def baselines(tr, h):
    return {"score": st([d_of(r, s, h) for r, s in tr]), "inverse_score": st([-d_of(r, s, h) for r, s in tr]),
            "short_all": st([-r[f"h{h}_ret_bp"] for r, s in tr]), "long_all": st([r[f"h{h}_ret_bp"] for r, s in tr]),
            "long_calls": st([d_of(r, s, h) for r, s in tr if s > 0]), "short_calls": st([d_of(r, s, h) for r, s in tr if s < 0])}


def components(tr, h):
    """per component: hit of its own sign (when nonzero, q>0) on the score's trades; dominant contributor on losers/winners."""
    out = {"own_sign_hit": {}, "agrees_with_trade_sign": {}, "dominant_on_losers": {}, "dominant_on_winners": {}}
    for c in COMPS:
        xs = [math.copysign(1, r[f"{c}_c"]) * r[f"h{h}_ret_bp"] for r, s in tr if r.get(f"{c}_c") and r.get(f"{c}_q")]
        out["own_sign_hit"][c] = st(xs)
        ag = [(math.copysign(1, r[f"{c}_c"]) == s) for r, s in tr if r.get(f"{c}_c") and r.get(f"{c}_q")]
        out["agrees_with_trade_sign"][c] = round(sum(ag) / len(ag), 4) if ag else None
    dl, dw = collections.Counter(), collections.Counter()
    for r, s in tr:
        contrib = {c: s * W[c] * (r.get(f"{c}_q") or 0) * (r.get(f"{c}_c") or 0) for c in COMPS}
        top = max(contrib, key=contrib.get)
        (dl if d_of(r, s, h) <= 0 else dw)[top] += 1
    nl, nw = sum(dl.values()), sum(dw.values())
    out["dominant_on_losers"] = {c: round(dl[c] / nl, 4) for c in COMPS} if nl else {}
    out["dominant_on_winners"] = {c: round(dw[c] / nw, 4) for c in COMPS} if nw else {}
    out["n_losers"], out["n_winners"] = nl, nw
    return out


def signatures(tr, h):
    """long calls (and mirrored short calls) by trend context at entry."""
    out = {}
    conds = {
        "below VWAP": lambda r: (r.get("trend_vwap_atr") or 0) < 0, "above VWAP": lambda r: (r.get("trend_vwap_atr") or 0) > 0,
        "below session open": lambda r: r["open"] and r["px"] < r["open"], "above session open": lambda r: r["open"] and r["px"] > r["open"],
        "3 lower 5m highs": lambda r: r["lower_highs"], "3 higher 5m lows": lambda r: r["higher_lows"],
        "below 20d SMA": lambda r: r["sma20"] and r["px"] < r["sma20"], "above 20d SMA": lambda r: r["sma20"] and r["px"] > r["sma20"],
        "below 50d SMA": lambda r: r["sma50"] and r["px"] < r["sma50"], "above 50d SMA": lambda r: r["sma50"] and r["px"] > r["sma50"],
        "after 15m drop <=-20bp": lambda r: r.get("back900_bp") is not None and r["back900_bp"] <= -20,
        "after 15m rise >=+20bp": lambda r: r.get("back900_bp") is not None and r["back900_bp"] >= 20,
        "prior 15m flat (|ret|<20bp)": lambda r: r.get("back900_bp") is not None and abs(r["back900_bp"]) < 20,
    }
    for side, sg in (("long", 1), ("short", -1)):
        sel = [(r, s) for r, s in tr if s == sg]
        o = {}
        for k, f in conds.items():
            xs = [d_of(r, s, h) for r, s in sel if f(r)]
            e = st(xs); e["share_of_side"] = round(len(xs) / len(sel), 4) if sel else None
            o[k] = e
        out[side] = o
    # mean reversion vs momentum on these days: forward return vs trailing 15m return, all rows' trades
    pr = [(r["back900_bp"], r[f"h{h}_ret_bp"]) for r, s in tr if r.get("back900_bp") is not None]
    if len(pr) > 10:
        mx = sum(a for a, _ in pr) / len(pr); my = sum(b for _, b in pr) / len(pr)
        cov = sum((a - mx) * (b - my) for a, b in pr); va = sum((a - mx) ** 2 for a, _ in pr); vb = sum((b - my) ** 2 for _, b in pr)
        out["corr_trailing15m_vs_forward"] = round(cov / math.sqrt(va * vb), 4) if va and vb else None
        out["n_corr"] = len(pr)
    return out


def lag_test(rows):
    """at each sign flip of trend_c / flow_c (from <=-0.2 to >=+0.2 or reverse, per symbol-day): signed price move over the
    15 min BEFORE the flip vs the 5/15/30 min AFTER, in the flip's direction. Late = most of the move happened before."""
    out = {}
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["symbol"], r["date"])].append(r)
    for c in ("trend", "flow", "volume", "market"):
        pre, post = [], {h: [] for h in HZ}
        for k, rs in by.items():
            st_ = 0
            for r in rs:
                v = r.get(f"{c}_c")
                if v is None:
                    continue
                s = 1 if v >= 0.2 else -1 if v <= -0.2 else 0
                if s and st_ and s != st_:
                    if r.get("back900_bp") is not None:
                        pre.append(s * r["back900_bp"])
                        for h in HZ:
                            if r.get(f"h{h}_full") and r.get(f"h{h}_ret_bp") is not None:
                                post[h].append(s * r[f"h{h}_ret_bp"])
                if s:
                    st_ = s
        out[c] = {"flips": len(pre), "pre15m_move_in_flip_dir_bp": st(pre), **{f"post{h // 60}m": st(post[h]) for h in HZ}}
    return out


VARIANTS = {"live (recomputed)": {}, **{f"drop {c}": {"drop": (c,)} for c in COMPS}}


def apply_variant(rows, key, spec, gate=None):
    for r in rows:
        sc = recompute(r, **{k: v for k, v in spec.items() if k in ("drop", "invert", "zero")})
        if gate and sc and not gate(r, sc):
            sc = 0
        r[key] = sc


def var_stats(rows, key):
    o = {}
    for h in HZ:
        tr = trades(rows, h, key)
        o[f"{h // 60}m"] = {"score": st([d_of(r, s, h) for r, s in tr]), "short_all": st([-r[f"h{h}_ret_bp"] for r, s in tr])}
    return o


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    R = {"version": "dirana-v1-20261024", "config": CFG["config_version"], "weights": W, "definitions": __doc__, "groups": GROUP,
         "daily_ctx_source": DCTX["source"], "vix": DCTX["vix"], "index_day": DCTX["index_day"]}
    data = {}
    for d in LIVE + REPLAY:
        data[d] = load(d, "live" if d in LIVE else "replay")
        print(d, len(data[d]), file=sys.stderr)
    # reconstruction check
    rc = {}
    for d, rows in data.items():
        ok = sum(1 for r in rows if recompute(r) == r["score"])
        rc[d] = {"rows": len(rows), "recomputed_score_matches_logged": round(ok / len(rows), 5)}
    R["reconstruction"] = rc
    allatr = [r["atr_bp"] for d in LIVE for r in data[d] if r.get("atr_bp")]
    cuts = tercile_cuts(allatr); R["atr_pct_tercile_cuts_bp"] = [round(x, 1) for x in cuts]
    for setname, days in (("live 10/21-23", LIVE), ("replay 10/19-20", REPLAY)):
        rows = [r for d in days for r in data[d]]
        S = {"rows": len(rows), "names": len({r["symbol"] for r in rows})}
        for h in HZ:
            tr = trades(rows, h); hz = f"{h // 60}m"
            S.setdefault("outcomes", {})[hz] = outcome_table(tr, h)
            S.setdefault("baselines", {})[hz] = baselines(tr, h)
            S.setdefault("baselines_by_day", {})[hz] = {d: baselines([(r, s) for r, s in tr if r["date"] == d], h) for d in days}
            S.setdefault("regimes", {})[hz] = regimes(tr, h, cuts)
            S.setdefault("components", {})[hz] = components(tr, h)
            S.setdefault("signatures", {})[hz] = signatures(tr, h)
        S["lag"] = lag_test(rows)
        R[setname] = S
    # drop-one + proposal candidates, per day
    CAND = {
        "P1 VWAP-side gate (long only above VWAP, short only below)": {"gate": lambda r, sc: (r.get("trend_vwap_atr") or 0) * sc > 0},
        "P2 long-only VWAP gate (longs need px>VWAP; shorts unchanged)": {"gate": lambda r, sc: sc < 0 or (r.get("trend_vwap_atr") or 0) > 0},
        "P3 open-side gate (long only above open, short only below)": {"gate": lambda r, sc: r["open"] and (r["px"] - r["open"]) * sc > 0},
        **{f"invert {c}": {"invert": (c,)} for c in COMPS},
        # NOTE: F1/F2 were added AFTER the inverse-score baseline had been seen on all 5 days (not a blind candidate)
        "F1 fade: flip the sign of the whole score (invert all six)": {"invert": tuple(COMPS)},
        "F2 invert the lagging trio (trend, volume, market)": {"invert": ("trend", "volume", "market")},
        # late-entry (stretch) gate: no call in the direction of a trailing-15m move already > k ATR (trend_ret_atr is the
        # trend component's own input: (px - close 15 1-min bars ago) / daily ATR, known at the snapshot)
        **{f"S{k} late-entry gate (skip if 15m move in call dir > {k} ATR)": {"gate": (lambda kk: lambda r, sc: (r.get("trend_ret_atr") or 0) * (1 if sc > 0 else -1) <= kk)(k)}
           for k in (0.05, 0.1, 0.2, 0.3)},
    }
    allv = {**VARIANTS, **CAND}
    V = {}
    for name, spec in allv.items():
        V[name] = {}
        for d, rows in data.items():
            apply_variant(rows, "_v", spec, spec.get("gate"))
            V[name][d] = var_stats(rows, "_v")
        for lab, days in (("fit 10/21-22", FIT), ("test 10/23", TEST), ("replay 10/19-20", REPLAY), ("live 10/21-23", LIVE)):
            rows = [r for d in days for r in data[d]]
            apply_variant(rows, "_v", spec, spec.get("gate"))
            V[name][lab] = var_stats(rows, "_v")
        print("variant", name, file=sys.stderr)
    R["variants"] = V
    # pre-declared selection: best FIT-day (10/21-22) 15m mean bp among non-drop candidates keeping >= 70 % of live fit trades
    base = V["live (recomputed)"]["fit 10/21-22"]["15m"]["score"]["n"]
    ok = {k: v["fit 10/21-22"]["15m"]["score"]["mean_bp"] for k, v in V.items() if k in CAND and v["fit 10/21-22"]["15m"]["score"]["n"] >= 0.7 * base}
    R["selection"] = {"rule": "max fit 10/21-22 15m mean_bp among CAND with trades >= 70% of live fit trades", "ranked": sorted(ok.items(), key=lambda x: -x[1]),
                      "chosen": max(ok, key=ok.get) if ok else None,
                      "caveat": "F1/F2 added after the inverse-score baseline was seen on all days; P*/invert*/S* were defined before looking at holdout results"}
    (OUT / "direction-analysis-results.json").write_text(json.dumps(R, indent=1, default=str))
    print("wrote", OUT / "direction-analysis-results.json", file=sys.stderr)


if __name__ == "__main__":
    main()
