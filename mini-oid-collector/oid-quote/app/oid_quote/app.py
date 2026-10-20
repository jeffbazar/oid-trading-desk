"""OID quote collector entrypoint: wires feeds, cache, snapshot writer, and HTTP API."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from . import __version__
from .api import build_app
from .cache import FeedMeta, QuoteCache, feed_meta_for
from .config import Config, load_config
from .credentials import KEY_ID, SECRET_KEY, RedactFilter, TokenStore, key_presence, load_alpaca_keys
from .feeds import AlpacaStream
from .livevol import LiveVolume
from .subs import FileSubs, normalize_option_list
from .timeutil import epoch_to_pt_iso, next_feed_switch_at, now, now_pt_iso, scheduled_stock_feed

log = logging.getLogger("oid_quote")


class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache = QuoteCache(stale_after_s=cfg.stale_after_s)
        self.tokens = TokenStore(cfg.secrets_dir)
        self.started_at = now()
        self.clock = now  # injectable for tests (feed schedule)
        self.stocks_subs = FileSubs(cfg.resolved_allowlist(), "stock")
        self.options_subs = FileSubs(cfg.resolved_options_subs(), "option", cap=cfg.option_cap)
        self.stocks: AlpacaStream | None = None
        self.options: AlpacaStream | None = None
        self._keys: tuple[str, str] | None = None
        self._had_keys = False
        self._runner: web.AppRunner | None = None
        self._stop = asyncio.Event()
        self._snapshot_writes = 0
        self._last_snapshot_at: float | None = None
        self._last_snapshot_error: str | None = None
        # v0.3.0 option seeding (REST snapshot for subscribed contracts that have no quote yet)
        self._seed_attempted: dict[str, float] = {}
        self._seed_stats: dict[str, Any] = {"runs": 0, "requested": 0, "seeded": 0, "empty": 0, "last_at": None, "last_error": None}
        self._subs_writes = 0
        self._subs_last_write: dict[str, Any] | None = None
        # live volume v1 (2026-10-18)
        self.livevol: LiveVolume | None = LiveVolume(cfg, self) if cfg.live_volume_enabled else None
        self.bars_proxy = None  # set by bars.register_bars

    # ------------------------------------------------------------------ lifecycle
    def reload_keys(self) -> None:
        keys = load_alpaca_keys(self.cfg.secrets_dir)
        if keys:
            # Register values with the log redactor; never log them.
            RedactFilter.add_secret(keys[0])
            RedactFilter.add_secret(keys[1])
            if not self._had_keys:
                log.info("Alpaca keys present; feeds will connect")
            self._had_keys = True
        elif self._had_keys:
            log.warning("Alpaca keys disappeared; feeds will stay idle until keys return")
            self._had_keys = False
        self._keys = keys

    def keys_provider(self) -> tuple[str, str] | None:
        return self._keys

    def status(self) -> str:
        if not self._keys:
            return "no_keys"
        streams = [s for s in (self.stocks, self.options) if s is not None]
        if streams and all(s.connected for s in streams):
            return "ok"
        if any(s.connected for s in streams):
            return "partial"
        if any(s.state == "auth_failed" for s in streams):
            return "auth_failed"
        if any(s.state in ("connecting", "authenticating", "backoff") for s in streams):
            return "connecting"
        return "idle"

    def scheduled_stock_feed(self, t: float | None = None) -> str:
        return scheduled_stock_feed(self.clock() if t is None else t, self.cfg.stock_feed, self.cfg.stock_overnight_feed)

    def fallback_for(self, feed: str) -> str | None:
        # iex fallback only makes sense for the day (SIP) feed; overnight has no substitute.
        return self.cfg.stock_feed_fallback if feed == self.cfg.stock_feed else None

    async def apply_feed_schedule(self, t: float | None = None) -> bool:
        """Move the single stock socket to the feed the session schedule wants (sip <-> overnight)."""
        if self.stocks is None:
            return False
        want = self.scheduled_stock_feed(t)
        if want == self.stocks.primary_feed:
            return False
        log.info("feed schedule: stocks %s -> %s", self.stocks.primary_feed, want)
        return await self.stocks.switch_feed(want, self.fallback_for(want))

    def stream_for(self, kind: str) -> AlpacaStream | None:
        return self.stocks if kind == "equity" else self.options

    async def start(self) -> None:
        self.cfg.root.mkdir(parents=True, exist_ok=True)
        for d in (self.cfg.secrets_dir, self.cfg.logs_dir, self.cfg.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.reload_keys()
        self.tokens.get()  # warm + redact

        self.stocks_subs.reload_if_changed()
        self.options_subs.reload_if_changed()

        first_feed = self.scheduled_stock_feed()
        self.stocks = AlpacaStream(
            name="stocks",
            kind="equity",
            ws_base=self.cfg.stocks_ws_base,
            feed=first_feed,
            fallback_feed=self.fallback_for(first_feed),
            encoding="json",
            channels=list(self.cfg.stock_channels),
            cache=self.cache,
            keys_provider=self.keys_provider,
            backoff_initial_s=self.cfg.backoff_initial_s,
            backoff_max_s=self.cfg.backoff_max_s,
            heartbeat_s=self.cfg.ws_heartbeat_s,
            fallback_retry_primary_s=self.cfg.fallback_retry_primary_s,
            feed_ws_bases={"overnight": self.cfg.overnight_ws_base, "boats": self.cfg.overnight_ws_base},
            extra_channels=list(self.cfg.stock_bar_channels) if self.livevol else None,
            extra_channel_feeds=list(self.cfg.stock_bar_feeds),
        )
        self.stocks.set_desired(self.stocks_subs.symbols)
        if self.livevol:
            self.stocks.trade_hook = self.livevol.on_trade
            self.stocks.bar_hook = self.livevol.on_bar
            self.stocks.cancel_hook = self.livevol.on_cancel

        if self.cfg.enable_options:
            self.options = AlpacaStream(
                name="options",
                kind="option",
                ws_base=self.cfg.options_ws_base,
                feed=self.cfg.options_feed,
                fallback_feed=self.cfg.options_feed_fallback,
                encoding="msgpack",
                channels=list(self.cfg.option_channels),
                cache=self.cache,
                keys_provider=self.keys_provider,
                backoff_initial_s=self.cfg.backoff_initial_s,
                backoff_max_s=self.cfg.backoff_max_s,
                heartbeat_s=self.cfg.ws_heartbeat_s,
                fallback_retry_primary_s=self.cfg.fallback_retry_primary_s,
            )
            self.options.set_desired(self.options_subs.symbols)
            if self.livevol:
                self.options.trade_hook = self.livevol.on_trade

        if self._keys:
            self.start_streams()
        else:
            log.warning("no Alpaca keys in %s (or env); placeholder mode: HTTP up, health status=no_keys", self.cfg.secrets_dir)

        app = build_app(self)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.cfg.host, self.cfg.port, reuse_address=True)
        await site.start()
        log.info(
            "HTTP listening on http://%s:%d  status=%s  stocks=%d  options=%d  version=%s",
            self.cfg.host,
            self.cfg.port,
            self.status(),
            len(self.stocks_subs.symbols),
            len(self.options_subs.symbols),
            __version__,
        )

    def start_streams(self) -> None:
        for s in (self.stocks, self.options):
            if s is not None:
                s.start()

    async def stop(self) -> None:
        self._stop.set()
        for s in (self.stocks, self.options):
            if s is not None:
                await s.stop()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def run(self) -> None:
        try:
            await self.start()
            await asyncio.gather(
                self._snapshot_loop(),
                self._subs_loop(),
                self._keys_loop(),
                self._feed_schedule_loop(),
                self._seed_loop(),
                self._livevol_tick_loop(),
                self._livevol_backfill_loop(),
                self._stop.wait(),
            )
        finally:
            await self.stop()

    # ------------------------------------------------------------------ background loops
    async def _snapshot_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.write_snapshot()
            except Exception as e:
                self._last_snapshot_error = f"{type(e).__name__}: {e}"[:200]
                log.exception("snapshot write failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.snapshot_interval_s)
                return
            except asyncio.TimeoutError:
                pass

    async def _subs_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.stocks_subs.reload_if_changed() and self.stocks:
                    self.stocks.set_desired(self.stocks_subs.symbols)
                if self.options_subs.reload_if_changed() and self.options:
                    self.options.set_desired(self.options_subs.symbols)
                keep_e = set(self.stocks_subs.symbols)
                keep_o = set(self.options_subs.symbols)
                n_e = self.cache.prune("equity", keep_e, self.cfg.prune_unsubscribed_after_s)
                n_o = self.cache.prune("option", keep_o, self.cfg.prune_unsubscribed_after_s)
                if n_e or n_o:
                    log.info("pruned %d equity + %d option rows", n_e, n_o)
            except Exception:
                log.exception("subscription reload failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.subs_poll_interval_s)
                return
            except asyncio.TimeoutError:
                pass

    async def _feed_schedule_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.apply_feed_schedule()
            except Exception:
                log.exception("feed schedule check failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.feed_schedule_interval_s)
                return
            except asyncio.TimeoutError:
                pass

    async def _keys_loop(self) -> None:
        while not self._stop.is_set():
            try:
                prev = bool(self._keys)
                self.reload_keys()
                now_have = bool(self._keys)
                if now_have and not prev:
                    self.start_streams()  # leaving placeholder mode; no restart needed
            except Exception:
                log.exception("keys reload failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.keys_poll_interval_s)
                return
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------------ live volume v1 loops
    async def _livevol_tick_loop(self) -> None:
        if not self.livevol:
            return
        while not self._stop.is_set():
            try:
                self.livevol.tick()
            except Exception:
                log.exception("livevol tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.live_tick_s)
                return
            except asyncio.TimeoutError:
                pass

    def _backfill_due(self, t: float) -> tuple[bool, bool]:
        """(due, finalize). Norms are rebuilt once per ET date (after 04:00 ET); after the close (finalize_after_et)
        the store is refreshed once more so today's REST bars replace the live ws/print bars."""
        import datetime as _dt
        from .timeutil import ET
        lv = self.livevol
        et = _dt.datetime.fromtimestamp(t, ET)
        today, hm = et.strftime("%Y-%m-%d"), et.strftime("%H:%M")
        last_err = getattr(self, "_lv_last_err_at", None)
        if last_err and t - last_err < 600:
            return False, False
        if lv.norm_meta.get("for_date") != today and (hm >= "04:00" or not lv.norms):
            return True, False
        if not lv.last_session and not getattr(self, "_lv_ls_tried", False):  # norms file from v0.4.0 (no last-session block)
            self._lv_ls_tried = True
            return True, False
        # symbols added to the subscription since the last build (no norm yet): one rebuild per new set per date
        missing = frozenset(set(self.stocks_subs.symbols) - set(lv.norms) - set(lv.norm_meta.get("sessions") or {}))
        if missing and getattr(self, "_lv_missing_tried", None) != (today, missing):
            self._lv_missing_tried = (today, missing)
            return True, False
        if et.weekday() < 5 and hm >= self.cfg.finalize_after_et and lv.stats.get("finalized_for") != today:
            traded = any(r.day == today and r.day_vol > 0 for r in lv.eq.values())
            if traded:
                return True, True
        return False, False

    async def _livevol_backfill_loop(self) -> None:
        if not self.livevol:
            return
        try:
            if self.livevol.load_norms_file():
                log.info("livevol: loaded norms for %s (%d symbols)", self.livevol.norm_meta.get("for_date"), len(self.livevol.norms))
        except Exception:
            log.exception("livevol: norms file load failed")
        first = True
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=10.0 if first else self.cfg.backfill_check_s)
                return
            except asyncio.TimeoutError:
                pass
            first = False
            if not self._keys or self.bars_proxy is None:
                continue
            due, fin = self._backfill_due(now())
            if not due:
                continue
            try:
                res = await self.livevol.backfill_once(list(self.stocks_subs.symbols), finalize_today=fin)
                log.info("livevol backfill ok: %d symbols, norms for %s, finalize=%s", res["symbols"], res["for_date"], fin)
            except Exception as e:
                self._lv_last_err_at = now()
                msg = str(e)[:120] if "HTTP" in str(e) else type(e).__name__
                self.livevol.stats["last_backfill_error"] = msg
                log.warning("livevol backfill failed: %s", msg)

    def live_volume_view(self, symbols: list[str] | None, contracts: list[str] | None, detail: bool) -> dict[str, Any]:
        assert self.livevol is not None
        return self.livevol.view(symbols, contracts, detail, self.stocks.health() if self.stocks else None)

    # ------------------------------------------------------------------ v0.3.0 options subs API + seeding
    def set_option_subs(self, data: Any, source: str | None = None) -> dict[str, Any]:
        """Validate + atomically write options-subs.json (same file the 5 s loop reads), then apply now."""
        good, bad, truncated = normalize_option_list(data, self.cfg.option_cap)
        path = self.cfg.resolved_options_subs()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"contracts": good, "updated_at": now_pt_iso(), "source": (source or "api")[:80]}
        tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, indent=1) + "\n")
        os.replace(tmp, path)
        changed = self.options_subs.reload_if_changed()
        if changed and self.options:
            self.options.set_desired(self.options_subs.symbols)
        for s in good:  # new/re-declared contracts get a fresh seed attempt if they still lack a quote
            self._seed_attempted.pop(s, None)
        self._subs_writes += 1
        self._subs_last_write = {"at": payload["updated_at"], "count": len(good), "invalid": len(bad), "truncated": truncated, "source": payload["source"]}
        log.info("options subs set via API by %s: %d contracts (%d invalid, %d truncated, changed=%s)", payload["source"], len(good), len(bad), truncated, changed)
        return {"ok": True, "count": len(good), "contracts": good, "invalid": bad[:20], "truncated": truncated, "changed": changed, "path": str(path)}

    def option_subs_view(self) -> dict[str, Any]:
        return {"contracts": self.options_subs.symbols, **self.options_subs.health(), "api_writes": self._subs_writes, "last_api_write": self._subs_last_write}

    def _needs_seed(self, t: float) -> list[str]:
        out: list[str] = []
        for s in self.options_subs.symbols:
            r = self.cache.rows["option"].get(s)
            if r is not None and (r.get("_qsrc") is not None or r.get("_tsrc") is not None):
                continue
            last = self._seed_attempted.get(s)
            if last is not None and t - last < self.cfg.option_seed_retry_s:
                continue
            out.append(s)
        return out

    def apply_option_snapshots(self, snaps: dict[str, Any], recv: float | None = None) -> int:
        """Apply Alpaca REST option snapshots {SYM: {latestQuote, latestTrade}} through the normal cache path."""
        base = feed_meta_for("option", self.cfg.options_feed)
        meta = FeedMeta(base.feed, base.venue_scope, base.delayed, f"{self.cfg.options_feed}-snapshot")
        n = 0
        for sym, snap in (snaps or {}).items():
            if not isinstance(snap, dict):
                continue
            q, tr = snap.get("latestQuote"), snap.get("latestTrade")
            if isinstance(q, dict) and q.get("t"):
                self.cache.apply_quote("option", {**q, "S": sym}, meta, recv)
            if isinstance(tr, dict) and tr.get("t"):
                self.cache.apply_trade("option", {**tr, "S": sym}, meta, recv)
            if (isinstance(q, dict) and q.get("t")) or (isinstance(tr, dict) and tr.get("t")):
                n += 1
        return n

    async def seed_options_once(self, session: aiohttp.ClientSession | None = None) -> int:
        if not (self.cfg.option_seed_enabled and self.cfg.enable_options and self._keys):
            return 0
        t = now()
        todo = self._needs_seed(t)
        if not todo:
            return 0
        key_id, secret = self._keys
        headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}
        own = session is None
        sess = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        seeded = 0
        try:
            for i in range(0, len(todo), 100):
                batch = todo[i : i + 100]
                for s in batch:
                    self._seed_attempted[s] = t
                params = {"symbols": ",".join(batch), "feed": self.cfg.options_feed, "limit": "100"}
                async with sess.get(self.cfg.options_snapshot_url, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        self._seed_stats["last_error"] = f"HTTP {resp.status}"
                        log.warning("option seed snapshot HTTP %s for %d contracts", resp.status, len(batch))
                        continue
                    body = await resp.json(content_type=None)
                got = self.apply_option_snapshots((body or {}).get("snapshots") or {})
                seeded += got
                self._seed_stats["requested"] += len(batch)
                self._seed_stats["empty"] += len(batch) - got
            self._seed_stats["runs"] += 1
            self._seed_stats["seeded"] += seeded
            self._seed_stats["last_at"] = now_pt_iso()
            if seeded:
                self._seed_stats["last_error"] = None
            log.info("option seed: %d/%d contracts seeded from REST snapshot", seeded, len(todo))
        finally:
            if own:
                await sess.close()
        return seeded

    async def _seed_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.seed_options_once()
            except Exception as e:
                self._seed_stats["last_error"] = type(e).__name__
                log.warning("option seed failed: %s", type(e).__name__)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.option_seed_interval_s)
                return
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------------ snapshot + health
    def write_snapshot(self) -> None:
        t = now()
        payload = {
            "as_of": now_pt_iso(),
            "collector": self.health(t),
            "equities": {
                s: self.cache.view("equity", s, bool(self.stocks and self.stocks.connected), self.stocks.is_subscribed if self.stocks else (lambda _: False), t)
                for s in self.cache.symbols("equity")
            },
            "options": {
                s: self.cache.view("option", s, bool(self.options and self.options.connected), self.options.is_subscribed if self.options else (lambda _: False), t)
                for s in self.cache.symbols("option")
            },
        }
        path = self.cfg.cache_file
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, separators=(",", ":"), default=str))
        os.replace(tmp, path)
        self._snapshot_writes += 1
        self._last_snapshot_at = t
        self._last_snapshot_error = None

    def health(self, t: float | None = None) -> dict[str, Any]:
        t = now() if t is None else t
        presence = key_presence(self.cfg.secrets_dir)
        return {
            "service": "oid-quote-collector",
            "version": __version__,
            "status": self.status(),
            "as_of": now_pt_iso(),
            "started_at": epoch_to_pt_iso(self.started_at),
            "uptime_s": round(t - self.started_at, 1),
            "root": str(self.cfg.root),
            "host": self.cfg.host,
            "port": self.cfg.port,
            "keys_present": {k: presence[k] for k in (KEY_ID, SECRET_KEY)},
            "token_configured": presence["OID_QUOTE_TOKEN"],
            "stocks": self.stocks.health(t) if self.stocks else None,
            "stock_schedule": {
                "day_feed": self.cfg.stock_feed,
                "overnight_feed": self.cfg.stock_overnight_feed,
                "scheduled_feed": self.scheduled_stock_feed(),
                "window_et": "overnight 20:00-04:00 ET Sun night->Fri morning; day feed otherwise",
                "next_switch_at": epoch_to_pt_iso(next_feed_switch_at(self.clock(), self.cfg.stock_feed, self.cfg.stock_overnight_feed)),
                "single_connection": True,
            },
            "options": self.options.health(t) if self.options else None,
            "subscriptions": {
                "stocks": self.stocks_subs.health(),
                "options": {**self.options_subs.health(), "api_writes": self._subs_writes, "last_api_write": self._subs_last_write},
            },
            "option_seed": {"enabled": self.cfg.option_seed_enabled, **self._seed_stats},
            "live_volume": self.livevol.health() if self.livevol else {"enabled": False},
            "cache": {
                "equity_symbols": len(self.cache.symbols("equity")),
                "option_symbols": len(self.cache.symbols("option")),
                "counters": dict(self.cache.counters),
                "lag": {"equity": self.cache.lag["equity"].to_dict(), "option": self.cache.lag["option"].to_dict()},
                "last_equity_received_at": epoch_to_pt_iso(self.cache.last_received("equity")),
                "last_option_received_at": epoch_to_pt_iso(self.cache.last_received("option")),
            },
            "snapshot": {
                "path": str(self.cfg.cache_file),
                "writes": self._snapshot_writes,
                "last_at": epoch_to_pt_iso(self._last_snapshot_at),
                "last_error": self._last_snapshot_error,
            },
        }


def setup_logging(cfg: Config) -> None:
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(cfg.log_file, maxBytes=cfg.log_max_bytes, backupCount=cfg.log_backups, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(RedactFilter())
    root.addHandler(fh)
    if cfg.log_to_stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh.addFilter(RedactFilter())
        root.addHandler(sh)
    # Quiet noisy libraries
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.client").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="oid-quote", description="OID Alpaca quote collector (data-only)")
    p.add_argument("--root", default=None, help="Install root (default ~/oid-quote or $OID_QUOTE_ROOT)")
    p.add_argument("--config", default=None, help="Path to config.json (default <root>/config.json)")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--stock-feed", default=None, dest="stock_feed", help="sip (default) | iex | delayed_sip | boats | overnight | test")
    p.add_argument("--options-feed", default=None, dest="options_feed", help="opra (default) | indicative")
    p.add_argument("--no-options", action="store_true", help="Disable the options websocket")
    p.add_argument("--no-overnight", action="store_true", help="Keep the stock socket on --stock-feed 24h (no overnight switch)")
    p.add_argument("--quiet", action="store_true", help="Log only to <root>/logs/collector.log (used by launchd)")
    p.add_argument("--check", action="store_true", help="Print resolved config + secret presence (never values) and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    overrides: dict[str, Any] = {}
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.stock_feed is not None:
        overrides["stock_feed"] = args.stock_feed
    if args.options_feed is not None:
        overrides["options_feed"] = args.options_feed
    if args.no_options:
        overrides["enable_options"] = False
    if args.no_overnight:
        overrides["stock_overnight_feed"] = "off"
    if args.quiet:
        overrides["log_to_stderr"] = False

    try:
        cfg = load_config(root=args.root, config_path=args.config, overrides=overrides)
    except Exception as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    if args.check:
        info = {"config": cfg.public_dict(), "secrets_present": key_presence(cfg.secrets_dir), "version": __version__}
        print(json.dumps(info, indent=2))
        return 0

    setup_logging(cfg)
    log.info("starting oid-quote-collector %s root=%s feed=%s(+%s overnight)/%s", __version__, cfg.root, cfg.stock_feed, cfg.stock_overnight_feed, cfg.options_feed)

    collector = Collector(cfg)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _signal(sig: signal.Signals) -> None:
        log.info("received %s; shutting down", sig.name)
        collector._stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _signal, s)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(s, lambda *_: collector._stop.set())

    try:
        loop.run_until_complete(collector.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()
    log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
