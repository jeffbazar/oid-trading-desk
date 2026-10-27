"""X sentiment SHADOW: daily chatter-spike vs price correlation report.

Display/research only. Nothing in the live direction score, alerts or orders reads these files.

Spikes are rebuilt from the feed's own dated snapshots (~/oid-data/sentiment/x/YYYYMMDD.jsonl), which is more robust
than a separate intraday logger (no extra job, no missed writes, re-runnable). Same rules as the live page panel:
  spike  = chatter_z >= 2 or chatter_ratio >= 2x   (red on the panel)
  watch  = chatter_ratio >= 1.5x                   (amber on the panel; logged so the 1.5-2x bucket can be graded)
  color  = net > +0.15 green, < -0.15 red, else gray (gray also = no tone sample)
Episode: the first spiking snapshot per ticker opens an episode; it closes on the next non-spiking snapshot of that
ticker or after a >35 min gap with no snapshot. Only the first row of an episode is graded.
Tone: the spike row's net if it was sampled, else the ticker's last sampled net from the prior 60 min (marked *).
Prices: collector 1m Alpaca SIP bars (~/oid-desk/desk/cache/bars/store/live/<SYM>-1m-<YYYYMMDD>.jsonl).
  price at spike = close of the last bar that ended at or before the snapshot time.
  1h  = +60 min (cut at the close and flagged 'cut' if the close comes first; 'open' if the data isn't there yet).
  close = last bar ending at or before the session close (13:00 PT, 10:00 PT on early-close days).
  up/down = beyond +/-0.05%; anything inside is 'flat' and left out of hit-rate denominators.
Writes corr-YYYYMMDD.md and corr-YYYYMMDD.json next to the feed. Run before the close => PRELIMINARY (partial).
Rolling section pools the last 10 final (non-partial) corr-*.json files plus today.
"""
import argparse, datetime as dt, json, os, statistics, sys
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HOME = Path.home()
DATA = Path(os.environ.get("OID_DATA_ROOT", str(HOME / "oid-data")))
OUT = DATA / "sentiment/x"
BARS = HOME / "oid-desk/desk/cache/bars/store/live"
VERSION = "x-sentiment-corr-v1"
Z_SPIKE, R_SPIKE, R_WATCH = 2.0, 2.0, 1.5
GREEN, RED = 0.15, -0.15
FLAT_PCT = 0.05
GAP_S = 35 * 60
TONE_CARRY_S = 60 * 60
ROLL_DAYS = 10
BUCKETS = ["1.5-2x", "2-3x", "3x+", "z-only"]
COLORS = ["green", "red", "gray"]

# NYSE full-day holidays and 10:00 PT early closes (2026-2027). Extend yearly.
HOLIDAYS = {"20260101", "20260119", "20260216", "20260403", "20260525", "20260619", "20260703", "20260907",
            "20261126", "20261225", "20270101", "20270118", "20270215", "20270326", "20270531", "20270618",
            "20270705", "20270906", "20271125", "20271224"}
EARLY_CLOSE = {"20261127", "20261224", "20271126"}


def pt(t):
    return dt.datetime.fromtimestamp(t, PT)


def session(ymd):
    d = dt.datetime.strptime(ymd, "%Y%m%d").replace(tzinfo=PT)
    o = d.replace(hour=6, minute=30).timestamp()
    c = d.replace(hour=10 if ymd in EARLY_CLOSE else 13, minute=0).timestamp()
    return o, c


def load_bars(sym, ymd):
    p = BARS / f"{sym}-1m-{ymd}.jsonl"
    bars = {}
    if not p.exists(): return []
    for line in open(p):
        try:
            b = json.loads(line)
            t = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).timestamp()
            bars[t] = float(b["c"])
        except Exception: pass
    return sorted(bars.items())


def px_at(bars, t):
    best = None
    for s, c in bars:
        if s + 60 <= t: best = c
        else: break
    return best


def last_end(bars):
    return bars[-1][0] + 60 if bars else None


def pct(a, b):
    return None if (a is None or b is None or a == 0) else round((b / a - 1) * 100, 3)


def direction(m):
    if m is None: return None
    return "up" if m > FLAT_PCT else "down" if m < -FLAT_PCT else "flat"


def color_of(net):
    if net is None: return "gray"
    return "green" if net > GREEN else "red" if net < RED else "gray"


def bucket_of(ratio, z):
    r = ratio or 0
    if r >= 3: return "3x+"
    if r >= 2: return "2-3x"
    if r >= 1.5: return "1.5-2x"
    return "z-only"


def is_spike(r):
    z, q = r.get("chatter_z"), r.get("chatter_ratio")
    return (z is not None and z >= Z_SPIKE) or (q is not None and q >= R_WATCH)


def load_rows(ymd, o, c):
    src = OUT / f"{ymd}.jsonl"; rows = []
    if not src.exists(): return rows
    for line in open(src):
        try: r = json.loads(line)
        except Exception: continue
        st = str(r.get("status") or "")
        if r.get("tier") == "manual" or not (st == "ok" or st.startswith("http:200")): continue
        if r.get("chatter_ratio") is None and r.get("chatter_z") is None: continue
        if not (o <= r.get("t", 0) < c): continue
        rows.append(r)
    return rows


def find_spikes(rows):
    by = {}
    for r in rows: by.setdefault(r["sym"], []).append(r)
    out = []
    for sym, rs in by.items():
        rs.sort(key=lambda r: r["t"])
        tone = []  # (t, net) sampled
        ep = None; prev_t = None
        for r in rs:
            if r.get("net") is not None and r.get("sampled") is not False: tone.append((r["t"], r["net"]))
            gap = prev_t is not None and r["t"] - prev_t > GAP_S
            if ep is not None and (gap or not is_spike(r)): ep = None
            if is_spike(r):
                if ep is None:
                    net, carried = r.get("net"), False
                    if net is None or r.get("sampled") is False:
                        prior = [n for (t, n) in tone if r["t"] - TONE_CARRY_S <= t <= r["t"]]
                        net, carried = (prior[-1], True) if prior else (None, False)
                        if net is not None and r.get("net") is not None and r.get("sampled") is not False: carried = False
                    ep = {"sym": sym, "t": r["t"], "t_pt": pt(r["t"]).strftime("%H:%M"), "ratio": r.get("chatter_ratio"),
                          "z": r.get("chatter_z"), "count": r.get("count"), "base": r.get("base_count"),
                          "net": None if net is None else round(net, 3), "tone_carried": carried,
                          "tone_sampled": net is not None, "color": color_of(net),
                          "level": "spike" if ((r.get("chatter_z") or 0) >= Z_SPIKE or (r.get("chatter_ratio") or 0) >= R_SPIKE) else "watch",
                          "bucket": bucket_of(r.get("chatter_ratio"), r.get("chatter_z")), "snapshots": 1,
                          "peak_ratio": r.get("chatter_ratio"), "peak_z": r.get("chatter_z")}
                    out.append(ep)
                else:
                    ep["snapshots"] += 1
                    if (r.get("chatter_ratio") or 0) > (ep["peak_ratio"] or 0): ep["peak_ratio"] = r.get("chatter_ratio")
                    if (r.get("chatter_z") or 0) > (ep["peak_z"] or 0): ep["peak_z"] = r.get("chatter_z")
            prev_t = r["t"]
    return sorted(out, key=lambda e: (e["t"], e["sym"]))


def grade(spikes, ymd, close_t, now_t):
    cache = {}
    def bars(s):
        if s not in cache: cache[s] = load_bars(s, ymd)
        return cache[s]
    qqq = bars("QQQ")
    for e in spikes:
        b = bars(e["sym"]); e["px"] = px_at(b, e["t"])
        end = min(close_t, last_end(b) or 0, now_t)
        tgt = e["t"] + 3600
        if e["px"] is None:
            e.update(m1h=None, mcl=None, d1h=None, dcl=None, w1h="no bars", wcl="no bars", x1h=None, xcl=None); continue
        if tgt <= end: e["w1h"], t1 = "full", tgt
        elif close_t < tgt and end >= close_t: e["w1h"], t1 = "cut", close_t
        else: e["w1h"], t1 = "open", end
        e["wcl"] = "full" if end >= close_t else "open"
        tcl = close_t if end >= close_t else end
        e["m1h"] = pct(e["px"], px_at(b, t1)); e["mcl"] = pct(e["px"], px_at(b, tcl))
        q0 = px_at(qqq, e["t"])
        qm1, qmc = pct(q0, px_at(qqq, t1)), pct(q0, px_at(qqq, tcl))
        e["x1h"] = None if (e["m1h"] is None or qm1 is None) else round(e["m1h"] - qm1, 3)
        e["xcl"] = None if (e["mcl"] is None or qmc is None) else round(e["mcl"] - qmc, 3)
        e["d1h"], e["dcl"] = direction(e["m1h"]), direction(e["mcl"])
    return spikes


def tally(spikes, win, final_only=True):
    """win = '1h' | 'cl'. Counts only graded windows (full or cut; 'open' excluded when final_only)."""
    ok = ("full", "cut") if final_only else ("full", "cut", "open")
    g = [e for e in spikes if e.get("w" + win) in ok and e.get("d" + win) is not None]
    def hits(sub):
        n_up = sum(e["d" + win] == "up" for e in sub); n_dn = sum(e["d" + win] == "down" for e in sub)
        n_fl = sum(e["d" + win] == "flat" for e in sub)
        h = sum((e["color"] == "green" and e["d" + win] == "up") or (e["color"] == "red" and e["d" + win] == "down") for e in sub)
        hn = sum(e["color"] in ("green", "red") and e["d" + win] != "flat" for e in sub)
        mv = [abs(e["m" + win]) for e in sub if e["m" + win] is not None]
        return {"n": len(sub), "up": n_up, "down": n_dn, "flat": n_fl, "hit": h, "hit_n": hn,
                "med_abs_move": round(statistics.median(mv), 2) if mv else None}
    return {"all": hits(g), "color": {c: hits([e for e in g if e["color"] == c]) for c in COLORS},
            "bucket": {b: hits([e for e in g if e["bucket"] == b]) for b in BUCKETS}}


def fr(h, n):
    return f"{100*h/n:.0f}% ({h}/{n})" if n else "—"


def color_cell(c, t):
    if c == "gray": return f"up {fr(t['up'], t['up']+t['down'])}"
    return fr(t["hit"], t["hit_n"])


def mv(x):
    return "—" if x is None else f"{x:+.2f}%"


def roll(ymd, today_spikes):
    files = sorted(p for p in OUT.glob("corr-2*.json") if p.stem[5:13] < ymd)
    days, pool = [], []
    for p in reversed(files):
        try: j = json.loads(p.read_text())
        except Exception: continue
        if j.get("partial"): continue
        days.append(j["date"]); pool += j.get("spikes", [])
        if len(days) >= ROLL_DAYS: break
    return sorted(days), pool + today_spikes


def pattern_lines(t1, tc, n_days, partial):
    L = []; MIN = 8
    n = t1["all"]["n"]
    if n < 20:
        L.append(f"- Not enough yet: {n} graded spikes over {n_days} day(s). Need ~20+ (about 2 weeks) before reading anything into it.")
    cells = []
    for win, t in (("1h", t1), ("to close", tc)):
        for c in ("green", "red"):
            x = t["color"][c]
            if x["hit_n"] >= MIN: cells.append((x["hit"] / x["hit_n"], f"{c} → {'up' if c == 'green' else 'down'} ({win})", x))
        g = t["color"]["gray"]
        if g["up"] + g["down"] >= MIN: cells.append((g["up"] / (g["up"] + g["down"]), f"gray → up share ({win})", g))
        for b in BUCKETS:
            x = t["bucket"][b]
            if x["hit_n"] >= MIN: cells.append((x["hit"] / x["hit_n"], f"{b} tone-right ({win})", x))
    strong = [c for c in cells if c[0] >= 0.65 or c[0] <= 0.35]
    for r, lab, x in sorted(strong, key=lambda c: -abs(c[0] - 0.5))[:4]:
        L.append(f"- {lab}: {r*100:.0f}% (n={x.get('hit_n') or x['up']+x['down']}){' — leaning' if r >= 0.65 else ' — inverse'}")
    if not strong and n >= 20: L.append("- No cell beyond 35/65% with n ≥ 8. Looks like a coin flip so far.")
    a1 = t1["all"]
    if a1["n"]:
        L.append(f"- Spiked names moved: median |1h| {a1['med_abs_move'] if a1['med_abs_move'] is not None else '—'}%, "
                 f"up {a1['up']} / down {a1['down']} / flat {a1['flat']}.")
    if partial: L.append("- Today is partial; final numbers land at the 1:10 PM PT run.")
    return L


def run(ymd=None, partial=None, now_t=None):
    now = dt.datetime.now(PT); now_t = now_t or now.timestamp()
    ymd = ymd or now.strftime("%Y%m%d")
    o, c = session(ymd)
    if partial is None: partial = now_t < c + 5 * 60
    rows = load_rows(ymd, o, c)
    spikes = grade(find_spikes(rows), ymd, c, now_t)
    t1, tc = tally(spikes, "1h", not partial), tally(spikes, "cl", not partial)
    days, pool = roll(ymd, spikes)
    r1, rc = tally(pool, "1h"), tally(pool, "cl")
    n_days = len(days) + 1
    stamp = now.strftime("%Y-%m-%d %I:%M %p PT")
    missing = sorted({e["sym"] for e in spikes if e["px"] is None})
    tickers = len({r["sym"] for r in rows})
    res = {"date": ymd, "writer": VERSION, "generated_pt": stamp, "partial": partial, "shadow": True,
           "rules": {"z_spike": Z_SPIKE, "ratio_spike": R_SPIKE, "ratio_watch": R_WATCH, "green_gt": GREEN, "red_lt": RED,
                     "flat_pct": FLAT_PCT, "episode_gap_min": GAP_S // 60, "tone_carry_min": TONE_CARRY_S // 60},
           "snapshots": len(rows), "tickers": tickers, "spike_count": len(spikes), "missing_bars": missing,
           "spikes": spikes, "today": {"1h": t1, "close": tc}, "rolling": {"days": days + [ymd], "1h": r1, "close": rc}}
    d = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
    L = [f"# X chatter spikes vs price, {d}" + (" — PRELIMINARY (partial day)" if partial else ""), "",
         f"Shadow / display only. Not used by the score, alerts or orders. Generated {stamp}.", "",
         f"**{len(spikes)} spikes** ({sum(e['level']=='spike' for e in spikes)} red-level, {sum(e['level']=='watch' for e in spikes)} amber 1.5–2×) "
         f"from {len(rows)} snapshots on {tickers} tickers. "
         f"1h tone-right: **{fr(t1['all']['hit'], t1['all']['hit_n'])}** · to close: **{fr(tc['all']['hit'], tc['all']['hit_n'])}**.", ""]
    L += ["## Spikes", "| time PT | sym | mult | z | tone | color | px | 1h | vs QQQ | to close | vs QQQ |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    flag = {"full": "", "cut": " ✂", "open": " …", "no bars": ""}
    for e in spikes:
        tone = "n/s" if e["net"] is None else f"{e['net']:+.2f}{'*' if e['tone_carried'] else ''}"
        L.append(f"| {e['t_pt']} | {e['sym']} | {e['ratio'] if e['ratio'] is not None else '—'}× | {e['z'] if e['z'] is not None else '—'} | {tone} | {e['color']} | "
                 f"{'—' if e['px'] is None else round(e['px'], 2)} | {mv(e['m1h'])}{flag[e['w1h']]} | {mv(e['x1h'])} | {mv(e['mcl'])}{flag[e['wcl']]} | {mv(e['xcl'])} |")
    if not spikes: L.append("| — | none | | | | | | | | | |")
    L += ["", "✂ 1h window cut by the close · … window still open (partial) · * tone carried from the last sample ≤60 min earlier · n/s no tone sample", ""]
    def names(win, dirn):
        xs = [f"{e['sym']} {mv(e['m'+win])}" for e in spikes if e.get("d" + win) == dirn]
        return ", ".join(xs) or "—"
    L += ["## Preceded", "| | 1h | to close |", "|---|---|---|",
          f"| up | {names('1h','up')} | {names('cl','up')} |", f"| down | {names('1h','down')} | {names('cl','down')} |",
          f"| flat (±{FLAT_PCT}%) | {names('1h','flat')} | {names('cl','flat')} |", ""]
    def table(t1_, tc_, title):
        out = [f"## {title}", "| | n | 1h | to close | med abs 1h |", "|---|---|---|---|---|"]
        for c_ in COLORS:
            a, b = t1_["color"][c_], tc_["color"][c_]
            lab = {"green": "green → up", "red": "red → down", "gray": "gray (up share)"}[c_]
            out.append(f"| {lab} | {a['n']} | {color_cell(c_, a)} | {color_cell(c_, b)} | {str(a['med_abs_move'])+'%' if a['med_abs_move'] is not None else '—'} |")
        out += ["", "| multiple | n | tone-right 1h | tone-right close | up share 1h |", "|---|---|---|---|---|"]
        for bk in BUCKETS:
            a, b = t1_["bucket"][bk], tc_["bucket"][bk]
            out.append(f"| {bk} | {a['n']} | {fr(a['hit'], a['hit_n'])} | {fr(b['hit'], b['hit_n'])} | {fr(a['up'], a['up']+a['down'])} |")
        return out
    L += table(t1, tc, "Hit rates today" + (" (windows still open count at their latest price)" if partial else ""))
    L += ["", "Tone-right = green spike then up, or red spike then down (gray and flats left out). Coin flip = 50%.", ""]
    L += table(r1, rc, f"Rolling {n_days} day(s): {', '.join(x[4:6]+'/'+x[6:] for x in days + [ymd])}" + (" (today partial; only full/cut windows)" if partial else ""))
    L += ["", "## Emerging pattern"] + pattern_lines(r1, rc, n_days, partial)
    L += ["", "Small samples: one day is noise. Treat anything under ~30 spikes per cell as anecdote."]
    gaps = []
    if missing: gaps.append(f"no 1m bars for {', '.join(missing)}")
    uns = sum(not e["tone_sampled"] for e in spikes)
    if uns: gaps.append(f"{uns}/{len(spikes)} spikes had no tone sample within 60 min (gray)")
    if not rows: gaps.append("no feed snapshots in RTH")
    if gaps: L += ["", "Data gaps: " + "; ".join(gaps) + "."]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in ((f"corr-{ymd}.json", json.dumps(res, indent=1, default=str)), (f"corr-{ymd}.md", "\n".join(L) + "\n")):
        tmp = OUT / (name + ".tmp"); tmp.write_text(body); os.replace(tmp, OUT / name)
    print(f"corr {ymd}{' PARTIAL' if partial else ''}: spikes={len(spikes)} 1h={t1['all']['hit']}/{t1['all']['hit_n']} "
          f"close={tc['all']['hit']}/{tc['all']['hit_n']} -> {OUT / f'corr-{ymd}.md'}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--partial", action="store_true")
    ap.add_argument("--force", action="store_true", help="run on weekends/holidays too")
    a = ap.parse_args()
    ymd = a.date or dt.datetime.now(PT).strftime("%Y%m%d")
    wd = dt.datetime.strptime(ymd, "%Y%m%d").weekday()
    if not a.force and (wd >= 5 or ymd in HOLIDAYS):
        print(f"corr {ymd}: market closed (weekend/holiday), skipped"); return 0
    return run(ymd, True if a.partial else None)


if __name__ == "__main__":
    sys.exit(main())
