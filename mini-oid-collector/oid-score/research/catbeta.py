"""Research only: category betas + tonight's attribution. Output ~/oid-data/patterns/catbeta-20261021.json"""
import json, math, statistics as st
from pathlib import Path
H = Path.home(); P = H / "oid-data/patterns"
X = json.loads((P / "readthrough-data-20261021.json").read_text())
RT = json.loads((P / "readthrough-20261021.json").read_text())
BS = json.loads((P / "neo-bs-20261021.json").read_text())
D = {s: {b[0]: b for b in bs} for s, bs in X["daily"].items()}
days = sorted(D["QQQ"]); S = X["snap"]
CAT = {"chip_equip": ["LRCX", "AMAT", "KLAC", "ASML"], "memory": ["MU", "SKHY", "DRAM", "SNDK"],
       "gpu_logic": ["NVDA", "AMD", "AVGO", "MRVL", "INTC", "ARM"], "neocloud": ["NBIS", "CRWV", "IREN", "WULF", "CIFR", "APLD", "CORZ"]}
WATCH = ["WDC", "STX"]
# ---- debt tag: net debt / EV with EV = mkt cap (10/21 close x shares) + net debt
debt = {}
for s, x in BS.items():
    px = (S.get(s) or {}).get("close") or D[s][days[-1]][4]
    mcap = px * float(x["common_stock_shares_outstanding"]); tot = float(x["short_long_term_debt_total"]); cash = float(x["cash_and_short_term_investments"] or 0)
    nd = tot - cash
    debt[s] = {"fiscal": x["fiscal_date_ending"], "debt_total_b": round(tot / 1e9, 2), "cash_b": round(cash / 1e9, 2), "mcap_b": round(mcap / 1e9, 1),
               "debt_to_mcap": round(tot / mcap, 3), "net_debt_to_ev": round(nd / (mcap + nd), 3)}
heavy = sorted([s for s in debt if debt[s]["net_debt_to_ev"] >= 0.25], key=lambda s: -debt[s]["net_debt_to_ev"])
CAT["neocloud_heavy_debt"] = heavy
def ret(s, d0, f0, d1, f1):
    a, b = D.get(s, {}).get(d0), D.get(s, {}).get(d1)
    x = (b[f1] / a[f0] - 1) if a and b else None
    return None if x is None or abs(x) > 0.6 else x  # data-artifact guard
O, C = 1, 4
def series(names, kind, win):
    """per-day EW returns over the last `win` sessions. kind cc or co"""
    out = {}
    ds = days[-(win + 1):]
    for i in range(1, len(ds)):
        rs = [ret(s, ds[i - 1], C, ds[i], C if kind == "cc" else O) for s in names]
        rs = [r for r in rs if r is not None]
        if rs: out[ds[i]] = st.mean(rs)
    return out
def ols(x, y):
    n = len(x)
    if n < 3: return None
    mx, my = st.mean(x), st.mean(y); sxx = sum((a - mx) ** 2 for a in x); syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0: return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    return {"beta": round(b, 2), "r2": round((b * b * sxx / syy), 3), "n": n, "alpha_bp": round((my - b * mx) * 1e4, 1)}
def beta(names, bench, kind, win):
    y = series(names, kind, win); x = series([bench], kind, win)
    k = sorted(set(x) & set(y)); return ols([x[d] for d in k], [y[d] for d in k])
EV = [e for e in RT["events"]]
EQ = {"LRCX", "AMAT", "KLAC", "ASML"}; CAPEX = {"META", "MSFT", "GOOG", "AMZN"}
def ev_beta(names, group, w):
    x, y = [], []
    for e in EV:
        if e["bw"] not in group: continue
        nm = [s for s in names if s != e["bw"] and not (e["bw"] == "GOOG" and s == "GOOGL")]
        rs = [ret(s, e["d0"], C, e["d1"], O if w == "co" else C) for s in nm]; rs = [r for r in rs if r is not None]
        if not rs: continue
        x.append(e[w]); y.append(st.mean(rs))
    return ols(x, y)
def block(names):
    return {"qqq_60d": beta(names, "QQQ", "cc", 60), "qqq_1y": beta(names, "QQQ", "cc", 252), "smh_60d": beta(names, "SMH", "cc", 60),
            "smh_1y": beta(names, "SMH", "cc", 252), "qqq_overnight_1y": beta(names, "QQQ", "co", 252),
            "equip_prints_co": ev_beta(names, EQ, "co"), "equip_prints_cc": ev_beta(names, EQ, "cc"),
            "capex_prints_co": ev_beta(names, CAPEX, "co"), "capex_prints_cc": ev_beta(names, CAPEX, "cc")}
out = {"categories": CAT, "watch_only": WATCH, "debt": debt, "heavy_rule": "net debt (debt incl. leases minus cash) / EV >= 25% (UW balance sheet, latest quarter; mkt cap at 10/21 close)",
       "basket": {}, "names": {}}
for c, names in CAT.items():
    out["basket"][c] = block(names)
for s in sorted({x for v in CAT.values() for x in v} | set(WATCH)):
    out["names"][s] = block([s])
# ---- tonight attribution
def ah(s):
    v = S.get(s) or {}
    if not v.get("last") or not v.get("close") or (v.get("last_t") or "") < "2026-10-21T20:00": return None
    x = v["last"] / v["close"] - 1
    return None if abs(x) < 1e-9 else x  # last print == close: no real extended-hours trade
q, l, m = ah("QQQ"), ah("LRCX"), ah("META")
att = {"qqq_ah": q, "lrcx_ah": l, "meta_ah": m, "smh_ah": ah("SMH"), "rows": {}}
for c, names in list(CAT.items()) + [("watch_WDC_STX", WATCH)]:
    nm = [s for s in names if s not in ("LRCX", "META")]
    a = [ah(s) for s in nm]; a = [x for x in a if x is not None]
    actual = st.mean(a) if a else None
    b = block(nm)
    imp = {"qqq": (b["qqq_overnight_1y"] or {}).get("beta"), "lrcx": (b["equip_prints_co"] or {}).get("beta"), "meta": (b["capex_prints_co"] or {}).get("beta")}
    impl = {"qqq": imp["qqq"] * q if imp["qqq"] is not None and q is not None else None,
            "lrcx": imp["lrcx"] * l if imp["lrcx"] is not None and l is not None else None,
            "meta": imp["meta"] * m if imp["meta"] is not None and m is not None else None}
    res = {k: (actual - v) if (v is not None and actual is not None) else None for k, v in impl.items()}
    best = min((k for k in res if res[k] is not None), key=lambda k: abs(res[k]), default=None)
    att["rows"][c] = {"names_used": nm, "n_with_ah": len(a), "actual_ah": actual, "betas": imp, "implied": impl, "residual": res, "best": best,
                      "per_name": {s: ah(s) for s in nm}}
out["tonight"] = att
(P / "catbeta-20261021.json").write_text(json.dumps(out, indent=1))
print(json.dumps(debt, indent=0)); print("heavy", heavy)
f = lambda b: "—" if not b else f"{b['beta']} (R2 {b['r2']}, n {b['n']})"
for c in CAT:
    b = out["basket"][c]; print(c, " | ".join(f"{k}: {f(v)}" for k, v in b.items()))
print("TONIGHT q/l/m/smh", q, l, m, att["smh_ah"])
for c, r in att["rows"].items():
    print(c, "actual", r["actual_ah"], "n", r["n_with_ah"], "betas", r["betas"], "implied", {k: (round(v, 4) if v is not None else None) for k, v in r["implied"].items()},
          "resid", {k: (round(v, 4) if v is not None else None) for k, v in r["residual"].items()}, "best", r["best"])
    print("   ", {k: (round(v, 4) if v is not None else None) for k, v in r["per_name"].items()})
