#!/usr/bin/env python3
"""Fill forward outcomes for logged score rows (launchd com.oid.desk.score-grade, every 15 min).

For each score row and horizon (+5m,+15m,+30m,+1h,+2h, close, next_open) once the window is complete:
  ret_pct  : close of last bar in window vs entry px (score-time price)
  up_pct   : max high in window vs entry (>=0) ; dn_pct : min low vs entry (<=0)
  mfe_pct / mae_pct : favorable / adverse excursion in the score's direction (score 0 -> up/down)
  touch    : whether the window's range reached the call wall / put wall / gamma flip (+ minutes to first touch)
Window = 1-min bars starting at the minute containing t through the bar ending at t+h. A window that
runs past the session close is cut at the close (truncated=true).
Appends to ~/oid-data/score/outcomes-YYYYMMDD.jsonl (live) / backfill-outcomes-YYYYMMDD.jsonl; never rewrites.
"""
import argparse, json, time
from datetime import datetime, timedelta
from pathlib import Path
import score_lib as L

CLOSE_GRACE_PT = (13, 10)


def read_jsonl(p):
    out = []
    try:
        for ln in p.read_text().splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    except OSError:
        pass
    return out


def session_over(date, now):
    d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=L.PT)
    return now >= d.replace(hour=CLOSE_GRACE_PT[0], minute=CLOSE_GRACE_PT[1]).timestamp()


_B = {}


def bars(sym, date):
    k = (sym, date)
    if k not in _B:
        _B[k] = L.load_day_bars(sym, date)
    return _B[k]


def next_session(sym, date):
    live = sorted(p.name.split("-1m-")[1][:8] for p in (L.STORE / "live").glob(f"{sym}-1m-*.jsonl"))
    cands = [f"{x[:4]}-{x[4:6]}-{x[6:]}" for x in live] + L.sessions(sym)
    nxt = sorted({d for d in cands if d > date})
    return nxt[0] if nxt else None


def window_stats(row, win, entry, h_label, truncated):
    comps = row.get("comps") or {}
    lv = {"cw": ((comps.get("walls") or {}).get("x") or {}).get("cw"), "pw": ((comps.get("walls") or {}).get("x") or {}).get("pw"),
          "gf": ((comps.get("flip") or {}).get("x") or {}).get("gf")}
    hi = max(b["h"] for b in win)
    lo = min(b["l"] for b in win)
    last = win[-1]["c"]
    up, dn = (hi / entry - 1) * 100, (lo / entry - 1) * 100
    s = row.get("score") or 0
    mfe, mae = (up, dn) if s >= 0 else (-dn, -up)
    touch, tmin = {}, {}
    for k, v in lv.items():
        if v is None:
            continue
        hit = None
        for b in win:
            if b["l"] <= v <= b["h"] or (k == "cw" and b["h"] >= v and entry < v) or (k == "pw" and b["l"] <= v and entry > v):
                hit = b
                break
        touch[k] = hit is not None
        if hit:
            tmin[k] = round(max(0.0, (hit["ts"] + 60 - row["t"]) / 60), 1)
    return {"id": row["id"], "sym": row["sym"], "date": row["date"], "mode": row.get("mode"), "h": h_label,
            "config_version": row.get("config_version"), "score": s, "raw": row.get("raw"), "entry": entry,
            "end_px": last, "end_t_pt": L.pt_str(win[-1]["ts"] + 60), "ret_pct": round((last / entry - 1) * 100, 4),
            "up_pct": round(up, 4), "dn_pct": round(dn, 4), "mfe_pct": round(mfe, 4), "mae_pct": round(mae, 4),
            "touch": touch, "touch_min": tmin, "truncated": truncated, "n_bars": len(win)}


def grade_file(sp, op, cfg, now, verbose=False):
    rows = read_jsonl(sp)
    done = {(o["id"], o["h"]) for o in read_jsonl(op)}
    hs = [(f"{h}m", h) for h in cfg.get("horizons_min", [5, 15, 30, 60, 120])] + [(x, None) for x in cfg.get("extra_horizons", [])]
    new = []
    for r in rows:
        if r.get("trigger") == "badge":
            continue
        B = bars(r["sym"], r["date"])
        if not B:
            continue
        m0 = int(r["t"] // 60) * 60
        entry = r["px"]
        over = session_over(r["date"], now)
        for lab, h in hs:
            if (r["id"], lab) in done:
                continue
            o = None
            if h is not None:
                end = m0 + h * 60
                win = [b for b in B if m0 <= b["ts"] < end]
                if not win:
                    continue
                complete = win[-1]["ts"] + 60 >= end
                if complete and now >= end + 60:
                    o = window_stats(r, win, entry, lab, False)
                elif over:
                    o = window_stats(r, win, entry, lab, True)
            elif lab == "close":
                if over:
                    win = [b for b in B if b["ts"] >= m0]
                    if win:
                        o = window_stats(r, win, entry, lab, False)
            elif lab == "next_open":
                nd = next_session(r["sym"], r["date"])
                if nd:
                    nb = bars(r["sym"], nd)
                    if nb:
                        b0 = nb[0]
                        o = {"id": r["id"], "sym": r["sym"], "date": r["date"], "mode": r.get("mode"), "h": lab,
                             "config_version": r.get("config_version"), "score": r.get("score"), "raw": r.get("raw"),
                             "entry": entry, "end_px": b0["o"], "end_t_pt": L.pt_str(b0["ts"]), "ret_pct": round((b0["o"] / entry - 1) * 100, 4),
                             "next_date": nd}
            if o:
                o["graded_pt"] = L.pt_str(now)
                new.append(o)
    if new:
        with op.open("a") as f:
            for o in new:
                f.write(json.dumps(o, separators=(",", ":")) + "\n")
    if verbose:
        print(f"{sp.name}: {len(rows)} rows, +{len(new)} outcomes -> {op.name}")
    return len(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    cfg = L.load_config()
    now = time.time()
    cutoff = (datetime.now(L.PT) - timedelta(days=a.days)).strftime("%Y%m%d")
    n = 0
    for sp in sorted(L.OUT.glob("*scores-*.jsonl")):
        d = sp.stem.split("-")[-1]
        if d < cutoff:
            continue
        op = sp.with_name(sp.name.replace("scores-", "outcomes-"))
        n += grade_file(sp, op, cfg, now, a.v)
    print(f"{L.pt_str(now)} graded +{n} outcomes")


if __name__ == "__main__":
    main()
