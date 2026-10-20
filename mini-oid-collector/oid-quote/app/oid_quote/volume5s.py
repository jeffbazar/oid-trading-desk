"""volume_5s archive writer (schema v1, SCHEMAS.md §2) + live bars_1m archive sink. Data-only; never raises into
the feed loop (every public method is wrapped).

Buckets are UTC epoch multiples of 5 s, left-closed [start, start+5). Fed from the same SIP prints and the same
condition filters as /v1/live-volume (volume excludes Q/M/9; price excludes PRICE_EXCLUDE). Cancels/corrections
are applied while the bucket is still open. Each bucket is written once, at bucket_end + 3 s:
  rth  -> dense: one row per universe symbol per bucket (volume 0 allowed), only once an RTH print has been seen
          that ET day (holidays write nothing; if none by 09:40 ET the day is treated as closed)
  pre/post -> sparse: only symbols with prints; overnight (20:00-04:00 ET) is not logged in v1.
Prints for a bucket already written count as `late_prints` on that symbol's next row.
Writes nothing unless the archive's data root (~/oid-data) exists, so shipping the code is inert until deploy.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from . import __version__
from .archive_io import ET, NS, JsonlWriter, archive_root, common, iso_ns, session_of

log = logging.getLogger("oid_quote.volume5s")

B = 5          # bucket seconds
GRACE = 3      # write at bucket_end + GRACE
OPEN_WAIT_S = 600  # RTH buckets are held up to 10 min after 09:30 ET waiting for the first RTH print


class Volume5s:
    def __init__(self, cfg: Any, livevol: Any, collector: Any = None, root: str | None = None, t0: float | None = None):
        self.cfg, self.lv, self.collector = cfg, livevol, collector
        r = root or getattr(cfg, "archive_dir", None)
        self.root = Path(os.path.expanduser(r)) if r else archive_root()  # env OID_ARCHIVE_ROOT / OID_DATA_ROOT, default ~/oid-data/archive
        self.writer_name = "oid-quote"
        self.writer_tag = f"oid-quote@{__version__}"
        self.w5 = JsonlWriter("volume_5s", self.writer_name, self.root)
        self.wb = JsonlWriter("bars_1m", self.writer_name, self.root)
        self.agg: dict[int, dict[str, list]] = {}  # bucket_start_s -> sym -> [vol, n, o, h, l, c, pv]
        self.bad: dict[int, set] = {}              # bucket_start_s -> symbols lagged > 5 s
        self.global_bad: set[int] = set()          # buckets where the stock socket was down at a tick
        self.feed_at: dict[int, str] = {}
        self.late: dict[str, int] = {}
        self.rth_seen: set[str] = set()            # ET dates with >= 1 RTH print
        self.wm: int | None = None                 # last bucket start written (or skipped)
        self.t0 = t0
        self.stats = {"rows": 0, "bar_rows": 0, "late_prints": 0, "errors": 0, "last_write_iso": None, "enabled": None}

    # ------------------------------------------------------------------ helpers
    def enabled(self) -> bool:
        ok = self.root.parent.exists()
        self.stats["enabled"] = ok
        return ok

    def _universe(self) -> list[str]:
        c = self.collector
        try:
            syms = list(c.stocks_subs.symbols) if c is not None else []
        except Exception:  # noqa: BLE001
            syms = []
        return sorted(set(syms) | set(self.lv.eq.keys()))

    def _feed(self) -> str | None:
        s = getattr(self.collector, "stocks", None)
        return getattr(s, "current_feed", None) if s is not None else None

    def _connected(self) -> bool:
        s = getattr(self.collector, "stocks", None)
        if s is None:
            return True  # tests / no stream object: assume up
        return bool(getattr(s, "connected", False))

    # ------------------------------------------------------------------ ingest (feed loop)
    def on_print(self, sym: str, ts: float, px: float | None, size: float, conds, recv: float, vol_ok: bool, px_ok: bool) -> None:
        try:
            b = int(ts) - int(ts) % B
            sess = session_of(b * NS)
            if sess is None:  # overnight / weekend prints are not logged in v1 (and never count as late)
                return
            if self.wm is not None and b <= self.wm:
                if (self.wm - b) < 3600:  # a genuinely late print for a bucket we already wrote
                    self.late[sym] = self.late.get(sym, 0) + 1
                    self.stats["late_prints"] += 1
                return
            if sess == "rth" and vol_ok:
                self.rth_seen.add(_et_date(b))
            a = self.agg.setdefault(b, {}).get(sym)
            if a is None:
                a = self.agg[b][sym] = [0.0, 0, None, None, None, None, 0.0]
            if vol_ok:
                a[0] += size; a[1] += 1
                if px is not None:
                    a[6] += size * px
            if px_ok and px is not None:
                if a[2] is None:
                    a[2] = px
                a[3] = px if a[3] is None else max(a[3], px)
                a[4] = px if a[4] is None else min(a[4], px)
                a[5] = px
            if recv - ts > 5.0:
                self.bad.setdefault(b, set()).add(sym)
        except Exception:  # noqa: BLE001
            self.stats["errors"] += 1

    def on_adjust(self, sym: str, ts: float, dsize: float, px: float | None) -> None:
        """Cancel/correction delta, applied only while the bucket is still open."""
        try:
            b = int(ts) - int(ts) % B
            a = (self.agg.get(b) or {}).get(sym)
            if a is None or (self.wm is not None and b <= self.wm):
                return
            a[0] = max(0.0, a[0] + dsize)
            if px is not None:
                a[6] = max(0.0, a[6] + dsize * px)
        except Exception:  # noqa: BLE001
            self.stats["errors"] += 1

    # ------------------------------------------------------------------ periodic (1 s tick)
    def tick(self, t: float) -> int:
        try:
            if not self.enabled():
                self.agg.clear(); self.bad.clear(); self.global_bad.clear(); self.feed_at.clear()
                return 0
            cur = int(t) - int(t) % B
            self.feed_at.setdefault(cur, self._feed() or "sip")
            if not self._connected():
                self.global_bad.add(cur)
            if self.wm is None:
                start = self.t0 if self.t0 is not None else t
                self.wm = int(start) - int(start) % B  # first full bucket after start is the first written
            return self._emit(t)
        except Exception:  # noqa: BLE001
            self.stats["errors"] += 1
            log.exception("volume_5s tick failed")
            return 0

    def _emit(self, t: float) -> int:
        due = int(t) - GRACE - B  # latest bucket start whose end + GRACE <= t
        due -= due % B
        if self.wm is None or due <= self.wm:
            return 0
        if due - self.wm > 86400:  # long idle (overnight / process paused): jump, never loop a whole day
            self.wm = due - 3600 - (due - 3600) % B
        rows: list[dict] = []
        uni = None
        b = self.wm + B
        while b <= due:
            sess = session_of(b * NS)
            if sess == "rth":
                d = _et_date(b)
                if d not in self.rth_seen:
                    if t - _rth_open_s(d) < OPEN_WAIT_S:
                        break  # hold: no RTH print yet this morning; decide by 09:40 ET
                else:
                    uni = uni if uni is not None else self._universe()
                    rows.extend(self._row(sym, b, sess) for sym in uni)
            elif sess in ("pre", "post"):
                rows.extend(self._row(sym, b, sess) for sym in sorted(self.agg.get(b) or {}))
            self.agg.pop(b, None); self.bad.pop(b, None); self.global_bad.discard(b); self.feed_at.pop(b, None)
            self.wm = b
            b += B
        for k in [k for k in self.agg if k <= (self.wm or 0)]:
            self.agg.pop(k, None)
        if rows:
            ing = None
            if self.w5.write(rows):
                self.stats["rows"] += len(rows)
                self.stats["last_write_iso"] = iso_ns(rows[-1]["ingest_ts_ns"])
                ing = True
            if not ing:
                self.stats["errors"] += 1
        return len(rows)

    def _row(self, sym: str, b: int, sess: str) -> dict[str, Any]:
        a = (self.agg.get(b) or {}).get(sym) or [0.0, 0, None, None, None, None, 0.0]
        vol = int(round(a[0]))
        rv = pace = None
        if sess == "rth":
            rv, pace = self._rvol(sym, b + B)
        late = self.late.pop(sym, 0)
        start = b * NS
        row = {"symbol": sym, "bucket_start_ns": start, "bucket_start_iso": iso_ns(start), "bucket_end_ns": start + B * NS,
               "session": sess, "volume": vol, "trade_count": int(a[1]),
               "open": a[2] if a[1] else None, "high": a[3] if a[1] else None, "low": a[4] if a[1] else None,
               "close": a[5] if a[1] else None, "vwap": (a[6] / a[0]) if a[0] and a[6] else None,
               "rvol_1m_at_end": rv, "pace_rvol_10s_at_end": pace,
               "stream_feed": self.feed_at.get(b) or self._feed() or "sip",
               "stream_ok": not (b in self.global_bad or sym in (self.bad.get(b) or ())), "late_prints": late}
        row.update(common(start, None, self.writer_tag))
        return row

    def _rvol(self, sym: str, t_end: float) -> tuple[float | None, float | None]:
        try:
            r = self.lv.eq.get(sym)
            if r is None or not self.lv.norms:
                return None, None
            n60, ncur = self.lv.norm_for(sym, t_end - 1e-6)
            v60, _ = r.window(t_end - 1e-6, 60)
            v10, _ = r.window(t_end - 1e-6, 10)
            return (round(v60 / n60, 3) if n60 else None), (round(v10 * 6 / ncur, 3) if ncur else None)
        except Exception:  # noqa: BLE001
            return None, None

    # ------------------------------------------------------------------ live bars_1m sink
    def bar_row(self, sym: str, start_s: int, b: dict, src: str) -> None:
        """Archive one closed 1-min bar (src alpaca-ws / alpaca-ws-updated / print-rollup); final=false until the
        2:00 PM PT REST reconcile."""
        try:
            if not self.enabled():
                return
            start = int(start_s) * NS
            sess = session_of(start)
            if sess is None:
                return
            row = {"symbol": sym, "timeframe": "1m", "bar_start_ns": start, "bar_start_iso": iso_ns(start),
                   "bar_end_ns": start + 60 * NS, "session": sess, "open": b.get("o"), "high": b.get("h"),
                   "low": b.get("l"), "close": b.get("c"), "volume": int(round(float(b.get("v") or 0))),
                   "vwap": b.get("vw"), "trade_count": int(b["n"]) if b.get("n") is not None else None, "src": src,
                   "feed": self._feed() or "sip", "adjustment": "raw", "final": False, "revised_ts_ns": None}
            row.update(common(start, None, self.writer_tag))
            if self.wb.write([row]):
                self.stats["bar_rows"] += 1
        except Exception:  # noqa: BLE001
            self.stats["errors"] += 1

    def health(self) -> dict[str, Any]:
        return dict(self.stats, root=str(self.root), watermark_iso=iso_ns(self.wm * NS) if self.wm else None,
                    open_buckets=len(self.agg), write_errors=self.w5.errors + self.wb.errors)


def _et_date(b: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(b, ET).strftime("%Y-%m-%d")


def _rth_open_s(date: str) -> float:
    import datetime as dt
    d = dt.date.fromisoformat(date)
    return dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET).timestamp()
