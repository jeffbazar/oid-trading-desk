"""Research only (no trading). Daily de-grossing gauge (Jeffrey 2026-10-22), built to Research Bot's spec
(studies/degrossing-gauge-20261022/SPEC.md; copy in ~/oid-score/research/degross-study/).

What it says: a DE-GROSSING / EXHAUSTION FLAG / CLEAR badge with severity. Detection is backtested (32 of 33 unwinds since 2017
caught; the 1-day DeepSeek shock was missed). The exhaustion flag ("selling may be ending") is UNTESTED out of sample. It is context, not timing.

Writes ~/oid-data/degross/:
  degrossing_gauge.csv   spec columns, one row per session, append-only (spreads as decimals; members space-separated)
  degross-YYYYMMDD.json  per session: the spec row + supporting readings (the last BACKFILL_FILES sessions are rewritten each run)
  latest.json            newest session + `history` (HIST_ROWS sessions) + rules/thresholds/caveat, for /credit and the desk bots
  cache/                 VIX/VIX3M CSVs, UW short-volume / skew / SOXL responses (the job runs from cache if a feed is down)
Feeds (all already on the mini; nothing new subscribed or paid): Alpaca SIP daily bars (adjustment=all) via optflow's REST helper;
Unusual Whales (short volume, 25-delta risk reversal, SOXL in/outflow); CBOE public index CSV + delayed quote, FRED fallback; the UW
borrow archive (read only). The spec used Yahoo adjusted closes; the mini uses Alpaca SIP adjusted closes, so the numbers can differ by a
few bp. FlashAlpha and X are not called.
Run: ~/oid-quote/venv/bin/python ~/oid-score/research/degross.py   (launchd com.oid.desk.degross, Mon-Fri 13:50 and 17:45 PT)
"""
import csv, json, os, subprocess, sys, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
H = Path.home(); sys.path.insert(0, str(H / "oid-optflow"))
import optflow as OF
PT = ZoneInfo("America/Los_Angeles")
OUT = H / "oid-data/degross"; CACHE = OUT / "cache"; CACHE.mkdir(parents=True, exist_ok=True)
VERSION = "degross/2.0 (2026-10-22, Research Bot spec)"
START_FETCH = "2024-06-01"; START_OUT = "2025-07-01"; BACKFILL_FILES = 30; HIST_ROWS = 130

# ---- spec universe: Research Bot's 74 tickers (tech, semis, AI infra; PSTG/QRVO dropped for missing history) ----
UNIVERSE = ("NVDA AMD INTC AVGO QCOM TXN MU AMAT LRCX KLAC ASML TSM ADI MRVL NXPI MCHP ON MPWR TER SWKS ENTG MKSI COHR LITE CIEN ANET CSCO GLW KEYS "
            "AAPL MSFT GOOGL AMZN META NFLX ORCL CRM ADBE INTU NOW IBM DELL HPE HPQ SMCI WDC STX NTAP CRDO VRT ARM PLTR SNOW CRWV NBIS IREN APLD WULF "
            "CIFR SNPS CDNS PANW CRWD FTNT ZS DDOG NET MDB TEAM SHOP TSLA AMKR SNDK ALAB").split()
# ---- desk basket (Jeffrey's hand-picked crowded AI names vs laggards+defensives): supporting reading only ----
DESK_CROWDED = ["NVDA", "AVGO", "MU", "CRWV", "IREN", "NBIS", "COHR", "LITE", "CRDO", "MRVL", "AMD", "LRCX"]
DESK_UNCROWDED = ["INTU", "NFLX", "MSFT", "XLP", "XLU", "XLV"]
CROWDED = DESK_CROWDED  # used by the borrow-archive helper
ETFS = ["SPY", "QQQ", "SMH", "GVIP", "MTUM", "USMV", "SOXL", "XLP", "XLU", "XLV"]
SYMS = sorted(set(UNIVERSE + DESK_CROWDED + DESK_UNCROWDED + ETFS))
# ---- fixed thresholds (pre-2024 2.5th percentiles of the 10-day sums; spec says keep fixed, don't refit) ----
TH = {"mtum_spy_10d": -0.0407, "gvip_spy_10d": -0.0327, "mtum_usmv_10d": -0.0468, "cvu_10d": -0.1195}  # cvu line is display only, not a trigger
RECORD_MTUM_USMV_10D = -0.1370  # record low, 2026-07
ARM_WINDOW = 20; EPISODE_GAP = 10; RELAPSE_WINDOW = 20
BASKET_NOTE = ("Spec cvu basket: rebalanced at each month-end close on 12-1 momentum (P[t-21]/P[t-252]-1) over universe names with 252 days of history; "
               "crowded = top decile (min 5 names), uncrowded = bottom tercile, equal weight. 'Crowded' here means price momentum, not ownership. "
               "Desk basket (supporting): crowded " + " ".join(DESK_CROWDED) + " vs uncrowded " + " ".join(DESK_UNCROWDED) + " (INTU/NFLX/MSFT laggards + staples/utilities/health-care ETFs).")
RULES_TEXT = [
    "trigger (a day): mtum_usmv_10d <= -4.68% OR mtum_spy_10d <= -4.07% OR gvip_spy_10d <= -3.27% (10-day sums of daily spreads; fixed pre-2024 2.5th percentiles).",
    "armed: a trigger on any of the last 20 sessions. A new episode starts on a trigger day more than 10 sessions after the previous trigger day.",
    "exhaustion flag (UNTESTED, rule GVIP_SPY A2): after the episode's first trigger, the last 2 SPY-down days both had GVIP >= SPY. Fires once per episode. relapse = a trigger within 20 sessions after the flag.",
    "badge: DE-GROSSING = armed and no standing flag (a relapse re-arms it); EXHAUSTION FLAG = flag fired and no trigger since; CLEAR = not armed. severity = mtum_usmv_10d / record low (-13.70%, 2026-07).",
]
CAVEAT = ("Exhaustion flag not validated out-of-sample. In 2024–26 (n=8) QQQ +10d was +0.1pp vs normal and the crowded basket was −4.1pp. "
          "In 38–44% of past flags the selling relapsed within 20 days. Use as context, not timing.")
CSV_COLS = ["date", "spy_ret", "qqq_ret", "smh_ret", "gvip_spy", "mtum_spy", "mtum_usmv", "cvu", "gvip_spy_10d", "mtum_spy_10d", "mtum_usmv_10d", "cvu_10d",
            "gvip_spy_ds5", "mtum_spy_ds5", "mtum_usmv_ds5", "cvu_ds5", "spy_down", "trigger", "armed", "episode_id", "days_since_first_trigger",
            "downdays_gvip_nonneg_streak", "exhaust_flag", "relapse", "severity", "crowded_members", "uncrowded_members"]

def get_alpaca(path, p):
    for k in range(5):
        try: return OF._get(path, p)
        except Exception: time.sleep(2 + 3 * k)
    raise RuntimeError("alpaca fetch failed " + path)
def bars():
    out = {}
    for i in range(0, len(SYMS), 25):
        tok = None
        while True:
            p = {"symbols": ",".join(SYMS[i:i + 25]), "timeframe": "1Day", "start": START_FETCH + "T00:00:00Z", "limit": 10000, "feed": "sip", "adjustment": "all"}
            if tok: p["page_token"] = tok
            d = get_alpaca("/v2/stocks/bars", p)
            for s, bs in (d.get("bars") or {}).items():
                for b in bs: out.setdefault(s, {})[b["t"][:10]] = {"c": b["c"], "l": b["l"], "v": b["v"]}
            tok = d.get("next_page_token")
            if not tok: break
    return out

def secret(name):
    v = os.environ.get(name)
    if v: return v.strip()
    try: return (H / "oid-quote/secrets" / name).read_text().strip() or None
    except OSError: return None
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def uw(path, cache_name):
    """UW GET -> json; on any failure fall back to the cached copy. Returns (json, status)."""
    cp = CACHE / f"uw_{cache_name}.json"; key = secret("UW_API_KEY")
    if key:
        for k in range(3):
            try:
                req = urllib.request.Request("https://api.unusualwhales.com/api" + path,
                                             headers={"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": "oid-degross/1"})
                with _OP.open(req, timeout=25) as r: j = json.load(r)
                cp.write_text(json.dumps(j)); return j, "live"
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 404): break
                time.sleep(2 + 2 * k)
            except Exception: time.sleep(2 + 2 * k)
    if cp.exists(): return json.loads(cp.read_text()), "cache"
    return None, "missing"

def curl(url):
    r = subprocess.run(["curl", "-sSL", "--http1.1", "-m", "30", "-A", "Mozilla/5.0 (OID-Research; paper-only)", url], capture_output=True, text=True, timeout=45)
    return r.stdout if r.returncode == 0 else ""
def index_hist(sym, fred_id):
    """{date: close} for a CBOE index: CBOE daily CSV -> cache -> FRED; plus today's close from the CBOE delayed quote after 13:15 PT."""
    cp = CACHE / f"cboe_{sym}.csv"; st = "missing"; v = {}
    t = curl(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv")
    if t.startswith("DATE") and t.count("\n") > 100: cp.write_text(t); st = "cboe"
    elif cp.exists(): t = cp.read_text(); st = "cboe-cache"
    else: t = ""
    for line in t.splitlines()[1:]:
        p = line.split(",")
        try: m, d_, y = p[0].split("/"); v[f"{y}-{int(m):02d}-{int(d_):02d}"] = float(p[4])
        except (ValueError, IndexError): pass
    if not v:
        f = curl(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}")
        for line in f.splitlines()[1:]:
            try: d_, x = line.split(","); v[d_] = float(x)
            except ValueError: pass
        st = "fred" if v else "missing"
    try:
        now = datetime.now(PT)
        q = json.loads(curl(f"https://cdn.cboe.com/api/global/delayed_quotes/quotes/_{sym}.json") or "{}").get("data") or {}
        lt = q.get("last_trade_time") or ""; today = now.strftime("%Y-%m-%d")
        if lt[:10] == today and now.strftime("%H%M") >= "1315" and q.get("close") and today not in v:
            v[today] = float(q["close"]); st += "+delayed-quote"
    except Exception: pass
    return v, st

def third_fridays(a, b):
    out = []; d = date(a.year, a.month, 1)
    while d <= b:
        f = d + timedelta(days=(4 - d.weekday()) % 7 + 14); out.append(f)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out
def skew_series(tk, days_needed):
    """25-delta risk reversal from UW, per date on the first monthly (3rd-Friday) expiry >= 20 calendar days out.
    UW value is put IV minus call IV in vol decimals (verified 10/22 against FlashAlpha skew_25d sign); we report vol points (x100)."""
    out, sts, need = {}, set(), {}
    for d in days_needed:
        dd = date.fromisoformat(d)
        e = next(f for f in third_fridays(dd, dd + timedelta(days=120)) if (f - dd).days >= 20)
        need.setdefault(e.isoformat(), []).append(d)
    for e, ds in need.items():
        j, st = uw(f"/stock/{tk}/historical-risk-reversal-skew?expiry={e}&delta=25", f"rr_{tk}_{e}"); sts.add(st)
        m = {r["date"]: float(r["risk_reversal"]) * 100 for r in ((j or {}).get("data") or []) if r.get("risk_reversal") is not None}
        for d in ds:
            if d in m: out[d] = (round(m[d], 2), e)
    return out, "/".join(sorted(sts))

def borrow_archive():
    out = {}
    for p in sorted((H / "oid-desk/desk/data/short-borrow/uw-borrow").glob("*.jsonl")):
        for line in p.read_text().splitlines():
            try: r = json.loads(line)
            except ValueError: continue
            if r.get("symbol") in CROWDED and r.get("fee_rate") is not None: out.setdefault(r["trade_date"], {})[r["symbol"]] = float(r["fee_rate"])
    return out

rd = lambda x, n=2: None if x is None else round(x, n)

r6 = lambda x: None if x is None else round(x, 6)
def rsum(xs):
    return None if any(x is None for x in xs) else sum(xs)
def main():
    t0 = time.time(); now = datetime.now(PT)
    B = bars(); days = sorted(B["SPY"])
    if now.weekday() < 5 and now.strftime("%H%M") < "1315" and days and days[-1] == now.strftime("%Y-%m-%d"): days = days[:-1]  # partial bar
    N = len(days); C = {s: [(B.get(s, {}).get(d) or {}).get("c") for d in days] for s in SYMS}
    def ret(s, i):
        a, b = C[s][i - 1] if i else None, C[s][i]
        if not a or not b: return None
        x = b / a - 1; return None if abs(x) > 0.6 else x
    RET = {s: [ret(s, i) for i in range(N)] for s in SYMS}
    # month-end rebalance (spec): crowded = top decile of 12-1 momentum (min 5), uncrowded = bottom tercile
    me = [i for i in range(N - 1) if days[i][:7] != days[i + 1][:7]]
    rank = {}
    for p in me:
        if p < 252: continue
        mom = {}
        for s in UNIVERSE:
            w = C[s][p - 252:p + 1]
            if all(w): mom[s] = C[s][p - 21] / C[s][p - 252] - 1
        n = len(mom); kt = max(5, int(round(n * 0.1))); kb = int(round(n / 3)); srt = sorted(mom, key=lambda s: mom[s])
        rank[p] = (sorted(srt[-kt:], key=lambda s: -mom[s]), srt[:kb], n)
    def ew(names, i):
        v = [RET[s][i] for s in names if RET[s][i] is not None]; return sum(v) / len(v) if v else None
    M = [None] * N; CVU = [None] * N; CRW = [None] * N; UNC = [None] * N
    for i in range(1, N):
        ps = [p for p in rank if p < i]
        if not ps: continue
        M[i] = rank[max(ps)]; CRW[i] = ew(M[i][0], i); UNC[i] = ew(M[i][1], i)
        CVU[i] = CRW[i] - UNC[i] if CRW[i] is not None and UNC[i] is not None else None
    sp = {"gvip_spy": ("GVIP", "SPY"), "mtum_spy": ("MTUM", "SPY"), "mtum_usmv": ("MTUM", "USMV")}
    S = {k: [RET[a][i] - RET[b][i] if RET[a][i] is not None and RET[b][i] is not None else None for i in range(N)] for k, (a, b) in sp.items()}
    S["cvu"] = CVU
    DOWN = [RET["SPY"][i] is not None and RET["SPY"][i] < 0 for i in range(N)]
    S10 = {k: [rsum(v[i - 9:i + 1]) if i >= 9 else None for i in range(N)] for k, v in S.items()}
    DS5 = {k: [rsum([v[j] if DOWN[j] else 0.0 for j in range(i - 4, i + 1)]) if i >= 4 else None for i in range(N)] for k, v in S.items()}
    TRIG = [any(S10[k][i] is not None and S10[k][i] <= TH[k + "_10d"] for k in ("mtum_spy", "gvip_spy", "mtum_usmv")) for i in range(N)]
    # episodes, armed, exhaustion flag (GVIP_SPY A2), relapse — walked forward one day at a time (no look-ahead)
    ep_id, first_trig, last_trig, flag_day, streak, fired = -1, None, None, None, 0, False
    ST = []
    for i in range(N):
        if TRIG[i]:
            if last_trig is None or i - last_trig > EPISODE_GAP:
                ep_id += 1; first_trig = i; flag_day = None; streak = 0; fired = False
            last_trig = i
        armed = last_trig is not None and i - last_trig < ARM_WINDOW
        flag_today = False
        if armed and first_trig is not None and i > first_trig and not fired and DOWN[i] and S["gvip_spy"][i] is not None:
            streak = streak + 1 if S["gvip_spy"][i] >= 0 else 0
            if streak >= 2: fired = True; flag_day = i; flag_today = True
        elif armed and first_trig is not None and i > first_trig and not fired and DOWN[i]:
            streak = 0
        relapse = bool(TRIG[i] and flag_day is not None and 0 < i - flag_day <= RELAPSE_WINDOW)
        standing = flag_day is not None and not any(TRIG[j] for j in range(flag_day + 1, i + 1))
        badge = "CLEAR" if not armed else ("EXHAUSTION FLAG" if standing else "DE-GROSSING")
        ST.append({"armed": armed, "episode_id": ep_id if armed else None, "first_trig": first_trig if armed else None,
                   "days_since_first_trigger": (i - first_trig) if armed else None, "streak": streak if armed else 0, "flag_today": flag_today,
                   "flag_day": flag_day if armed else None, "relapse": relapse, "badge": badge,
                   "relapsed_since_flag": bool(flag_day is not None and armed and not standing)})
    # supporting readings (other existing feeds)
    vix, vix_st = index_hist("VIX", "VIXCLS"); v3, v3_st = index_hist("VIX3M", "VXVCLS")
    out_idx = [i for i in range(N) if days[i] >= START_OUT]; out_days = [days[i] for i in out_idx]
    sk = {t: skew_series(t, out_days[-60:]) for t in ("QQQ", "SMH")}
    SV, sv_st = {}, set()
    for t in DESK_CROWDED:
        j, st = uw(f"/shorts/{t}/volume-and-ratio", f"sv_{t}"); sv_st.add(st)
        for r in ((j or {}).get("si") or []):
            try: SV.setdefault(r["market_date"], {})[t] = (float(r["short_volume"]), float(r["total_volume"]))
            except (KeyError, TypeError, ValueError): pass
    sv_dates = sorted(SV)
    SVR = {}
    for d in sv_dates:
        x = SV[d]; tv = sum(v[1] for v in x.values()); SVR[d] = (sum(v[0] for v in x.values()) / tv * 100 if tv else None, len(x))
    sj, soxl_st = uw("/etfs/SOXL/in-outflow", "soxl_flow"); SOXL = {r["date"]: r for r in ((sj or {}).get("data") or [])}
    BOR = borrow_archive()
    rows = []
    for i in out_idx:
        d = days[i]; s = ST[i]; m = M[i] or ([], [], 0)
        dc = ew(DESK_CROWDED, i); du = ew(DESK_UNCROWDED, i); smh = RET["SMH"][i]
        svd = max([x for x in sv_dates if x <= d], default=None); svr = SVR.get(svd, (None, 0))
        prev20 = [SVR[x][0] for x in sv_dates if x < (svd or "") and SVR[x][0] is not None][-20:]
        skq, sks = sk["QQQ"][0].get(d), sk["SMH"][0].get(d)
        soxd = max([x for x in SOXL if x <= d], default=None); so = SOXL.get(soxd) if soxd else None
        bor = BOR.get(d) or {}; vx, vx3 = vix.get(d), v3.get(d)
        row = {"date": d, "spy_ret": r6(RET["SPY"][i]), "qqq_ret": r6(RET["QQQ"][i]), "smh_ret": r6(smh),
               **{k: r6(S[k][i]) for k in S}, **{k + "_10d": r6(S10[k][i]) for k in S}, **{k + "_ds5": r6(DS5[k][i]) for k in S},
               "spy_down": DOWN[i], "trigger": TRIG[i], "armed": s["armed"], "episode_id": s["episode_id"], "days_since_first_trigger": s["days_since_first_trigger"],
               "downdays_gvip_nonneg_streak": s["streak"], "exhaust_flag": s["flag_today"], "relapse": s["relapse"],
               "severity": r6(S10["mtum_usmv"][i] / RECORD_MTUM_USMV_10D) if S10["mtum_usmv"][i] is not None else None,
               "crowded_members": " ".join(m[0]), "uncrowded_members": " ".join(m[1]),
               # ---- not in the spec CSV ----
               "badge": s["badge"], "exhaust_flag_standing": s["badge"] == "EXHAUSTION FLAG", "relapsed_since_flag": s["relapsed_since_flag"],
               "first_trigger_date": days[s["first_trig"]] if s["first_trig"] is not None else None,
               "flag_date": days[s["flag_day"]] if s["flag_day"] is not None else None, "universe_eligible": m[2],
               "triggered_by": [k for k in ("mtum_usmv", "mtum_spy", "gvip_spy") if S10[k][i] is not None and S10[k][i] <= TH[k + "_10d"]],
               "gvip_ret": r6(RET["GVIP"][i]), "mtum_ret": r6(RET["MTUM"][i]), "usmv_ret": r6(RET["USMV"][i]),
               "crowded_ret": r6(CRW[i]), "uncrowded_ret": r6(UNC[i]), "gvip_volume": (B["GVIP"].get(d) or {}).get("v"),
               "desk_crowded_ret": r6(dc), "desk_uncrowded_ret": r6(du), "desk_cvu": r6(dc - du if dc is not None and du is not None else None),
               "desk_crowded_minus_smh": r6(dc - smh if dc is not None and smh is not None else None),
               "desk_names_worse_than_smh": sum(1 for x in DESK_CROWDED if RET[x][i] is not None and smh is not None and RET[x][i] < smh),
               "vix": vx, "vix3m": vx3, "vix_vix3m": rd(vx / vx3, 3) if vx and vx3 else None, "vix_inverted": (vx / vx3 >= 1) if vx and vx3 else None,
               "qqq_skew25_volpts": skq[0] if skq else None, "smh_skew25_volpts": sks[0] if sks else None, "skew_expiry": (skq or sks or (None, None))[1],
               "shortvol_date": svd, "shortvol_ratio_pct": rd(svr[0]), "shortvol_names": svr[1], "shortvol_prior20_mean_pct": rd(sum(prev20) / len(prev20)) if prev20 else None,
               "soxl_flow_date": soxd, "soxl_shares_change": so and so.get("change"),
               "soxl_flow_usd": so and (float(so["change_prem"]) if so.get("change_prem") not in (None, "") else None),
               "borrow_fee_mean_pct": rd(sum(bor.values()) / len(bor), 3) if bor else None}
        rows.append(row)
    # down-day check: last 5 SPY-down days, did GVIP beat SPY?
    L = rows[-1]; li = out_idx[-1]
    dd = [j for j in range(li, -1, -1) if DOWN[j]][:5]
    downcheck = [{"date": days[j], "spy_ret": r6(RET["SPY"][j]), "gvip_ret": r6(RET["GVIP"][j]), "gvip_spy": r6(S["gvip_spy"][j]),
                  "gvip_beat_spy": S["gvip_spy"][j] is not None and S["gvip_spy"][j] >= 0} for j in dd]
    ep_dd = [j for j in range(ST[li]["first_trig"] + 1, li + 1) if DOWN[j]] if ST[li]["first_trig"] is not None else []
    # CSV: append-only (rows already in the file are never rewritten)
    cp = OUT / "degrossing_gauge.csv"; have = set()
    if cp.exists():
        with open(cp) as f: have = {r["date"] for r in csv.DictReader(f)}
    new = [r for r in rows if r["date"] not in have and r["date"] > max(have, default="")]
    with open(cp, "a", newline="") as f:
        w = csv.DictWriter(f, CSV_COLS, extrasaction="ignore")
        if not have: w.writeheader()
        for r in new: w.writerow({k: ("" if r.get(k) is None else r[k]) for k in CSV_COLS})
    meta = {"schema": "oid-degross/2", "version": VERSION, "research_only": True, "built_pt": now.strftime("%Y-%m-%d %-I:%M %p PT"),
            "spec": "Research Bot, studies/degrossing-gauge-20261022/SPEC.md (2026-10-22); copy at ~/oid-score/research/degross-study/",
            "thresholds_10d": TH, "record_mtum_usmv_10d": RECORD_MTUM_USMV_10D, "rules": RULES_TEXT, "caveat": CAVEAT,
            "validation": {"detection": "32 of 33 unwinds since 2017 caught (missed: the one-day DeepSeek shock, 2025-01-27); 23 train / 10 holdout episodes",
                           "exhaustion_flag": "UNTESTED out of sample: holdout n=8, QQQ +10d +0.14pp vs normal, crowded basket −4.1pp, relapse within 20 sessions 38% (38–44% across rules)",
                           "survivorship": "74-ticker universe is all 2026 survivors (delisted/acquired names such as XLNX, JNPR, ANSS missing)"},
            "baskets": {"universe": UNIVERSE, "desk_crowded": DESK_CROWDED, "desk_uncrowded": DESK_UNCROWDED, "note": BASKET_NOTE},
            "units": "spec fields (*_ret, gvip_spy, mtum_spy, mtum_usmv, cvu, *_10d, *_ds5, severity) are decimals (−0.1277 = −12.77%); fields ending _pct / _volpts are already in % / vol points",
            "sources": {"bars": "Alpaca SIP daily, adjustment=all", "vix": vix_st, "vix3m": v3_st, "skew": "UW risk-reversal 25-delta: " + sk["QQQ"][1] + "/" + sk["SMH"][1],
                        "short_volume": "UW /shorts/{T}/volume-and-ratio (FINRA consolidated, ~1 session behind): " + "/".join(sorted(sv_st)),
                        "soxl_flow": "UW /etfs/SOXL/in-outflow: " + soxl_st, "borrow": "UW borrow archive (short-borrow job), read only"},
            "notes": ["Raw daily values, never smoothed; *_10d = 10-session sums, *_ds5 = 5-session sums of the spread on SPY-down days only.",
                      "GVIP trades thinly (often <20k shares/day); gvip_volume is shown so a stale close is visible.",
                      "Supporting readings (desk basket, VIX term structure, 25-delta skew, short volume, SOXL flow, borrow) are shown but not used by the badge; they are not in the backtest.",
                      "Research only, not an order signal."]}
    for r in rows[-BACKFILL_FILES:]:
        p = OUT / f"degross-{r['date'].replace('-', '')}.json"; p.with_suffix(".tmp").write_text(json.dumps(dict(meta, date=r["date"], gauge=r), indent=1)); p.with_suffix(".tmp").replace(p)
    latest = dict(meta, date=L["date"], badge=L["badge"], gauge=L, downday_check=downcheck,
                  episode_downdays={"since": L["first_trigger_date"], "n": len(ep_dd), "gvip_beat_spy": sum(1 for j in ep_dd if S["gvip_spy"][j] is not None and S["gvip_spy"][j] >= 0)},
                  history=[{k: v for k, v in r.items() if k not in ("crowded_members", "uncrowded_members")} for r in rows[-HIST_ROWS:]],
                  rows=len(rows), first_date=rows[0]["date"], csv=str(cp), csv_rows_appended=len(new), elapsed_s=round(time.time() - t0, 1))
    (OUT / "latest.json.tmp").write_text(json.dumps(latest, indent=1)); (OUT / "latest.json.tmp").replace(OUT / "latest.json")
    pc = lambda x: "—" if x is None else f"{x*100:+.2f}%"
    print(f"[{now:%Y-%m-%d %H:%M %Z}] degross ok: {L['date']} {L['badge']} ep{L['episode_id']} day{L['days_since_first_trigger']} sev={L['severity']} "
          f"mtum_usmv_10d={pc(L['mtum_usmv_10d'])} gvip_spy_10d={pc(L['gvip_spy_10d'])} mtum_spy_10d={pc(L['mtum_spy_10d'])} cvu_10d={pc(L['cvu_10d'])} "
          f"csv+{len(new)} {time.time()-t0:.0f}s", flush=True)
if __name__ == "__main__": main()
