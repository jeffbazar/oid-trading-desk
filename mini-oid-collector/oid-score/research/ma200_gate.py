#!/usr/bin/env python3
"""MA200-GATE (2026-10-24, Jeffrey): research-only replay of the LIVE direction score (score_lib.combine, v1.2-20261022)
split by each name's distance from its 200-day SMA. Reads archives only; nothing live is touched.

Inputs  ~/oid-data/archive/parquet/score_labels (kind=snap, 15 s rows, h300/h900/h1800 labels)
        ~/oid-data/score/episodes[-widefull]-YYYYMMDD.jsonl (scorecard holds)
        ~/oid-data/score/ma200-gate/sma200.json (200-day SMA from prior closes; source recorded in the file)
Output  ~/oid-data/score/ma200-gate/ma200-gate-results.{json,md}

dist = px / SMA200 - 1 at the row (price known live; SMA uses closes strictly before the session).
Buckets on |dist|: pinned < 1 %, near 1-2 %, off > 2 %; side above / below.
Trade dedupe: per symbol per day, a trade = the first 15 s snapshot of a run of same-sign nonzero score (a run ends when the
score goes to 0 or flips, or the snapshot gap is > 60 s). Primary count = NON-OVERLAPPING trades per horizon: a new run's
first snapshot is taken only if it starts >= horizon after the last taken trade on that symbol. P&L = directional move
(sign(score) * forward return) in bp to the horizon; the score has no stop/target, so this is not trade P&L with exits.
"""
import collections, json, math, os, statistics, sys
from pathlib import Path
import duckdb

D = Path.home() / "oid-data"
OUT = D / "score" / "ma200-gate"
HZ = (300, 900, 1800)
SETS = [("core", ["2026-10-21", "2026-10-22", "2026-10-23"], "live"),
        ("core", ["2026-10-19", "2026-10-20"], "replay"),
        ("wide_full", ["2026-10-21", "2026-10-22", "2026-10-23"], "live")]
SMA = json.load(open(OUT / "sma200.json"))["by_date"]


def bucket(d):
    a = abs(d)
    return "pinned<1%" if a < 0.01 else ("near1-2%" if a < 0.02 else "off>2%")


def load(profile, date, mode):
    cols = "symbol, t, score, px, " + ", ".join(f"h{h}_ret_bp, h{h}_full" for h in HZ)
    q = (f"select {cols} from read_parquet('{D}/archive/parquet/score_labels/date={date}/*.parquet') "
         f"where kind='snap' and mode='{mode}' and profile='{profile}' order by symbol, t")
    c = duckdb.connect(); r = c.execute(q); names = [x[0] for x in r.description]
    rows = []
    for v in r.fetchall():
        x = dict(zip(names, v)); s = SMA[date].get(x["symbol"]) or {}
        if not s.get("sma200") or not x["px"]:
            continue
        x["dist"] = x["px"] / s["sma200"] - 1; x["bucket"] = bucket(x["dist"]); x["side"] = "above" if x["dist"] >= 0 else "below"
        x["date"] = date; rows.append(x)
    return rows


def stats(xs):
    n = len(xs)
    if not n:
        return {"n": 0}
    return {"n": n, "hit": round(sum(1 for v in xs if v > 0) / n, 4), "mean_bp": round(sum(xs) / n, 2),
            "median_bp": round(statistics.median(xs), 2), "total_bp": round(sum(xs), 1)}


def dm(r, h, sgn=None):
    ret = r.get(f"h{h}_ret_bp")
    if ret is None or not r.get(f"h{h}_full"):
        return None
    s = sgn if sgn is not None else (1 if r["score"] > 0 else -1)
    return s * ret


def trades(rows, h):
    """non-overlapping first-snapshot-of-run trades at horizon h; also returns all run starts."""
    runs, taken = [], []
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["symbol"], r["date"])].append(r)
    for k, rs in by.items():
        prev_sign, prev_t, last_taken = 0, None, -1e18
        for r in rs:
            sg = (r["score"] > 0) - (r["score"] < 0)
            new = sg != 0 and (sg != prev_sign or (prev_t is not None and r["t"] - prev_t > 60))
            if new:
                runs.append(r)
                if r["t"] >= last_taken + h:
                    taken.append(r); last_taken = r["t"]
            prev_sign, prev_t = sg, r["t"]
    return runs, taken


GATES = {"no gate": lambda r: True, "gate: drop pinned<1%": lambda r: r["bucket"] != "pinned<1%",
         "gate: drop <2%": lambda r: r["bucket"] == "off>2%"}


def analyse(rows):
    res = {"rows": len(rows), "names": len({r["symbol"] for r in rows})}
    nz = [r for r in rows if r["score"]]
    # (a)/(b) row level
    rl = {}
    for h in HZ:
        tot_miss = sum(1 for r in nz if (dm(r, h) or 0) <= 0 and dm(r, h) is not None)
        tot = sum(1 for r in nz if dm(r, h) is not None)
        for b in ("pinned<1%", "near1-2%", "off>2%"):
            xs = [dm(r, h) for r in nz if r["bucket"] == b and dm(r, h) is not None]
            st = stats(xs); miss = sum(1 for v in xs if v <= 0)
            st["row_share"] = round(len(xs) / tot, 4) if tot else None
            st["miss_share"] = round(miss / tot_miss, 4) if tot_miss else None
            rl.setdefault(f"{h // 60}m", {})[b] = st
        for sd in ("above", "below"):
            for b in ("pinned<1%", "near1-2%", "off>2%"):
                xs = [dm(r, h) for r in nz if r["side"] == sd and r["bucket"] == b and dm(r, h) is not None]
                rl[f"{h // 60}m"][f"{sd} {b}"] = stats(xs)
        # with-trend: score direction agrees with side of the 200-day (long above / short below)
        for lab, f in (("with 200d side", lambda r: (r["score"] > 0) == (r["dist"] >= 0)),
                       ("against 200d side", lambda r: (r["score"] > 0) != (r["dist"] >= 0))):
            rl[f"{h // 60}m"][lab] = stats([dm(r, h) for r in nz if f(r) and dm(r, h) is not None])
    res["rows_by_bucket"] = rl
    # (c) trades
    tr = {}
    for h in HZ:
        runs, taken = trades(rows, h)
        hz = f"{h // 60}m"; tr[hz] = {"run_starts": len(runs)}
        for g, f in GATES.items():
            sel = [r for r in taken if f(r)]
            xs = [dm(r, h) for r in sel if dm(r, h) is not None]
            st = stats(xs)
            st["trades_incl_unlabelled"] = len(sel)
            st["short_all_same_trades"] = stats([dm(r, h, -1) for r in sel if dm(r, h, -1) is not None])
            st["long_all_same_trades"] = stats([dm(r, h, 1) for r in sel if dm(r, h, 1) is not None])
            tr[hz][g] = st
        base = tr[hz]["no gate"]["n"]
        for g in list(GATES)[1:]:
            tr[hz][g]["pct_trades_removed"] = round(1 - tr[hz][g]["n"] / base, 4) if base else None
        for b in ("pinned<1%", "near1-2%", "off>2%"):
            tr[hz]["only " + b] = stats([dm(r, h) for r in taken if r["bucket"] == b and dm(r, h) is not None])
    res["trades"] = tr
    return res


def episodes(tag, days):
    """scorecard holds: start-to-stop gain_bp (scorecard definition), bucketed by dist at start_px."""
    out = {}
    eps = []
    for d in days:
        p = D / "score" / f"episodes{tag}-{d.replace('-', '')}.jsonl"
        if not p.exists():
            continue
        for ln in open(p):
            e = json.loads(ln)
            if not e.get("dir") or e.get("gain_bp") is None or e.get("mode", "live") != "live":
                continue
            s = (SMA[d].get(e["sym"]) or {}).get("sma200")
            if not s or not e.get("start_px"):
                continue
            e["bucket"] = bucket(e["start_px"] / s - 1); eps.append(e)
    tot = len(eps); miss = sum(1 for e in eps if e["gain_bp"] <= 0)
    for g, f in (("no gate", lambda e: True), ("gate: drop pinned<1%", lambda e: e["bucket"] != "pinned<1%"),
                 ("gate: drop <2%", lambda e: e["bucket"] == "off>2%"), ("only pinned<1%", lambda e: e["bucket"] == "pinned<1%"),
                 ("only near1-2%", lambda e: e["bucket"] == "near1-2%"), ("only off>2%", lambda e: e["bucket"] == "off>2%")):
        xs = [e["gain_bp"] for e in eps if f(e)]
        st = stats(xs); st["share_of_holds"] = round(len(xs) / tot, 4) if tot else None
        st["miss_share"] = round(sum(1 for v in xs if v <= 0) / miss, 4) if miss else None
        out[g] = st
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    R = {"version": "ma200gate-v1-20261024", "sma_source": json.load(open(OUT / "sma200.json"))["source"], "sets": []}
    # SMA cross-check vs the mini's own Alpaca daily bars (core names, no split in the window)
    c = duckdb.connect()
    bars = c.execute(f"select symbol, trade_date, close from read_parquet('{D}/archive/parquet/bars_1d/**/*.parquet', hive_partitioning=1) "
                     "where trade_date < '2026-10-23' order by symbol, trade_date").fetchall()
    bs = collections.defaultdict(list)
    for s, d, cl in bars:
        bs[s].append(cl)
    diffs = []
    for s, cl in bs.items():
        if len(cl) < 200 or any(cl[i] / cl[i - 1] > 1.6 or cl[i] / cl[i - 1] < 0.6 for i in range(1, len(cl))):
            continue
        y = (SMA["2026-10-23"].get(s) or {}).get("sma200")
        if y:
            diffs.append((abs(sum(cl[-200:]) / 200 / y - 1), s))
    diffs.sort()
    R["sma_crosscheck_vs_mini_alpaca_bars_1d"] = {"names": len(diffs), "median_rel_diff": round(statistics.median(d for d, _ in diffs), 5) if diffs else None,
                                                  "max_rel_diff": [round(diffs[-1][0], 5), diffs[-1][1]] if diffs else None}
    for prof, days, mode in SETS:
        allrows = []
        S = {"profile": prof, "mode": mode, "days": days, "by_day": {}}
        for d in days:
            rows = load(prof, d, mode); allrows += rows
            a = analyse(rows)
            a["bucket_mix_names"] = dict(collections.Counter(bucket(SMA[d][s]["prev_close"] / SMA[d][s]["sma200"] - 1)
                                                             for s in {r["symbol"] for r in rows}))
            S["by_day"][d] = a
            print(prof, mode, d, "rows", len(rows), file=sys.stderr)
        S["pooled"] = analyse(allrows)
        if mode == "live":
            tag = "" if prof == "core" else "-widefull"
            S["holds_scorecard_def"] = episodes(tag, days)
            S["holds_by_day"] = {d: episodes(tag, [d]) for d in days}
        R["sets"].append(S)
    # per name/day distance table
    R["dist_by_name_day"] = {d: {s: (round(v["prev_close"] / v["sma200"] - 1, 4) if v.get("sma200") else None) for s, v in SMA[d].items()} for d in SMA}
    (OUT / "ma200-gate-results.json").write_text(json.dumps(R, indent=1))
    print("wrote", OUT / "ma200-gate-results.json", file=sys.stderr)


if __name__ == "__main__":
    main()
