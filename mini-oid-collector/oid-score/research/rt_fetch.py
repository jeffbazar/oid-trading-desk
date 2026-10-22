"""Research (read-only): bellwether read-through data. Alpaca SIP daily bars since 2023, first 30-min RTH bar on each
reaction day, and tonight's extended-hours snapshot. Uses optflow's REST helper (keys never printed)."""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path.home() / "oid-optflow")); sys.path.insert(0, str(Path.home() / "oid-score"))
import optflow as OF
import pattern_io as IO
H = Path.home(); P = H / "oid-data/patterns"; ET = ZoneInfo("America/New_York")
uni = IO.universe()
syms = sorted({s for s, _, _ in uni} | {"SMH", "QQQ", "SPY"} | {"LRCX","AMAT","KLAC","ASML","TSM","MU","NVDA","AMD","AVGO","META","MSFT","GOOG","AMZN","ORCL","SMCI"})
tiers = {s: t for s, t, _ in uni}
def get(path, p):
    for k in range(5):
        try: return OF._get(path, p)
        except Exception: time.sleep(2 + 3 * k)
    raise RuntimeError("fetch failed " + path)
def bars(ch, tf, start, end):
    out = {}; tok = None
    while True:
        p = {"symbols": ",".join(ch), "timeframe": tf, "start": start, "end": end, "limit": 10000, "feed": "sip", "adjustment": "all"}
        if tok: p["page_token"] = tok
        d = get("/v2/stocks/bars", p)
        for s, bs in (d.get("bars") or {}).items(): out.setdefault(s, []).extend([[b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bs])
        tok = d.get("next_page_token")
        if not tok: return out
t0 = time.time()
D = {}
with ThreadPoolExecutor(6) as ex:
    for r in ex.map(lambda c: bars(c, "1Day", "2023-01-01T00:00:00Z", "2026-10-22T00:00:00Z"), [syms[i:i + 20] for i in range(0, len(syms), 20)]): D.update(r)
print("daily", len(D), f"{time.time()-t0:.0f}s", flush=True)
# reaction days: label -> reaction date; both candidates when time unknown
ev = json.loads((P / "bw-earnings.json").read_text())
days = sorted({b[0] for b in D["SPY"]})
rx = set()
for bw, es in ev.items():
    for e in es:
        d = e["date"]
        if d >= "2026-10-21": continue
        import bisect
        j = bisect.bisect_left(days, d)
        if j >= len(days): continue
        if days[j] != d: rx.add(days[j]); continue
        if e.get("time") == "premarket": rx.add(d)
        else:
            if j + 1 < len(days): rx.add(days[j + 1])
            if e.get("time") != "postmarket": rx.add(d)
rx = sorted(rx)
def first30(day):
    o = datetime.fromisoformat(day + "T09:30:00").replace(tzinfo=ET)
    out = {}
    for i in range(0, len(syms), 110):
        ch = syms[i:i + 110]; tok = None
        while True:
            p = {"symbols": ",".join(ch), "timeframe": "30Min", "start": o.isoformat(), "end": (o + timedelta(minutes=29)).isoformat(),
                 "limit": 10000, "feed": "sip", "adjustment": "all"}
            if tok: p["page_token"] = tok
            d = get("/v2/stocks/bars", p)
            for s, bs in (d.get("bars") or {}).items():
                if bs: out[s] = [bs[0]["o"], bs[0]["h"], bs[0]["l"], bs[0]["c"]]
            tok = d.get("next_page_token")
            if not tok: break
    return day, out
F30 = {}
with ThreadPoolExecutor(6) as ex:
    for day, o in ex.map(first30, rx): F30[day] = o
print("first30", len(F30), f"{time.time()-t0:.0f}s", flush=True)
snap = {}
for i in range(0, len(syms), 100):
    d = get("/v2/stocks/snapshots", {"symbols": ",".join(syms[i:i + 100]), "feed": "sip"})
    for s, v in d.items():
        if not v: continue
        lt = v.get("latestTrade") or {}; db = v.get("dailyBar") or {}; lq = v.get("latestQuote") or {}
        snap[s] = {"last": lt.get("p"), "last_t": lt.get("t"), "close": db.get("c"), "bar_t": db.get("t"), "bid": lq.get("bp"), "ask": lq.get("ap")}
(P / "readthrough-data-20261021.json").write_text(json.dumps({"daily": D, "first30": F30, "snap": snap, "tiers": tiers,
    "built": time.strftime("%Y-%m-%d %H:%M %Z")}))
print("snap", len(snap), f"{time.time()-t0:.0f}s")
