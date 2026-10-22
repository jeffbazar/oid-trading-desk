"""Research (read-only): fetch Alpaca SIP 5-min + daily bars for the core tickers and a 45-DTE OPRA snapshot.
Uses optflow's REST helper (keys never printed). Output: ~/oid-data/patterns/onhold-bars-20261021.json, onhold-snap45-20261021.json"""
import json, sys, time, re, math
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path.home() / "oid-optflow")); sys.path.insert(0, str(Path.home() / "oid-score"))
import optflow as OF
import pattern_io as IO
H = Path.home()
syms = [s for s, t, _ in IO.universe() if t == "core"]
def fetch(ch, tf, start):
    out = {}; tok = None
    while True:
        p = {"symbols": ",".join(ch), "timeframe": tf, "start": start, "end": "2026-10-21T21:00:00Z", "limit": 10000, "feed": "sip", "adjustment": "split"}
        if tok: p["page_token"] = tok
        for k in range(4):
            try: d = OF._get("/v2/stocks/bars", p); break
            except Exception as e:
                time.sleep(2 + 3 * k); d = None
        if d is None: raise RuntimeError("bars fetch failed")
        for s, bs in (d.get("bars") or {}).items():
            out.setdefault(s, []).extend([[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bs])
        tok = d.get("next_page_token")
        if not tok: return out
t0 = time.time()
BF = H / "oid-data/patterns/onhold-bars-20261021.json"
chunks = [syms[i:i + 4] for i in range(0, len(syms), 4)]
B5, BD = {}, {}
if BF.exists():
    _b = json.loads(BF.read_text()); B5, BD = _b["5m"], _b["1d"]
else:
  with ThreadPoolExecutor(6) as ex:
      for r in ex.map(lambda c: fetch(c, "5Min", "2026-07-15T00:00:00Z"), chunks): B5.update(r)
      for r in ex.map(lambda c: fetch(c, "1Day", "2026-07-01T00:00:00Z"), [syms[i:i + 20] for i in range(0, len(syms), 20)]): BD.update(r)
  BF.write_text(json.dumps({"5m": B5, "1d": BD}))
print("bars", len(B5), len(BD), sum(len(v) for v in B5.values()), f"{time.time()-t0:.0f}s", flush=True)
OCC = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
spots = {s: BD[s][-1][4] for s in BD if BD[s]}
snap = {}
def one(s):
    S = spots.get(s)
    if not S: return s, None
    p = {"feed": "opra", "limit": 1000, "type": "call", "expiration_date_gte": "2026-11-19", "expiration_date_lte": "2026-12-24",
         "strike_price_gte": f"{S*0.97:.2f}", "strike_price_lte": f"{S*1.20:.2f}"}
    rows, tok = [], None
    try:
        while True:
            if tok: p["page_token"] = tok
            d = OF._get(f"/v1beta1/options/snapshots/{s}", p)
            for c, v in (d.get("snapshots") or {}).items():
                m = OCC.match(c); q = v.get("latestQuote") or {}; g = v.get("greeks") or {}
                if m and q.get("bp") and q.get("ap") and q["ap"] >= q["bp"] > 0:
                    rows.append({"c": c, "exp": m.group(2), "k": int(m.group(4)) / 1000, "bid": q["bp"], "ask": q["ap"],
                                 "delta": g.get("delta"), "theta": g.get("theta"), "vega": g.get("vega"), "iv": v.get("impliedVolatility")})
            tok = d.get("next_page_token")
            if not tok: break
    except Exception as e:
        return s, {"err": type(e).__name__}
    if not rows: return s, None
    exps = sorted({r["exp"] for r in rows}, key=lambda e: abs((date(2000 + int(e[:2]), int(e[2:4]), int(e[4:6])) - date(2026, 10, 21)).days - 45))
    ex = exps[0]; R = [r for r in rows if r["exp"] == ex]
    atm = min(R, key=lambda r: abs(r["k"] - S))
    d35 = [r for r in R if r["delta"] and 0.30 <= r["delta"] <= 0.40]
    o35 = min(d35, key=lambda r: abs(r["delta"] - 0.35)) if d35 else None
    f = lambda r: None if not r else dict(r, mid=round((r["bid"] + r["ask"]) / 2, 4), spr_pct=round((r["ask"] - r["bid"]) / ((r["bid"] + r["ask"]) / 2), 4))
    return s, {"spot": S, "exp": ex, "atm": f(atm), "d35": f(o35)}
with ThreadPoolExecutor(4) as ex:
    for s, v in ex.map(one, syms): snap[s] = v
(H / "oid-data/patterns/onhold-snap45-20261021.json").write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M %Z"),
    "source": "Alpaca OPRA snapshots, ~45-DTE calls (Dec 4/5 2026 expiry), last NBBO of the 10/21 session", "by_sym": snap}, indent=1))
print("snap", sum(1 for v in snap.values() if v and v.get("atm")), "atm,", sum(1 for v in snap.values() if v and v.get("d35")), "d35", f"{time.time()-t0:.0f}s")
