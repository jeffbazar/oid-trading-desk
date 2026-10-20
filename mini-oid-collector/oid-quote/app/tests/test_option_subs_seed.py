"""v0.3.0: PUT/GET /v1/options/subs + REST snapshot seeding of quote-less option contracts (fake servers)."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests

import asyncio
import json
import time
import unittest

import aiohttp
from aiohttp import web

from oid_quote.app import Collector

from .helpers import clear_env, fast_config, free_port, make_root

TOKEN = "test-token-abcdef123456"


class OptionSubsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_env()
        self.root = make_root(token=TOKEN, options=[])
        self.port = free_port()
        self.col = Collector(fast_config(self.root, self.port))
        await self.col.start()
        self.base = f"http://127.0.0.1:{self.port}"
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close()
        await self.col.stop()

    async def test_put_requires_bearer(self):
        async with self.http.put(self.base + "/v1/options/subs", json=["NVDA261120C00245000"]) as r:
            self.assertEqual(r.status, 401)
        self.assertEqual(json.loads((self.root / "options-subs.json").read_text()), [])

    async def test_put_writes_file_validates_and_applies(self):
        h = {"Authorization": f"Bearer {TOKEN}", "X-OID-Client": "oid-box-test"}
        body = {"contracts": ["nvda261120c00245000", "O:NFLX261016P00070000", "BAD", "NVDA261120C00245000"]}
        async with self.http.put(self.base + "/v1/options/subs", json=body, headers=h) as r:
            self.assertEqual(r.status, 200)
            res = await r.json()
        self.assertEqual(res["contracts"], ["NVDA261120C00245000", "NFLX261016P00070000"])
        self.assertEqual(res["invalid"], ["BAD"])
        disk = json.loads((self.root / "options-subs.json").read_text())
        self.assertEqual(disk["contracts"], res["contracts"])
        self.assertEqual(disk["source"], "oid-box-test")
        self.assertEqual(self.col.options.desired, res["contracts"])
        async with self.http.get(self.base + "/v1/options/subs", headers=h) as r:
            view = await r.json()
        self.assertEqual(view["count"], 2)
        self.assertEqual(view["last_api_write"]["source"], "oid-box-test")
        async with self.http.get(self.base + "/v1/health") as r:
            hb = await r.json()
        self.assertEqual(hb["subscriptions"]["options"]["count"], 2)
        self.assertNotIn(TOKEN, json.dumps(hb))

    async def test_put_bad_json(self):
        h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        async with self.http.put(self.base + "/v1/options/subs", data=b"{nope", headers=h) as r:
            self.assertEqual(r.status, 400)
        async with self.http.put(self.base + "/v1/options/subs", json={"x": 1}, headers=h) as r:
            self.assertEqual(r.status, 400)


class SeedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_env()
        self.calls = []
        ts = "2026-10-09T19:59:59.123456789Z"

        async def snapshots(request):
            self.calls.append((dict(request.query), request.headers.get("APCA-API-KEY-ID")))
            syms = request.query["symbols"].split(",")
            snaps = {}
            for s in syms:
                if s.startswith("NVDA"):
                    snaps[s] = {"latestQuote": {"ap": 5.15, "as": 30, "ax": "C", "bp": 5.0, "bs": 20, "bx": "N", "c": "A", "t": ts},
                                "latestTrade": {"c": "I", "p": 5.08, "s": 2, "t": "2026-10-09T19:59:40Z", "x": "C"}}
            return web.json_response({"snapshots": snaps, "next_page_token": None})

        self.fake = web.Application()
        self.fake.router.add_get("/v1beta1/options/snapshots", snapshots)
        self.runner = web.AppRunner(self.fake)
        await self.runner.setup()
        self.fport = free_port()
        await web.TCPSite(self.runner, "127.0.0.1", self.fport).start()
        self.root = make_root(token=TOKEN, options=["NVDA261120C00245000", "INTC261002C00115000"])
        (self.root / "secrets" / "APCA_API_KEY_ID").write_text("PKTESTKEYID123\n")
        (self.root / "secrets" / "APCA_API_SECRET_KEY").write_text("testsecret123456\n")
        cfg = fast_config(self.root, free_port(), enable_options=True,
                          options_snapshot_url=f"http://127.0.0.1:{self.fport}/v1beta1/options/snapshots",
                          options_ws_base="ws://127.0.0.1:1", stocks_ws_base="ws://127.0.0.1:1")
        self.col = Collector(cfg)
        self.col.cfg.root.mkdir(parents=True, exist_ok=True)
        self.col.reload_keys()
        self.col.options_subs.reload_if_changed()

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_seed_applies_snapshot_and_backs_off(self):
        n = await self.col.seed_options_once()
        self.assertEqual(n, 1)
        q, key = self.calls[0]
        self.assertEqual(q["feed"], "opra")
        self.assertEqual(key, "PKTESTKEYID123")
        row = self.col.cache.view("option", "NVDA261120C00245000", True, lambda s: True, time.time())
        self.assertEqual((row["bid"], row["ask"], row["last"]), (5.0, 5.15, 5.08))
        self.assertEqual(row["feed"], "alpaca-opra")
        self.assertEqual(row["quote_feed"], "opra-snapshot")
        self.assertTrue(row["quote_observed_at"].startswith("2026-10-09T19:59:59"))
        # NVDA now has a quote, INTC (expired: empty snapshot) is inside its retry window -> no new call
        n2 = await self.col.seed_options_once()
        self.assertEqual(n2, 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.col._seed_stats["empty"], 1)

    async def test_stream_quote_not_overwritten_by_older_snapshot(self):
        from oid_quote.cache import feed_meta_for
        self.col.cache.apply_quote("option", {"S": "NVDA261120C00245000", "bp": 6.0, "ap": 6.1, "t": "2026-10-12T13:31:00Z"}, feed_meta_for("option", "opra"))
        self.col.apply_option_snapshots({"NVDA261120C00245000": {"latestQuote": {"bp": 5.0, "ap": 5.15, "t": "2026-10-09T19:59:59Z"}}})
        row = self.col.cache.view("option", "NVDA261120C00245000", True, lambda s: True, time.time())
        self.assertEqual(row["bid"], 6.0)

    async def test_no_keys_no_seed(self):
        self.col._keys = None
        self.assertEqual(await self.col.seed_options_once(), 0)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
