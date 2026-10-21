"""Read-only: ATM weekly call/put snapshot (Alpaca OPRA, already-subscribed feed) per ticker for the options-cost study.
Uses optflow's own REST helper (keys never printed). Writes ~/oid-data/patterns/opt-cost-snap-20261021.json."""
import json, sys, time, re
from pathlib import Path
sys.path.insert(0, str(Path.home() / "oid-optflow"))
import optflow as OF
H = Path.home()
syms = set()
for ln in open(H / "oid-data/patterns/backtest-grades.jsonl"):
    if '"interval":"1m"' in ln and ('"higher_low"' in ln or '"lower_high"' in ln):
        syms.add(json.loads(ln)["ticker"])
syms = sorted(syms)
spots = {}
for i in range(0, len(syms), 50):
    ch = syms[i:i + 50]
    try:
        d = OF._get("/v2/stocks/snapshots", {"symbols": ",".join(ch), "feed": "sip"})
        for s, v in d.items():
            px = ((v or {}).get("dailyBar") or {}).get("c") or ((v or {}).get("latestTrade") or {}).get("p")
            if px: spots[s] = px
    except Exception as e:
        print("spot err", type(e).__name__, e)
OCC = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
out = {}
for s in syms:
    S = spots.get(s)
    if not S: continue
    params = {"feed": "opra", "limit": 1000, "expiration_date_gte": "2026-10-23", "expiration_date_lte": "2026-10-30",
              "strike_price_gte": f"{S*0.95:.2f}", "strike_price_lte": f"{S*1.05:.2f}"}
    rows = []
    try:
        tok = None
        while True:
            if tok: params["page_token"] = tok
            d = OF._get(f"/v1beta1/options/snapshots/{s}", params)
            for c, v in (d.get("snapshots") or {}).items():
                m = OCC.match(c)
                if not m: continue
                q = v.get("latestQuote") or {}
                rows.append({"c": c, "exp": m.group(2), "cp": m.group(3), "k": int(m.group(4)) / 1000, "bid": q.get("bp"),
                             "ask": q.get("ap"), "qt": q.get("t"), "greeks": v.get("greeks"), "iv": v.get("impliedVolatility")})
            tok = d.get("next_page_token")
            if not tok: break
    except Exception as e:
        print("opt err", s, type(e).__name__, str(e)[:120]); continue
    exps = sorted({r["exp"] for r in rows})
    rec = {"spot": S}
    for tag, ex in (("w1", exps[0] if exps else None), ("w2", exps[-1] if len(exps) > 1 else None)):
        if not ex: continue
        for cp in "CP":
            cand = [r for r in rows if r["exp"] == ex and r["cp"] == cp and r["bid"] and r["ask"] and r["ask"] >= r["bid"] > 0]
            if not cand: continue
            r = min(cand, key=lambda r: abs(r["k"] - S))
            mid = (r["bid"] + r["ask"]) / 2
            rec[f"{tag}{cp}"] = {"c": r["c"], "exp": ex, "k": r["k"], "bid": r["bid"], "ask": r["ask"], "mid": round(mid, 4),
                                 "spread": round(r["ask"] - r["bid"], 4), "spread_pct_mid": round((r["ask"] - r["bid"]) / mid, 4),
                                 "spread_bp_und": round((r["ask"] - r["bid"]) / S * 1e4, 2), "qt": r["qt"],
                                 "theta": (r["greeks"] or {}).get("theta"), "delta": (r["greeks"] or {}).get("delta"),
                                 "iv": r["iv"]}
    out[s] = rec
    time.sleep(0.25)
doc = {"built": time.strftime("%Y-%m-%d %H:%M %Z"), "source": "Alpaca OPRA option snapshots (latestQuote = last NBBO, ~1:00 PM PT close Oct 21); greeks from Alpaca", "by_sym": out}
(H / "oid-data/patterns/opt-cost-snap-20261021.json").write_text(json.dumps(doc, indent=1))
print(len(syms), "syms,", len(spots), "spots,", len(out), "with chains")
