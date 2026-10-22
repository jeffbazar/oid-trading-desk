"""Research only: close-to-open overnight hold, core tickers, last 60 sessions. Shares + modelled 45-DTE calls + filters.
Inputs: onhold-bars / onhold-snap45 / earnings-core (data dir). Output: ~/oid-data/patterns/onhold-20261021.json"""
import json, math, statistics as st, sys, bisect
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
H = Path.home(); P = H / "oid-data/patterns"
ET = ZoneInfo("America/New_York")
bars = json.loads((P / "onhold-bars-20261021.json").read_text())
snap = json.loads((P / "onhold-snap45-20261021.json").read_text())["by_sym"]
earn = json.loads((P / "earnings-core-20261021.json").read_text())
N_SESS = 60
COST_SH = {"open": 4e-4, "645": 3e-4}   # shares round trip (assumption): 1 bp/side at 12:55, 3 bp at the 6:30 open, 2 bp at 6:45
SPR_MULT = {"open": 2.0, "645": 1.25}   # option exit spread vs the close snapshot spread (open quotes are wider; assumption)
R = 0.04
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def bs(S, K, T, v):
    if T <= 0: return max(S - K, 0)
    d1 = (math.log(S / K) + (R + v * v / 2) * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    return S * ncdf(d1) - K * math.exp(-R * T) * ncdf(d2)
def delta(S, K, T, v):
    return ncdf((math.log(S / K) + (R + v * v / 2) * T) / (v * math.sqrt(T)))
def k_for_delta(S, T, v, dt=0.35):
    lo, hi = S, S * 3
    for _ in range(60):
        m = (lo + hi) / 2
        if delta(S, m, T, v) > dt: lo = m
        else: hi = m
    return (lo + hi) / 2
# ---- per-ticker session table
def et(t): return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ET)
days = {}
for s, bs5 in bars["5m"].items():
    D = defaultdict(dict)
    for t, o, h, l, c, v in bs5:
        x = et(t); hm = x.hour * 100 + x.minute; d = x.strftime("%Y-%m-%d")
        if 930 <= hm <= 1550:
            r = D[d]; r["hi"] = max(r.get("hi", h), h); r["lo"] = min(r.get("lo", l), l)
            if hm == 1550: r["p1255"], r["t1255"] = c, x.timestamp() + 300
            if hm == 940: r["p645"], r["t645"] = c, x.timestamp() + 300
    days[s] = D
nights = defaultdict(list)  # s -> list of nights
sess_all = sorted({b[0][:10] for v in bars["1d"].values() for b in v})
sess = sess_all[-(N_SESS + 1):]
def ev_entries(s):
    out = set()
    for e in earn.get(s, []):
        d = e["date"]
        if e.get("time") == "postmarket": out.add(d)
        elif e.get("time") == "premarket":
            j = bisect.bisect_left(sess_all, d); out.add(sess_all[j - 1] if j > 0 else d)
        else:
            out.add(d); j = bisect.bisect_left(sess_all, d); out.add(sess_all[j - 1] if j > 0 else d)
    return out
for s, bd in bars["1d"].items():
    byd = {b[0][:10]: b for b in bd}
    E = ev_entries(s)
    for i in range(len(sess) - 1):
        d0, d1 = sess[i], sess[i + 1]
        if d0 not in byd or d1 not in byd: continue
        a, b = days[s].get(d0, {}), days[s].get(d1, {})
        entry = a.get("p1255") or byd[d0][4]; src = "12:55" if a.get("p1255") else "close"
        t_entry = a.get("t1255") or datetime.fromisoformat(d0 + "T16:00:00").replace(tzinfo=ET).timestamp()
        o1 = byd[d1][1]; t_open = datetime.fromisoformat(d1 + "T09:30:00").replace(tzinfo=ET).timestamp()
        p645 = b.get("p645"); t645 = b.get("t645")
        rng = (a.get("hi"), a.get("lo"))
        loc = (entry - rng[1]) / (rng[0] - rng[1]) if rng[0] and rng[1] and rng[0] > rng[1] else None
        nights[s].append({"d0": d0, "d1": d1, "entry": entry, "src": src, "t0": t_entry, "open": o1, "t_open": t_open, "p645": p645, "t645": t645,
                          "loc": loc, "event": d0 in E, "c0": byd[d0][4], "o0": byd[d0][1], "c1": byd[d1][4]})
# ---- context filters (score / C/P at ~12:55, only 10/19-10/21 archived)
score, cp = {}, {}
for f in sorted((H / "oid-data/archive/score_features").glob("date=*/part-score-*core-1.jsonl")):
    for ln in f.read_text().splitlines():
        try: x = json.loads(ln)
        except Exception: continue
        if x.get("profile") != "core" or x.get("score") is None: continue
        hm = et(datetime.utcfromtimestamp(x["t"]).isoformat() + "Z"); k = (x["symbol"], hm.strftime("%Y-%m-%d"))
        if hm.hour * 100 + hm.minute <= 1555: score[k] = (x["t"], x["score"]) if (k not in score or x["t"] > score[k][0]) else score[k]
import gzip
for f in sorted((H / "oid-optflow/data/cp-history").glob("2026-*.jsonl*")):
    with (gzip.open if f.suffix == ".gz" else open)(f, "rt") as fh:
        for ln in fh:
            try: x = json.loads(ln)
            except Exception: continue
            if x.get("hdr"): continue
            xt = datetime.fromtimestamp(x["t"], ET)
            if xt.hour * 100 + xt.minute > 1555: continue
            for s, u in (x.get("u") or {}).items():
                v = (u.get("60") or [None])[0]
                if v is None: v = (u.get("15") or [None])[0]
                if v is not None: cp[(s, xt.strftime("%Y-%m-%d"))] = v
# ---- returns
def opt_ret(n, s, kind, exit_):
    sn = (snap.get(s) or {}).get(kind)
    if not sn or not sn.get("iv"): return None
    v = sn["iv"]; S0 = n["entry"]
    S1, t1 = (n["open"], n["t_open"]) if exit_ == "open" else (n["p645"], n["t645"])
    if S1 is None: return None
    T0 = 45 / 365; T1 = T0 - (t1 - n["t0"]) / (365 * 86400)
    K = S0 if kind == "atm" else k_for_delta(S0, T0, v)
    m0, m1 = bs(S0, K, T0, v), bs(S1, K, T1, v)
    sp = sn["spr_pct"]
    ask0 = m0 * (1 + sp / 2); bid1 = m1 * (1 - sp * SPR_MULT[exit_] / 2)
    return bid1 / ask0 - 1
def sh_ret(n, exit_, gross=False):
    S1 = n["open"] if exit_ == "open" else n["p645"]
    if S1 is None: return None
    return S1 / n["entry"] - 1 - (0 if gross else COST_SH[exit_])
def stats(rs, compound=True):
    rs = [r for r in rs if r is not None]
    if len(rs) < 2: return {"n": len(rs)}
    eq, peak, dd = 1.0, 1.0, 0.0
    cum = 0.0; pk2 = 0.0; dd2 = 0.0
    for r in rs:
        eq *= (1 + r); peak = max(peak, eq); dd = min(dd, eq / peak - 1)
        cum += r; pk2 = max(pk2, cum); dd2 = min(dd2, cum - pk2)
    sd = st.pstdev(rs); tot_sum = sum(rs)
    top5 = sum(sorted(rs, reverse=True)[:5])
    return {"n": len(rs), "total": round(eq - 1, 4) if compound else round(tot_sum, 4), "sum": round(tot_sum, 4), "mean": round(st.mean(rs), 5),
            "win": round(sum(r > 0 for r in rs) / len(rs), 3), "sharpe": round(st.mean(rs) / sd * math.sqrt(252), 2) if sd else None,
            "maxdd": round(dd if compound else dd2, 4), "worst": round(min(rs), 4), "best": round(max(rs), 4),
            "top5_share": round(top5 / tot_sum, 2) if tot_sum > 0 else None}
VAR = {"sh_open": lambda n, s: sh_ret(n, "open"), "sh_645": lambda n, s: sh_ret(n, "645"), "sh_open_gross": lambda n, s: sh_ret(n, "open", True),
       "c_atm_open": lambda n, s: opt_ret(n, s, "atm", "open"), "c_atm_645": lambda n, s: opt_ret(n, s, "atm", "645"),
       "c_d35_open": lambda n, s: opt_ret(n, s, "d35", "open"), "c_d35_645": lambda n, s: opt_ret(n, s, "d35", "645")}
FILT = {"all": lambda n, s: True, "ex_earnings": lambda n, s: not n["event"], "earnings_only": lambda n, s: n["event"],
        "close_top25": lambda n, s: n["loc"] is not None and n["loc"] >= 0.75, "close_not_top25": lambda n, s: n["loc"] is not None and n["loc"] < 0.75,
        "score_bull": lambda n, s: (score.get((s, n["d0"])) or (0, 0))[1] > 0, "cp_bull": lambda n, s: (cp.get((s, n["d0"])) or 0) > 1.10,
        "ctx_covered": lambda n, s: (s, n["d0"]) in score or (s, n["d0"]) in cp}
out = {"sessions": [sess[0], sess[-1]], "n_nights_per_ticker": len(sess) - 1, "assumptions": {"cost_shares_rt": COST_SH, "opt_exit_spread_mult": SPR_MULT,
       "opt_model": "Black-Scholes repricing, r=4%, IV held constant at each ticker's 10/21 45-DTE snapshot IV (vega = 0), theta = actual clock time held, entry at modelled ask / exit at modelled bid using the snapshot's real bid-ask % of mid"},
       "ticker": {}, "group": {}, "basket": {}, "benchmarks": {}}
for s, ns in nights.items():
    out["ticker"][s] = {v: stats([f(n, s) for n in ns], compound=v.startswith("sh")) for v, f in VAR.items()}
    out["ticker"][s]["sh_open_exE"] = stats([sh_ret(n, "open") for n in ns if not n["event"]])
    out["ticker"][s]["c_atm_open_exE"] = stats([opt_ret(n, s, "atm", "open") for n in ns if not n["event"]], compound=False)
    bh = ns[-1]["c1"] / ns[0]["c0"] - 1
    intr = math.prod(n["c1"] / n["open"] for n in ns) - 1
    out["benchmarks"][s] = {"buy_hold": round(bh, 4), "intraday_open_close": round(intr, 4), "intraday_n": len(ns)}
for fk, ff in FILT.items():
    out["group"][fk] = {}
    for v, f in VAR.items():
        rs = [f(n, s) for s, ns in nights.items() for n in ns if ff(n, s)]
        out["group"][fk][v] = stats(rs, compound=False)  # pooled ticker-nights: sum-based
    # equal-weight basket: per night average across tickers passing the filter
    for v, f in VAR.items():
        by = defaultdict(list)
        for s, ns in nights.items():
            for n in ns:
                if ff(n, s):
                    r = f(n, s)
                    if r is not None: by[n["d0"]].append(r)
        rs = [st.mean(by[d]) for d in sorted(by)]
        out["basket"].setdefault(fk, {})[v] = dict(stats(rs, compound=v.startswith("sh")), avg_names=round(st.mean(len(by[d]) for d in by), 1) if by else 0)
# basket benchmarks
bh = st.mean(b["buy_hold"] for b in out["benchmarks"].values()); intr = st.mean(b["intraday_open_close"] for b in out["benchmarks"].values())
by_i = defaultdict(list); by_c = defaultdict(list)
for s, ns in nights.items():
    for n in ns:
        by_i[n["d1"]].append(n["c1"] / n["open"] - 1); by_c[n["d1"]].append(n["c1"] / n["c0"] - 1)
out["basket_bench"] = {"buy_hold_mean_of_tickers": round(bh, 4), "intraday_mean_of_tickers": round(intr, 4),
                       "ew_daily_rebal_close_close": stats([st.mean(by_c[d]) for d in sorted(by_c)]),
                       "ew_intraday_open_close": stats([st.mean(by_i[d]) for d in sorted(by_i)])}
out["ctx_coverage"] = {"score_nights": sum(1 for s, ns in nights.items() for n in ns if (s, n["d0"]) in score),
                       "cp_nights": sum(1 for s, ns in nights.items() for n in ns if (s, n["d0"]) in cp),
                       "entry_src_close": sum(1 for ns in nights.values() for n in ns if n["src"] == "close"),
                       "event_nights": sum(1 for ns in nights.values() for n in ns if n["event"])}
(P / "onhold-20261021.json").write_text(json.dumps(out, indent=1))
print(json.dumps({"sessions": out["sessions"], "cov": out["ctx_coverage"]}))
# ---- liquid subset + mid-to-mid (no spread) variant
LIQ = sorted(s for s, v in snap.items() if v and v.get("atm") and v["atm"]["spr_pct"] <= 0.03)
def opt_mid(n, s, kind, exit_):
    sn = (snap.get(s) or {}).get(kind)
    if not sn or not sn.get("iv"): return None
    v = sn["iv"]; S0 = n["entry"]
    S1, t1 = (n["open"], n["t_open"]) if exit_ == "open" else (n["p645"], n["t645"])
    if S1 is None: return None
    T0 = 45 / 365; T1 = T0 - (t1 - n["t0"]) / (365 * 86400)
    K = S0 if kind == "atm" else k_for_delta(S0, T0, v)
    return bs(S1, K, T1, v) / bs(S0, K, T0, v) - 1
V2 = dict(VAR, c_atm_open_mid=lambda n, s: opt_mid(n, s, "atm", "open"), c_atm_645_mid=lambda n, s: opt_mid(n, s, "atm", "645"),
          c_d35_open_mid=lambda n, s: opt_mid(n, s, "d35", "open"))
out["liquid"] = {"tickers": LIQ, "rule": "ATM 45-DTE call spread <= 3% of mid on 10/21", "basket": {}}
for fk in ("all", "ex_earnings", "close_top25"):
    ff = FILT[fk]
    for v, f in V2.items():
        by = defaultdict(list)
        for s in LIQ:
            for n in nights.get(s, []):
                if ff(n, s):
                    r = f(n, s)
                    if r is not None: by[n["d0"]].append(r)
        rs = [st.mean(by[d]) for d in sorted(by)]
        out["liquid"]["basket"].setdefault(fk, {})[v] = stats(rs, compound=v.startswith("sh"))
for v in ("c_atm_open_mid", "c_atm_645_mid", "c_d35_open_mid"):
    by = defaultdict(list)
    for s, ns in nights.items():
        for n in ns:
            r = V2[v](n, s)
            if r is not None: by[n["d0"]].append(r)
    out["basket"]["all"][v] = stats([st.mean(by[d]) for d in sorted(by)], compound=False)
lb = defaultdict(list); li = defaultdict(list)
for s in LIQ:
    for n in nights.get(s, []): lb[n["d1"]].append(n["c1"] / n["c0"] - 1); li[n["d1"]].append(n["c1"] / n["open"] - 1)
out["liquid"]["bench"] = {"ew_close_close": stats([st.mean(lb[d]) for d in sorted(lb)]), "ew_intraday": stats([st.mean(li[d]) for d in sorted(li)])}
(P / "onhold-20261021.json").write_text(json.dumps(out, indent=1))
print("liquid", len(LIQ), LIQ)
