"""Fake Alpaca market-data websocket server for offline tests (no network, no real keys).

Speaks the documented protocol: connected -> auth -> authenticated -> subscribe -> subscription,
then streams quotes/trades. Stocks (/v2/{feed}) use JSON; options (/v1beta1/{feed}) require
Content-Type: application/msgpack and emit msgpack with Timestamp ext types, like OPRA.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import msgpack
from aiohttp import WSMsgType, web

GOOD_KEY, GOOD_SECRET = "FAKEKEYID123", "FAKESECRETVALUE456"


class FakeAlpaca:
    STOCK_V1BETA1_FEEDS = ("overnight", "boats")  # stock feeds that live under /v1beta1 (JSON, like /v2)

    def __init__(self, entitled_stock_feeds=("sip", "iex", "overnight"), entitled_option_feeds=("opra",), tick_s: float = 0.05):
        self.entitled_stock_feeds = set(entitled_stock_feeds)
        self.entitled_option_feeds = set(entitled_option_feeds)
        self.tick_s = tick_s
        self.sockets: list[web.WebSocketResponse] = []
        self.auth_messages: list[dict[str, Any]] = []
        self.sub_messages: list[dict[str, Any]] = []
        self.connections: dict[str, int] = {}
        self.active: dict[str, int] = {"stock": 0, "option": 0}
        self.max_active: dict[str, int] = {"stock": 0, "option": 0}
        self.runner: web.AppRunner | None = None
        self.port: int | None = None

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/v2/{feed}", self.stocks)
        app.router.add_get("/v1beta1/{feed}", self.options)
        return app

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        self.runner = web.AppRunner(self.app())
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        return self.port

    async def stop(self) -> None:
        await self.drop_all()
        if self.runner:
            await self.runner.cleanup()

    async def drop_all(self) -> None:
        for ws in list(self.sockets):
            await ws.close()

    # ------------------------------------------------------------------
    async def stocks(self, request: web.Request) -> web.WebSocketResponse:
        return await self._serve(request, "stock", request.match_info["feed"])

    async def options(self, request: web.Request) -> web.WebSocketResponse:
        feed = request.match_info["feed"]
        if feed in self.STOCK_V1BETA1_FEEDS:
            return await self._serve(request, "stock", feed)
        return await self._serve(request, "option", feed)

    async def _serve(self, request: web.Request, kind: str, feed: str) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=None, compress=True)
        await ws.prepare(request)
        self.sockets.append(ws)
        key = f"{kind}/{feed}"
        self.connections[key] = self.connections.get(key, 0) + 1
        self.active[kind] += 1
        self.max_active[kind] = max(self.max_active[kind], self.active[kind])
        use_msgpack = kind == "option"

        async def send(obj: Any) -> None:
            if use_msgpack:
                await ws.send_bytes(msgpack.packb(obj, use_bin_type=True, datetime=False))
            else:
                await ws.send_str(json.dumps(obj))

        if kind == "option" and request.headers.get("Content-Type") != "application/msgpack":
            await ws.send_str(json.dumps([{"T": "error", "code": 412, "msg": "option messages are only available in MsgPack format"}]))
            await ws.close()
            return ws

        await send([{"T": "success", "msg": "connected"}])
        subs: dict[str, set[str]] = {"quotes": set(), "trades": set()}
        authed = False
        streamer: asyncio.Task[None] | None = None
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    req = msgpack.unpackb(msg.data, raw=False)
                elif msg.type == WSMsgType.TEXT:
                    req = json.loads(msg.data)
                else:
                    continue
                action = req.get("action")
                if action == "auth":
                    self.auth_messages.append(req)
                    if req.get("key") != GOOD_KEY or req.get("secret") != GOOD_SECRET:
                        await send([{"T": "error", "code": 402, "msg": "auth failed"}])
                        await ws.close()
                        break
                    entitled = self.entitled_option_feeds if kind == "option" else self.entitled_stock_feeds
                    if feed not in entitled:
                        await send([{"T": "error", "code": 409, "msg": "insufficient subscription"}])
                        await ws.close()
                        break
                    authed = True
                    await send([{"T": "success", "msg": "authenticated"}])
                    streamer = asyncio.create_task(self._stream(send, subs, kind))
                elif action in ("subscribe", "unsubscribe"):
                    if not authed:
                        await send([{"T": "error", "code": 401, "msg": "not authenticated"}])
                        continue
                    self.sub_messages.append({"kind": kind, **req})
                    for ch in ("quotes", "trades"):
                        vals = req.get(ch) or []
                        if kind == "option" and ch == "quotes" and "*" in vals:
                            await send([{"T": "error", "code": 413, "msg": "star subscription is not allowed for option quotes"}])
                            continue
                        if action == "subscribe":
                            subs[ch].update(vals)
                        else:
                            subs[ch].difference_update(vals)
                    await send([{"T": "subscription", "trades": sorted(subs["trades"]), "quotes": sorted(subs["quotes"])}])
        finally:
            self.active[kind] -= 1
            if streamer:
                streamer.cancel()
            if ws in self.sockets:
                self.sockets.remove(ws)
        return ws

    async def _stream(self, send, subs: dict[str, set[str]], kind: str) -> None:
        while True:
            await asyncio.sleep(self.tick_s)
            batch: list[dict[str, Any]] = []
            ns = time.time_ns() - 3_000_000  # pretend 3 ms exchange->collector lag
            ts: Any
            if kind == "option":
                ts = msgpack.Timestamp.from_unix_nano(ns)
            else:
                secs, frac = divmod(ns, 1_000_000_000)
                ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(secs)) + f".{frac:09d}Z"
            for s in sorted(subs["quotes"]):
                bid = round(random.uniform(1, 200), 2)
                q = {"T": "q", "S": s, "bx": "C", "bp": bid, "bs": 10, "ax": "C", "ap": round(bid + 0.05, 2), "as": 12, "c": "A" if kind == "option" else ["R"], "t": ts}
                if kind == "stock":
                    q["z"] = "C"
                batch.append(q)
            for s in sorted(subs["trades"]):
                batch.append({"T": "t", "S": s, "p": round(random.uniform(1, 200), 2), "s": 1, "x": "N", "c": "S" if kind == "option" else ["@"], "t": ts, **({"i": 1, "z": "C"} if kind == "stock" else {})})
            if batch:
                await send(batch)


async def _main(port: int) -> None:
    fake = FakeAlpaca(tick_s=1.0)
    p = await fake.start(port=port)
    print(f"fake alpaca on ws://127.0.0.1:{p}  (key={GOOD_KEY})", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    import sys

    asyncio.run(_main(int(sys.argv[1]) if len(sys.argv) > 1 else 8790))
