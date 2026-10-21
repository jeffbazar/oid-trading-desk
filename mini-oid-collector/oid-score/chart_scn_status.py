#!/usr/bin/env python3
"""CHARTSCN (2026-10-21): live status for Chart Bot's CB-SCN-V1 primaries on the mini (display / shadow only).

Every 30 min in RTH (launchd com.oid.desk.chart-scn-status, :01 and :31 past the hour 7:01 AM-1:31 PM PT weekdays):
reads the synced ~/oid-desk/desk/chart-bot/scenarios/latest.json (box -> mini desk-state push), rolls COMPLETED 30-min
bars (ET :00/:30 boundaries from 9:30 ET) from the mini's own 1-min SIP bars (core store, else the wide store) for every
session after the scenario's asof_bar_date, and applies Chart Bot's status rules (chart-bot/scenario_status.py
status_of, copied verbatim in logic): close-above/below trigger on a 30m close, touch-above/below on high/low,
T1/T2 on a touch (same bar: on the close), void = closing stop after trigger (RANGE_CHOP: any close outside the range),
window = horizon_days sessions -> expired / held.
Writes ~/oid-data/chart-scenarios/status-live.json atomically. Never touches Chart Bot's predictions/outcomes (those are
scored on real daily bars on the box). No orders, no paid API calls.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
sys.path.insert(0, str(HOME / "oid-score"))
import score_lib as L  # noqa: E402

SRC = Path(os.environ.get("OID_CHART_SCENARIOS", str(HOME / "oid-desk/desk/chart-bot/scenarios/latest.json")))
OUT = Path(os.environ.get("OID_CHART_SCN_STATUS", str(HOME / "oid-data/chart-scenarios/status-live.json")))
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = None


def wide_store():
    try:
        import score_wide as W
        _, paths = W.setup(L.load_config())
        return paths["store"]
    except Exception:
        return None


def bars_30m(sym, dates, now, wstore):
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
            k = int(ts // 1800) * 1800   # ET 9:30/10:00 boundaries are :00/:30 UTC too
            by.setdefault(k, []).append(b)
        for k in sorted(by):
            if k + 1800 > now:
                continue  # still forming
            xs = sorted(by[k], key=lambda b: b["ts"])
            out.append({"session": d, "o": xs[0]["o"], "h": max(b["h"] for b in xs), "l": min(b["l"] for b in xs),
                        "c": xs[-1]["c"], "src": "mini-1m-30m", "n_1m": len(xs),
                        "end": time.strftime("%Y-%m-%d %-I:%M %p PT", time.localtime(k + 1800))})
    return out


def status_of(s, bars):
    """Chart Bot scenario_status.status_of (CB-SCN-V1), on 30m bars rolled on the mini."""
    lab, rule, H = s["label"], s["trigger_rule"], int(s.get("horizon_days") or 5)
    sessions, use = [], []
    for b in bars:
        if b["session"] not in sessions:
            sessions.append(b["session"])
        if len(sessions) > H:
            break
        use.append(b)
    window_done = len(sessions) > H
    st = {"status": "active", "status_asof": None, "status_bar_source": None, "last_close": None,
          "sessions_elapsed": len(sessions), "triggered_at": None, "t1_hit_at": None, "t2_hit_at": None, "void_at": None}
    if use:
        st.update(status_asof=use[-1]["end"], status_bar_source=use[-1]["src"], last_close=round(use[-1]["c"], 2))
    if rule == "stay-inside":
        lo, hi = s.get("range_low"), s.get("range_high")
        if lo is None or hi is None:
            return st
        for b in use:
            if b["c"] > hi or b["c"] < lo:
                st.update(status="void", void_at=b["end"])
                return st
        if window_done:
            st["status"] = "held"
        return st
    sg = 1 if s.get("direction") == "long" else -1
    T, T1, T2, S = s.get("trigger_price"), s.get("target_1"), s.get("target_2"), s.get("invalidation")
    if T is None:
        return st
    beyond = (lambda x, l: x > l) if sg > 0 else (lambda x, l: x < l)
    touch = (lambda b, l: b["h"] >= l) if sg > 0 else (lambda b, l: b["l"] <= l)
    ti = None
    for i, b in enumerate(use):
        if (rule in ("close-above", "close-below") and beyond(b["c"], T)) or \
           (rule == "touch-below" and b["l"] <= T) or (rule == "touch-above" and b["h"] >= T):
            ti = i
            st.update(status="triggered", triggered_at=b["end"])
            break
    if ti is None:
        if window_done:
            st["status"] = "expired"
        return st
    for i in range(ti, len(use)):
        b = use[i]
        same = i == ti
        t1 = T1 is not None and ((beyond(b["c"], T1) or b["c"] == T1) if same else touch(b, T1))
        t2 = T2 is not None and ((beyond(b["c"], T2) or b["c"] == T2) if same else touch(b, T2))
        if st["t1_hit_at"] is None and t1:
            st.update(status="target_hit", t1_hit_at=b["end"])
        if st["t1_hit_at"] is not None and t2:
            st.update(status="target2_hit", t2_hit_at=b["end"])
            return st
        if S is not None and ((b["c"] < S) if sg > 0 else (b["c"] > S)):
            st["void_at"] = b["end"]
            if st["t1_hit_at"] is None:
                st["status"] = "void"
            return st
    if window_done and st["status"] == "triggered":
        st["status"] = "expired"
    return st


def sessions_after(asof, today):
    d = datetime.strptime(asof, "%Y-%m-%d").date() + timedelta(days=1)
    end = datetime.strptime(today, "%Y-%m-%d").date()
    out = []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def main():
    t0 = time.time()
    if not SRC.exists():
        print(json.dumps({"skip": f"no {SRC}"}))
        return 0
    doc = json.loads(SRC.read_text())
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    ws = wide_store()
    out, cnt = {}, {}
    for sym, v in (doc.get("tickers") or {}).items():
        p = v.get("primary") or {}
        if not p:
            continue
        asof = v.get("asof_bar_date") or doc.get("asof_bar_date")
        dates = sessions_after(asof, today)
        bars = bars_30m(sym, dates, now, ws)
        st = status_of(p, bars)
        st = {k: st[k] for k in ("status", "status_asof", "status_bar_source", "last_close", "sessions_elapsed",
                                 "triggered_at", "t1_hit_at", "t2_hit_at", "void_at")}
        out[sym] = {"prediction_id": p.get("prediction_id"), "label": p.get("label"), "direction": p.get("direction"),
                    "trigger_price": p.get("trigger_price"), "trigger_rule": p.get("trigger_rule"), "target_1": p.get("target_1"),
                    "target_2": p.get("target_2"), "invalidation": p.get("invalidation"), "range_low": p.get("range_low"),
                    "range_high": p.get("range_high"), "calibrated_score": p.get("calibrated_score"),
                    "file_status": p.get("status"), "file_status_asof": p.get("status_asof"), "n_30m_bars": len(bars), **st}
        cnt[st["status"]] = cnt.get(st["status"], 0) + 1
    res = {"method_version": doc.get("method_version"), "kind": "chart_scenario_status_live", "shadow_only": True,
           "source": str(SRC).replace(str(HOME), "~"), "source_run_ts_pt": doc.get("run_ts_pt"), "asof_bar_date": doc.get("asof_bar_date"),
           "bars": "mini 1-min SIP bars (core store, else wide store) rolled to completed 30-min bars",
           "refreshed_ts": round(now, 1), "refreshed_pt": time.strftime("%Y-%m-%d %-I:%M:%S %p PT", time.localtime(now)),
           "note": "display/shadow only; Chart Bot's own outcomes are scored on real daily bars on the box. calibrated_score on primaries runs hot (~44% est vs ~36% realized).",
           "count": len(out), "status_counts": cnt, "tickers": out}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(res, indent=1))
    tmp.replace(OUT)
    print(json.dumps({"count": len(out), "status_counts": cnt, "secs": round(time.time() - t0, 2), "at": res["refreshed_pt"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
