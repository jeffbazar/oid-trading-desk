"""Live volume v1 (2026-10-18): seconds-level rolling volume + 1-min bars from the SIP trade prints.

Equities (the 24 streamed names): every SIP trade print the stock socket already receives is rolled up
in memory into per-second buckets -> rolling 1s / 10s / 30s / 60s volume, live last price, the current
partial 1-min bar, RTH day high/low. Closed 1-min bars come from Alpaca's websocket `bars` channel
(authoritative, src alpaca-sip-ws; `updatedBars` corrections applied) with the print roll-up as fallback
(src prints) when no ws bar arrives within `ws_bar_grace_s`.

Baseline: 1-min SIP bars backfilled from Alpaca REST (via the collector's BarsProxy, data-only) for
~36 calendar days -> per-minute-of-day mean volume over the prior `norm_lookback` FULL RTH sessions
(half days excluded). Live rvol_1m = rolling 60 s volume / time-weighted norm of the minute slots that
window covers; pace_rvol_10s = (10 s volume * 6) / norm of the current slot.

Options (held contracts in options-subs.json): OPRA prints -> rolling 60 s / 5 min / day volume.

Calibrated 2026-10-18 against Alpaca 1Min bars (Fri 10/16 NVDA, BE 09:30-09:50 ET):
  volume  = all prints except official open/close re-reports (conditions Q, M, 9)  -> exact match
  price   = prints without odd-lot / average-price / out-of-sequence / derivative etc. conditions
            (PRICE_EXCLUDE)                                                       -> exact h/l match
Data-only. No trading calls. Never logs keys.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Any

from .timeutil import ET, PT, coerce_ts, now
from .volume5s import Volume5s

log = logging.getLogger("oid_quote.livevol")

VOLUME_EXCLUDE = frozenset({"Q", "M", "9"})
PRICE_EXCLUDE = frozenset({"I", "W", "4", "5", "7", "9", "B", "C", "G", "H", "M", "N", "P", "Q", "R", "T", "U", "V", "Z"})
RTH_SLOTS = 390
KEEP_S = 330  # per-second buckets kept (>= 5 min for options + ref price lookups)


def et_parts(epoch: float) -> tuple[str, int]:
    """(ET date 'YYYY-MM-DD', RTH slot 0..389 or -1 outside 09:30-16:00 ET)."""
    t = dt.datetime.fromtimestamp(epoch, ET)
    m = t.hour * 60 + t.minute - 570
    return t.strftime("%Y-%m-%d"), (m if 0 <= m < RTH_SLOTS and t.weekday() < 5 else -1)


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pt(epoch: float | None) -> str | None:
    return None if epoch is None else dt.datetime.fromtimestamp(epoch, PT).strftime("%Y-%m-%d %I:%M:%S %p PT")


class SymRoll:
    __slots__ = ("sym", "secs", "last", "last_t", "last_recv", "lag_s", "cur", "closed", "ws", "pending",
                 "day", "day_vol", "day_trades", "hi", "lo", "trades", "cancels")

    def __init__(self, sym: str):
        self.sym = sym
        self.secs: deque = deque()  # [sec, vol, notional, last_px_in_sec]
        self.last = self.last_t = self.last_recv = self.lag_s = None
        self.cur: dict | None = None  # partial minute bar (prints)
        self.closed: dict[int, dict] = {}  # minute_start -> prints bar (today, RTH + ext)
        self.ws: dict[int, dict] = {}  # minute_start -> ws bar
        self.pending: set[int] = set()  # closed RTH minutes not yet persisted
        self.day = None
        self.day_vol = 0
        self.day_trades = 0
        self.hi = self.lo = None  # RTH filtered
        self.trades = 0
        self.cancels = 0

    # -------------------------------------------------------------- ingest
    def add(self, ts: float, px: float | None, size: float, conds, recv: float) -> None:
        cs = set(conds or ())
        vol_ok = not (cs & VOLUME_EXCLUDE)
        px_ok = px is not None and not (cs & PRICE_EXCLUDE)
        sec = int(ts)
        self.trades += 1
        d, slot = et_parts(ts)
        if d != self.day:
            self.day, self.day_vol, self.day_trades, self.hi, self.lo = d, 0, 0, None, None
            self.closed.clear(); self.ws.clear(); self.pending.clear(); self.cur = None
        if vol_ok and slot >= 0:
            self.day_vol += size
            self.day_trades += 1
        # per-second bucket (append or late insert)
        if vol_ok or px_ok:
            b = None
            if self.secs and self.secs[-1][0] == sec:
                b = self.secs[-1]
            elif not self.secs or self.secs[-1][0] < sec:
                b = [sec, 0.0, 0.0, None]
                self.secs.append(b)
            else:  # late print: find its bucket (rare, short scan from the right)
                for x in reversed(self.secs):
                    if x[0] == sec:
                        b = x; break
                    if x[0] < sec:
                        break
            if b is not None:
                if vol_ok:
                    b[1] += size
                    if px is not None:
                        b[2] += size * px
                if px_ok and (self.last_t is None or ts >= self.last_t):
                    b[3] = px
        if px_ok and (self.last_t is None or ts >= self.last_t):
            self.last, self.last_t = px, ts
            self.last_recv, self.lag_s = recv, max(0.0, recv - ts)
        if px_ok and slot >= 0:
            self.hi = px if self.hi is None else max(self.hi, px)
            self.lo = px if self.lo is None else min(self.lo, px)
        # minute bar from prints
        ms = sec - sec % 60
        bar = self.cur if (self.cur and self.cur["ms"] == ms) else self.closed.get(ms)
        if bar is None:
            if self.cur is not None and self.cur["ms"] > ms:
                return  # print for a minute we never saw open (very late); volume already counted above
            if self.cur is not None:
                self._close_cur()
            bar = self.cur = {"ms": ms, "o": None, "h": None, "l": None, "c": None, "v": 0.0, "n": 0, "pv": 0.0}
        if vol_ok:
            bar["v"] += size; bar["n"] += 1
            if px is not None:
                bar["pv"] += size * px
        if px_ok:
            if bar["o"] is None:
                bar["o"] = px
            bar["h"] = px if bar["h"] is None else max(bar["h"], px)
            bar["l"] = px if bar["l"] is None else min(bar["l"], px)
            bar["c"] = px

    def adjust(self, ts: float, dsize: float, px: float | None, conds) -> None:
        """Cancel (dsize<0) / correction delta for an earlier print: fixes volume in the second bucket (if still
        kept), the minute bar (current or closed, not yet-persisted ws bars) and RTH day volume. Price/high/low
        are not rewound (rare; ws updatedBars carry the corrected bar)."""
        if set(conds or ()) & VOLUME_EXCLUDE:
            return
        sec = int(ts)
        d, slot = et_parts(ts)
        if d == self.day and slot >= 0:
            self.day_vol = max(0.0, self.day_vol + dsize)
        for b in reversed(self.secs):
            if b[0] == sec:
                b[1] = max(0.0, b[1] + dsize)
                if px is not None:
                    b[2] = max(0.0, b[2] + dsize * px)
                break
            if b[0] < sec:
                break
        ms = sec - sec % 60
        bar = self.cur if (self.cur and self.cur["ms"] == ms) else self.closed.get(ms)
        if bar is not None:
            bar["v"] = max(0.0, bar["v"] + dsize)
            if px is not None:
                bar["pv"] = max(0.0, bar["pv"] + dsize * px)
        self.cancels += 1

    def _close_cur(self) -> None:
        c = self.cur
        if c is None:
            return
        self.closed[c["ms"]] = c
        if et_parts(c["ms"])[1] >= 0:
            self.pending.add(c["ms"])
        self.cur = None

    def add_ws_bar(self, msg: dict) -> int | None:
        e, _ = coerce_ts(msg.get("t"))
        if e is None:
            return None
        ms = int(e) - int(e) % 60
        self.ws[ms] = {k: msg.get(k) for k in ("o", "h", "l", "c", "v", "n", "vw")}
        if et_parts(ms)[1] >= 0 and (self.cur is None or self.cur["ms"] != ms):
            self.pending.add(ms)
        return ms

    def tick(self, t: float) -> None:
        cut = int(t) - KEEP_S
        while self.secs and self.secs[0][0] < cut:
            self.secs.popleft()
        if self.cur is not None and t >= self.cur["ms"] + 60:
            self._close_cur()
        if len(self.closed) > 1000:
            for k in sorted(self.closed)[:-900]:
                self.closed.pop(k, None)
                self.ws.pop(k, None)

    # -------------------------------------------------------------- views
    def window(self, t: float, secs: int) -> tuple[float, float]:
        """Volume / notional of prints in the last `secs` seconds ending t (1 s bucket resolution)."""
        lo = t - secs
        v = pv = 0.0
        for b in reversed(self.secs):
            if b[0] + 1 <= lo:
                break
            w = 1.0 if b[0] >= lo else (b[0] + 1 - lo)  # boundary second counted pro rata
            v += b[1] * w; pv += b[2] * w
        return v, pv

    def px_at(self, t_ago: float) -> float | None:
        """Last filtered price at or before epoch t_ago (from per-second buckets)."""
        for b in reversed(self.secs):
            if b[0] <= t_ago and b[3] is not None:
                return b[3]
        return None

    def minute_bars_today(self) -> list[tuple[int, dict, str]]:
        out = []
        for ms in sorted(set(self.closed) | set(self.ws)):
            if et_parts(ms)[1] < 0:
                continue
            if ms in self.ws:
                out.append((ms, self.ws[ms], "alpaca-sip-ws"))
            else:
                b = self.closed[ms]
                out.append((ms, {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "n": b["n"],
                                 "vw": round(b["pv"] / b["v"], 4) if b["v"] else None}, "prints"))
        return out


class OptRoll:
    __slots__ = ("secs", "day", "day_vol", "day_trades", "last", "last_t", "last_recv")

    def __init__(self):
        self.secs: deque = deque()
        self.day = None
        self.day_vol = 0.0
        self.day_trades = 0
        self.last = self.last_t = self.last_recv = None

    def add(self, ts: float, px: float | None, size: float, recv: float) -> None:
        d = dt.datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")
        if d != self.day:
            self.day, self.day_vol, self.day_trades = d, 0.0, 0
        self.day_vol += size; self.day_trades += 1
        sec = int(ts)
        if self.secs and self.secs[-1][0] == sec:
            self.secs[-1][1] += size
        elif not self.secs or self.secs[-1][0] < sec:
            self.secs.append([sec, size])
        if px is not None and (self.last_t is None or ts >= self.last_t):
            self.last, self.last_t, self.last_recv = px, ts, recv

    def tick(self, t: float) -> None:
        cut = int(t) - KEEP_S
        while self.secs and self.secs[0][0] < cut:
            self.secs.popleft()

    def window(self, t: float, secs: int) -> float:
        lo = t - secs
        return round(sum(b[1] * (1.0 if b[0] >= lo else b[0] + 1 - lo) for b in self.secs if b[0] + 1 > lo))


class LiveVolume:
    def __init__(self, cfg: Any, collector: Any = None, tier: str = "core"):
        self.cfg = cfg
        self.collector = collector
        self.tier = tier  # "core" (stream allowlist) | "wide" (sector watch: trades + bars only, own store/norms/archive)
        self.eq: dict[str, SymRoll] = {}
        self.opt: dict[str, OptRoll] = {}
        self.norms: dict[str, list[float | None]] = {}
        self.norm_median: dict[str, float] = {}
        self.last_session: dict[str, dict[str, Any]] = {}  # latest backfilled RTH session per symbol (closed-market view)
        self.norm_meta: dict[str, Any] = {"for_date": None, "sessions": {}, "built_at": None, "error": None, "lookback": cfg.norm_lookback}
        self.store_dir = self._store_dir()
        self.stats: dict[str, Any] = {"ws_bars": 0, "ws_updated_bars": 0, "cancels": 0, "corrections": 0, "persisted": {"alpaca-sip-ws": 0, "prints": 0},
                                      "backfills": 0, "last_backfill_at": None, "last_backfill_error": None,
                                      "store_dir": str(self.store_dir), "finalized_for": None}
        # v0.5.0 (2026-10-18): volume_5s + live bars_1m archive sink (inert unless ~/oid-data exists)
        if tier == "wide":
            self.v5 = Volume5s(cfg, self, collector, root=getattr(cfg, "wide_archive_dir", "~/oid-data/archive-wide"),
                               universe_fn=(lambda: collector.wide_symbols()) if collector is not None else (lambda: [])) \
                if getattr(cfg, "volume_5s_enabled", True) else None
            if self.v5 is not None:
                self.v5.writer_name = "oid-quote-wide"
                from .archive_io import JsonlWriter
                self.v5.w5 = JsonlWriter("volume_5s", self.v5.writer_name, self.v5.root)
                self.v5.wb = JsonlWriter("bars_1m", self.v5.writer_name, self.v5.root)
        else:
            self.v5: Volume5s | None = Volume5s(cfg, self, collector) if getattr(cfg, "volume_5s_enabled", True) else None
        self._arch_done: dict[tuple[str, int], float] = {}

    def _store_dir(self) -> Path:
        if self.tier == "wide":
            return self.cfg.resolved_wide_store()
        if getattr(self.cfg, "live_store_dir", None):
            return Path(os.path.expanduser(self.cfg.live_store_dir))
        desk = Path.home() / "oid-desk/desk/cache/bars/store"
        return desk if desk.parent.exists() else self.cfg.cache_dir / "bars/store"

    # -------------------------------------------------------------- hooks (called from the feed recv loop)
    def on_trade(self, kind: str, m: dict, recv: float) -> None:
        sym = m.get("S")
        if not sym:
            return
        ts, _ = coerce_ts(m.get("t"))
        if ts is None:
            return
        try:
            size = float(m.get("s") or 0)
            px = float(m["p"]) if m.get("p") is not None else None
        except (TypeError, ValueError):
            return
        if kind == "equity":
            r = self.eq.get(sym)
            if r is None:
                r = self.eq[sym] = SymRoll(sym)
            r.add(ts, px, size, m.get("c"), recv)
            if self.v5 is not None:
                cs = set(m.get("c") or ())
                self.v5.on_print(sym, ts, px, size, m.get("c"), recv, not (cs & VOLUME_EXCLUDE),
                                 px is not None and not (cs & PRICE_EXCLUDE))
        else:
            r = self.opt.get(sym)
            if r is None:
                r = self.opt[sym] = OptRoll()
            r.add(ts, px, size, recv)

    def on_cancel(self, kind: str, m: dict, recv: float) -> None:
        """Alpaca trade cancel ('x') / correction ('c') messages (auto-delivered with the trades channel).
        Calibrated 10/16: Alpaca's 1-min bars drop canceled prints (e.g. INTC 2 x 500k QCT prints)."""
        if kind != "equity" or not m.get("S"):
            return
        r = self.eq.get(m["S"])
        if r is None:
            return
        ts, _ = coerce_ts(m.get("t"))
        if ts is None:
            return
        try:
            if m.get("T") == "x":
                deltas = [(-float(m.get("s") or 0), float(m["p"]) if m.get("p") is not None else None, m.get("c"))]
            else:  # correction: remove original, add corrected
                deltas = [(-float(m.get("os") or 0), float(m["op"]) if m.get("op") is not None else None, m.get("oc")),
                          (float(m.get("cs") or 0), float(m["cp"]) if m.get("cp") is not None else None, m.get("cc"))]
            for dsz, dpx, dc in deltas:
                r.adjust(ts, dsz, dpx, dc)
                if self.v5 is not None and not (set(dc or ()) & VOLUME_EXCLUDE):
                    self.v5.on_adjust(m["S"], ts, dsz, dpx)
        except (TypeError, ValueError):
            return
        self.stats["cancels" if m.get("T") == "x" else "corrections"] = self.stats.get("cancels" if m.get("T") == "x" else "corrections", 0) + 1

    def on_bar(self, kind: str, m: dict, recv: float, updated: bool = False) -> None:
        if kind != "equity" or not m.get("S"):
            return
        r = self.eq.get(m["S"])
        if r is None:
            r = self.eq[m["S"]] = SymRoll(m["S"])
        ms = r.add_ws_bar(m)
        self.stats["ws_updated_bars" if updated else "ws_bars"] += 1
        if self.v5 is not None and ms is not None:
            if updated:
                self.v5.bar_row(m["S"], ms, r.ws[ms], "alpaca-ws-updated")
                self._arch_done[(m["S"], ms)] = recv
            elif et_parts(ms)[1] < 0:  # pre/post bars: archived as they arrive (RTH goes through _persist_pending)
                self.v5.bar_row(m["S"], ms, r.ws[ms], "alpaca-ws")
                self._arch_done[(m["S"], ms)] = recv

    # -------------------------------------------------------------- periodic
    def tick(self, t: float | None = None) -> None:
        t = now() if t is None else t
        for r in self.eq.values():
            r.tick(t)
        for r in self.opt.values():
            r.tick(t)
        self._persist_pending(t)
        if self.v5 is not None:
            self.v5.tick(t)

    def _persist_pending(self, t: float) -> None:
        grace = float(self.cfg.ws_bar_grace_s)
        lines: dict[str, list[str]] = {}
        for sym, r in self.eq.items():
            done = []
            for ms in sorted(r.pending):
                if r.cur is not None and r.cur["ms"] == ms:
                    continue
                if ms in r.ws:
                    b, src = r.ws[ms], "alpaca-sip-ws"
                elif t >= ms + 60 + grace and ms in r.closed:
                    pb = r.closed[ms]
                    b = {"o": pb["o"], "h": pb["h"], "l": pb["l"], "c": pb["c"], "v": pb["v"], "n": pb["n"],
                         "vw": round(pb["pv"] / pb["v"], 4) if pb["v"] else None}
                    src = "prints"
                else:
                    continue
                d, slot = et_parts(ms)
                row = {"t": _iso(ms), "d": d, "slot": slot, **b, "src": src}
                lines.setdefault(sym, []).append(json.dumps(row, separators=(",", ":")))
                if self.v5 is not None and (sym, ms) not in self._arch_done:
                    self.v5.bar_row(sym, ms, b, "alpaca-ws" if src == "alpaca-sip-ws" else "print-rollup")
                    self._arch_done[(sym, ms)] = t
                self.stats["persisted"][src] = self.stats["persisted"].get(src, 0) + 1
                done.append(ms)
            r.pending.difference_update(done)
        if len(self._arch_done) > 60000:
            self._arch_done = {k: v for k, v in self._arch_done.items() if v > t - 86400}
        if not lines:
            return
        live_dir = self.store_dir / "live"
        try:
            live_dir.mkdir(parents=True, exist_ok=True)
            day = dt.datetime.fromtimestamp(t, ET).strftime("%Y%m%d")
            for sym, ls in lines.items():
                with open(live_dir / f"{sym}-1m-{day}.jsonl", "a") as f:
                    f.write("\n".join(ls) + "\n")
        except OSError as e:
            log.warning("live 1m persist failed: %s", type(e).__name__)

    # -------------------------------------------------------------- norms / backfill
    def half_day(self, date: str) -> bool:
        return date in set(self.cfg.half_days or [])

    def build_norms(self, by_sym: dict[str, dict[str, list[float | None]]], for_date: str) -> None:
        """by_sym: {SYM: {date: [390 volumes or None]}} (RTH only). Uses prior FULL sessions only."""
        lb = int(self.cfg.norm_lookback)
        norms, sess_meta = {}, {}
        for sym, days in by_sym.items():
            # full session = traded into the last 10 minutes (half days close 13:00 ET -> excluded); thin names may
            # have gappy minutes, a missing 1-min bar counts as 0 volume
            full = [d for d in sorted(days) if d < for_date and not self.half_day(d)
                    and sum(1 for v in days[d] if v is not None) >= self.cfg.full_session_min_bars
                    and max((i for i, v in enumerate(days[d]) if v is not None), default=-1) >= 380]
            use = full[-lb:]
            sess_meta[sym] = {"n": len(use), "range": [use[0], use[-1]] if use else None}
            if len(use) < int(getattr(self.cfg, "min_norm_sessions", 5)):
                sess_meta[sym]["note"] = "too few full sessions for a norm"
                continue
            row: list[float | None] = []
            for i in range(RTH_SLOTS):
                vals = [(days[d][i] or 0.0) for d in use]  # a missing 1-min bar on a full day = 0 volume
                row.append(sum(vals) / len(vals))
            norms[sym] = row
        self.norms = norms
        self.norm_median = {sym: sorted(row)[len(row) // 2] for sym, row in norms.items()}
        self.norm_meta = {"for_date": for_date, "sessions": sess_meta, "built_at": _pt(now()), "error": None, "lookback": lb}

    async def backfill_once(self, symbols: list[str], finalize_today: bool = False) -> dict[str, Any]:
        proxy = getattr(self.collector, "bars_proxy", None) if self.collector else None
        if proxy is None:
            raise RuntimeError("bars proxy not ready")
        end = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=20)
        start = end - dt.timedelta(days=int(self.cfg.backfill_calendar_days))
        today = dt.datetime.now(ET).strftime("%Y-%m-%d")
        by_sym: dict[str, dict[str, list]] = {}
        counts = {}
        self.store_dir.mkdir(parents=True, exist_ok=True)
        failed = {}
        for sym in symbols:
            try:
                res = await proxy.fetch([sym], "1Min", start, end, "sip", "raw")
            except Exception as e:  # one bad symbol never blocks the rest
                failed[sym] = str(e)[:80] if "HTTP" in str(e) else type(e).__name__
                continue
            rows = (res.get("bars") or {}).get(sym) or []
            days: dict[str, list] = {}
            keep = []
            for b in rows:
                e, _ = coerce_ts(b.get("t"))
                if e is None:
                    continue
                d, slot = et_parts(e)
                if slot < 0:
                    continue
                days.setdefault(d, [None] * RTH_SLOTS)[slot] = float(b.get("v") or 0)
                keep.append({"t": _iso(e), "d": d, "slot": slot, **{k: b.get(k) for k in ("o", "h", "l", "c", "v", "n", "vw")}, "src": "alpaca-sip-rest"})
            by_sym[sym] = days
            counts[sym] = len(keep)
            if keep:
                ld = keep[-1]["d"]
                lb = [k for k in keep if k["d"] == ld]
                hs = [float(k["h"]) for k in lb if k.get("h") is not None]
                ls_ = [float(k["l"]) for k in lb if k.get("l") is not None]
                self.last_session[sym] = {"date": ld, "close": lb[-1].get("c"), "high": max(hs) if hs else None,
                                          "low": min(ls_) if ls_ else None, "volume": round(sum(float(k.get("v") or 0) for k in lb)),
                                          "last_bar_t": lb[-1]["t"], "bars": len(lb), "complete": lb[-1]["slot"] >= 380}
            dates = sorted({k["d"] for k in keep})[-(int(self.cfg.norm_lookback) + 6):]
            keep = [k for k in keep if k["d"] in set(dates)]
            payload = {"symbol": sym, "interval": "1m", "bounds": "regular", "updated_pt": _pt(now()),
                       "writer": "oid-quote-collector livevol", "source": "Alpaca SIP 1Min REST (raw); today's live bars in live/<SYM>-1m-<YYYYMMDD>.jsonl",
                       "sessions": dates, "bars": keep}
            p = self.store_dir / f"{sym}-1m.json"
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, separators=(",", ":")))
            os.replace(tmp, p)
            await asyncio.sleep(0)
        self.build_norms(by_sym, today)
        for sym, why in failed.items():
            self.norm_meta["sessions"][sym] = {"n": 0, "range": None, "note": f"backfill failed: {why}"}
        self.stats["backfill_failed"] = failed
        self._write_norms()
        self._prune_live()
        if self.tier == "wide":
            self.prune_archive(int(getattr(self.cfg, "wide_archive_keep_days", 21)))
        self.stats["backfills"] += 1
        self.stats["last_backfill_at"] = _pt(now())
        self.stats["last_backfill_error"] = None
        if finalize_today:
            self.stats["finalized_for"] = today
        return {"symbols": len(symbols), "bars": counts, "for_date": today, "failed": failed}

    def _write_norms(self) -> None:
        p = self.store_dir.parent / "live-norms-1m.json"
        payload = {"generated_pt": _pt(now()), "writer": "oid-quote-collector livevol", **self.norm_meta,
                   "def": "mean 1-min volume per RTH minute-of-day slot (0=09:30 ET) over the prior N full RTH sessions (half days excluded)",
                   "norms": {s: [round(v) if v is not None else None for v in row] for s, row in self.norms.items()},
                   "last_session": self.last_session}
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")))
        os.replace(tmp, p)

    def load_norms_file(self) -> bool:
        p = self.store_dir.parent / "live-norms-1m.json"
        try:
            d = json.loads(p.read_text())
        except Exception:
            return False
        self.norms = {s: [float(v) if v is not None else None for v in row] for s, row in (d.get("norms") or {}).items()}
        self.norm_median = {s: sorted(row)[len(row) // 2] for s, row in self.norms.items()}
        self.norm_meta = {k: d.get(k) for k in ("for_date", "sessions", "built_at", "lookback")}
        self.last_session = d.get("last_session") or {}
        self.norm_meta["error"] = None
        return bool(self.norms)

    def prune_archive(self, keep_days: int) -> int:
        """WIDE tier only: delete archive-wide/<table>/date=YYYY-MM-DD partitions older than keep_days (raw JSONL, never
        compacted). The core archive keeps its own 90-day policy (oid_archive.integrity) and is never touched here."""
        if self.tier != "wide" or self.v5 is None:
            return 0
        import shutil
        root = self.v5.root
        cutoff = (dt.datetime.now(ET).date() - dt.timedelta(days=int(keep_days))).isoformat()
        n = 0
        try:
            if "archive-wide" not in str(root):  # safety: never prune anything but the wide root
                return 0
            for tdir in root.iterdir() if root.exists() else []:
                if not tdir.is_dir():
                    continue
                for ddir in tdir.glob("date=*"):
                    if ddir.is_dir() and ddir.name[5:] < cutoff:
                        shutil.rmtree(ddir, ignore_errors=True)
                        n += 1
        except OSError:
            pass
        self.stats["archive_pruned"] = self.stats.get("archive_pruned", 0) + n
        return n

    def _prune_live(self) -> None:
        live_dir = self.store_dir / "live"
        if not live_dir.exists():
            return
        cutoff = (dt.datetime.now(ET) - dt.timedelta(days=10)).strftime("%Y%m%d")
        for f in live_dir.glob("*-1m-*.jsonl"):
            if f.stem.rsplit("-", 1)[-1] < cutoff:
                try:
                    f.unlink()
                except OSError:
                    pass

    # -------------------------------------------------------------- read views
    def norm_for(self, sym: str, t: float) -> tuple[float | None, float | None]:
        """(time-weighted norm for the rolling 60 s window ending t, norm of current slot)."""
        row = self.norms.get(sym)
        d, slot = et_parts(t)
        if row is None or slot < 0:
            return None, None
        cur = row[slot]
        frac = (t % 60) / 60.0
        prev = row[slot - 1] if slot > 0 else cur
        if cur is None or prev is None:
            return None, cur
        return cur * frac + prev * (1 - frac), cur

    def day_norm_to_now(self, sym: str, t: float) -> float | None:
        """Normal RTH cumulative volume from 09:30 ET through now (pro rata current minute)."""
        row = self.norms.get(sym)
        d, slot = et_parts(t)
        if row is None:
            return None
        if slot < 0:
            et = dt.datetime.fromtimestamp(t, ET)
            if et.hour * 60 + et.minute < 570:
                return None
            return round(sum(v or 0 for v in row))  # after the close: full-day norm
        return round(sum(v or 0 for v in row[:slot]) + (row[slot] or 0) * ((t % 60) / 60.0))

    def view_symbol(self, sym: str, t: float, detail: bool = False) -> dict[str, Any] | None:
        r = self.eq.get(sym)
        if r is None:
            return None
        v1, _ = r.window(t, 1)
        v10, _ = r.window(t, 10)
        v30, _ = r.window(t, 30)
        v60, pv60 = r.window(t, 60)
        v15, _ = r.window(t, 15)   # VOLDIR (2026-10-20): last 15 s vs the prior 60 s (15-75 s ago)
        v75, _ = r.window(t, 75)
        n60, ncur = self.norm_for(sym, t)
        d, slot = et_parts(t)
        bars = r.minute_bars_today()
        cutoff = int(t) - int(t) % 60 - 300  # ref levels exclude the last 5 minutes (incl. current)
        ref = [b for ms, b, _ in bars if ms < cutoff and b.get("h") is not None]
        cur = r.cur if (r.cur and r.cur["ms"] == int(t) - int(t) % 60) else None
        out: dict[str, Any] = {
            "last": r.last, "last_trade_pt": _pt(r.last_t), "last_trade_epoch": r.last_t,
            "last_age_s": round(t - r.last_t, 3) if r.last_t else None,
            "lag_s": round(r.lag_s, 3) if r.lag_s is not None else None,
            "vol_1s": round(v1), "vol_10s": round(v10), "vol_30s": round(v30), "vol_60s": round(v60),
            "vol_15s": round(v15), "vol_prev60_15": round(max(0.0, v75 - v15)),
            "vwap_60s": round(pv60 / v60, 4) if v60 else None,
            "px_10s_ago": r.px_at(t - 10), "px_30s_ago": r.px_at(t - 30), "px_60s_ago": r.px_at(t - 60),
            "norm_1m": round(n60) if n60 else None, "norm_slot": round(ncur) if ncur else None,
            "norm_median_1m": round(self.norm_median[sym]) if sym in self.norm_median else None,
            "day_norm_to_now": self.day_norm_to_now(sym, t), "day_rvol": None,
            "rvol_1m": round(v60 / n60, 2) if n60 else None,
            "pace_rvol_10s": round(v10 * 6 / ncur, 2) if ncur else None,
            "pace_rvol_30s": round(v30 * 2 / ncur, 2) if ncur else None,
            "cur_bar": ({"t": _iso(cur["ms"]), "o": cur["o"], "h": cur["h"], "l": cur["l"], "c": cur["c"], "v": cur["v"],
                         "n": cur["n"], "partial": True, "elapsed_s": round(t - cur["ms"], 1)} if cur else None),
            "last_closed_bar": ({"t": _iso(bars[-1][0]), **bars[-1][1], "src": bars[-1][2]} if bars else None),
            "day_date": r.day, "day_vol_rth": r.day_vol, "day_high": r.hi, "day_low": r.lo,
            "ref_high_5m": max(b["h"] for b in ref) if ref else None,
            "ref_low_5m": min(b["l"] for b in ref) if ref else None,
            "bars_today": len(bars),
        }
        ls = self.last_session.get(sym) or {}
        out["prev_close"] = ls.get("close") if ls.get("date") and ls["date"] < (r.day or d) and ls.get("complete") else None
        if r.day and r.day != d and sym in self.norms:  # last session was an earlier day (weekend/overnight): full-day norm
            out["day_norm_to_now"] = round(sum(v or 0 for v in self.norms[sym]))
        dn = out["day_norm_to_now"]
        if dn and r.day:
            out["day_rvol"] = round(r.day_vol / dn, 2)
        if detail:
            lo = int(t) - 60
            out["seconds"] = [[b[0], b[1]] for b in r.secs if b[0] > lo]
        return out

    def view_option(self, occ: str, t: float) -> dict[str, Any] | None:
        r = self.opt.get(occ)
        if r is None:
            return None
        return {"last": r.last, "last_trade_pt": _pt(r.last_t), "last_age_s": round(t - r.last_t, 1) if r.last_t else None,
                "vol_60s": r.window(t, 60), "vol_5m": r.window(t, 300), "day_date": r.day, "day_vol": r.day_vol,
                "day_trades": r.day_trades}

    def view(self, symbols: list[str] | None, contracts: list[str] | None, detail: bool, stream_health: dict | None,
             t: float | None = None) -> dict[str, Any]:
        t = now() if t is None else t
        d, slot = et_parts(t)
        syms = symbols if symbols is not None else sorted(self.eq)
        occs = contracts if contracts is not None else sorted(self.opt)
        sh = stream_health or {}
        return {
            "as_of_pt": _pt(t), "as_of_epoch": round(t, 3), "et_date": d, "rth_slot": slot,
            "session": "RTH" if slot >= 0 else "off-RTH", "half_day": self.half_day(d),
            "stream": {k: sh.get(k) for k in ("feed", "connected", "last_data_age_s", "state")},
            "norms": {"for_date": self.norm_meta.get("for_date"), "built_at": self.norm_meta.get("built_at"),
                      "symbols": len(self.norms), "lookback": self.norm_meta.get("lookback"),
                      "current": self.norm_meta.get("for_date") == d},
            "rules": {"volume_excludes_conditions": sorted(VOLUME_EXCLUDE), "rvol_1m": "rolling 60s vol / time-weighted same-minute norm",
                      "pace_rvol_10s": "10s vol x6 / current-slot norm"},
            "symbols": {s: v for s in syms if (v := self.view_symbol(s, t, detail)) is not None},
            "missing": [s for s in syms if s not in self.eq],
            "last_session": {s: self.last_session_view(s) for s in (symbols if symbols is not None else sorted(set(self.eq) | set(self.last_session)))
                             if s in self.last_session},
            "options": {o: v for o in occs if (v := self.view_option(o, t)) is not None},
            "stats": self.stats,
        }

    def last_session_view(self, sym: str) -> dict[str, Any]:
        ls = dict(self.last_session[sym])
        row = self.norms.get(sym)
        full = round(sum(v or 0 for v in row)) if row else None
        ls["norm_day"] = full
        ls["day_rvol"] = round(ls["volume"] / full, 2) if full and ls.get("complete") else None
        return ls

    def health(self) -> dict[str, Any]:
        return {"symbols": len(self.eq), "options": len(self.opt), "norms_for": self.norm_meta.get("for_date"),
                "norm_symbols": len(self.norms), **{k: self.stats[k] for k in ("ws_bars", "ws_updated_bars", "cancels", "corrections", "persisted",
                                                                               "backfills", "last_backfill_at", "last_backfill_error", "finalized_for")},
                "volume_5s": self.v5.health() if self.v5 is not None else {"enabled": False}}


def read_vol_surge(state_dir: str, n: int = 20, tail_bytes: int = 512_000) -> dict[str, Any]:
    """Read-only peek at the trigger engine's vol_surge output on this host: latest n events (compact) + loop status."""
    root = Path(state_dir).expanduser()
    out: dict[str, Any] = {"events": [], "status": None}
    try:
        st = json.loads((root / "volsurge-status.json").read_text())
        out["status"] = {k: st.get(k) for k in ("mode", "last_gate", "updated_pt", "updated_epoch", "started_pt", "ticks", "errors", "fired", "vol_surge_live_flag", "global_live")
                         if k in st}
    except Exception:
        pass
    p = root / "events.jsonl"
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except Exception:
        return out
    evs = []
    for ln in reversed(lines):
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("event_type") != "vol_surge":
            continue
        d = e.get("details") or {}
        evs.append({"symbol": e.get("symbol"), "engine_pt": e.get("engine_pt"), "data_stamp": e.get("data_stamp"),
                    "level": d.get("level"), "level_price": d.get("level_price"), "dir": d.get("dir"), "last": d.get("last"),
                    "rvol_1m": d.get("rvol_1m"), "pace_rvol_10s": d.get("pace_rvol_10s"), "vol_60s": d.get("vol_60s"),
                    "seat_id": e.get("seat_id"), "dry_run": bool(e.get("dry_run", True)), "batch_id": e.get("batch_id")})
        if len(evs) >= n:
            break
    out["events"] = evs
    return out
