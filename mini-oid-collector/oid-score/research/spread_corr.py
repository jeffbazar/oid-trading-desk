"""Research only (no trading). Daily credit-spread + rolling category beta/correlation series.

Writes ~/oid-data/research/spread-corr/:
  spread_corr_daily.csv  one row per session (backfilled ~2y), wide columns (see COLUMNS in latest.json)
  latest.json            last row, nested by category/benchmark, plus sources/status
  fred/<id>.csv          cached FRED history (the job tolerates FRED being down)
Data: Alpaca SIP daily bars (adjustment=all) via optflow's REST helper (keys never printed);
FRED ICE BofA OAS CSV (no key). Categories reused from the read-through study (catbeta-20261021.json).
Run: ~/oid-quote/venv/bin/python ~/oid-score/research/spread_corr.py   (launchd com.oid.desk.spread-corr, 13:30 PT Mon-Fri)
"""
import csv, json, math, statistics as st, subprocess, sys, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
H = Path.home(); sys.path.insert(0, str(H / "oid-optflow"))
import optflow as OF
PT = ZoneInfo("America/Los_Angeles")
OUT = H / "oid-data/research/spread-corr"; (OUT / "fred").mkdir(parents=True, exist_ok=True)
START_FETCH, START_OUT = "2023-06-01", "2024-10-01"
WINS = (20, 60, 120); BENCH = ["QQQ", "SMH", "META", "MSFT", "GOOGL", "AMZN", "ORCL", "LRCX"]
HYPER = ["META", "MSFT", "GOOGL", "AMZN", "ORCL"]  # also get QQQ-removed (residual) beta/corr: xbeta/xcorr
# ---- categories: reuse the read-through/catbeta membership; heavy-debt = desk list (catbeta's SEC split + CORZ)
try:
    CAT = json.loads((H / "oid-data/patterns/catbeta-20261021.json").read_text())["categories"]; CAT_SRC = "catbeta-20261021.json"
except Exception:
    CAT = {"chip_equip": ["LRCX", "AMAT", "KLAC", "ASML"], "memory": ["MU", "SKHY", "DRAM", "SNDK"],
           "gpu_logic": ["NVDA", "AMD", "AVGO", "MRVL", "INTC", "ARM"], "neocloud": ["NBIS", "CRWV", "IREN", "WULF", "CIFR", "APLD", "CORZ"],
           "neocloud_heavy_debt": ["CRWV", "WULF", "CIFR", "APLD"], "neocloud_low_debt": ["NBIS", "IREN"]}; CAT_SRC = "fallback"
CAT["neocloud_heavy_debt"] = sorted(set(CAT["neocloud_heavy_debt"]) | {"CORZ"})
SYMS = sorted({s for v in CAT.values() for s in v} | set(BENCH) | {"HYG", "LQD", "IEF", "CRWV", "ORCL"})

def get(path, p):
    for k in range(5):
        try: return OF._get(path, p)
        except Exception: time.sleep(2 + 3 * k)
    raise RuntimeError("alpaca fetch failed " + path)
def daily():
    out = {}
    for i in range(0, len(SYMS), 25):
        tok = None
        while True:
            p = {"symbols": ",".join(SYMS[i:i + 25]), "timeframe": "1Day", "start": START_FETCH + "T00:00:00Z", "limit": 10000, "feed": "sip", "adjustment": "all"}
            if tok: p["page_token"] = tok
            d = get("/v2/stocks/bars", p)
            for s, bs in (d.get("bars") or {}).items():
                for b in bs: out.setdefault(s, {})[b["t"][:10]] = b["c"]
            tok = d.get("next_page_token")
            if not tok: break
    return out

def fred(sid, tape):
    """FRED CSV -> {date: value}. live -> cache -> cache + market-tape latest level -> missing."""
    cache = OUT / "fred" / f"{sid}.csv"; status = "missing"
    try:
        r = subprocess.run(["curl", "-sS", "--http1.1", "-m", "30", "-A", "OID-Research/1.0 (+research; paper-only)",
                            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"], capture_output=True, text=True, timeout=45)
        t = r.stdout
        if r.returncode == 0 and t.split(",", 1)[0].strip().lower() in ("observation_date", "date") and t.count("\n") > 100:
            cache.write_text(t); status = "live"
    except Exception: pass
    v = {}
    if cache.exists():
        for row in csv.reader(cache.read_text().splitlines()[1:]):
            try: v[row[0]] = float(row[1])
            except (ValueError, IndexError): pass
        if status != "live": status = "cache"
    try:  # desk market tape (refresh_market_tape.py) keeps the latest print even when this job can't reach FRED
        pl = json.loads((H / "oid-desk/desk/market-data/latest" / tape).read_text())["payload"]
        if pl.get("as_of_date") and pl.get("level") is not None and pl["as_of_date"] not in v:
            v[pl["as_of_date"]] = float(pl["level"]); status += "+tape"
            hdr = "" if cache.exists() else "observation_date,%s\n" % sid  # keep tape prints so history builds while FRED is down
            with open(cache, "a") as f: f.write(hdr + f"{pl['as_of_date']},{pl['level']}\n")
    except Exception: pass
    return v, status

def stats(x, y):
    n = len(x)
    if n < 10: return None, None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x); syy = sum((b - my) ** 2 for b in y); sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    if sxx <= 0 or syy <= 0: return None, None
    return sxy / sxx, sxy / math.sqrt(sxx * syy)
def pct_rank_thr(hist, q):
    h = sorted(hist); return h[min(len(h) - 1, int(q * len(h)))]

def main():
    t0 = time.time(); now = datetime.now(PT)
    C = daily()
    days = sorted(C["QQQ"])
    if now.weekday() < 5 and now.strftime("%H%M") < "1315" and days and days[-1] == now.strftime("%Y-%m-%d"): days = days[:-1]  # partial bar
    def r(s, i):
        a, b = C.get(s, {}).get(days[i - 1]), C.get(s, {}).get(days[i])
        if not a or not b: return None
        x = b / a - 1; return None if abs(x) > 0.6 else x
    R = {s: [None] + [r(s, i) for i in range(1, len(days))] for s in SYMS}
    def basket(names, ex):
        out = [None]
        for i in range(1, len(days)):
            v = [R[s][i] for s in names if s != ex and R[s][i] is not None]; out.append(sum(v) / len(v) if v else None)
        return out
    hy, hy_st = fred("BAMLH0A0HYM2", "fred-hy-oas.json"); ig, ig_st = fred("BAMLC0A0CM", "fred-ig-oas.json")
    def ffill(v, d):
        k = [x for x in v if x <= d]; return (v[max(k)], max(k)) if k else (None, None)
    ratio = lambda a, b, i: (C["HYG"].get(days[i]) / C[b].get(days[i])) if C.get("HYG", {}).get(days[i]) and C.get(b, {}).get(days[i]) else None
    HI = [ratio("HYG", "IEF", i) for i in range(len(days))]; HL = [ratio("HYG", "LQD", i) for i in range(len(days))]
    chg = lambda S, i: (S[i] / S[i - 20] - 1) * 100 if i >= 20 and S[i] and S[i - 20] else None
    CH = [chg(HI, i) for i in range(len(days))]
    def xs20(s, i):
        a, b, qa, qb = C.get(s, {}).get(days[i - 20]) if i >= 20 else None, C.get(s, {}).get(days[i]), C["QQQ"].get(days[i - 20]) if i >= 20 else None, C["QQQ"].get(days[i])
        return round(((b / a) - (qb / qa)) * 100, 2) if a and b and qa and qb else None
    BK = {(c, b): basket(names, b) for c, names in CAT.items() for b in BENCH}
    cols = ["date", "hy_oas", "hy_oas_obs_date", "ig_oas", "hy_oas_chg20_bp", "hyg_ief", "hyg_lqd", "hyg_ief_chg20_pct", "hyg_lqd_chg20_pct",
            "regime", "regime_p33", "regime_p67", "regime_hy_check", "crwv_minus_qqq_20d_pct", "orcl_minus_qqq_20d_pct"]
    cols += [f"{c}__{b}__{k}{w}" for c in CAT for b in BENCH for w in WINS for k in ("beta", "corr")]
    cols += [f"{c}__{b}__{k}{w}" for c in CAT for b in HYPER for w in WINS for k in ("xbeta", "xcorr")]
    rows = []
    for i, d in enumerate(days):
        if d < START_OUT: continue
        h, hd = ffill(hy, d); g, _ = ffill(ig, d)
        h20 = None
        if h is not None and i >= 20:
            h0, _ = ffill(hy, days[i - 20]); h20 = round((h - h0) * 100, 1) if h0 is not None else None
        hist = [x for x in CH[max(0, i - 252):i] if x is not None]; reg, p33, p67 = None, None, None
        if CH[i] is not None and len(hist) >= 60:
            p33, p67 = pct_rank_thr(hist, 1 / 3), pct_rank_thr(hist, 2 / 3)
            reg = "widening" if CH[i] <= p33 else "narrowing" if CH[i] >= p67 else "flat"  # HYG/IEF falling = spreads widening
        chk = "na"
        if reg and h20 is not None:
            hs = "widening" if h20 >= 15 else "narrowing" if h20 <= -15 else "flat"
            chk = "agree" if hs == reg else ("disagree" if {hs, reg} == {"widening", "narrowing"} else "partial")
        row = {"date": d, "hy_oas": h, "hy_oas_obs_date": hd, "ig_oas": g, "hy_oas_chg20_bp": h20,
               "hyg_ief": round(HI[i], 5) if HI[i] else None, "hyg_lqd": round(HL[i], 5) if HL[i] else None,
               "hyg_ief_chg20_pct": round(CH[i], 3) if CH[i] is not None else None, "hyg_lqd_chg20_pct": round(chg(HL, i), 3) if chg(HL, i) is not None else None,
               "regime": reg, "regime_p33": round(p33, 3) if p33 is not None else None, "regime_p67": round(p67, 3) if p67 is not None else None,
               "regime_hy_check": chk, "crwv_minus_qqq_20d_pct": xs20("CRWV", i), "orcl_minus_qqq_20d_pct": xs20("ORCL", i)}
        for (c, b), y in BK.items():
            for w in WINS:
                pr = [(R[b][j], y[j]) for j in range(max(1, i - w + 1), i + 1) if R[b][j] is not None and y[j] is not None]
                be, co = stats([p[0] for p in pr], [p[1] for p in pr]) if len(pr) >= max(10, int(0.75 * w)) else (None, None)
                row[f"{c}__{b}__beta{w}"] = round(be, 3) if be is not None else None
                row[f"{c}__{b}__corr{w}"] = round(co, 3) if co is not None else None
                if b in HYPER:  # QQQ-removed: regress basket and benchmark on QQQ within the window, then beta/corr of the residuals
                    xb = xc = None
                    tr = [(R["QQQ"][j], R[b][j], y[j]) for j in range(max(1, i - w + 1), i + 1) if R["QQQ"][j] is not None and R[b][j] is not None and y[j] is not None]
                    if len(tr) >= max(10, int(0.75 * w)):
                        q = [t[0] for t in tr]
                        def resid(v):
                            bb, _ = stats(q, v)
                            if bb is None: return None
                            mq, mv = sum(q) / len(q), sum(v) / len(v)
                            return [vi - (mv + bb * (qi - mq)) for qi, vi in zip(q, v)]
                        ex, ey = resid([t[1] for t in tr]), resid([t[2] for t in tr])
                        if ex and ey: xb, xc = stats(ex, ey)
                    row[f"{c}__{b}__xbeta{w}"] = round(xb, 3) if xb is not None else None
                    row[f"{c}__{b}__xcorr{w}"] = round(xc, 3) if xc is not None else None
        rows.append(row)
    tmp = OUT / "spread_corr_daily.csv.tmp"
    with open(tmp, "w", newline="") as f:
        wr = csv.DictWriter(f, cols); wr.writeheader()
        for row in rows: wr.writerow({k: ("" if row.get(k) is None else row[k]) for k in cols})
    tmp.replace(OUT / "spread_corr_daily.csv")
    L = rows[-1]
    latest = {"schema": "oid-spread-corr/1", "built_pt": now.strftime("%Y-%m-%d %-I:%M %p PT"), "date": L["date"], "rows": len(rows), "first_date": rows[0]["date"],
              "research_only": True,
              "spreads": {k: L[k] for k in cols[1:15]},
              "fred_status": {"BAMLH0A0HYM2": hy_st, "BAMLC0A0CM": ig_st},
              "categories": CAT, "category_source": CAT_SRC + " (+CORZ in heavy-debt per desk list)", "benchmarks": BENCH, "windows": WINS,
              "rolling": {c: {b: {f"{k}{w}": L[f"{c}__{b}__{k}{w}"] for w in WINS for k in (("beta", "corr", "xbeta", "xcorr") if b in HYPER else ("beta", "corr"))} for b in BENCH} for c in CAT},
              "hyperscalers_qqq_removed": HYPER,
              "notes": ["Basket = equal-weight daily close-to-close return of members with data that day; the benchmark is excluded from its own basket (e.g. chip_equip vs LRCX is ex-LRCX).",
                        "regime: 20-session % change in HYG/IEF vs its trailing-252-session terciles (min 60 obs). Bottom tercile = widening, top = narrowing. HYG/IEF falls when spreads widen.",
                        "regime_hy_check: HY OAS 20-session change (>=+15bp widening, <=-15bp narrowing) vs regime: agree/partial/disagree/na. FRED is optional; OAS is forward-filled from its last observation (hy_oas_obs_date).",
                        "AI-debt proxy is equity, not credit: CRWV and ORCL 20-session return minus QQQ (no free CDS/bond feed).",
                        "Bars: Alpaca SIP daily, adjustment=all (HYG/LQD/IEF ratios are total-return-ish, not price-only). Rows need >=75% of the window with data; newer listings (CRWV, SNDK, etc.) start later.",
                        "xbeta/xcorr (QQQ removed, hyperscaler benchmarks only): within each window, regress the basket's and the benchmark's daily returns on QQQ (OLS), then take the OLS beta and correlation of basket residuals on benchmark residuals.",
                        "Before rolling numbers fill: 20d needs 15 obs, 60d 45, 120d 90."],
              "columns": cols, "csv": str(OUT / "spread_corr_daily.csv"), "elapsed_s": round(time.time() - t0, 1)}
    (OUT / "latest.json.tmp").write_text(json.dumps(latest, indent=1)); (OUT / "latest.json.tmp").replace(OUT / "latest.json")
    print(f"[{now:%Y-%m-%d %H:%M %Z}] spread-corr ok: {len(rows)} rows {rows[0]['date']}..{L['date']} regime={L['regime']} hygief20={L['hyg_ief_chg20_pct']} "
          f"hy={L['hy_oas']}({L['hy_oas_obs_date']}) fred={hy_st}/{ig_st} {time.time()-t0:.0f}s", flush=True)
if __name__ == "__main__": main()
