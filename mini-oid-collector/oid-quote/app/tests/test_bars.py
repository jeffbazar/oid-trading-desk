"""GET /v1/bars proxy tests with a fake Alpaca REST server (no keys / network)."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests

import asyncio
import os
import unittest

import aiohttp
from aiohttp import web

from oid_quote import bars as bars_mod
from oid_quote.app import Collector

from .helpers import clear_env, fast_config, free_port, make_root

TOKEN = "test-token-abcdef123456"


class BarsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_env()
        self.calls = []
        fake = web.Application()

        async def handler(request):
            self.calls.append(dict(request.query))
            assert request.headers.get("APCA-API-KEY-ID") == "kid-123456"
            if not request.query.get("page_token"):
                return web.json_response({"bars": {"NVDA": [{"t": "2026-10-09T13:30:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100, "n": 5, "vw": 1.2}]},
                                          "next_page_token": "p2"})
            return web.json_response({"bars": {"NVDA": [{"t": "2026-10-09T13:35:00Z", "o": 1.5, "h": 2, "l": 1, "c": 1.8, "v": 50, "n": 3, "vw": 1.6}]},
                                      "next_page_token": None})

        fake.router.add_get("/v2/stocks/bars", handler)
        self.fake_runner = web.AppRunner(fake)
        await self.fake_runner.setup()
        fport = free_port()
        await web.TCPSite(self.fake_runner, "127.0.0.1", fport).start()
        self.root = make_root(token=TOKEN)
        (self.root / "secrets" / "APCA_API_KEY_ID").write_text("kid-123456\n")
        (self.root / "secrets" / "APCA_API_SECRET_KEY").write_text("sec-123456\n")
        self.port = free_port()
        self.col = Collector(fast_config(self.root, self.port, enable_options=False))
        self.col.start_streams = lambda: None  # no websockets in this test
        await self.col.start()
        self.col.reload_keys()
        self.col.bars_proxy.url = f"http://127.0.0.1:{fport}/v2/stocks/bars"
        self.http = aiohttp.ClientSession()
        self.base = f"http://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.http.close()
        self.col._stop.set()
        await self.col.stop()
        await self.fake_runner.cleanup()

    async def get(self, path, token=TOKEN):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        async with self.http.get(self.base + path, headers=h) as r:
            return r.status, await r.json()

    async def test_auth_required(self):
        st, _ = await self.get("/v1/bars?symbols=NVDA", token=None)
        self.assertEqual(st, 401)

    async def test_paginates_and_caches(self):
        q = "/v1/bars?symbols=NVDA&timeframe=5Min&start=2026-10-09T13:30:00Z&end=2026-10-09T20:00:00Z"
        st, body = await self.get(q)
        self.assertEqual(st, 200)
        self.assertEqual(body["source"], "alpaca-sip-rest")
        self.assertEqual([b["v"] for b in body["bars"]["NVDA"]], [100, 50])
        self.assertEqual(self.calls[0]["feed"], "sip")
        n = len(self.calls)
        st, _ = await self.get(q)
        self.assertEqual(len(self.calls), n)  # cached
        self.assertNotIn("kid-123456", str(body))

    async def test_bad_params(self):
        st, body = await self.get("/v1/bars?symbols=NVDA&timeframe=3Min")
        self.assertEqual(st, 400)
        st, body = await self.get("/v1/bars?symbols=NVDA&start=2026-01-01T00:00:00Z&end=2026-10-01T00:00:00Z")
        self.assertEqual(body["error"], "bad_range")
