"""Task 4 (research, read-only): overnight vs intraday split, last 60 trading days, Alpaca SIP bars via optflow's REST helper.
Writes ~/oid-data/patterns/overnight-intraday-20261021.json. Keys never printed."""
import json, sys, time, math, statistics as st
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path.home() / "oid-optflow")); sys.path.insert(0, str(Path.home() / "oid-score"))
import optflow as OF
ET = ZoneInfo("America/New_York")
H = Path.home()
snap = json.loads((H / "oid-data/patterns/opt-cost-snap-20261021.json").read_text())["by_sym"]
syms = sorted(snap)
core = set(p.name[:-8] for p in (H / "oid-data").glob("**/core-bars-placeholder"))  # filled below
def fetch(tf, start):
    out = defaultdict(list)
    for i in range(0, len(syms), 40):
        ch = syms[i:i + 40]; tok = None
        while True:
            p = {"symbols": ",".join(ch), "timeframe": tf, "start": start, "end": "2026-10-21T21:00:00Z", "limit": 10000,
                 "feed": "sip", "adjustment": "split"}
            if tok: p["page_token"] = tok
            d = OF._get("/v2/stocks/bars", p)
            for s, bs in (d.get("bars") or {}).items(): out[s] += bs
            tok = d.get("next_page_token")
            if not tok: break
            time.sleep(0.2)
    return out
D = fetch("1Day", "2026-07-01T00:00:00Z")
M = fetch("30Min", "2026-07-01T00:00:00Z")
open30 = {}
for s, bs in M.items():
    for b in bs:
        t = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if t.hour == 9 and t.minute == 30: open30[(s, t.strftime("%Y-%m-%d"))] = b
res = {}; days_all = set()
for s, bs in D.items():
    bs = [b for b in bs]
    rows = []
    for j in range(1, len(bs)):
        pc, o, c = bs[j - 1]["c"], bs[j]["o"], bs[j]["c"]
        day = bs[j]["t"][:10]
        rows.append((day, o / pc - 1, c / o - 1, (bs[j]["h"] - bs[j]["l"]) / o * 1e4, pc, o))
    rows = rows[-60:]
    if len(rows) < 40: continue
    days_all |= {r[0] for r in rows}
    on = [r[1] for r in rows]; idy = [r[2] for r in rows]
    cum_on = math.prod(1 + x for x in on) - 1; cum_id = math.prod(1 + x for x in idy) - 1
    abs_on = sum(abs(x) for x in on); abs_id = sum(abs(x) for x in idy)
    fol = fad = fill = gaps = 0; fol5 = fad5 = gaps5 = 0
    for day, g, _, _, pc, o in rows:
        b = open30.get((s, day))
        if not b or g == 0: continue
        gaps += 1; f = (b["c"] - o) * g > 0
        fol += f; fad += (not f)
        if (b["l"] <= pc) if g > 0 else (b["h"] >= pc): fill += 1
        if abs(g) >= 0.005:
            gaps5 += 1; fol5 += f; fad5 += (not f)
    res[s] = {"days": len(rows), "first": rows[0][0], "last": rows[-1][0], "cum_overnight": round(cum_on, 4), "cum_intraday": round(cum_id, 4),
              "cum_total": round(math.prod((1 + a) * (1 + b) for a, b in zip(on, idy)) - 1, 4),
              "share_abs_overnight": round(abs_on / (abs_on + abs_id), 4) if abs_on + abs_id else None,
              "med_gap_abs_bp": round(st.median(abs(x) * 1e4 for x in on), 1), "med_intraday_range_bp": round(st.median(r[3] for r in rows), 1),
              "med_intraday_abs_ret_bp": round(st.median(abs(x) * 1e4 for x in idy), 1),
              "gaps": gaps, "follow30": round(fol / gaps, 4) if gaps else None, "fade30": round(fad / gaps, 4) if gaps else None,
              "fill30": round(fill / gaps, 4) if gaps else None, "gaps_ge50bp": gaps5, "follow30_ge50bp": round(fol5 / gaps5, 4) if gaps5 else None,
              "sum_overnight_bp": round(sum(on) * 1e4, 1), "sum_intraday_bp": round(sum(idy) * 1e4, 1)}
import pattern_io as IO
tiers = {s: t for s, t, _ in IO.universe()}
def grp(keys):
    v = [res[k] for k in keys if k in res]
    if not v: return {}
    g = lambda f: round(st.median(x[f] for x in v if x[f] is not None), 4)
    tot_g = sum(x["gaps"] for x in v)
    return {"tickers": len(v), "med_cum_overnight": g("cum_overnight"), "med_cum_intraday": g("cum_intraday"),
            "mean_cum_overnight": round(st.mean(x["cum_overnight"] for x in v), 4), "mean_cum_intraday": round(st.mean(x["cum_intraday"] for x in v), 4),
            "n_overnight_gt_intraday": sum(x["cum_overnight"] > x["cum_intraday"] for x in v),
            "med_share_abs_overnight": g("share_abs_overnight"), "med_gap_abs_bp": g("med_gap_abs_bp"), "med_intraday_range_bp": g("med_intraday_range_bp"),
            "med_intraday_abs_ret_bp": g("med_intraday_abs_ret_bp"),
            "pooled_gaps": tot_g, "pooled_follow30": round(sum(x["follow30"] * x["gaps"] for x in v if x["gaps"]) / tot_g, 4),
            "pooled_fill30": round(sum(x["fill30"] * x["gaps"] for x in v if x["gaps"]) / tot_g, 4),
            "pooled_gaps_ge50bp": sum(x["gaps_ge50bp"] for x in v),
            "pooled_follow30_ge50bp": round(sum((x["follow30_ge50bp"] or 0) * x["gaps_ge50bp"] for x in v) / max(1, sum(x["gaps_ge50bp"] for x in v)), 4)}
doc = {"built": time.strftime("%Y-%m-%d %H:%M %Z"), "source": "Alpaca SIP daily + 30-min bars (split-adjusted); overnight = prior official close -> official open (includes pre/post); intraday = open -> close; follow30 = 9:30-10:00 ET bar close vs open in the gap direction; fill30 = first 30 min touches prior close",
       "days": [min(days_all), max(days_all)] if days_all else None,
       "group": {"all": grp(res), "core": grp([s for s in res if tiers.get(s) == "core"]), "sector": grp([s for s in res if tiers.get(s) == "wide"])},
       "by_ticker": res}
(H / "oid-data/patterns/overnight-intraday-20261021.json").write_text(json.dumps(doc, indent=1))
print(json.dumps(doc["group"], indent=1)); print(doc["days"], len(res))
