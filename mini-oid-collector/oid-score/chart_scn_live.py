#!/usr/bin/env python3
"""CHARTSCN-CB (2026-10-21): live status for Chart Bot's CB-SCN-V1 scenarios on the mini (display / shadow only).
Replaces chart_scn_status.py (kept as chart_scn_status.py.retired-20261021) so there is ONE status implementation:
Chart Bot's canonical scenario_status.py, run portable via run_scenarios.py --status-only.

launchd com.oid.desk.chart-scn-status (:01 and :31 past the hour, 7:01 AM-1:31 PM PT weekdays):
 1. rolls COMPLETED 30-min RTH bars (ET :00/:30 boundaries, 9:30-16:00 ET) from the mini's own 1-min SIP bars (core
    store, else wide store) for every session after each scenario's asof_bar_date
    -> ~/oid-data/chart-scenarios/bars-30m-live.csv  (symbol,ts,open,high,low,close,volume; ts = bar START, ISO + ET offset)
 2. python3 ~/oid-desk/chart-bot/run_scenarios.py --status-only --scenarios <synced latest.json> --bars-30m <csv>
        --out ~/oid-data/chart-scenarios/status-live.json      (exit 2 + JSON error on bad input; old file kept)
 3. adds the flat per-ticker primary fields the earlier job wrote (prediction_id, label, status, status_asof, ...;
    read by score_features.py and chart_backend.py) next to Chart Bot's own primary / alternates, plus status_counts.
No orders, no paid calls, never touches Chart Bot's predictions/outcomes (scored on real daily bars on the box).
Flags: --now ISO (replay clock, passed through)  --dry (write to status-live-test.json)
"""
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HOME = Path.home()
sys.path.insert(0, str(HOME / "oid-score"))
import score_lib as L  # noqa: E402

ET = ZoneInfo("America/New_York")
CB_DIR = Path(os.environ.get("OID_CHART_BOT_DIR", str(HOME / "oid-desk/chart-bot")))
SRC = Path(os.environ.get("OID_CHART_SCENARIOS", str(HOME / "oid-desk/desk/chart-bot/scenarios/latest.json")))
OUT = Path(os.environ.get("OID_CHART_SCN_STATUS", str(HOME / "oid-data/chart-scenarios/status-live.json")))
CSV = OUT.parent / "bars-30m-live.csv"
FLAT = ("prediction_id", "label", "direction", "trigger_price", "trigger_rule", "target_1", "target_2", "invalidation",
        "range_low", "range_high", "calibrated_score", "horizon_days", "status", "status_asof", "status_bar_source",
        "last_close", "sessions_elapsed", "triggered_at", "t1_hit_at", "t2_hit_at", "void_at")


def wide_store():
    try:
        import score_wide as W
        _, paths = W.setup(L.load_config())
        return paths["store"]
    except Exception:
        return None


def sessions_after(asof, today):
    d = datetime.strptime(asof, "%Y-%m-%d").date() + timedelta(days=1)
    end = datetime.strptime(today, "%Y-%m-%d").date()
    out = []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def roll(sym, dates, now, wstore):
    """Completed RTH 30m bars from the mini's 1m bars -> [(start_epoch, o, h, l, c, v, n_1m)]."""
    out = []
    for d in dates:
        b1 = L.load_day_bars(sym, d)
        if not b1 and wstore:
            b1 = L.load_day_bars(sym, d, store=wstore)
        by = {}
        for b in b1:
            ts = b.get("ts")
            if ts is None or b.get("c") is None:
                continue
            by.setdefault(int(ts // 1800) * 1800, []).append(b)
        for k in sorted(by):
            e = datetime.fromtimestamp(k, ET)
            if not ((9, 30) <= (e.hour, e.minute) < (16, 0)) or e.date().isoformat() != d:
                continue  # RTH only, session = ET date
            if k + 1800 > now:
                continue  # still forming
            xs = sorted(by[k], key=lambda b: b["ts"])
            out.append((k, xs[0]["o"], max(b["h"] for b in xs), min(b["l"] for b in xs), xs[-1]["c"],
                        sum(float(b.get("v") or 0) for b in xs), len(xs)))
    return out


def atomic(path, doc):
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(path)


def main(argv):
    t0 = time.time()
    now_iso = argv[argv.index("--now") + 1] if "--now" in argv else None
    out = OUT.with_name("status-live-test.json") if "--dry" in argv else OUT
    csv_path = CSV.with_name("bars-30m-test.csv") if "--dry" in argv else CSV
    if not SRC.exists():
        print(json.dumps({"skip": f"no {SRC}"}))
        return 0
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).timestamp() if now_iso else time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    doc = json.loads(SRC.read_text())
    ws = wide_store()
    nbars = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmpcsv = csv_path.with_name("." + csv_path.name + ".tmp")
    with tmpcsv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "ts", "open", "high", "low", "close", "volume"])
        for sym, v in sorted((doc.get("tickers") or {}).items()):
            asof = v.get("asof_bar_date") or doc.get("asof_bar_date")
            bars = roll(sym, sessions_after(asof, today), now, ws)
            nbars[sym] = len(bars)
            for k, o, h, l, c, vol, _n in bars:
                w.writerow([sym, datetime.fromtimestamp(k, ET).isoformat(), o, h, l, c, int(vol)])
    tmpcsv.replace(csv_path)
    if not any(nbars.values()):
        print(json.dumps({"skip": "no completed 30m bars after asof yet (keeping previous status file)",
                          "asof_bar_date": doc.get("asof_bar_date")}))
        return 0
    cmd = ["/usr/bin/python3", str(CB_DIR / "run_scenarios.py"), "--status-only", "--scenarios", str(SRC),
           "--bars-30m", str(csv_path), "--out", str(out)] + (["--now", now_iso] if now_iso else [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(json.dumps({"error": "run_scenarios.py --status-only failed", "rc": r.returncode,
                          "stderr": r.stderr.strip()[-800:], "kept_previous": str(out)}))
        return r.returncode or 1
    d = json.loads(out.read_text())
    cnt, acnt = {}, {}
    for sym, t in (d.get("tickers") or {}).items():
        p = t.get("primary") or {}
        for k in FLAT:  # back-compat flat primary fields (score_features / chart_backend read these)
            t[k] = p.get(k)
        t["n_30m_bars"] = nbars.get(sym, 0)
        cnt[p.get("status")] = cnt.get(p.get("status"), 0) + 1
        for a in t.get("alternates") or []:
            acnt[a.get("status")] = acnt.get(a.get("status"), 0) + 1
    d.update(kind="chart_scenario_status_live", shadow_only=True, source=str(SRC).replace(str(HOME), "~"),
             source_run_ts_pt=doc.get("run_ts_pt"), refreshed_ts=round(time.time(), 1),
             refreshed_pt=d.get("status_refreshed_pt"), status_counts=cnt, alt_status_counts=acnt,
             bars="mini 1-min SIP bars (core store, else wide store) rolled to completed RTH 30-min bars -> "
                  + str(csv_path).replace(str(HOME), "~"),
             engine="chart-bot scenario_status.py (canonical) via run_scenarios.py --status-only; " + str(CB_DIR).replace(str(HOME), "~"),
             note="display/shadow only; Chart Bot's own outcomes are scored on real daily bars on the box. "
                  "calibrated_score on primaries runs hot (~44% est vs ~36% realized).")
    atomic(out, d)
    print(json.dumps({"count": d.get("count"), "status_counts": cnt, "alt_status_counts": acnt,
                      "bars_30m": sum(nbars.values()), "secs": round(time.time() - t0, 2), "at": d.get("refreshed_pt")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
