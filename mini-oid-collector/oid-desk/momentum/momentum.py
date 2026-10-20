#!/usr/bin/env python3
"""OID momentum detector (2026-10-20), SHADOW: logs accelerate / decelerate / resume / market-recede events. No chat alerts.

Why: Jeffrey trades calls on market-wide upside volume surges: buys as price breaks levels, takes profit at each
deceleration, re-enters when momentum resumes, stops when the whole market slows/recedes (10/20 ~7:46 AM PT).
This puts that eye-read into events. Calibrated on his 10/20 CRWV/NVDA fills (see README.md, --replay).

Per-name state machine on CLOSED 1m SIP bars (collector live/<SYM>-1m-<YYYYMMDD>.jsonl):
  z   = 1m close-to-close change / median |1m change| over the prior 30 bars (vol-normalised velocity)
  accelerate  flat  -> up     z >= accel_z (1.25) and close > prior 15-min high
  decelerate  up    -> decel  v1 <= decel_frac (0.35) x max v1 of prior 3 bars, and z <= decel_stall_z (0.5)
  resume      decel -> up     z >= accel_z and close > held level (high of the prior impulse)
  decel -> flat (silent) on a close under the prior 15-min low.
Intrabar (provisional, uncalibrated): every tick, last SIP trade from the collector cache ~/oid-quote/cache/quotes.json vs last closed bar; a forming bar
  >= intrabar_min_s old that already meets the decel/resume test logs basis=intrabar once per bar (for tomorrow's calibration).
Market (breadth over non-ETF universe): hit = name with 1m high > prior 15-min high on 1m rvol >= 2 (same-slot norm).
  b5 = hits summed over last 5 bars; peak = max b5 over last 45 min.
  market-recede stage=warn when peak >= recede_min_peak and b5 <= recede_frac x peak; stage=confirm when warn has held
  recede_confirm_min bars. market-resume when b5 climbs back >= resume_frac x peak after a warn.
Output: ~/oid-desk/state/momentum/events-YYYYMMDD.jsonl (+ ticks-YYYYMMDD.jsonl = 15s last-price samples, status.json,
        current.json = per-name state + market gauge, read by the private live page every ~5 s).
NEVER posts, never calls RH/FA/UW/X, never trades. "live" in momentum.json is informational only: there is no sender.

  python3 momentum.py --loop                 # launchd com.oid.desk.momentum
  python3 momentum.py --replay [--date 2026-10-20] [--symbols CRWV,NVDA] [--from 06:30 --to 08:30]
  python3 momentum.py --once
"""
from __future__ import annotations

import argparse, json, math, os, statistics as st, sys, time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
sys.path.insert(0, str(HOME / "oid-desk" / "triggers"))
import mover_alert as MA  # noqa: E402  reuse Bars/Norms/merged_walls/universe/iso_ep/pt_str/jload
T = MA.T
PT = MA.PT
VERSION = "momentum@0.1-shadow"
CFG = HOME / "oid-desk" / "triggers" / "momentum.json"
DEFAULTS = {
    "enabled": True, "live": False, "interval_s": 15, "rth_pt": ["06:31", "13:00"],
    "exclude": ["WDC", "STX", "SNDK", "VIX", "WTI", "BRENT"],
    "etfs": ["SPY", "QQQ", "DIA", "IWM", "RSP", "VTV", "VUG", "EWY", "TQQQ", "SMH", "SOXX", "DRAM"],
    "mad_bars": 30, "hi_bars": 15, "accel_z": 1.25, "decel_frac": 0.35, "decel_stall_z": 0.5, "peak_bars": 3,
    "intrabar": True, "intrabar_min_s": 30, "max_quote_age_s": 20,
    "breadth_rvol": 2.0, "breadth_sum_bars": 5, "breadth_peak_min": 45, "recede_min_peak": 25,
    "recede_frac": 0.35, "recede_confirm_min": 10, "resume_frac": 0.6,
    "levels": [0.25, 0.5, 1.0], "walls_max_age_min": 120,
    "sectors": "~/oid-live-page/sectors.json", "bars_live_dir": "~/oid-desk/desk/cache/bars/store/live",
    "bars_store_dir": "~/oid-desk/desk/cache/bars/store", "quotes": "~/oid-quote/cache/quotes.json",
    "state_dir": "~/oid-desk/state/momentum",
    "wall_files": MA.DEFAULTS["wall_files"],
}
X = MA.X


def cfg_load(path=CFG):
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (T.jload(path, {}) or {}).items() if not str(k).startswith("_")})
    return c


def in_rth(c, now):
    d = datetime.fromtimestamp(now, PT)
    if d.weekday() >= 5:
        return False
    hm = d.strftime("%H:%M")
    return c["rth_pt"][0] <= hm < c["rth_pt"][1]


def ns_ep(v):
    """'2026-10-20T17:19:05.450445584Z' -> epoch (mover_alert.iso_ep drops nanosecond+Z stamps)."""
    try:
        v = str(v).strip()
        if v.endswith("Z"):
            v = v[:-1]
        head, _, frac = v.partition(".")
        return datetime.fromisoformat(head).replace(tzinfo=timezone.utc).timestamp() + (float("0." + frac) if frac else 0.0)
    except Exception:
        return None


_CACHE = {}


def cached(name, fn):
    if name not in _CACHE:
        _CACHE[name] = fn()
    return _CACHE[name]


def lv_dist(px, step):
    nxt = math.floor(px / step + 1e-9) * step + step
    return round((nxt - px) * 100, 1), round(nxt, 2)


def ffill(bars):
    """Collector 'prints' bars can carry volume with null OHLC; carry the prior close so volume still counts."""
    out, last = [], None
    for b in bars:
        if b.get("c") is None:
            if last is None:
                continue
            b = dict(b, o=last, h=last, l=last, c=last)
        last = b["c"]
        b["v"] = float(b.get("v") or 0)
        out.append(b)
    return out


def features(c, norms, sym, day_iso, bars):
    sm, _ = norms.get(sym, day_iso)
    out = []
    for i, b in enumerate(bars):
        p = bars[i - 1]["c"] if i else b["o"]
        v1 = (b["c"] - p) * 100
        prior = [abs(x["v1"]) for x in out[max(0, i - c["mad_bars"]):i]]
        mad = (st.median(prior) if len(prior) >= 5 else None) or None
        s = b.get("slot")
        rv = (b["v"] / sm[s]) if (s is not None and sm.get(int(s))) else None
        hi15 = max([x["h"] for x in bars[max(0, i - c["hi_bars"]):i]] or [b["h"]])
        lo15 = min([x["c"] for x in bars[max(0, i - c["hi_bars"]):i]] or [b["c"]])
        v3 = (b["c"] - bars[max(i - 3, 0)]["c"]) * 100 / min(max(i, 1), 3)
        out.append({"ep": b["ep"], "c": b["c"], "h": b["h"], "v": b["v"], "v1": round(v1, 2),
                    "v1_pct": round(v1 / p, 4) if p else None, "z": round(v1 / mad, 2) if mad else None,
                    "mad": mad, "v3": round(v3, 2), "rv": None if rv is None else round(rv, 2),
                    "nh15": b["h"] > hi15, "brk15": b["c"] > hi15, "hi15": hi15, "lo15": lo15})
    for i, f in enumerate(out):
        f["accel"] = round(f["v3"] - out[i - 1]["v3"], 2) if i else 0.0
    return out


def name_events(c, sym, F):
    """Deterministic replay of the state machine over closed bars. Returns (events, final_state_dict)."""
    ev, state, held, peakhi = [], "flat", None, None
    for i, f in enumerate(F):
        if i < 5 or f["z"] is None:
            continue
        t = f["ep"] + 60
        if state == "flat" and f["z"] >= c["accel_z"] and f["brk15"]:
            state, peakhi = "up", f["h"]; ev.append(("accelerate", t, i, None)); continue
        if state == "decel" and f["z"] >= c["accel_z"] and f["c"] > held:
            state, peakhi = "up", f["h"]; ev.append(("resume", t, i, held)); continue
        if state == "up":
            peakhi = max(peakhi, f["h"])
            pk = max(x["v1"] for x in F[i - c["peak_bars"]:i])
            if pk > 0 and f["v1"] <= c["decel_frac"] * pk and f["z"] <= c["decel_stall_z"]:
                state, held = "decel", peakhi; ev.append(("decelerate", t, i, held)); continue
        if state == "decel" and f["c"] < f["lo15"]:
            state = "flat"
    return ev, {"state": state, "held": held, "peakhi": peakhi}


def breadth_series(c, FE):
    names = [s for s in FE if s not in set(c["etfs"])]
    eps = sorted({f["ep"] for s in names for f in FE[s]})
    idx = {s: {f["ep"]: f for f in FE[s]} for s in names}
    hits = []
    for ep in eps:
        k = n = 0
        for s in names:
            f = idx[s].get(ep)
            if f is None:
                continue
            n += 1
            if f["nh15"] and (f["rv"] or 0) >= c["breadth_rvol"]:
                k += 1
        hits.append((ep, k, n))
    out, warn_run, stage = [], 0, None
    for j, (ep, k, n) in enumerate(hits):
        b5 = sum(h[1] for h in hits[max(0, j - c["breadth_sum_bars"] + 1):j + 1])
        lo = ep - c["breadth_peak_min"] * 60
        peak = max([o["b5"] for o in out if o["ep"] >= lo] + [b5])
        ev = None
        if peak >= c["recede_min_peak"] and b5 <= c["recede_frac"] * peak:
            warn_run += 1
            if warn_run == 1:
                ev = ("market-recede", "warn")
            elif warn_run == c["recede_confirm_min"]:
                ev = ("market-recede", "confirm")
        else:
            if warn_run and peak >= c["recede_min_peak"] and b5 >= c["resume_frac"] * peak:
                ev = ("market-resume", None)
            if b5 > c["recede_frac"] * peak or peak < c["recede_min_peak"]:
                warn_run = 0
        out.append({"ep": ep, "hits": k, "n": n, "b5": b5, "peak45": peak, "recede_run": warn_run, "event": ev})
    return out


def wall_view(walls, px, now, c):
    if not walls:
        return None
    age = (now - walls["as_of_ep"]) / 60 if walls.get("as_of_ep") else None
    cand = [(n, k) for n, k in (("call_wall", walls.get("call_wall")), ("put_wall", walls.get("put_wall")),
                                ("gamma_flip", walls.get("gamma_flip"))) if k]
    if not cand:
        return None
    n, k = min(cand, key=lambda x: abs(x[1] - px))
    return {"nearest": n, "level": k, "dist_c": round((k - px) * 100, 1), "call_wall": walls.get("call_wall"),
            "put_wall": walls.get("put_wall"), "gamma_flip": walls.get("gamma_flip"),
            "age_min": None if age is None else round(age), "stale": age is None or age > c["walls_max_age_min"]}


def build(c, sym, kind, t, f, held, walls, mk, basis="bar_close", px=None, extra=None):
    px = f["c"] if px is None else px
    lv = {f"next_{s:g}": dict(zip(("dist_c", "level"), lv_dist(px, s))) for s in c["levels"]}
    e = {"event_type": "momentum_event", "kind": kind, "symbol": sym, "basis": basis,
         "event_id": f"mom-{sym}-{kind}-{datetime.fromtimestamp(t, PT):%Y%m%dT%H%M%S}-{basis[0]}",
         "time_pt": MA.pt_str(t, "%Y-%m-%d %I:%M:%S %p PT"), "bar_pt": MA.pt_str(f["ep"], "%-I:%M %p PT"),
         "price": round(px, 4), "v1_c": f["v1"], "v1_pct": f["v1_pct"], "z": f["z"], "v3_c": f["v3"],
         "accel_c": f["accel"], "rvol_1m": f["rv"], "new_high_15m": f["nh15"], "held_level": held,
         "levels": lv, "wall": wall_view(walls, px, t, c), "market": mk,
         "shadow": True, "live": False, "trade_action": "none", "mandate": "research/log only - not an order",
         "writer": VERSION}
    if extra:
        e.update(extra)
    return e


def market_now(B, t):
    rows = [b for b in B if b["ep"] + 60 <= t]
    if not rows:
        return None
    b = rows[-1]
    st_ = "receded" if b["recede_run"] >= 1 else "normal"
    return {"b5": b["b5"], "peak45": b["peak45"], "hits_1m": b["hits"], "n": b["n"], "state": st_,
            "recede_run_min": b["recede_run"]}


def compute(c, day_iso, syms=None, now=None):
    day = day_iso.replace("-", "")
    bars = cached("bars", lambda: MA.Bars(c))
    norms = cached("norms-" + day_iso, lambda: MA.Norms(c))
    walls = MA.merged_walls(c)
    uni = MA.universe({"sectors": c["sectors"], "exclude": c["exclude"]})
    FE, raw = {}, {}
    for s in uni:
        try:
            b = bars.get(s, day)
            if now is not None:
                b = [x for x in b if x["ep"] + 60 <= now + 1]
            b = ffill(b)
            if len(b) >= 6:
                raw[s] = b
                FE[s] = features(c, norms, s, day_iso, b)
        except Exception as ex:  # one bad file never stops the tick
            print(f"feature error {s}: {type(ex).__name__}: {ex}"[:200], flush=True)
    Bser = breadth_series(c, FE)
    events, states = [], {}
    for s in (syms or list(FE)):
        if s not in FE:
            continue
        ev, stt = name_events(c, s, FE[s])
        states[s] = stt
        for kind, t, i, held in ev:
            events.append(build(c, s, kind, t, FE[s][i], held, walls.get(s), market_now(Bser, t)))
    for b in Bser:
        if b["event"]:
            kind, stage = b["event"]
            t = b["ep"] + 60
            mk = {"b5": b["b5"], "peak45": b["peak45"], "hits_1m": b["hits"], "n": b["n"], "recede_run_min": b["recede_run"]}
            spy = FE.get("SPY") and next((f for f in FE["SPY"] if f["ep"] == b["ep"]), None)
            events.append({"event_type": "momentum_event", "kind": kind, "stage": stage, "symbol": "MARKET",
                           "basis": "bar_close", "event_id": f"mom-MARKET-{kind}-{stage}-{datetime.fromtimestamp(t, PT):%Y%m%dT%H%M%S}",
                           "time_pt": MA.pt_str(t, "%Y-%m-%d %I:%M:%S %p PT"), "bar_pt": MA.pt_str(b["ep"], "%-I:%M %p PT"),
                           "market": mk, "spy_v1_pct": spy["v1_pct"] if spy else None,
                           "shadow": True, "live": False, "trade_action": "none", "writer": VERSION})
    events.sort(key=lambda e: e["time_pt"])
    return events, FE, states, Bser, walls


def intrabar(c, FE, states, walls, Bser, now):
    """Provisional decel/resume from the forming bar (last trade vs last closed close)."""
    q = (T.jload(X(c["quotes"]), {}) or {}).get("equities") or {}
    out, ticks = [], []
    for s, F in FE.items():
        r = q.get(s) if isinstance(q, dict) else None
        r = r if isinstance(r, dict) else {}
        last = r.get("last")
        te = ns_ep(r.get("trade_observed_at"))
        age = None if te is None else round(now - te, 1)
        if last is None or age is None or age > c["max_quote_age_s"]:
            continue
        ticks.append({"s": s, "last": last, "age_s": age})
        if not F:
            continue
        f0 = F[-1]
        start = f0["ep"] + 60
        el = now - start
        if el < c["intrabar_min_s"] or el >= 60 or not f0.get("mad"):
            continue
        v1 = (last - f0["c"]) * 100
        z = v1 / f0["mad"]
        stt = states.get(s) or {}
        kind = None
        if stt.get("state") == "up":
            pk = max(x["v1"] for x in F[-c["peak_bars"]:])
            if pk > 0 and v1 <= c["decel_frac"] * pk and z <= c["decel_stall_z"]:
                kind = "decelerate"
        elif stt.get("state") == "decel" and stt.get("held") and z >= c["accel_z"] and last > stt["held"]:
            kind = "resume"
        if kind:
            f = dict(f0, v1=round(v1, 2), z=round(z, 2), v1_pct=round(v1 / f0["c"], 4), ep=start)
            out.append(build(c, s, kind, now, f, stt.get("held"), walls.get(s), market_now(Bser, now), basis="intrabar",
                             px=last, extra={"provisional": True, "bar_elapsed_s": round(el)}))
    return out, ticks


def current_doc(c, now, states, ev, ib, Bser):
    """Snapshot for the live page: per-name state since its last bar-close flag, newest provisional, market gauge."""
    last_by = {}
    for e in ev:
        if e["symbol"] != "MARKET":
            last_by[e["symbol"]] = e
    prov = {e["symbol"]: e for e in ib}
    tp = lambda e: datetime.strptime(e["time_pt"], "%Y-%m-%d %I:%M:%S %p PT").replace(tzinfo=PT).timestamp()
    by = {}
    for s, stt in states.items():
        e = last_by.get(s)
        kind = e["kind"] if e else None
        state = {"up": ("resume" if kind == "resume" else "accelerate"), "decel": "decelerate"}.get(stt["state"], "quiet")
        r = {"state": state, "held": stt.get("held"), "since_ep": round(tp(e)) if (e and state != "quiet") else None,
             "since_pt": e["time_pt"][11:] if (e and state != "quiet") else None, "price": e.get("price") if e else None}
        p = prov.get(s)
        if p:
            r["provisional"] = {"kind": p["kind"], "ep": round(now), "price": p.get("price")}
        by[s] = r
    mk = None
    closed = [b for b in Bser if b["ep"] + 60 <= now + 1]
    if closed:
        b = closed[-1]
        run = b["recede_run"]
        stage = "confirm" if run >= c["recede_confirm_min"] else ("warn" if run >= 1 else "normal")
        mk = {"b5": b["b5"], "peak45": b["peak45"], "hits_1m": b["hits"], "n": b["n"], "stage": stage, "recede_run_min": run,
              "pct_of_peak": round(100 * b["b5"] / b["peak45"]) if b["peak45"] else None,
              "armed": b["peak45"] >= c["recede_min_peak"], "bar_pt": MA.pt_str(b["ep"], "%-I:%M %p PT"),
              "warn_frac": c["recede_frac"], "confirm_min": c["recede_confirm_min"], "min_peak": c["recede_min_peak"]}
    return {"as_of": round(now, 1), "as_of_pt": MA.pt_str(now, "%Y-%m-%d %I:%M:%S %p PT"), "writer": VERSION,
            "shadow": True, "by_sym": by, "market": mk}


def loop(c_path):
    c = cfg_load(c_path)
    sd = X(c["state_dir"]); sd.mkdir(parents=True, exist_ok=True)
    print(f"{MA.pt_str(time.time(), '%Y-%m-%d %H:%M:%S')} momentum start {VERSION} shadow (no sender)", flush=True)
    seen, seen_day = set(), None
    while True:
        now = time.time()
        c = cfg_load(c_path)
        day_iso = datetime.fromtimestamp(now, PT).strftime("%Y-%m-%d")
        day = day_iso.replace("-", "")
        if seen_day != day_iso:
            seen_day, seen = day_iso, set()
            try:
                for ln in open(sd / f"events-{day}.jsonl"):
                    seen.add(json.loads(ln)["event_id"])
            except Exception:
                pass
        status = {"pt": MA.pt_str(now, "%Y-%m-%d %I:%M:%S %p PT"), "writer": VERSION, "mode": "shadow", "live": False}
        if c.get("enabled") and in_rth(c, now):
            try:
                t0 = time.time()
                ev, FE, states, Bser, walls = compute(c, day_iso, now=now)
                ib, ticks = intrabar(c, FE, states, walls, Bser, now) if c.get("intrabar") else ([], [])
                new = [e for e in ev + ib if e["event_id"] not in seen]
                for e in new:
                    e["logged_pt"] = MA.pt_str(now, "%Y-%m-%d %I:%M:%S %p PT")
                    try:
                        lag = now - datetime.strptime(e["time_pt"], "%Y-%m-%d %I:%M:%S %p PT").replace(tzinfo=PT).timestamp()
                    except Exception:
                        lag = 0
                    e["backfill"] = lag > 90  # caught up after a (re)start, not seen live
                with open(sd / f"events-{day}.jsonl", "a") as fh:
                    for e in new:
                        seen.add(e["event_id"]); fh.write(json.dumps(e) + "\n")
                        if e.get("backfill"):
                            continue
                        print(f"{MA.pt_str(now, '%H:%M:%S')} {e['symbol']} {e['kind']}{('/' + e['stage']) if e.get('stage') else ''}"
                              f" {e['basis']} @{e.get('price', '')} bar {e['bar_pt']}", flush=True)
                try:
                    tmp = sd / "current.json.tmp"
                    tmp.write_text(json.dumps(current_doc(c, now, states, ev, ib, Bser)))
                    tmp.replace(sd / "current.json")
                except Exception as ex:
                    print(f"current.json error {type(ex).__name__}: {ex}"[:200], flush=True)
                if ticks:
                    with open(sd / f"ticks-{day}.jsonl", "a") as fh:
                        fh.write(json.dumps({"ep": round(now, 1), "q": ticks}) + "\n")
                mk = market_now(Bser, now + 60) if Bser else None
                status.update(state="rth", names=len(FE), new_events=len(new), events_today=len(seen), market=mk,
                              tick_ms=round((time.time() - t0) * 1000),
                              up=sorted(s for s, v in states.items() if v["state"] == "up"),
                              decel=sorted(s for s, v in states.items() if v["state"] == "decel"))
            except Exception as ex:
                status.update(state="error", err=f"{type(ex).__name__}: {ex}"[:200])
                print(f"{MA.pt_str(now, '%H:%M:%S')} error {status['err']}", flush=True)
            sleep = c["interval_s"]
        else:
            status.update(state="idle (outside 6:31-13:00 PT / weekend / disabled)")
            sleep = 60
        try:
            (sd / "status.json").write_text(json.dumps(status))
        except Exception:
            pass
        time.sleep(max(1, sleep - (time.time() - now)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CFG))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--loop", action="store_true"); g.add_argument("--once", action="store_true")
    g.add_argument("--replay", action="store_true")
    ap.add_argument("--date", default=datetime.now(PT).strftime("%Y-%m-%d"))
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--from", dest="frm", default="06:30"); ap.add_argument("--to", default="13:00")
    a = ap.parse_args()
    c = cfg_load(a.config)
    if a.loop:
        return loop(a.config)
    syms = [s.strip().upper() for s in a.symbols.split(",")] if a.symbols else None
    if a.once:
        ev, FE, states, Bser, walls = compute(c, a.date, syms, now=time.time())
        ib, _ = intrabar(c, FE, states, walls, Bser, time.time())
        print(json.dumps({"states": states, "intrabar": ib, "market": market_now(Bser, time.time()),
                          "last_events": ev[-10:]}, indent=1, default=str)); return 0
    ev, *_ = compute(c, a.date, syms)
    for e in ev:
        hm = datetime.strptime(e["time_pt"], "%Y-%m-%d %I:%M:%S %p PT").strftime("%H:%M")
        if a.frm <= hm <= a.to and (syms is None or e["symbol"] in syms + ["MARKET"]):
            m = e.get("market") or {}
            print(f"{e['time_pt'][11:]} {e['symbol']:5} {e['kind']:<13}{(e.get('stage') or ''):<8} "
                  f"px {e.get('price', '')} z {e.get('z', '')} rv {e.get('rvol_1m', '')} b5 {m.get('b5')}/{m.get('peak45')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
