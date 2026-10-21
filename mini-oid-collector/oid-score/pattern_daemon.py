#!/usr/bin/env python3
"""PATTERNS (2026-10-21): live chart-pattern detector daemon (launchd com.oid.desk.patterns). SHADOW ONLY.

At each 1-min bar close (+8 s, so the collector has written the bar) in RTH (6:30 AM-1:00 PM PT, weekdays) it reads
today's 1-min SIP bars for every tracked ticker (core bar store + Sector watch store), feeds the closed 1-min bars to
the 1m engine and every completed 5-min / 30-min bucket to the 5m / 30m engines (patterns.py), and for each state
change appends one record to ~/oid-data/archive/patterns/date=YYYY-MM-DD/part-patterns-live-<n>.jsonl with prob_est
(base-rates.json), the score values and momentum state at that moment. It rewrites ~/oid-data/patterns/live.json
(active patterns per ticker; read by score_features as shadow fields, the live page Patterns column and the chart).
Restart-safe: engines are re-warmed on prior sessions, today's bars replayed, and records already in today's archive
(same rec_id) are not written again. Never feeds a score or a trade; no paid calls; no network except the local
live page state.json (momentum state). Kill switch: touch ~/oid-data/patterns/disabled
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / "oid-score"))
import patterns as PT  # noqa: E402
import pattern_io as IO  # noqa: E402

FORCE_OPEN = os.environ.get("OID_PATTERNS_FORCE_OPEN") == "1"   # test only: treat now as RTH, use the day's REST bars
FORCE_DATE = os.environ.get("OID_PATTERNS_DATE")


def rth(now):
    d = datetime.fromtimestamp(now, IO.PTZ)
    return d.weekday() < 5 and (6, 30) <= (d.hour, d.minute) <= (13, 1)


class Day:
    def __init__(self, date, uni):
        self.date, self.uni = date, uni
        self.eng, self.fed1, self.fedk, self.store = {}, {}, {}, {}
        self.seen = IO.seen_ids(date)
        self.writer = IO.Writer("live")
        t0 = time.time()
        for sym, tier, store in uni:
            try:
                h = IO.hist_1m(sym, store, before=date)
                self.eng[sym] = IO.warm(sym, h)
                self.store[sym] = store
                self.fed1[sym] = 0
                self.fedk[sym] = {"5m": 0, "30m": 0}
            except Exception as e:
                IO.log(f"warm {sym} failed: {type(e).__name__}: {e}")
        IO.log(f"day {date}: {len(self.eng)} tickers warmed in {time.time() - t0:.1f} s; {len(self.seen)} records already archived")

    def pass_(self, now, ctx):
        rd = IO.rates()
        recs, nbars = [], 0
        for sym, eng in self.eng.items():
            try:
                b1 = IO.day_1m(sym, self.date, self.store[sym], live_only=not FORCE_OPEN)
            except Exception:
                continue
            cut = now - 2
            closed = [b for b in b1 if b[0] + 60 <= cut]
            new = [b for b in closed if b[0] > self.fed1[sym]]
            out = []
            for b in new:
                out += eng["1m"].step(b)
                self.fed1[sym] = b[0]
                nbars += 1
            if new:
                for iv in ("5m", "30m"):
                    s = PT.IV_MIN[iv] * 60
                    for bb in PT.roll(closed, iv):
                        if bb[0] + s <= cut and bb[0] > self.fedk[sym][iv]:
                            out += eng[iv].step(bb)
                            self.fedk[sym][iv] = bb[0]
            for r in out:
                IO.enrich(r, rd, ctx, "live")
                if r["rec_id"] in self.seen:
                    continue
                self.seen.add(r["rec_id"])
                recs.append(r)
        self.writer.write(self.date, recs)
        IO.write_live(self.eng, rd, now)
        return recs, nbars


def main():
    IO.log(f"pattern daemon up ({PT.DETECTOR_VERSION}){' FORCE_OPEN' if FORCE_OPEN else ''}")
    day, uni, ctx = None, None, IO.LiveCtx()
    stats = {"recs": 0, "passes": 0, "errors": 0, "ms": 0.0}
    last_log = 0
    while True:
        now = time.time()
        if (IO.PDIR / "disabled").exists():
            time.sleep(30)
            continue
        if not (FORCE_OPEN or rth(now)):
            if day is not None:
                IO.log(f"session over: {stats}")
                day = None
            time.sleep(30)
            continue
        date = FORCE_DATE or datetime.fromtimestamp(now, IO.ET).strftime("%Y-%m-%d")
        try:
            if day is None or day.date != date:
                uni = IO.universe()
                day = Day(date, uni)
                stats = {"recs": 0, "passes": 0, "errors": 0, "ms": 0.0}
            t0 = time.time()
            ctx.refresh(now)
            recs, nb = day.pass_(now, ctx)
            stats["recs"] += len(recs)
            stats["passes"] += 1
            stats["ms"] = round((time.time() - t0) * 1000, 1)
            if recs or now - last_log > 900:
                IO.log(f"pass: {nb} new 1m bars, {len(recs)} records ({stats})")
                last_log = now
        except Exception as e:
            stats["errors"] += 1
            IO.log(f"pass error: {type(e).__name__}: {e}")
        if FORCE_OPEN and os.environ.get("OID_PATTERNS_ONCE") == "1":
            return 0
        nxt = (int(time.time()) // 60 + 1) * 60 + 8
        time.sleep(max(1.0, nxt - time.time()))


if __name__ == "__main__":
    sys.exit(main())
