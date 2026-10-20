"""In-memory latest-quote cache (equities + option contracts) with read-time freshness views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .timeutil import coerce_ts, epoch_to_pt_iso, now, session_for

LAG_BUCKETS_MS = (50, 100, 250, 500, 1000, 5000)


@dataclass
class FeedMeta:
    """Describes where a cache row came from (attached at write time)."""

    feed: str  # alpaca-sip / alpaca-iex / alpaca-overnight / alpaca-opra / alpaca-indicative / ...
    venue_scope: str  # consolidated / iex / overnight / OPRA / indicative
    delayed: bool
    stream_feed: str = ""  # raw Alpaca feed name the row came in on: sip / overnight / iex / opra ...


def feed_meta_for(kind: str, feed: str) -> FeedMeta:
    if kind == "option":
        if feed == "opra":
            return FeedMeta("alpaca-opra", "OPRA", False, feed)
        return FeedMeta(f"alpaca-{feed}", feed, True, feed)
    if feed == "sip":
        return FeedMeta("alpaca-sip", "consolidated", False, feed)
    if feed == "iex":
        return FeedMeta("alpaca-iex", "iex", False, feed)
    if feed == "delayed_sip":
        return FeedMeta("alpaca-delayed_sip", "consolidated", True, feed)
    if feed == "overnight":
        # Alpaca's derived overnight feed (BOATS-sourced, 8 PM-4 AM ET). Real-time, not consolidated.
        return FeedMeta("alpaca-overnight", "overnight", False, feed)
    return FeedMeta(f"alpaca-{feed}", feed, False, feed)


@dataclass
class LagHistogram:
    counts: dict[str, int] = field(default_factory=lambda: {**{f"le_{b}ms": 0 for b in LAG_BUCKETS_MS}, "gt_5000ms": 0})
    n: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, lag_ms: float) -> None:
        lag_ms = max(0.0, lag_ms)
        self.n += 1
        self.total_ms += lag_ms
        self.max_ms = max(self.max_ms, lag_ms)
        for b in LAG_BUCKETS_MS:
            if lag_ms <= b:
                self.counts[f"le_{b}ms"] += 1
                return
        self.counts["gt_5000ms"] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean_ms": round(self.total_ms / self.n, 1) if self.n else None,
            "max_ms": round(self.max_ms, 1) if self.n else None,
            "buckets": dict(self.counts),
        }


class QuoteCache:
    def __init__(self, stale_after_s: float = 120.0):
        self.stale_after_s = stale_after_s
        self.rows: dict[str, dict[str, dict[str, Any]]] = {"equity": {}, "option": {}}
        self.lag: dict[str, LagHistogram] = {"equity": LagHistogram(), "option": LagHistogram()}
        self.counters: dict[str, int] = {"equity_quotes": 0, "equity_trades": 0, "option_quotes": 0, "option_trades": 0}

    # ---------------- writes ----------------
    def _row(self, kind: str, symbol: str) -> dict[str, Any]:
        rows = self.rows[kind]
        r = rows.get(symbol)
        if r is None:
            r = {"symbol": symbol, "_updates": 0}
            rows[symbol] = r
        return r

    def _stamp(self, kind: str, r: dict[str, Any], src_epoch: float | None, src_iso: str | None, meta: FeedMeta, recv: float) -> None:
        r["_recv"] = recv
        if src_epoch is not None and (r.get("_src") is None or src_epoch >= r["_src"]):
            r["_src"] = src_epoch
            r["source_observed_at"] = src_iso
        r["received_at"] = epoch_to_pt_iso(recv)
        r["feed"], r["venue_scope"], r["delayed"] = meta.feed, meta.venue_scope, meta.delayed
        r["stream_feed"] = meta.stream_feed  # sip / overnight / iex / opra: which socket wrote the newest field
        r["_updates"] += 1
        if src_epoch is not None:
            self.lag[kind].add((recv - src_epoch) * 1000.0)

    def apply_quote(self, kind: str, msg: dict[str, Any], meta: FeedMeta, recv: float | None = None) -> None:
        sym = msg.get("S")
        if not sym:
            return
        recv = now() if recv is None else recv
        src_epoch, src_iso = coerce_ts(msg.get("t"))
        r = self._row(kind, sym)
        if src_epoch is not None and r.get("_qsrc") is not None and src_epoch < r["_qsrc"]:
            return  # out-of-order older quote; keep newest
        r["bid"], r["ask"] = msg.get("bp"), msg.get("ap")
        r["bid_size"], r["ask_size"] = msg.get("bs"), msg.get("as")
        r["bid_exchange"], r["ask_exchange"] = msg.get("bx"), msg.get("ax")
        r["quote_conditions"] = msg.get("c")
        if "z" in msg:
            r["tape"] = msg.get("z")
        r["quote_observed_at"] = src_iso
        r["quote_feed"] = meta.stream_feed
        r["_qsrc"] = src_epoch
        self._stamp(kind, r, src_epoch, src_iso, meta, recv)
        self.counters[f"{kind}_quotes"] += 1

    def apply_trade(self, kind: str, msg: dict[str, Any], meta: FeedMeta, recv: float | None = None) -> None:
        sym = msg.get("S")
        if not sym:
            return
        recv = now() if recv is None else recv
        src_epoch, src_iso = coerce_ts(msg.get("t"))
        r = self._row(kind, sym)
        if src_epoch is not None and r.get("_tsrc") is not None and src_epoch < r["_tsrc"]:
            return
        r["last"], r["last_size"] = msg.get("p"), msg.get("s")
        r["last_exchange"] = msg.get("x")
        r["trade_conditions"] = msg.get("c")
        r["trade_observed_at"] = src_iso
        r["trade_feed"] = meta.stream_feed
        r["_tsrc"] = src_epoch
        self._stamp(kind, r, src_epoch, src_iso, meta, recv)
        self.counters[f"{kind}_trades"] += 1

    def prune(self, kind: str, keep: set[str], older_than_s: float, t: float | None = None) -> int:
        t = now() if t is None else t
        drop = [s for s, r in self.rows[kind].items() if s not in keep and t - r.get("_recv", 0) > older_than_s]
        for s in drop:
            del self.rows[kind][s]
        return len(drop)

    # ---------------- reads ----------------
    def view(self, kind: str, symbol: str, connected: bool, subscribed: Callable[[str], bool], t: float | None = None) -> dict[str, Any] | None:
        r = self.rows[kind].get(symbol)
        if r is None:
            return None
        t = now() if t is None else t
        id_key = "contract_id" if kind == "option" else "instrument_id"
        out: dict[str, Any] = {id_key: symbol}
        for k, v in r.items():
            if not k.startswith("_") and k != "symbol":
                out[k] = v
        src, recv = r.get("_src"), r.get("_recv")
        out["source_age_s"] = round(t - src, 3) if src is not None else None
        out["received_age_s"] = round(t - recv, 3) if recv is not None else None
        out["session"] = session_for(src)
        out["updates"] = r.get("_updates", 0)
        if not subscribed(symbol):
            status = "unsubscribed"
        elif not connected:
            status = "disconnected"
        elif recv is None or t - recv > self.stale_after_s:
            status = "stale"
        else:
            status = "ok"
        out["feed_status"] = status
        return out

    def symbols(self, kind: str) -> list[str]:
        return sorted(self.rows[kind])

    def last_received(self, kind: str) -> float | None:
        vals = [r["_recv"] for r in self.rows[kind].values() if "_recv" in r]
        return max(vals) if vals else None
