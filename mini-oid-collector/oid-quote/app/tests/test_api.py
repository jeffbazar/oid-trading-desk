"""API + snapshot tests with a fake-populated cache (no feeds, no keys)."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests

import asyncio
import json
import os
import time
import unittest

import aiohttp

from oid_quote.app import Collector
from oid_quote.cache import feed_meta_for

from .helpers import clear_env, fast_config, free_port, make_root

TOKEN = "test-token-abcdef123456"


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_env()
        self.root = make_root(token=TOKEN, options=["NVDA261016C00190000"])
        self.port = free_port()
        self.cfg = fast_config(self.root, self.port)
        self.col = Collector(self.cfg)
        await self.col.start()
        self.bg = asyncio.create_task(self.col._snapshot_loop())
        # Fake feed: inject rows as if streams delivered them
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".123456789Z"
        self.col.cache.apply_quote("equity", {"S": "NVDA", "bp": 190.0, "bs": 1, "ap": 190.02, "as": 2, "t": ts}, feed_meta_for("equity", "sip"))
        self.col.cache.apply_quote("equity", {"S": "SPY", "bp": 660.0, "bs": 1, "ap": 660.01, "as": 2, "t": ts}, feed_meta_for("equity", "sip"))
        self.col.cache.apply_quote("option", {"S": "NVDA261016C00190000", "bp": 5.1, "bs": 10, "ap": 5.2, "as": 12, "t": ts}, feed_meta_for("option", "opra"))
        self.base = f"http://127.0.0.1:{self.port}"
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close()
        self.col._stop.set()
        await self.bg
        await self.col.stop()

    async def get(self, path, token=None):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        async with self.http.get(self.base + path, headers=h) as r:
            return r.status, await r.json()

    async def test_health_no_auth_no_keys(self):
        st, body = await self.get("/v1/health")
        self.assertEqual(st, 200)
        self.assertEqual(body["status"], "no_keys")
        self.assertEqual(body["keys_present"], {"APCA_API_KEY_ID": False, "APCA_API_SECRET_KEY": False})
        self.assertTrue(body["token_configured"])
        self.assertFalse(body["stocks"]["connected"])
        self.assertEqual(body["stocks"]["desired_count"], 20)
        self.assertEqual(body["options"]["desired_count"], 1)
        self.assertEqual(body["subscriptions"]["stocks"]["count"], 20)
        self.assertEqual(body["cache"]["equity_symbols"], 2)
        self.assertNotIn(TOKEN, json.dumps(body))

    async def test_quotes_requires_bearer(self):
        st, body = await self.get("/v1/quotes?symbols=NVDA")
        self.assertEqual(st, 401)
        st, _ = await self.get("/v1/quotes?symbols=NVDA", token="wrong")
        self.assertEqual(st, 401)
        st, _ = await self.get("/v1/options", token="wrong")
        self.assertEqual(st, 401)

    async def test_quotes_with_token(self):
        st, body = await self.get("/v1/quotes?symbols=nvda,SPY,ZZZZ", token=TOKEN)
        self.assertEqual(st, 200)
        self.assertEqual(set(body["quotes"]), {"NVDA", "SPY"})
        self.assertEqual(body["missing"], ["ZZZZ"])
        q = body["quotes"]["NVDA"]
        self.assertEqual((q["bid"], q["ask"]), (190.0, 190.02))
        self.assertEqual(q["feed"], "alpaca-sip")
        self.assertEqual(q["feed_status"], "disconnected")  # no live feed in this test
        self.assertTrue(q["source_observed_at"].endswith(".123456789Z"))
        st, body = await self.get("/v1/quotes", token=TOKEN)  # all
        self.assertEqual(body["count"], 2)

    async def test_options_with_token(self):
        st, body = await self.get("/v1/options?contracts=NVDA261016C00190000", token=TOKEN)
        self.assertEqual(st, 200)
        o = body["options"]["NVDA261016C00190000"]
        self.assertEqual(o["contract_id"], "NVDA261016C00190000")
        self.assertEqual(o["feed"], "alpaca-opra")
        self.assertFalse(o["delayed"])
        st, body = await self.get("/v1/options?symbols=NVDA261016C00190000", token=TOKEN)
        self.assertEqual(body["count"], 1)

    async def test_token_unconfigured_returns_503(self):
        os.remove(self.root / "secrets" / "OID_QUOTE_TOKEN")
        st, body = await self.get("/v1/quotes", token=TOKEN)
        self.assertEqual(st, 503)
        self.assertEqual(body["error"], "token_not_configured")

    async def test_snapshot_atomic_file(self):
        await asyncio.sleep(0.5)
        p = self.root / "cache" / "quotes.json"
        data = json.loads(p.read_text())
        self.assertIn("NVDA", data["equities"])
        self.assertIn("NVDA261016C00190000", data["options"])
        self.assertEqual(data["collector"]["status"], "no_keys")
        self.assertGreaterEqual(data["collector"]["snapshot"]["writes"], 1)
        leftovers = [f for f in os.listdir(self.root / "cache") if ".tmp" in f]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
