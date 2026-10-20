"""Builds score rows for a set of symbols at time t (shared by the live daemon and the backfill)."""
import json
from datetime import datetime
import score_lib as L


def schedule(cfg, date):
    """Scheduled score times (epoch) for a PT date string: anchors + grid. -> [(t, 'HH:MM', trigger)]"""
    cd = cfg["cadence_pt"]
    anchors = set(cd.get("anchors") or [])
    slots = {}
    g = int(cd.get("grid_every_min") or 0)
    if g:
        h0, m0 = map(int, cd["grid_start"].split(":"))
        h1, m1 = map(int, cd["grid_end"].split(":"))
        m = h0 * 60 + m0
        while m <= h1 * 60 + m1:
            slots[f"{m // 60:02d}:{m % 60:02d}"] = "grid"
            m += g
    for a in anchors:
        slots[a] = "anchor"
    out = []
    d = datetime.strptime(date, "%Y-%m-%d")
    for hm, trig in slots.items():
        hh, mm = map(int, hm.split(":"))
        t = d.replace(hour=hh, minute=mm, tzinfo=L.PT).timestamp()
        out.append((t, hm, trig))
    return sorted(out)


def market_inputs(t, date, cfg, bars_by, atr_by, vix=None, tide=True):
    idx = {}
    for s in ("SPY", "QQQ"):
        bars, atr = bars_by.get(s), atr_by.get(s)
        if not bars or not atr:
            continue
        closed = [b for b in bars if b["ts"] + 60 <= t + 1]
        if not closed:
            continue
        bm = L.bar_measures(s, bars, t, closed[-1]["c"], atr, cfg)
        if bm:
            idx[s] = {"vwap_atr": L.rnd(bm["vwap_atr"]), "ret_atr": L.rnd(bm["ret_atr"])}
    x = {"idx": idx}
    if vix:
        x.update(vix)
    if tide:
        td, age = L.tide_delta(t, cfg["components"]["market"].get("tide_window_min", 30))
        if td is not None:
            x["tide_delta"] = td
            x["tide_age_s"] = round(age)
            x["tide_stale"] = age > cfg.get("staleness", {}).get("tide_stale_s", 1200)
    return x


def make_row(sym, t, px, date, cfg, bars, atr, walls, flow, mkt, mode, trigger, slot=None, event=None, extra=None):
    bm = L.bar_measures(sym, bars, t, px, atr, cfg) if bars and atr else None
    comps = L.build_components(sym, t, px, atr, bm, walls, flow, mkt, cfg)
    raw, score, cov = L.combine(comps, cfg)
    stale = sorted(k for k, c in comps.items() if (c.get("f") or {}).get("stale"))
    missing = sorted(k for k, c in comps.items() if (c.get("f") or {}).get("missing"))
    row = {"id": f"{'bf-' if mode == 'backfill' else ''}{sym}-{int(t)}-{trigger}", "sym": sym, "t": round(t, 1),
           "t_pt": L.pt_str(t), "date": date, "slot": slot, "mode": mode, "trigger": trigger,
           "config_version": cfg["config_version"], "px": L.rnd(px, 4), "atr": L.rnd(atr, 4),
           "score": score, "raw": raw, "coverage": cov, "stale": stale, "missing": missing, "comps": comps}
    if event:
        row["event"] = event
    if extra:
        row.update(extra)
    return row


def summary(row):
    """Compact form for the live page badge."""
    return {"s": row["score"], "raw": row["raw"], "cov": row["coverage"], "t": row["t"], "t_pt": row["t_pt"],
            "trigger": row["trigger"], "cfg": row["config_version"], "stale": row["stale"], "missing": row["missing"],
            "comps": {k: [c["c"], c["q"], c["w"]] for k, c in row["comps"].items()},
            "why": {k: (c.get("f") or {}).get("why") for k, c in row["comps"].items() if (c.get("f") or {}).get("why")}}
