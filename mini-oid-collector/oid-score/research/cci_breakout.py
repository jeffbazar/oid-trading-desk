#!/usr/bin/env python3
"""CCI-breakout filter test (2026-10-25, Jeffrey; X post @onlybreakouts 2114454472248230234 / breakoutos.com blog).
Research only; reads bar files, touches nothing live.
Post's setup: e-mini NASDAQ 60-min bars; buy stop at previous day's (session ending 16:00 CT) low + 0.8 x ATR(40);
session 00:00-23:00 CT, exit end of day 23:00; long only. Filter: Lowest(CCI(27), 18 bars) < -100.
Family ('similar DNA', 1,008 variants): ref {LOD, COD, HOD, OPEN} x k {0.2,0.4,0.6,0.8,1.0,1.2,1.5} x ATR {20,40,80}
x start {session start, ~RTH} x exit {EOD, H4, H8, SL1, SL2, TP2SL1}. Daily family: Donchian N {5,10,20,50,100} x entry
{close, next_open} x exit {hold1,5,10,20, SL2, TRAIL, TP3SL2} = 70 variants.
Usage: cci_breakout.py SERIES_KEY OUTDIR   (see SERIES below)."""
import json, sys, time, statistics, math
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cci_lib as X

ROOT = Path.home() / "oid-data/score/cci-breakout-filter"
KS = (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5); REFS = ("LOD", "COD", "HOD", "OPEN"); EXITS = ("EOD", "H4", "H8", "SL1", "SL2", "TP2SL1")
NAMED = ["CCI27_lo18<-100 (post)", "NOT CCI (complement)", "RSI14_lo18<30", "close<SMA20 in last 18", "RSI14_lo18 calibrated",
         "min(close-SMA20)/ATR lo18 calibrated", "pullback depth (36h high - 18 low)/ATR calibrated"]

def intraday_grid(full, starts):
    if full: return [(r, k, a, s, e) for r in REFS for k in KS for a in (20, 40, 80) for s in starts for e in EXITS]
    return [(r, k, 40, s, e) for r in REFS for k in (0.4, 0.8, 1.2) for s in starts for e in EXITS]
def daily_grid():
    return [(N, en, ex) for N in (5, 10, 20, 50, 100) for en in ("close", "next_open") for ex in ("hold1", "hold5", "hold10", "hold20", "SL2", "TRAIL", "TP3SL2")]

def summarize(base, filt):
    """base/filt: dict variant -> stats. Post-style family metrics."""
    v = [k for k in base if base[k]["n"] >= 20 and filt[k]["n"] >= 10]
    if not v: return {"n_variants": 0}
    net_up = [k for k in v if filt[k]["net"] > base[k]["net"]]
    avg_up = [k for k in v if filt[k]["avg"] > base[k]["avg"]]
    pos = [k for k in v if base[k]["avg"] > 0]
    avg22 = [k for k in pos if filt[k]["avg"] >= 1.22 * base[k]["avg"]]
    pdd_up = [k for k in v if (filt[k]["pdd"] or -1e9) > (base[k]["pdd"] or -1e9)]
    losers = [k for k in v if base[k]["net"] <= 0]
    bounce = [k for k in losers if filt[k]["net"] > 0]
    dav = [filt[k]["avg"] - base[k]["avg"] for k in v]
    return {"n_variants": len(v), "pct_net_improved": len(net_up) / len(v), "pct_avg_improved": len(avg_up) / len(v),
            "pct_avg_up22_of_profitable": (len(avg22) / len(pos)) if pos else None, "n_profitable_base": len(pos),
            "pct_pdd_improved": len(pdd_up) / len(v), "bounce_index": (len(bounce) / len(losers)) if losers else None,
            "n_losing_base": len(losers), "median_davg_bp": statistics.median(dav), "mean_davg_bp": statistics.mean(dav),
            "median_trade_retention": statistics.median(filt[k]["n"] / base[k]["n"] for k in v),
            "pct_variants_base_profitable": len(pos) / len(v), "pct_variants_filt_profitable": sum(filt[k]["avg"] > 0 for k in v) / len(v)}

def welch(a, b):
    if len(a) < 3 or len(b) < 3: return None
    ma, mb = statistics.mean(a), statistics.mean(b); va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b)); return (ma - mb) / se if se > 0 else None

def run_series(key, cfg, outdir):
    t0 = time.time()
    res = {"key": key, "desc": cfg["desc"], "cost_bp": cfg["cost"], "cut": cfg["cut"]}
    cut = datetime.fromisoformat(cfg["cut"]).replace(tzinfo=timezone.utc)
    if cfg["kind"] == "intraday":
        series = {s: X.prep_intraday(X.load_csv(p), cfg["mode"]) for s, p in cfg["files"].items()}
        filters = {}
        for s, P in series.items():
            A40 = X.atr(P["H"], P["L"], P["C"], 40)
            F, p = X.filter_bank(P["H"], P["L"], P["C"], A40, neighborhood=cfg.get("nb", False), n_random=cfg.get("nrand", 20))
            res.setdefault("calib", {})[s] = F.pop("_calib"); filters[s] = F; P["ATR"] = {a: X.atr(P["H"], P["L"], P["C"], a) for a in (20, 40, 80)}
            res.setdefault("bars", {})[s] = {"n": P["n"], "first": P["T"][0].isoformat(), "last": P["T"][-1].isoformat(), "cci_pass_rate": p}
        full = intraday_grid(cfg["full"], cfg["starts"]); small = intraday_grid(False, cfg["starts"])
        fnames = list(filters[next(iter(filters))].keys())
        def run(var, fname):
            r, k, a, s, e = var; out = []
            for sym, P in series.items():
                act = None if fname is None else filters[sym][fname]
                tr = X.run_intraday(P, P["ATR"][a], r, k, s, e, act, cfg["cost"])
                out += [t + (sym,) for t in tr]
            out.sort(key=lambda t: t[0]); return out
        trades_base = {}
        fam = {}  # fname -> {"all":(base,filt),"is":..,"oos":..}
        def acc(fname, var, trb, trf):
            d = fam.setdefault(fname, {"all": ({}, {}), "is": ({}, {}), "oos": ({}, {})})
            vk = "|".join(map(str, var))
            d["all"][0][vk] = X.stats(trb); d["all"][1][vk] = X.stats(trf)
            bi, bo = X.split(trb, cut); fi, fo = X.split(trf, cut)
            d["is"][0][vk] = X.stats(bi); d["is"][1][vk] = X.stats(fi); d["oos"][0][vk] = X.stats(bo); d["oos"][1][vk] = X.stats(fo)
        for var in full:
            trb = run(var, None); trades_base[var] = trb
            for fn in NAMED: acc(fn, var, trb, run(var, fn))
        for var in small:
            trb = trades_base[var]
            for fn in fnames:
                if fn in NAMED: continue
                acc(fn, var, trb, run(var, fn))
        res["family"] = {fn: {sp: summarize(*d[sp]) for sp in d} for fn, d in fam.items()}
        res["family_size"] = {"full": len(full), "small": len(small)}
        # post's exact base case
        bc = cfg["base_case"]; res["base_case_def"] = "|".join(map(str, bc))
        trb = trades_base[bc]; trf = run(bc, NAMED[0]); trn = run(bc, NAMED[1])
        res["base_case"] = {"base": X.stats(trb), "cci": X.stats(trf), "not_cci": X.stats(trn),
                            "base_is_oos": [X.stats(x) for x in X.split(trb, cut)], "cci_is_oos": [X.stats(x) for x in X.split(trf, cut)],
                            "welch_t_cci_vs_notcci": welch([t[3] for t in trf], [t[3] for t in trn])}
        for fn in NAMED[2:]: res["base_case"][fn] = X.stats(run(bc, fn))
        if cfg.get("dollar_per_pt"):
            for nm, tr in (("base", trb), ("cci", trf)):
                pts = [t[4] - cfg["cost_pts"] for t in tr]; eq = pk = dd = 0.0
                for x in pts: eq += x * cfg["dollar_per_pt"]; pk = max(pk, eq); dd = max(dd, pk - eq)
                res["base_case"][nm + "_usd"] = {"avg_trade_usd": statistics.mean(pts) * cfg["dollar_per_pt"], "net_usd": eq, "maxdd_usd": dd, "net_over_dd": eq / dd if dd else None}
    else:
        series = {}
        for s, p in cfg["files"].items():
            b = X.load_csv(p)
            if cfg.get("drop_after"): b = [x for x in b if x[0] < datetime.fromisoformat(cfg["drop_after"]).replace(tzinfo=timezone.utc)]
            T = [x[0] for x in b]; O = [x[1] for x in b]; H = [x[2] for x in b]; L = [x[3] for x in b]; C = [x[4] for x in b]
            A20 = X.atr(H, L, C, 20); A40 = X.atr(H, L, C, 40)
            F, p = X.filter_bank(H, L, C, A40, neighborhood=cfg.get("nb", False), n_random=cfg.get("nrand", 20))
            res.setdefault("calib", {})[s] = F.pop("_calib"); series[s] = (T, O, H, L, C, A20, F)
            res.setdefault("bars", {})[s] = {"n": len(T), "first": T[0].isoformat(), "last": T[-1].isoformat(), "cci_pass_rate": p}
        fnames = list(next(iter(series.values()))[6].keys())
        def run(var, fname):
            N, en, ex = var; out = []
            for sym, (T, O, H, L, C, A20, F) in series.items():
                out += [t + (sym,) for t in X.run_daily(T, O, H, L, C, A20, N, en, ex, None if fname is None else F[fname], cfg["cost"])]
            out.sort(key=lambda t: t[0]); return out
        fam = {}
        grid = daily_grid(); base = {v: run(v, None) for v in grid}
        for fn in fnames:
            d = {"all": ({}, {}), "is": ({}, {}), "oos": ({}, {})}
            for v in grid:
                vk = "|".join(map(str, v)); trb = base[v]; trf = run(v, fn)
                d["all"][0][vk] = X.stats(trb); d["all"][1][vk] = X.stats(trf)
                bi, bo = X.split(trb, cut); fi, fo = X.split(trf, cut)
                d["is"][0][vk] = X.stats(bi); d["is"][1][vk] = X.stats(fi); d["oos"][0][vk] = X.stats(bo); d["oos"][1][vk] = X.stats(fo)
            fam[fn] = {sp: summarize(*d[sp]) for sp in d}
        res["family"] = fam; res["family_size"] = {"full": len(grid)}
        bc = cfg["base_case"]; res["base_case_def"] = "|".join(map(str, bc))
        trb = base[bc]; trf = run(bc, NAMED[0]); trn = run(bc, NAMED[1])
        res["base_case"] = {"base": X.stats(trb), "cci": X.stats(trf), "not_cci": X.stats(trn),
                            "base_is_oos": [X.stats(x) for x in X.split(trb, cut)], "cci_is_oos": [X.stats(x) for x in X.split(trf, cut)],
                            "welch_t_cci_vs_notcci": welch([t[3] for t in trf], [t[3] for t in trn])}
        for fn in NAMED[2:]: res["base_case"][fn] = X.stats(run(bc, fn))
    # random-filter distribution
    rk = [k for k in res["family"] if k.startswith("RANDOM#")]
    if rk:
        rr = {}
        for sp in ("all", "is", "oos"):
            vals = sorted(res["family"][k][sp].get("pct_net_improved") for k in rk if res["family"][k][sp].get("n_variants"))
            davg = sorted(res["family"][k][sp].get("median_davg_bp") for k in rk if res["family"][k][sp].get("n_variants"))
            if vals:
                cc = res["family"][NAMED[0]][sp]
                rr[sp] = {"n_seeds": len(vals), "pct_net_improved_mean": statistics.mean(vals), "pct_net_improved_max": vals[-1],
                          "median_davg_bp_mean": statistics.mean(davg), "median_davg_bp_max": davg[-1],
                          "cci_pct_net_improved_rank": sum(x < cc.get("pct_net_improved", 0) for x in vals) / len(vals)}
        res["random_summary"] = rr
        for k in rk: res["family"].pop(k)
    res["runtime_s"] = round(time.time() - t0, 1)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / f"{key}.json").write_text(json.dumps(res, indent=1, default=str))
    print(key, "done", res["runtime_s"], "s", flush=True)

def SERIES(root):
    y = root / "yahoo"; b1h = root / "bars/1h"; b1d = root / "bars/1d"
    core = sorted(p.stem for p in b1h.glob("*.csv")) if b1h.exists() else []
    S = {
     "nq_60m_yahoo": dict(kind="intraday", mode="nq", files={"NQ=F": y / "yahoo_NQF_60m.csv"}, cost=0.6, full=True, starts=(0, 8), nb=True,
                          base_case=("LOD", 0.8, 40, 0, "EOD"), cut="2025-07-01", dollar_per_pt=20, cost_pts=1.25,
                          desc="NQ=F continuous front month, Yahoo 60m, 2024-06..2026-10 (closest to the post); cost 0.6 bp (~1.25 pt = $25 round trip)"),
     "qqq_60m_ext": dict(kind="intraday", mode="eq_ext", files={"QQQ": b1h / "QQQ.csv"}, cost=2.0, full=True, starts=(4, 9), nb=True,
                         base_case=("LOD", 0.8, 40, 4, "EOD"), cut="2021-01-01",
                         desc="QQQ Alpaca SIP 1h incl. extended hours 04:00-20:00 ET, 2016-01..2026-10; cost 2 bp round trip"),
     "qqq_60m_rth": dict(kind="intraday", mode="eq_rth", files={"QQQ": b1h / "QQQ.csv"}, cost=2.0, full=True, starts=(9, 11), nb=True,
                         base_case=("LOD", 0.8, 40, 9, "EOD"), cut="2021-01-01",
                         desc="QQQ Alpaca SIP 1h regular hours (bars starting 09:00-15:00 ET), 2016-01..2026-10; cost 2 bp"),
     "core_60m_rth": dict(kind="intraday", mode="eq_rth", files={s: b1h / f"{s}.csv" for s in core}, cost=5.0, full=False, starts=(9,), nrand=10,
                          base_case=("LOD", 0.8, 40, 9, "EOD"), cut="2021-01-01",
                          desc="61 desk core names, Alpaca SIP 1h regular hours, 2016-01..2026-10 (shorter for later listings); pooled; cost 5 bp"),
     "qqq_1d": dict(kind="daily", files={"QQQ": y / "yahoo_QQQ_1d.csv"}, cost=2.0, nb=True, base_case=(20, "next_open", "hold5"), cut="2018-01-01",
                    desc="QQQ Yahoo daily 1999-03..2026-10 (adjusted); cost 2 bp"),
     "ndx_1d": dict(kind="daily", files={"NDX": y / "yahoo_NDX_1d.csv"}, cost=2.0, nb=True, base_case=(20, "next_open", "hold5"), cut="2018-01-01",
                    desc="^NDX Yahoo daily 1985-10..2026-10; cost 2 bp"),
     "nq_1d": dict(kind="daily", files={"NQ=F": y / "yahoo_NQF_1d.csv"}, cost=1.0, nb=True, base_case=(20, "next_open", "hold5"), cut="2018-01-01",
                   drop_after="2026-10-24", desc="NQ=F Yahoo daily 2000-09..2026-10 (continuous, roll gaps unadjusted); cost 1 bp"),
     "core_1d": dict(kind="daily", files={s: b1d / f"{s}.csv" for s in core}, cost=5.0, nrand=10, base_case=(20, "next_open", "hold5"), cut="2021-01-01",
                     desc="61 desk core names Alpaca daily 2016-01..2026-10, pooled; cost 5 bp"),
    }
    return S

if __name__ == "__main__":
    key = sys.argv[1]; outdir = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "results")
    root = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT
    run_series(key, SERIES(root)[key], outdir)
