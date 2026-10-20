"""Mini marks adapter: replaces the agent's RH get_equity_quotes step of dashboard/live_refresh.py.

Each cycle (60 s RTH / 300 s PRE-AH-overnight / idle CLOSED):
  symbols  = live_refresh.py --emit-symbols  ∪ stream allowlist ∪ config/mini-desk.json marks.extra_symbols
  live     = cache/mini-quotes.json rows with fresh=true (5 s poller against the local collector)
  snapshot = Alpaca SIP /v2/stocks/snapshots (prev close + fallback last/bid/ask), every snapshot_every_s
  -> RH-shaped equity file (last_trade_price, adjusted_previous_close, previous_close_date, bid/ask, times)
  -> python3 dashboard/live_refresh.py --equity-quotes-file F --options-from-mini --skip-rebuild
Rebuild/publish is the publish job's work. Heartbeat: cache/mini-marks.json. Research / paper only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Optional

from . import alpaca_rest, util

JOB = "marks"


def universe() -> list[str]:
    d = util.desk()
    syms: list[str] = []
    try:
        out = subprocess.run([sys.executable, str(d / "dashboard" / "live_refresh.py"), "--emit-symbols"],
                             capture_output=True, text=True, timeout=60, cwd=str(d))
        syms += json.loads(out.stdout).get("symbols", [])
    except Exception as e:  # noqa: BLE001
        util.log(JOB, f"emit-symbols failed: {type(e).__name__}")
    al = util.read_json(d / "config" / "stream-quote-allowlist.json")
    if isinstance(al, dict):
        al = al.get("underlyings") or al.get("symbols") or []
    syms += [s for s in (al or []) if isinstance(s, str)]
    syms += (util.desk_config("mini-desk.json").get("marks") or {}).get("extra_symbols", [])
    seen: set[str] = set()
    return [s.upper() for s in syms if s and not (s.upper() in seen or seen.add(s.upper()))]


def build_equity_payload(symbols: list[str], mini: dict, snaps: dict, today_et: Optional[str] = None) -> tuple[dict, dict]:
    """-> (RH-shaped {SYM: {...}}, counts). mini row wins for live fields when fresh; snapshot fills the rest."""
    if today_et is None:
        from datetime import datetime
        today_et = datetime.now(util.ET).strftime("%Y-%m-%d")
    out: dict[str, dict] = {}
    counts = {"mini": 0, "snapshot": 0, "missing": 0}
    mq = (mini or {}).get("quotes") or {}
    for s in symbols:
        sn = snaps.get(s) or {}
        prev = (sn.get("prevDailyBar") or {})
        day = (sn.get("dailyBar") or {})
        lt, lq = sn.get("latestTrade") or {}, sn.get("latestQuote") or {}
        row: dict[str, Any] = {}
        m = mq.get(s) or {}
        if m.get("fresh") and (m.get("last") or m.get("bid")):
            row = {"last_trade_price": m.get("last"), "bid_price": m.get("bid"), "ask_price": m.get("ask"),
                   "venue_last_trade_time": m.get("trade_time") or m.get("quote_time"), "src": "alpaca-sip-stream"}
            counts["mini"] += 1
        elif lt.get("p"):
            row = {"last_trade_price": lt.get("p"), "bid_price": lq.get("bp"), "ask_price": lq.get("ap"),
                   "venue_last_trade_time": lt.get("t"), "src": "alpaca-sip-snapshot"}
            counts["snapshot"] += 1
        else:
            counts["missing"] += 1
            continue
        # Alpaca: once today's session has a dailyBar, prevDailyBar is the prior close. Before today's first
        # regular-session bar (pre-market / overnight), dailyBar IS the prior session -> use it instead.
        pc_bar = prev
        if day.get("t") and day["t"][:10] < today_et:
            pc_bar = day
        if pc_bar.get("c") is not None:
            row["adjusted_previous_close"] = pc_bar.get("c")
            row["previous_close_date"] = (pc_bar.get("t") or "")[:10] or None
        row["state"] = "active"
        row["symbol"] = s
        if day.get("t"):
            row["day_bar_date"] = day["t"][:10]
        out[s] = row
    return out, counts


def cycle(*, force: bool = False) -> dict:
    d = util.desk()
    sess = util.session()
    res: dict[str, Any] = {"at_pt": util.now_pt_str(), "session": sess, "ok": False}
    if sess == "closed" and not force:
        res.update(ok=True, skipped="closed")
        return res
    syms = universe()
    snap_path = d / "cache" / "alpaca-snapshots.json"
    snap = util.read_json(snap_path) or {}
    every = float((util.desk_config("mini-desk.json").get("marks") or {}).get("snapshot_every_s", 60))
    if force or time.time() - float(snap.get("epoch") or 0) >= every:
        try:
            snap = {"epoch": time.time(), "at_pt": util.now_pt_str(), "snapshots": alpaca_rest.snapshots(syms)}
            util.atomic_write_json(snap_path, snap)
        except Exception as e:  # noqa: BLE001
            res["snapshot_error"] = type(e).__name__ + ": " + str(e)[:120]
    mini = util.read_json(d / "cache" / "mini-quotes.json") or {}
    payload, counts = build_equity_payload(syms, mini, snap.get("snapshots") or {})
    res.update(symbols=len(syms), counts=counts)
    if not payload:
        res["error"] = "no equity rows"
        return res
    eq = d / "tmp" / "mini-equity-quotes.json"
    util.atomic_write_json(eq, payload)
    p = subprocess.run([sys.executable, str(d / "dashboard" / "live_refresh.py"), "--equity-quotes-file", str(eq),
                        "--options-from-mini", "--skip-rebuild"], capture_output=True, text=True, timeout=240,
                       cwd=str(d))
    res["live_refresh_rc"] = p.returncode
    res["tail"] = " ".join((p.stdout + p.stderr).split())[-400:]
    res["ok"] = p.returncode == 0
    return res


def write_heartbeat(res: dict) -> None:
    util.atomic_write_json(util.desk() / "cache" / "mini-marks.json",
                           {**res, "writer": "mini:oid_desk.marks", "written_epoch": time.time()})


def loop() -> int:
    cfg = util.desk_config("mini-desk.json").get("marks") or {}
    while True:
        t0 = time.time()
        try:
            res = cycle()
        except Exception as e:  # noqa: BLE001
            res = {"at_pt": util.now_pt_str(), "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        write_heartbeat(res)
        if not res.get("ok"):
            util.log(JOB, json.dumps(res)[:500])
        sess = res.get("session") or "closed"
        wait = float(cfg.get("interval_rth_s", 60)) if sess == "rth" else float(cfg.get("interval_ext_s", 300))
        time.sleep(max(5.0, wait - (time.time() - t0)))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini marks adapter")
    ap.add_argument("cmd", choices=["loop", "once"])
    ap.add_argument("--force", action="store_true", help="run even when CLOSED")
    a = ap.parse_args(argv)
    if a.cmd == "loop":
        return loop()
    res = cycle(force=a.force)
    write_heartbeat(res)
    print(json.dumps(res, indent=1))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
