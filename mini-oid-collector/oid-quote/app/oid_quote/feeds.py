"""Alpaca market-data websocket clients (stocks v2 JSON, options v1beta1 msgpack).

Data-only: connects to stream.data.alpaca.markets market-data streams. No trading endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
from typing import Any, Callable

import aiohttp
import msgpack

from .cache import QuoteCache, feed_meta_for
from .timeutil import epoch_to_pt_iso, now

SUB_CHUNK = 200
AUTH_TIMEOUT_S = 10.0


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover
        return ssl.create_default_context()


class StreamError(Exception):
    def __init__(self, code: int | None, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code, self.msg = code, msg


class AlpacaStream:
    """One websocket to one Alpaca market-data endpoint, with reconnect/backoff and live resubscribe."""

    def __init__(
        self,
        name: str,
        kind: str,  # "equity" | "option"
        ws_base: str,
        feed: str,
        fallback_feed: str | None,
        encoding: str,  # "json" | "msgpack"
        channels: list[str],
        cache: QuoteCache,
        keys_provider: Callable[[], tuple[str, str] | None],
        backoff_initial_s: float = 1.0,
        backoff_max_s: float = 60.0,
        heartbeat_s: float = 20.0,
        fallback_retry_primary_s: float = 1800.0,
        feed_ws_bases: dict[str, str] | None = None,
        extra_channels: list[str] | None = None,
        extra_channel_feeds: list[str] | None = None,
    ):
        self.name, self.kind = name, kind
        self.ws_base = ws_base.rstrip("/")
        # Some feeds live under a different version path (e.g. stocks 'overnight' is v1beta1, 'sip' is v2).
        self.feed_ws_bases = {k: v.rstrip("/") for k, v in (feed_ws_bases or {}).items()}
        self.primary_feed, self.fallback_feed = feed, fallback_feed
        self.current_feed = feed
        self.encoding = encoding
        self.channels = channels
        # live volume v1: extra channels (e.g. bars/updatedBars) only on these feeds (never overnight)
        self.extra_channels = list(extra_channels or [])
        self.extra_channel_feeds = set(extra_channel_feeds or [])
        self.trade_hook: Callable[[str, dict, float], None] | None = None
        self.bar_hook: Callable[..., None] | None = None
        self.cancel_hook: Callable[[str, dict, float], None] | None = None
        self.hook_errors = 0
        self.bars_received = 0
        self.subscribed_bars = 0
        self.cache = cache
        self.keys_provider = keys_provider
        self.backoff_initial_s, self.backoff_max_s = backoff_initial_s, backoff_max_s
        self.heartbeat_s = heartbeat_s
        self.fallback_retry_primary_s = fallback_retry_primary_s
        self.log = logging.getLogger(f"oid_quote.feed.{name}")

        self.desired: list[str] = []
        self.requested: set[str] = set()
        self.subscribed: set[str] = set()  # server-confirmed (quotes channel)
        # WIDE tier (2026-10-20): extra symbols on the SAME socket with trades (+ bars) only, no quotes.
        # Only subscribed on `wide_feeds` (never the overnight socket). Their trades skip the quote cache
        # (cache_skip) and go to the trade/bar hooks only (the collector routes them to the wide LiveVolume).
        self.wide_channels: list[str] = []
        self.wide_extra_channels: list[str] = []
        self.wide_feeds: set[str] = set()
        self.desired_wide: list[str] = []
        self.requested_wide: set[str] = set()
        self.subscribed_wide = 0
        self.cache_skip: set[str] = set()
        self._subs_changed = asyncio.Event()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

        self.state = "idle"  # idle/connecting/authenticating/connected/backoff/auth_failed/stopped
        self.connected = False
        self.authenticated = False
        self.fallback_active = False
        self.fallback_since: float | None = None
        self.connect_count = 0
        self.reconnects = 0
        self.last_connect_at: float | None = None
        self.last_disconnect_at: float | None = None
        self.last_message_at: float | None = None
        self.last_data_at: float | None = None
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.messages = 0
        self.next_retry_at: float | None = None
        # Scheduled feed switching (one socket at a time: close old, then open new).
        self._switch_pending = False
        self._session_feed: str | None = None  # feed of the socket currently open/opening
        self._wake = asyncio.Event()
        self.feed_switches = 0
        self.last_switch_at: float | None = None
        self.last_switch: str | None = None

    # ------------------------------------------------------------------ control
    def base_for(self, feed: str) -> str:
        return self.feed_ws_bases.get(feed, self.ws_base)

    def url(self) -> str:
        return f"{self.base_for(self.current_feed)}/{self.current_feed}"

    async def switch_feed(self, feed: str, fallback_feed: str | None) -> bool:
        """Move this single connection to another feed (e.g. sip <-> overnight).

        Closes the current socket first, so at most one connection to Alpaca is ever open for this
        stream; _run then reconnects (no backoff) on the new feed and re-subscribes the same symbols.
        Returns True when a switch was started.
        """
        if feed == self.primary_feed and not self.fallback_active:
            return False
        prev = self.current_feed
        self.primary_feed, self.current_feed, self.fallback_feed = feed, feed, fallback_feed
        self.fallback_active, self.fallback_since = False, None
        self._switch_pending = True
        self.feed_switches += 1
        self.last_switch_at = now()
        self.last_switch = f"{prev}->{feed}"
        self.log.info("%s scheduled feed switch %s -> %s", self.name, prev, feed)
        self._wake.set()  # cut short any backoff sleep
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        return True

    def set_desired(self, symbols: list[str]) -> None:
        self.desired = list(symbols)
        self._subs_changed.set()

    def set_desired_wide(self, symbols: list[str]) -> None:
        self.desired_wide = [s for s in symbols if s not in set(self.desired)]
        self._subs_changed.set()

    def wide_active_channels(self) -> list[str]:
        if not self.wide_channels or self.current_feed not in self.wide_feeds:
            return []
        out = list(self.wide_channels)
        if self.extra_channels and self.current_feed in self.extra_channel_feeds:
            out += [c for c in self.wide_extra_channels if c not in out]
        return out

    def is_subscribed(self, symbol: str) -> bool:
        return symbol in self.subscribed or (symbol in self.desired and not self.connected)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name=f"stream-{self.name}")

    async def stop(self) -> None:
        self._stopping = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self.state, self.connected, self.authenticated = "stopped", False, False

    async def force_reconnect(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()

    def active_channels(self) -> list[str]:
        if self.extra_channels and self.current_feed in self.extra_channel_feeds:
            return self.channels + [c for c in self.extra_channels if c not in self.channels]
        return list(self.channels)

    # ------------------------------------------------------------------ codec
    def _encode_send(self, obj: dict[str, Any]) -> Any:
        assert self._ws is not None
        if self.encoding == "msgpack":
            return self._ws.send_bytes(msgpack.packb(obj, use_bin_type=True))
        return self._ws.send_str(json.dumps(obj))

    def _decode(self, msg: aiohttp.WSMessage) -> list[dict[str, Any]]:
        if msg.type == aiohttp.WSMsgType.BINARY:
            data = msgpack.unpackb(msg.data, raw=False)
        elif msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
        else:
            return []
        if isinstance(data, dict):
            data = [data]
        return [d for d in data if isinstance(d, dict)]

    # ------------------------------------------------------------------ main loop
    async def _run(self) -> None:
        backoff = self.backoff_initial_s
        timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self._stopping:
                delay = backoff
                try:
                    await self._session(session)
                except asyncio.CancelledError:
                    raise
                except StreamError as e:
                    self._record_error(f"alpaca error {e.code}: {e.msg}")
                    if e.code == 409 and self.fallback_feed and self.current_feed != self.fallback_feed:
                        self.log.warning("%s feed '%s' not entitled (409); falling back to '%s'", self.name, self.current_feed, self.fallback_feed)
                        self.current_feed = self.fallback_feed
                        self.fallback_active, self.fallback_since = True, now()
                        delay = 0.5
                    elif e.code == 402:
                        self.state = "auth_failed"
                        delay = max(backoff, 30.0)
                    elif e.code == 406:  # connection limit: another client holds the stream
                        delay = max(backoff, 30.0)
                    elif e.code == 409:
                        delay = max(backoff, 60.0)
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, msgpack.ExtraData) as e:
                    self._record_error(f"{type(e).__name__}: {e}"[:300])
                except Exception as e:  # never let the loop die
                    self.log.exception("%s unexpected error", self.name)
                    self._record_error(f"{type(e).__name__}: {e}"[:300])
                finally:
                    was_connected = self.connected
                    self.connected = self.authenticated = False
                    self.subscribed.clear()
                    self.requested.clear()
                    self.requested_wide.clear()
                    self.subscribed_wide = 0
                    self._ws = None
                    if was_connected:
                        self.last_disconnect_at = now()
                        self.log.warning("%s disconnected (feed=%s)", self.name, self.current_feed)
                        if self.last_connect_at and self.last_disconnect_at - self.last_connect_at >= 30:
                            # a healthy, long-lived session dropped: reconnect fast, reset backoff
                            backoff = self.backoff_initial_s
                            delay = min(delay, self.backoff_initial_s)
                if self._stopping:
                    break
                if self._switch_pending:
                    # deliberate feed change: old socket is closed, open the new one right away
                    self._switch_pending = False
                    backoff = self.backoff_initial_s
                    delay = 0.25
                    if self.state == "auth_failed":
                        self.state = "backoff"
                if self.state != "auth_failed":
                    self.state = "backoff"
                jitter = random.uniform(0, min(1.0, delay * 0.2))
                self.next_retry_at = now() + delay + jitter
                self.log.info("%s reconnecting in %.1fs (feed=%s)", self.name, delay + jitter, self.current_feed)
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay + jitter)
                except asyncio.TimeoutError:
                    pass
                if self._switch_pending:
                    self._switch_pending = False
                    backoff = self.backoff_initial_s
                else:
                    backoff = min(self.backoff_max_s, max(self.backoff_initial_s, backoff * 2))
                self.reconnects += 1

    def _record_error(self, text: str) -> None:
        self.last_error, self.last_error_at = text, now()
        self.log.warning("%s: %s", self.name, text)

    async def _session(self, session: aiohttp.ClientSession) -> None:
        keys = self.keys_provider()
        if not keys:
            raise StreamError(None, "no keys")
        # If running on fallback long enough, retry the primary feed on this (re)connect.
        if self.fallback_active and self.fallback_since and now() - self.fallback_since > self.fallback_retry_primary_s:
            self.log.info("%s retrying primary feed '%s'", self.name, self.primary_feed)
            self.current_feed, self.fallback_active, self.fallback_since = self.primary_feed, False, None

        headers = {"Content-Type": "application/msgpack" if self.encoding == "msgpack" else "application/json"}
        url = self.url()
        self._session_feed = self.current_feed
        self.state = "connecting"
        self.next_retry_at = None
        ssl_ctx: ssl.SSLContext | bool = _ssl_context() if url.startswith("wss://") else True
        self.log.info("%s connecting to %s", self.name, url)
        async with session.ws_connect(url, headers=headers, heartbeat=self.heartbeat_s, ssl=ssl_ctx, max_msg_size=0, compress=15) as ws:
            self._ws = ws
            self.state = "authenticating"
            await self._handshake(ws, keys)
            self.connected = self.authenticated = True
            self.state = "connected"
            self.connect_count += 1
            self.last_connect_at = now()
            self.last_error = None
            self.log.info("%s authenticated on feed=%s (connect #%d)", self.name, self.current_feed, self.connect_count)
            self._subs_changed.set()
            sync_task = asyncio.create_task(self._sync_loop(), name=f"sync-{self.name}")
            try:
                await self._recv_loop(ws)
            finally:
                sync_task.cancel()
                try:
                    await sync_task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _handshake(self, ws: aiohttp.ClientWebSocketResponse, keys: tuple[str, str]) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + AUTH_TIMEOUT_S
        sent_auth = False
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("auth handshake timed out")
            msg = await ws.receive(timeout=remaining)
            if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                raise aiohttp.ClientError(f"socket closed during handshake ({msg.type.name})")
            self.last_message_at = now()
            for m in self._decode(msg):
                t = m.get("T")
                if t == "error":
                    raise StreamError(m.get("code"), str(m.get("msg")))
                if t == "success" and m.get("msg") == "connected" and not sent_auth:
                    # Key + secret go only into this frame; never logged.
                    await self._encode_send({"action": "auth", "key": keys[0], "secret": keys[1]})
                    sent_auth = True
                elif t == "success" and m.get("msg") == "authenticated":
                    return

    async def _recv_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        meta = feed_meta_for(self.kind, self.current_feed)
        while True:
            if self._session_feed != self.current_feed:  # scheduled switch landed while this socket was opening
                await ws.close()
                return
            try:
                msg = await ws.receive(timeout=5.0)
            except asyncio.TimeoutError:
                if self.fallback_active and self.fallback_since and now() - self.fallback_since > self.fallback_retry_primary_s:
                    await ws.close()
                    return
                continue
            if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                return
            if msg.type == aiohttp.WSMsgType.ERROR:
                raise aiohttp.ClientError(f"websocket error: {ws.exception()}")
            t_recv = now()
            self.last_message_at = t_recv
            for m in self._decode(msg):
                self.messages += 1
                typ = m.get("T")
                if typ == "q":
                    self.cache.apply_quote(self.kind, m, meta, t_recv)
                    self.last_data_at = t_recv
                elif typ == "t":
                    if not (self.cache_skip and m.get("S") in self.cache_skip):
                        self.cache.apply_trade(self.kind, m, meta, t_recv)
                    self.last_data_at = t_recv
                    if self.trade_hook is not None:
                        try:
                            self.trade_hook(self.kind, m, t_recv)
                        except Exception:  # live-volume roll-up must never break the quote feed
                            self.hook_errors += 1
                            if self.hook_errors <= 5:
                                self.log.exception("%s trade hook failed", self.name)
                elif typ in ("b", "u"):
                    self.bars_received += 1
                    if self.bar_hook is not None:
                        try:
                            self.bar_hook(self.kind, m, t_recv, typ == "u")
                        except Exception:
                            self.hook_errors += 1
                            if self.hook_errors <= 5:
                                self.log.exception("%s bar hook failed", self.name)
                elif typ in ("x", "c"):  # trade cancel / correction (auto with trades); live volume only
                    if self.cancel_hook is not None:
                        try:
                            self.cancel_hook(self.kind, m, t_recv)
                        except Exception:
                            self.hook_errors += 1
                            if self.hook_errors <= 5:
                                self.log.exception("%s cancel hook failed", self.name)
                elif typ == "subscription":
                    tr = set(m.get("trades") or [])
                    wide = set(self.desired_wide)
                    self.subscribed = set(m.get("quotes") or []) | (tr - wide)
                    self.subscribed_wide = len(tr & wide)
                    self.subscribed_bars = len(m.get("bars") or [])
                    self.log.info("%s subscription now: quotes=%d trades=%d bars=%d (wide trades=%d)", self.name, len(m.get("quotes") or []), len(tr), self.subscribed_bars, self.subscribed_wide)
                elif typ == "error":
                    code, text = m.get("code"), str(m.get("msg"))
                    self._record_error(f"alpaca error {code}: {text}")
                    if code in (402, 406, 409):
                        raise StreamError(code, text)
                # other types (status, lulds) ignored

    async def _sync_loop(self) -> None:
        while True:
            await self._subs_changed.wait()
            self._subs_changed.clear()
            await self._sync_subs()

    async def _sync_subs(self) -> None:
        if self._ws is None or self._ws.closed or not self.authenticated:
            return
        desired = set(self.desired)
        add = [s for s in self.desired if s not in self.requested]
        remove = sorted(self.requested - desired)
        for i in range(0, len(remove), SUB_CHUNK):
            chunk = remove[i : i + SUB_CHUNK]
            await self._encode_send({"action": "unsubscribe", **{c: chunk for c in self.active_channels()}})
            self.requested.difference_update(chunk)
        for i in range(0, len(add), SUB_CHUNK):
            chunk = add[i : i + SUB_CHUNK]
            await self._encode_send({"action": "subscribe", **{c: chunk for c in self.active_channels()}})
            self.requested.update(chunk)
        if add or remove:
            self.log.info("%s subscribe +%d -%d (requested=%d)", self.name, len(add), len(remove), len(self.requested))
        # WIDE tier: trades (+bars) only, on day feeds only
        wch = self.wide_active_channels()
        want_w = [s for s in self.desired_wide if s not in desired] if wch else []
        want_set = set(want_w)
        add_w = [s for s in want_w if s not in self.requested_wide]
        rem_w = sorted(self.requested_wide - want_set)
        if rem_w:
            # channels used when they were added may differ only by bars on a feed switch; a switch reconnects anyway
            chans = wch or list(self.wide_channels)
            for i in range(0, len(rem_w), SUB_CHUNK):
                chunk = rem_w[i : i + SUB_CHUNK]
                await self._encode_send({"action": "unsubscribe", **{c: chunk for c in chans}})
                self.requested_wide.difference_update(chunk)
        for i in range(0, len(add_w), SUB_CHUNK):
            chunk = add_w[i : i + SUB_CHUNK]
            await self._encode_send({"action": "subscribe", **{c: chunk for c in wch}})
            self.requested_wide.update(chunk)
        if add_w or rem_w:
            self.log.info("%s wide subscribe +%d -%d (requested_wide=%d, channels=%s)", self.name, len(add_w), len(rem_w), len(self.requested_wide), ",".join(wch))

    # ------------------------------------------------------------------ health
    def health(self, t: float | None = None) -> dict[str, Any]:
        t = now() if t is None else t
        return {
            "feed": self.current_feed,
            "primary_feed": self.primary_feed,
            "fallback_feed": self.fallback_feed,
            "fallback_active": self.fallback_active,
            "state": self.state,
            "connected": self.connected and self.authenticated,
            "url": self.url(),
            "last_message_at": epoch_to_pt_iso(self.last_message_at),
            "last_message_age_s": round(t - self.last_message_at, 3) if self.last_message_at else None,
            "last_data_at": epoch_to_pt_iso(self.last_data_at),
            "last_data_age_s": round(t - self.last_data_at, 3) if self.last_data_at else None,
            "last_connect_at": epoch_to_pt_iso(self.last_connect_at),
            "last_disconnect_at": epoch_to_pt_iso(self.last_disconnect_at),
            "connects": self.connect_count,
            "reconnects": self.reconnects,
            "next_retry_at": epoch_to_pt_iso(self.next_retry_at),
            "desired_count": len(self.desired),
            "subscribed_count": len(self.subscribed),
            "channels": self.active_channels(),
            "subscribed_bars": self.subscribed_bars,
            "wide": {"desired": len(self.desired_wide), "requested": len(self.requested_wide), "subscribed_trades": self.subscribed_wide,
                     "channels": self.wide_active_channels(), "feeds": sorted(self.wide_feeds)},
            "bars_received": self.bars_received,
            "hook_errors": self.hook_errors,
            "messages": self.messages,
            "last_error": self.last_error,
            "last_error_at": epoch_to_pt_iso(self.last_error_at),
            "feed_switches": self.feed_switches,
            "last_switch": self.last_switch,
            "last_switch_at": epoch_to_pt_iso(self.last_switch_at),
        }
