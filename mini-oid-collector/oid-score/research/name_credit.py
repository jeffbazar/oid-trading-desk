"""Research only (no trading). Company-level credit log: single-name CDS + bond prices/yields, all free sources.

Writes ~/oid-data/research/name-credit/:
  cds_dtcc_trades.csv  single-name CDS trades from DTCC's public SEC security-based-swap slices (free, no key; reference
                       entity is public). One row per disseminated trade, deduped by Dissemination Identifier.
  cds_dtcc_daily.csv   per name per day: on-the-run 5y level in bp (median of quoted spreads, else spread implied from the
                       upfront on exact-notional trades), trade counts.
  cds_x_prints.csv     5y CDS levels quoted in X posts (recent search, a few calls/day, budgeted), parsed with the date
                       the level refers to, author and post link; approximate values flagged.
  bond_yields.csv      daily bond prices/yields from Kilambi News leverage pages (FINRA TRACE last prints; no key).
  latest.json          latest values per name + source status + X spend.
Run:  ~/oid-quote/venv/bin/python ~/oid-score/research/name_credit.py [--backfill] [--x-only] [--no-x]
      launchd com.oid.desk.name-credit (13:40 PT Mon-Fri). Keys are read from the x-on-surge config path and never printed.
Rules: never invents values; a field that a source does not give stays blank.
"""
import csv, io, json, math, os, re, statistics as st, sys, time, urllib.parse, urllib.request, urllib.error, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

H = Path.home(); PT = ZoneInfo("America/Los_Angeles"); ET = ZoneInfo("America/New_York"); UTC = timezone.utc
OUT = H / "oid-data/research/name-credit"; OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / "state.json"
XSTATE = H / "oid-data/state/x"
LEDGER = XSTATE / "name_credit_budget.json"            # read by x-on-surge budget_guard (month pacing)
UA = "OID-Research/1.0 (+research; paper-only)"
NOW = datetime.now(PT)

# ---- names -------------------------------------------------------------------------------------------------------
ROLE = {"CRWV": "neocloud", "NBIS": "neocloud", "IREN": "neocloud", "APLD": "neocloud", "WULF": "neocloud", "CIFR": "neocloud",
        "CORZ": "neocloud", "ORCL": "hyperscaler", "META": "hyperscaler", "AMZN": "hyperscaler", "MSFT": "hyperscaler",
        "GOOGL": "backer", "NVDA": "backer"}   # NVDA = CRWV backer (stake + capacity backstop); GOOGL tagged backer per desk 10/21
CORE = ["CRWV", "ORCL", "META", "AMZN", "GOOGL", "MSFT", "NVDA"]
DTCC_ENT = [("CRWV", r"COREWEAVE"), ("ORCL", r"\bORACLE\b"), ("META", r"META PLATFORMS"), ("AMZN", r"AMAZON"),
            ("GOOGL", r"ALPHABET|\bGOOGLE\b"), ("MSFT", r"MICROSOFT"), ("NVDA", r"NVIDIA"), ("NBIS", r"NEBIUS"),
            ("IREN", r"^IREN\b|IRIS ENERGY"), ("APLD", r"APPLIED DIGITAL"), ("WULF", r"TERAWULF"), ("CIFR", r"CIPHER MINING"),
            ("CORZ", r"CORE SCIENTIFIC")]
X_ALIAS = [("CRWV", r"CoreWeave|\$CRWV\b|\bCRWV\b"), ("ORCL", r"\bOracle\b|\$ORCL\b|\bORCL\b"), ("META", r"\bMeta\b|\$META\b"),
           ("AMZN", r"\bAmazon\b|\$AMZN\b"), ("GOOGL", r"\bAlphabet\b|\bGoogle\b|\$GOOGL?\b"), ("MSFT", r"\bMicrosoft\b|\$MSFT\b"),
           ("NVDA", r"\bNvidia\b|\bNVIDIA\b|\$NVDA\b"), ("NBIS", r"\bNebius\b|\$NBIS\b"), ("IREN", r"\bIREN\b|\$IREN\b"),
           ("APLD", r"Applied Digital|\$APLD\b"), ("WULF", r"TeraWulf|\$WULF\b"), ("CIFR", r"Cipher Mining|\$CIFR\b"),
           ("CORZ", r"Core Scientific|\$CORZ\b")]
DATA_ACCOUNTS = ["GlobalMktObserv", "zerohedge", "KobeissiLetter", "lisaabramowicz1", "tracyalloway", "DeItaone", "FirstSquawk",
                 "charliebilello", "Barchart", "SpecialSitsNews", "creditbubble", "M_McDonough"]
KNOWN_USERS = {"1679591758332657665": "GlobalMktObserv"}

def jload(p, d):
    try: return json.loads(Path(p).read_text())
    except Exception: return d
def jsave(p, obj):
    p = Path(p); t = p.with_suffix(p.suffix + ".tmp"); t.write_text(json.dumps(obj, indent=1)); t.replace(p)
def http(url, data=None, headers=None, timeout=40):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()
def upsert_csv(path, cols, rows, key):
    """Append rows whose key is new; rows with an existing key replace the old row (same source re-read)."""
    old = []
    if path.exists():
        with open(path, newline="") as f: old = list(csv.DictReader(f))
    idx = {key(r): i for i, r in enumerate(old)}; added = 0
    for r in rows:
        r = {c: ("" if r.get(c) is None else r.get(c)) for c in cols}; k = key(r)
        if k in idx: old[idx[k]] = r
        else: idx[k] = len(old); old.append(r); added += 1
    t = path.with_suffix(".csv.tmp")
    with open(t, "w", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); [w.writerow({c: r.get(c, "") for c in cols}) for r in old]
    t.replace(path); return added, len(old)

# ---- CDS math (flat hazard, flat 4% rate, 40% recovery: the usual quick quoted-spread conversion; ~±2% of level) ------
def cds_legs(lam, T, r=0.04, R=0.4):
    n = max(1, int(math.ceil(T / 0.25 - 1e-9))); rp = 0.0; prev = 0.0
    for i in range(1, n + 1):
        t = min(T, i * 0.25); rp += (t - prev) * math.exp(-(r + lam) * t); prev = t
    prot = (1 - R) * lam / (r + lam) * (1 - math.exp(-(r + lam) * T)) if lam > 0 else 0.0
    return prot, rp
def implied_spread_bp(upfront_frac, coupon, T):
    f = lambda lam: (lambda p, rp: p - coupon * rp)(*cds_legs(lam, T)) - upfront_frac
    lo, hi = 1e-7, 3.0
    if f(lo) > 0 or f(hi) < 0: return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0: hi = mid
        else: lo = mid
    p, rp = cds_legs((lo + hi) / 2, T); return round(p / rp * 1e4, 1)
def otr5y(d):
    """On-the-run 5y CDS maturity for a trade date (rolls 20 Mar / 20 Sep; maturities 20 Jun / 20 Dec)."""
    if d >= date(d.year, 9, 20): return date(d.year + 5, 12, 20)
    if d >= date(d.year, 3, 20): return date(d.year + 5, 6, 20)
    return date(d.year + 4, 12, 20)

# ---- 1) DTCC public SEC slices ------------------------------------------------------------------------------------
DT_COLS = ["dissemination_id", "exec_ts_utc", "exec_date", "ticker", "role", "entity", "action", "event", "effective", "expiration",
           "tenor_y", "is_otr5y", "notional", "notional_capped", "currency", "coupon_bp", "quoted_spread_bp", "upfront_amt",
           "upfront_pts", "implied_spread_bp", "spread_method", "cleared", "platform", "underlier_id", "package", "slice", "sign_ref", "source_quality"]
def dtcc_slice(d):
    url = f"https://kgc0418-tdw-data-0.s3.amazonaws.com/sec/eod/SEC_CUMULATIVE_CREDITS_{d:%Y_%m_%d}.zip"
    try: s, b = http(url, timeout=60)
    except urllib.error.HTTPError as e: return None, f"http {e.code}"
    except Exception as e: return None, type(e).__name__
    z = zipfile.ZipFile(io.BytesIO(b)); name = [n for n in z.namelist() if n.endswith(".csv")][0]
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace"))), "ok"
def fnum(s):
    try: return float(str(s).replace(",", "").replace("+", ""))
    except ValueError: return None
def dtcc(stt, days_back):
    done = set(stt.get("dtcc_done", [])); rows = []; log = []
    today = NOW.date()
    for k in range(days_back, -1, -1):
        d = today - timedelta(days=k)
        if d.weekday() >= 5 or (d.isoformat() in done and k > 3): continue   # cumulative slices fill during the day: re-read the last 3 days
        recs, why = dtcc_slice(d); log.append(f"{d}:{why}")
        if recs is None: continue
        bad = {r.get("Original Dissemination Identifier") for r in recs if r.get("Action type") in ("EROR", "CORR")} - {""}
        # portfolio/compression/backload batches: one upfront+notional+maturity+timestamp shared by many reference names is not a
        # market price for any of them (e.g. 10/21: AMZN, MSFT, Dow, GM... all at the same $34,565). Drop those.
        bk = lambda r: (r.get("Other payment amount"), r.get("Notional amount-Leg 1"), r.get("Expiration Date"), (r.get("Execution Timestamp") or "")[:16])
        cnt = {}
        for r in recs:
            if r.get("Other payment amount"): cnt.setdefault(bk(r), set()).add((r.get("Underlying Asset Name") or "").upper())
        batch = {k for k, v in cnt.items() if len(v) >= 3}
        for r in recs:
            nm = ((r.get("Underlying Asset Name") or "") + " | " + (r.get("UPI Underlier Name") or "")).upper()
            if "SN" not in (r.get("UPI FISN") or "") and "CDS" not in (r.get("UPI FISN") or ""): continue
            tk = next((t for t, rx in DTCC_ENT if re.search(rx, nm)), None)
            if not tk or r.get("Action type") not in ("NEWT", "CORR") or (r.get("Event type") not in ("TRAD", "")): continue
            if r["Dissemination Identifier"] in bad or bk(r) in batch: continue
            try:
                ex = datetime.fromisoformat(r["Execution Timestamp"].replace("Z", "+00:00"))
                eff = date.fromisoformat(r["Effective Date"]); mat = date.fromisoformat(r["Expiration Date"])
            except Exception: continue
            ed = ex.astimezone(ET).date(); T = (mat - eff).days / 365.25
            noti = fnum(r.get("Notional amount-Leg 1")); capped = "+" in (r.get("Notional amount-Leg 1") or "")
            cpn = fnum(r.get("Fixed rate-Leg 1")); qs = fnum(r.get("Spread-Leg 1"))
            up = fnum(r.get("Other payment amount")) if "UFRO" in (r.get("Other payment type") or "") else None
            row = {"dissemination_id": r["Dissemination Identifier"], "exec_ts_utc": r["Execution Timestamp"], "exec_date": ed.isoformat(),
                   "ticker": tk, "role": ROLE.get(tk), "entity": (r.get("UPI Underlier Name") or r.get("Underlying Asset Name") or "").strip(),
                   "action": r.get("Action type"), "event": r.get("Event type"), "effective": eff.isoformat(), "expiration": mat.isoformat(),
                   "tenor_y": round(T, 2), "is_otr5y": int(mat == otr5y(ed)), "notional": noti, "notional_capped": int(capped),
                   "currency": r.get("Notional currency-Leg 1"), "coupon_bp": round(cpn * 1e4, 1) if cpn is not None and abs(cpn) < 1 else None,
                   "quoted_spread_bp": round(qs * 1e4, 2) if qs is not None and (r.get("Spread notation-Leg 1") in ("3", "")) and 0 < qs < 1 else None,
                   "upfront_amt": up, "upfront_pts": round(up / noti * 100, 4) if up is not None and noti and not capped else None,
                   "cleared": r.get("Cleared"), "platform": r.get("Platform identifier"), "underlier_id": r.get("Underlier ID-Leg 1"),
                   "package": r.get("Package indicator"), "slice": d.isoformat(), "source_quality": "firsthand_dtcc"}
            rows.append(row)
        done.add(d.isoformat())
    # implied spreads: quoted spread wins; else upfront (exact notional only). 1% coupon upfronts carry no sign in the
    # public record, so both signs are tried and kept only when exactly one solves, or the one nearest that day's quoted median.
    qmed = {}
    for r in rows:
        if r["quoted_spread_bp"] is not None and r["is_otr5y"]: qmed.setdefault((r["ticker"], r["exec_date"]), []).append(r["quoted_spread_bp"])
    qmed = {k: st.median(v) for k, v in qmed.items()}
    for r in rows:
        if r["quoted_spread_bp"] is not None: r["implied_spread_bp"], r["spread_method"] = r["quoted_spread_bp"], "quoted"; continue
        if r["upfront_pts"] is None or r["coupon_bp"] is None or r["tenor_y"] <= 0.2: r["spread_method"] = "n/a (capped notional or no upfront)"; continue
        c = r["coupon_bp"] / 1e4; u = r["upfront_pts"] / 100; T = r["tenor_y"]
        cands = [s for s in (implied_spread_bp(u, c, T), implied_spread_bp(-u, c, T)) if s is not None]
        q, qsrc = qmed.get((r["ticker"], r["exec_date"])), "same-day quoted median"
        if q is None: q, qsrc = sign_ref(r["ticker"], r["exec_date"])
        if len(cands) == 1: r["implied_spread_bp"], r["spread_method"] = cands[0], "upfront->spread"
        elif len(cands) == 2 and q is not None and (lambda c, o: abs(c - q) <= 0.25 * q and abs(c - q) < 0.5 * abs(o - q))(
                *sorted(cands, key=lambda s: abs(s - q))):
            r["implied_spread_bp"] = min(cands, key=lambda s: abs(s - q)); r["spread_method"] = "upfront->spread (sign picked by reference)"
            r["sign_ref"] = f"{qsrc} {q:.0f}bp"   # kept only if within 25% of the reference and clearly nearer than the other sign
        else: r["spread_method"] = "upfront sign ambiguous"
    stt["dtcc_done"] = sorted(done)[-60:]
    return rows, log
def sign_ref(tk, d):
    """Reference level used only to pick the sign of an unsigned upfront (two candidates far apart). Order: firsthand
    DTCC 5y level on an earlier day, then firsthand FINRA bond spread-to-Treasury (median, latest run), then a secondhand X print
    within 7 days. Returns (bp, label) or (None, None)."""
    try:
        for r in reversed(rd(OUT / "cds_dtcc_daily.csv")):
            if r["ticker"] == tk and r["date"] < d and r["cds5y_bp"] and r["method"] == "quoted median": return float(r["cds5y_bp"]), f"DTCC quoted {r['date']}"
        b = [float(r["spread_tsy_bp"]) for r in rd(OUT / "bond_yields.csv") if r["ticker"] == tk and r["spread_tsy_bp"]]
        if b: return st.median(b), "FINRA bond spread median"
        dd = date.fromisoformat(d)
        x = [float(r["level_bp"]) for r in rd(OUT / "cds_x_prints.csv") if r["ticker"] == tk and r["level_bp"]
             and abs((date.fromisoformat(r["refers_date"]) - dd).days) <= 7]
        if x: return st.median(x), "X print median (secondhand)"
    except Exception: pass
    return None, None
def dtcc_daily():
    p = OUT / "cds_dtcc_trades.csv"
    if not p.exists(): return []
    with open(p, newline="") as f: tr = list(csv.DictReader(f))
    g = {}
    for r in tr:
        g.setdefault((r["exec_date"], r["ticker"]), []).append(r)
    out = []
    for (d, tk), rs in sorted(g.items()):
        o = [r for r in rs if r["is_otr5y"] == "1"]
        q = [float(r["quoted_spread_bp"]) for r in o if r["quoted_spread_bp"]]
        u = [float(r["implied_spread_bp"]) for r in o if r["implied_spread_bp"] and not r["quoted_spread_bp"]]
        lvl, meth = (st.median(q), "quoted median") if q else ((st.median(u), "upfront-implied median") if u else (None, "no priced 5y trade"))
        out.append({"date": d, "ticker": tk, "role": ROLE.get(tk), "cds5y_bp": round(lvl, 1) if lvl is not None else None, "method": meth,
                    "n_quoted_5y": len(q), "n_upfront_5y": len(u), "n_trades_5y": len(o), "n_trades_all": len(rs),
                    "min_5y_bp": round(min(q or u), 1) if (q or u) else None, "max_5y_bp": round(max(q or u), 1) if (q or u) else None})
    cols = ["date", "ticker", "role", "cds5y_bp", "method", "n_quoted_5y", "n_upfront_5y", "n_trades_5y", "n_trades_all", "min_5y_bp", "max_5y_bp"]
    t = OUT / "cds_dtcc_daily.csv.tmp"
    with open(t, "w", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); [w.writerow({c: ("" if x[c] is None else x[c]) for c in cols}) for x in out]
    t.replace(OUT / "cds_dtcc_daily.csv"); return out

# ---- 2) bonds: Kilambi News leverage pages (FINRA TRACE last prints) -----------------------------------------------------
KIL = {"CRWV": "coreweave", "ORCL": "oracle", "IREN": "iren", "APLD": "applied-digital", "WULF": "terawulf"}
BD_COLS = ["source_quality", "run_date", "data_asof", "trade_date", "ticker", "role", "cusip", "description", "coupon", "maturity", "price",
           "yield_pct", "yield_type", "spread_tsy_bp", "last_trade_et", "source", "url"]
def strip(h): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()
def ytm_30360(price, cpn, settle, mat):
    """Yield to maturity, 30/360 semiannual, clean price -> dirty with 30/360 accrued. Ignores calls/conversion."""
    if price is None or cpn is None or mat <= settle or price <= 0: return None
    d360 = lambda a, b: (b.year - a.year) * 360 + (b.month - a.month) * 30 + (min(b.day, 30) - min(a.day, 30))
    cds = [mat]
    while True:
        y, m = cds[-1].year, cds[-1].month - 6
        if m <= 0: y, m = y - 1, m + 12
        prev = date(y, m, min(mat.day, 28) if m == 2 else mat.day)
        if prev <= settle: break
        cds.append(prev)
    cds = sorted(cds); prev_cd = prev
    acc = cpn / 2 * d360(prev_cd, settle) / 180; dirty = price + acc
    w = d360(settle, cds[0]) / 180
    pv = lambda y: sum((cpn / 2 + (100 if i == len(cds) - 1 else 0)) / (1 + y / 2) ** (w + i) for i in range(len(cds)))
    lo, hi = -0.5, 2.0
    if not (pv(hi) <= dirty <= pv(lo)): return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if pv(mid) > dirty: lo = mid
        else: hi = mid
    return round((lo + hi) / 2 * 100, 3)
def kil_bond_page(slug):
    url = f"https://news.kilambi.com/leverage/bond/{slug}/"
    _, b = http(url); t = strip(b.decode("utf-8", "replace"))
    g = lambda rx: (re.search(rx, t) or [None, None])[1]
    return {"price": fnum(g(r"Last TRACE trade ([\d.]+)")), "ts": g(r"Last TRACE trade [\d.]+ (\d{1,2} \w{3} \d{4}, \d{1,2}:\d{2} ET)"),
            "ytw": fnum(g(r"Yield to worst (-?[\d.]+)%")), "spr": fnum(g(r"Spread to Treasury ([+\-]?\d+) bp")), "url": url}
def bonds():
    rows, log = [], []
    for tk, slug in KIL.items():
        url = f"https://news.kilambi.com/leverage/issuer/{slug}/"
        try: _, b = http(url); h = b.decode("utf-8", "replace")
        except Exception as e: log.append(f"{tk}:{type(e).__name__}"); continue
        asof = (re.search(r"Data as of (\d{4}-\d{2}-\d{2})", h) or [None, None])[1]
        tb = re.search(r"<table[^>]*data-tid=iss-b-[^>]*>(.*?)</table>", h, re.S)
        if not tb: log.append(f"{tk}:no table"); continue
        hdr = [strip(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", tb.group(1), re.S)]
        n = 0
        for tr in re.findall(r"<tr>(.*?)</tr>", tb.group(1), re.S):
            cells = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
            if len(cells) != len(hdr): continue
            def cv(at, inner):
                m = re.search(r'data-v=(?:"([^"]*)"|([^\s>]+))', at)
                return (m.group(1) if m.group(1) is not None else m.group(2)) if m else strip(inner)
            v = {hdr[i]: cv(*c) for i, c in enumerate(cells)}
            link = (re.search(r"href=(/leverage/bond/[a-z0-9]+/)", tr) or [None, None])[1]
            px = fnum(v.get("Last print (% of par)")); td = v.get("Traded") or None; cp = fnum(v.get("Coupon (%)")); mt = v.get("Matures")
            if px is None or not td or not mt: continue
            try: settle = date.fromisoformat(td) + timedelta(days=1 if date.fromisoformat(td).weekday() < 4 else 3); md = date.fromisoformat(mt)
            except ValueError: continue
            row = {"source_quality": "firsthand_finra", "run_date": NOW.date().isoformat(), "data_asof": asof, "trade_date": td, "ticker": tk, "role": ROLE.get(tk),
                   "cusip": v.get("CUSIP"), "description": v.get("Bond", "").replace("&amp;", "&"), "coupon": cp, "maturity": mt, "price": px,
                   "yield_pct": ytm_30360(px, cp, settle, md), "yield_type": "ytm_calc_30360 (ignores calls)",
                   "spread_tsy_bp": None, "last_trade_et": None, "source": "kilambi issuer table (FINRA TRACE last print)",
                   "url": "https://news.kilambi.com" + link if link else url}
            if ROLE.get(tk) == "neocloud" and (cp is None or cp < 4 or re.search(r"conver", row["description"], re.I)):
                row.update(yield_pct=None, yield_type="convert/low-coupon: price only (straight yield is meaningless)")
            if tk == "CRWV" and link:  # key name: per-bond page gives the last TRACE trade time, yield to worst and spread
                try:
                    bp = kil_bond_page(link.split("/")[-2]); time.sleep(0.7)
                    if bp["price"] is not None:
                        row.update(price=bp["price"], last_trade_et=bp["ts"], spread_tsy_bp=bp["spr"], url=bp["url"],
                                   source="kilambi bond page (FINRA TRACE last trade)")
                        if row["yield_type"].startswith("convert"): row["spread_tsy_bp"] = None
                        elif bp["ytw"] is not None: row.update(yield_pct=bp["ytw"], yield_type="ytw_kilambi")
                        else: row["yield_pct"] = ytm_30360(bp["price"], cp, settle, md)
                except Exception as e: log.append(f"CRWV bond page {link}:{type(e).__name__}")
            rows.append(row); n += 1
        log.append(f"{tk}:{n} bonds asof {asof}"); time.sleep(0.7)
    return rows, log

# ---- 3) X prints ------------------------------------------------------------------------------------------------------
X_COLS = ["source_quality", "post_id", "post_url", "author", "author_id", "data_account", "post_created_utc", "post_date_et", "refers_date", "date_basis",
          "ticker", "role", "tenor", "level_bp", "level_approx", "change_bp", "change_approx", "change_since", "prior_bp", "prior_ref",
          "record", "query_id", "snippet", "fetched_pt"]
NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
BP = re.compile(r"([+\-−]?)\s*([~≈]?)\s*" + NUM + r"\s*(?:basis[\s-]points?|bps?\b|bp\b)", re.I)
CDS_CTX = re.compile(r"\bCDS\b|default swap|default insurance|default protection", re.I)
APPROX = re.compile(r"(~|≈|as much as|about|around|roughly|nearly|over|more than|almost|near|some|above|below|under|past|beyond|topping|top)\s*[+\-]?\s*$", re.I)
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
WD = {d: i for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
def refers(sent, pdate):
    s = sent.lower()
    m = re.search(r"\b(?:on\s+)?(?:(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?)\b(?!\s*,?\s*\d{4})", s)
    if m:
        try:
            mo = MON[m.group(2) or m.group(3)]; dy = int(m.group(1) or m.group(4)); y = pdate.year - (1 if mo > pdate.month else 0)
            return date(y, mo, dy).isoformat(), f"'{m.group(0).strip()}' in post"
        except ValueError: pass
    m = re.search(r"\b(?:on|this|last)\s+(monday|tuesday|wednesday|thursday|friday)\b", s)
    if m:
        back = (pdate.weekday() - WD[m.group(1)]) % 7
        if m.group(0).startswith("last") and back == 0: back = 7
        return (pdate - timedelta(days=back)).isoformat(), f"'{m.group(0)}' vs post date"
    if re.search(r"\byesterday\b", s):
        d = pdate - timedelta(days=1)
        while d.weekday() >= 5: d -= timedelta(days=1)
        return d.isoformat(), "'yesterday' vs post date"
    if re.search(r"\btoday\b|this morning|right now", s): return pdate.isoformat(), "'today/now' = post date"
    return pdate.isoformat(), "post date (no day stated)"
def parse_post(text, created_utc):
    """-> list of dicts (one per company with a CDS level in a sentence). Only numbers written in the post are used."""
    cdt = datetime.fromisoformat(created_utc.replace("Z", "+00:00")); pdate = cdt.astimezone(ET).date()
    out = []; last_day = None
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z$\"'(])|\n+", text)
    for s in sents:
        if not CDS_CTX.search(s):
            rd0, b0 = refers(s, pdate)
            if not b0.startswith("post date"): last_day = (rd0, b0)
            continue
        ments = sorted((m.start(), tk) for tk, rx in X_ALIAS for m in re.finditer(rx, s))
        if not ments: continue
        recs = {}
        for m in BP.finditer(s):
            sign, tilde, val = m.group(1), m.group(2), float(m.group(3).replace(",", ""))
            pre = s[max(0, m.start() - 40):m.start()]; post = s[m.end():m.end() + 30]
            before = [t for p, t in ments if p < m.start()]; tk = before[-1] if before else ments[0][1]
            fm = next((t for p, t in ments if m.end() <= p <= m.end() + 12 and re.match(r"\s*(for|at)\s", s[m.end():p + 1])), None)
            if fm: tk = fm   # "about 101 basis points for Nvidia"
            r = recs.setdefault(tk, {})
            approx = bool(tilde) or bool(APPROX.search(pre))
            if re.search(r"(up|down)?\s*from\s*(a\s+)?~?$", pre, re.I):
                r.setdefault("prior_bp", val); pr = re.match(r"\s*(?:bps?|basis points)?\s*([^,.;]{0,30})", post); r["prior_ref"] = (pr.group(1) if pr else "").strip()
            elif sign or re.search(r"(surged|rose|jumped|widened|climbed|spiked|soared|added|gained|fell|tightened|narrowed|dropped|declined|increased|up|down|by)\s*(as much as|about|around|nearly|more than|over|roughly)?\s*[~≈]?\s*$", pre, re.I) \
                    and not re.search(r"\bto\s*(a\s+)?(fresh\s+|new\s+)?(record\s+)?(high\s+of\s+)?$", pre, re.I):
                neg = sign in ("-", "−") or re.search(r"(fell|tightened|narrowed|dropped|declined|down)\s*\S*\s*$", pre, re.I)
                if re.match(r"\s*since\b", post, re.I) or re.search(r"since", post[:25], re.I):
                    r.setdefault("change_since", f"{'-' if neg else '+'}{val:g} bp {post.strip()[:25]}")
                else:
                    r.setdefault("change_bp", -val if neg else val); r.setdefault("change_approx", int(approx))
            else:
                if "level_bp" not in r:  # 'as much as' earlier in the sentence = intraday peak, so the level is flagged too
                    r["level_bp"], r["level_approx"] = val, int(approx or bool(re.search(r"as much as", s[:m.start()], re.I)))
        rd, basis = refers(s, pdate)
        if basis.startswith("post date") and last_day: rd, basis = last_day[0], last_day[1] + " (earlier in the post)"
        elif not basis.startswith("post date"): last_day = (rd, basis)
        tenor = "5y" if re.search(r"\b5[\s-]?(year|yr|y)\b|five[\s-]year", s, re.I) else "unspecified"
        for tk, r in recs.items():
            if "level_bp" not in r: continue
            out.append({"ticker": tk, "role": ROLE.get(tk), "tenor": tenor, "refers_date": rd, "date_basis": basis,
                        "post_date_et": pdate.isoformat(), "record": int(bool(re.search(r"\brecord\b", s, re.I))),
                        "snippet": s.strip()[:240], **r})
    return out

X_DAY_CAP = 0.30          # this job's own daily ceiling; x-on-surge keeps reserve_other_usd = 0.30 out of its allowance
X_MONTH_CAP_TOTAL = 209.0  # combined (x-on-surge + this job) month ceiling, under the $220 cap (XSENT 10/26: was 95 under $100)
X_DAY_CAP_TOTAL = 4.75    # combined day ceiling, under the $5 cap
POST_USD = 0.005
def xq():
    fa = " OR ".join(f"from:{a}" for a in DATA_ACCOUNTS)
    return [("data_accts", f"({fa}) (CDS OR \"default swap\" OR \"default swaps\") -is:retweet", 25, 30),
            ("neocloud_orcl", "(\"credit default swap\" OR \"credit default swaps\" OR \"5-year CDS\" OR \"CDS spread\" OR \"CDS spreads\") "
             "(CoreWeave OR $CRWV OR Oracle OR $ORCL OR Nebius OR IREN OR \"Applied Digital\" OR TeraWulf OR \"Cipher Mining\" OR \"Core Scientific\") "
             "\"basis points\" -is:retweet lang:en", 15, 10),
            ("megacap", "(\"credit default swap\" OR \"credit default swaps\" OR \"5-year CDS\" OR \"CDS spread\") "
             "(Meta OR Amazon OR Alphabet OR Google OR Microsoft OR Nvidia) \"basis points\" -is:retweet lang:en", 10, 10)]
def x_budget_ok(led, worst):
    surge = jload(XSTATE / "budget.json", {}); today = NOW.strftime("%Y-%m-%d"); mon = NOW.strftime("%Y-%m")
    sd = float(surge.get("day_spent") or 0) if surge.get("day_pt") == today else 0.0
    sm = float(surge.get("month_spent") or 0)
    if (H / "oid-data/state/x/STOP").exists(): return False, "kill file"
    if led["day_spent"] + worst > X_DAY_CAP + 1e-9: return False, f"own day cap ${X_DAY_CAP:.2f}"
    if sd + led["day_spent"] + worst > X_DAY_CAP_TOTAL: return False, f"combined day ${sd + led['day_spent']:.3f} + ${worst:.3f} > ${X_DAY_CAP_TOTAL}"
    if sm + led["month_spent"] + worst > X_MONTH_CAP_TOTAL: return False, "combined month cap"
    return True, "ok"
def x_prints(stt, backfill):
    log = []; rows = []
    cfg = jload(H / "oid-data/config/x-on-surge-config.json", {})
    tp = Path(os.path.expanduser((cfg.get("credentials") or {}).get("x_bearer_token_path", "")))
    tok = tp.read_text().strip() if tp.is_file() else None
    led = jload(LEDGER, {}); today = NOW.strftime("%Y-%m-%d"); mon = NOW.strftime("%Y-%m")
    if led.get("day_pt") != today: led.update(day_pt=today, day_spent=0.0, requests_day=0)
    if led.get("month") != mon: led.update(month=mon, month_spent=0.0)
    led.setdefault("calls", [])
    if not tok: return rows, ["no X token file"], led
    ucache = (jload(XSTATE / "user_cache.json", {}).get("users") or {})
    since = stt.setdefault("x_since_id", {})
    for qid, q, mr_daily, mr_back in xq():
        mr = mr_back if backfill else mr_daily
        room = min(X_DAY_CAP - led["day_spent"], X_DAY_CAP_TOTAL)
        while mr > 10 and mr * POST_USD > room + 1e-9: mr -= 5
        ok, why = x_budget_ok(led, mr * POST_USD)
        if not ok: log.append(f"{qid}: skipped ({why})"); continue
        p = {"query": q, "max_results": str(mr), "sort_order": "recency", "tweet.fields": "created_at,author_id,note_tweet"}
        if since.get(qid) and not backfill: p["since_id"] = since[qid]
        else: p["start_time"] = (datetime.now(UTC) - timedelta(days=7) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = "https://api.x.com/2/tweets/search/recent?" + urllib.parse.urlencode(p)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "User-Agent": "oid-name-credit/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r: body = json.loads(r.read().decode()); status = r.status
        except urllib.error.HTTPError as e: body, status = {}, e.code
        except Exception as e: body, status = {}, type(e).__name__
        data = body.get("data") or []; cost = round(len(data) * POST_USD, 4)
        led["day_spent"] = round(led["day_spent"] + cost, 4); led["month_spent"] = round(led["month_spent"] + cost, 4); led["requests_day"] += 1
        led["calls"] = (led["calls"] + [{"pt": NOW.strftime("%Y-%m-%d %H:%M"), "q": qid, "status": status, "posts": len(data), "usd": cost}])[-200:]
        log.append(f"{qid}: http {status}, {len(data)} posts, ${cost:.3f}")
        if body.get("meta", {}).get("newest_id"): since[qid] = max(since.get(qid, "0"), body["meta"]["newest_id"], key=int)
        for t in data:
            text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
            au = KNOWN_USERS.get(t.get("author_id")) or (ucache.get(t.get("author_id")) or {}).get("username")
            for r in parse_post(text, t["created_at"]):
                r.update(source_quality="secondhand_x", post_id=t["id"], author=au, author_id=t.get("author_id"), data_account=int(bool(au and au in DATA_ACCOUNTS)),
                         post_created_utc=t["created_at"], post_url=f"https://x.com/{au or 'i'}/status/{t['id']}" if au else f"https://x.com/i/status/{t['id']}",
                         query_id=qid, fetched_pt=NOW.strftime("%Y-%m-%d %H:%M"))
                rows.append(r)
    # authors: posts that produced rows but whose author isn't cached -> one batch /2/users call (budgeted $0.01/user)
    old = rd(OUT / "cds_x_prints.csv"); need = sorted({r["author_id"] for r in rows + old if r.get("author_id") and not r.get("author")
                                                      and r["author_id"] not in KNOWN_USERS and not (ucache.get(r["author_id"]) or {}).get("username")})[:20]
    own = jload(OUT / "x_users.json", {})
    need = [u for u in need if u not in own]
    if need:
        ok, why = x_budget_ok(led, len(need) * 0.01)
        if ok:
            req = urllib.request.Request("https://api.x.com/2/users?" + urllib.parse.urlencode({"ids": ",".join(need), "user.fields": "username"}),
                                         headers={"Authorization": f"Bearer {tok}", "User-Agent": "oid-name-credit/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=25) as r: ub = json.loads(r.read().decode())
                us = ub.get("data") or []; cost = round(len(us) * 0.01, 4)
                for u in us: own[u["id"]] = u["username"]
                led["day_spent"] = round(led["day_spent"] + cost, 4); led["month_spent"] = round(led["month_spent"] + cost, 4); led["requests_day"] += 1
                led["calls"] = (led["calls"] + [{"pt": NOW.strftime("%Y-%m-%d %H:%M"), "q": "users", "status": 200, "users": len(us), "usd": cost}])[-200:]
                log.append(f"users: {len(us)} authors, ${cost:.3f}"); jsave(OUT / "x_users.json", own)
            except Exception as e: log.append(f"users: {type(e).__name__}")
        else: log.append(f"users: skipped ({why})")
    def fill(r):
        au = r.get("author") or KNOWN_USERS.get(r.get("author_id")) or own.get(r.get("author_id")) or (ucache.get(r.get("author_id")) or {}).get("username")
        if au:
            r["author"] = au; r["post_url"] = f"https://x.com/{au}/status/{r['post_id']}"; r["data_account"] = int(au in DATA_ACCOUNTS)
        r["source_quality"] = "secondhand_x"
        return r
    rows = [fill(r) for r in rows] + [fill(dict(r)) for r in old if not r.get("author") or not r.get("source_quality")]
    jsave(LEDGER, led)
    return rows, log, led

# ---- main ---------------------------------------------------------------------------------------------------------------
def main():
    a = set(sys.argv[1:]); backfill = "--backfill" in a; t0 = time.time()
    stt = jload(STATE, {}); status = {}
    if "--x-only" not in a:
        try:
            br, lg = bonds(); ad, tot = upsert_csv(OUT / "bond_yields.csv", BD_COLS, br, lambda r: (r["trade_date"], r["cusip"], r["ticker"]))
            status["bonds"] = {"ok": bool(br), "rows_today": len(br), "new": ad, "total": tot, "log": lg}
        except Exception as e: status["bonds"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        try:
            dr, lg = dtcc(stt, 35 if backfill or not stt.get("dtcc_done") else 6)
            ad, tot = upsert_csv(OUT / "cds_dtcc_trades.csv", DT_COLS, dr, lambda r: r["dissemination_id"])
            dtcc_daily(); status["dtcc"] = {"ok": True, "new_trades": ad, "total": tot, "slices": lg[-8:]}
        except Exception as e: status["dtcc"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    led = jload(LEDGER, {})
    if "--no-x" not in a:
        try:
            xr, lg, led = x_prints(stt, backfill)
            ad, tot = upsert_csv(OUT / "cds_x_prints.csv", X_COLS, xr, lambda r: (r["post_id"], r["ticker"], str(r["level_bp"])))
            status["x"] = {"ok": True, "parsed": len(xr), "new": ad, "total": tot, "log": lg}
        except Exception as e: status["x"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    jsave(STATE, stt)
    write_latest(status, led, t0)
def rd(p):
    if not p.exists(): return []
    with open(p, newline="") as f: return list(csv.DictReader(f))
def write_latest(status, led, t0):
    L = {"schema": "oid-name-credit/1", "built_pt": NOW.strftime("%Y-%m-%d %-I:%M %p PT"), "research_only": True, "roles": ROLE,
         "backers_note": "NVDA (10% CRWV stake + capacity backstop) and GOOGL tagged 'backer' to compare their CDS with CRWV's.",
         "cds_dtcc": {}, "cds_x": {}, "bonds": {}, "status": status,
         "source_quality": {"cds_dtcc": "firsthand_dtcc (DTCC SBSDR public trade reports)", "cds_x": "secondhand_x (levels quoted in X posts; check the link)",
                            "bonds": "firsthand_finra (FINRA TRACE last prints, via Kilambi News pages)"},
         "x_spend": {k: led.get(k) for k in ("day_pt", "day_spent", "month", "month_spent", "requests_day")},
         "files": {k: str(OUT / k) for k in ("cds_dtcc_trades.csv", "cds_dtcc_daily.csv", "cds_x_prints.csv", "bond_yields.csv")},
         "notes": ["DTCC = DTCC SBSDR public dissemination (SEC security-based swaps, end-of-day cumulative slice, free, no key). "
                   "cds5y_bp = median quoted spread of on-the-run 5y trades that day, else median spread implied from upfront "
                   "(exact-notional trades only; flat-hazard, 4% rate, 40% recovery). Notionals above $5M are capped in the public record.",
                   "X = levels quoted in posts; refers_date resolves 'on Wednesday' etc. against the post's ET date; *_approx=1 for '~', 'as much as', 'about'.",
                   "Bonds = Kilambi News leverage pages, built from the FINRA TRACE tape. CRWV rows use the per-bond page (last trade, YTW, spread to "
                   "Treasury); others use the issuer table price with a 30/360 YTM computed here (ignores calls and conversion)."]}
    dd = rd(OUT / "cds_dtcc_daily.csv")
    for tk in ROLE:
        x = [r for r in dd if r["ticker"] == tk and r["cds5y_bp"]]
        if x: L["cds_dtcc"][tk] = {"date": x[-1]["date"], "cds5y_bp": float(x[-1]["cds5y_bp"]), "method": x[-1]["method"], "source_quality": "firsthand_dtcc",
                                   "n_trades_5y": int(x[-1]["n_trades_5y"]), "prev": ({"date": x[-2]["date"], "cds5y_bp": float(x[-2]["cds5y_bp"])} if len(x) > 1 else None),
                                   "series": [[r["date"], float(r["cds5y_bp"])] for r in x[-30:]]}
    xp = rd(OUT / "cds_x_prints.csv")
    for tk in ROLE:
        x = sorted([r for r in xp if r["ticker"] == tk], key=lambda r: (r["refers_date"], r["post_created_utc"]))
        if x: r = x[-1]; L["cds_x"][tk] = {k: r.get(k) for k in ("source_quality", "refers_date", "date_basis", "post_date_et", "level_bp", "level_approx", "change_bp", "change_approx", "prior_bp", "author", "post_url", "tenor", "record")}
    bd = rd(OUT / "bond_yields.csv")
    for tk in KIL:
        x = [r for r in bd if r["ticker"] == tk]
        if not x: continue
        last = max(r["trade_date"] for r in x); cur = [r for r in x if r["trade_date"] == last or r["run_date"] == max(z["run_date"] for z in x)]
        seen = {}
        for r in sorted(cur, key=lambda r: r["trade_date"]): seen[r["cusip"]] = r
        L["bonds"][tk] = [{k: r.get(k) for k in ("source_quality", "trade_date", "last_trade_et", "cusip", "description", "coupon", "maturity", "price", "yield_pct", "yield_type", "spread_tsy_bp", "url")}
                          for r in sorted(seen.values(), key=lambda r: r["maturity"])][:20]
    L["elapsed_s"] = round(time.time() - t0, 1)
    jsave(OUT / "latest.json", L)
    # MIRROR 10/22: publish a copy into the desk data-API tree (catalog group "credit") so the box mirror_poller pulls it to /workspace/oid-shared/credit/
    try:
        import shutil
        MD = H / "oid-desk/desk/market-data/latest/credit"; MD.mkdir(parents=True, exist_ok=True)
        for src, dst in ((OUT / "latest.json", "name-credit-latest.json"), (OUT / "bond_yields.csv", "bond_yields.csv"),
                         (OUT / "cds_dtcc_daily.csv", "cds_dtcc_daily.csv"), (OUT / "cds_x_prints.csv", "cds_x_prints.csv")):
            if src.is_file():
                tmp = MD / ("." + dst + ".tmp"); shutil.copyfile(src, tmp); tmp.replace(MD / dst)
    except Exception as e:  # noqa: BLE001 - never fail name-credit over the mirror copy
        print(f"name-credit mirror copy failed: {type(e).__name__}: {e}", flush=True)
    c = L["cds_dtcc"].get("CRWV", {}); o = L["cds_dtcc"].get("ORCL", {})
    print(f"[{NOW:%Y-%m-%d %H:%M %Z}] name-credit: dtcc CRWV {c.get('cds5y_bp')} ({c.get('date')}) ORCL {o.get('cds5y_bp')} ({o.get('date')}); "
          f"x {status.get('x', {}).get('log')}; bonds {status.get('bonds', {}).get('rows_today')}; {L['elapsed_s']}s", flush=True)
if __name__ == "__main__": main()
