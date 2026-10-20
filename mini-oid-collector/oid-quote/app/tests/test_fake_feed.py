"""End-to-end: real collector code against a local fake Alpaca websocket server (JSON stocks + msgpack OPRA)."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests

import asyncio
import json
import os
import time
import unittest

import aiohttp

from oid_quote.app import Collector, setup_logging

from .fake_alpaca import GOOD_KEY, GOOD_SECRET, FakeAlpaca
from .helpers import clear_env, fast_config, free_port, make_root

TOKEN = "test-token-abcdef123456"
C1, C2, C3 = "NVDA261016C00190000", "SPY261009P00650000", "QQQ261009C00600000"


async def wait_for(pred, timeout=8.0, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        await asyncio.sleep(step)
    return False


class FakeFeedTests(unittest.IsolatedAsyncioTestCase):
    entitled_stock = ("sip", "iex")
    key, secret = GOOD_KEY, GOOD_SECRET
    options = [C1, C2]

    async def asyncSetUp(self):
        clear_env()
        self.fake = FakeAlpaca(entitled_stock_feeds=self.entitled_stock)
        fport = await self.fake.start()
        self.fport = fport
        self.root = make_root(token=TOKEN, options=self.options)
        (self.root / "secrets" / "APCA_API_KEY_ID").write_text(self.key + "\n")
        (self.root / "secrets" / "APCA_API_SECRET_KEY").write_text(self.secret + "\n")
        self.port = free_port()
        self.cfg = fast_config(
            self.root,
            self.port,
            stocks_ws_base=f"ws://127.0.0.1:{fport}/v2",
            options_ws_base=f"ws://127.0.0.1:{fport}/v1beta1",
            **self.extra_config(),
        )
        setup_logging(self.cfg)
        self.col = Collector(self.cfg)
        self.configure_collector(self.col)
        self.task = asyncio.create_task(self.col.run())
        self.http = aiohttp.ClientSession()
        self.base = f"http://127.0.0.1:{self.port}"

    def configure_collector(self, col):  # hook for subclasses (e.g. fake clock)
        pass

    def extra_config(self):
        return {}

    async def asyncTearDown(self):
        await self.http.close()
        self.col._stop.set()
        await asyncio.wait_for(self.task, 5)
        await self.fake.stop()

    async def get(self, path, auth=True):
        h = {"Authorization": f"Bearer {TOKEN}"} if auth else {}
        async with self.http.get(self.base + path, headers=h) as r:
            return r.status, await r.json()

    def assert_no_secrets_in_logs(self):
        text = (self.root / "logs" / "collector.log").read_text()
        self.assertNotIn(GOOD_SECRET, text)
        self.assertNotIn(GOOD_KEY, text)
        snap = (self.root / "cache" / "quotes.json").read_text() if (self.root / "cache" / "quotes.json").exists() else ""
        self.assertNotIn(GOOD_SECRET, snap)


class HappyPath(FakeFeedTests):
    async def test_stream_cache_api_dynamic_subs_reconnect(self):
        col = self.col
        self.assertTrue(await wait_for(lambda: col.status() == "ok"), col.health())
        self.assertTrue(await wait_for(lambda: len(col.stocks.subscribed) == 20 and len(col.options.subscribed) == 2))
        self.assertTrue(await wait_for(lambda: "NVDA" in col.cache.rows["equity"] and C1 in col.cache.rows["option"]))

        st, h = await self.get("/v1/health", auth=False)
        self.assertEqual(st, 200)
        self.assertEqual(h["status"], "ok")
        self.assertTrue(h["stocks"]["connected"] and h["options"]["connected"])
        self.assertEqual(h["stocks"]["feed"], "sip")
        self.assertEqual(h["stocks"]["subscribed_count"], 20)
        self.assertEqual(h["options"]["subscribed_count"], 2)
        self.assertLess(h["stocks"]["last_message_age_s"], 2)

        st, q = await self.get("/v1/quotes?symbols=NVDA,SPY")
        nv = q["quotes"]["NVDA"]
        self.assertEqual(nv["feed"], "alpaca-sip")
        self.assertEqual(nv["feed_status"], "ok")
        self.assertIsNotNone(nv["bid"])
        self.assertIsNotNone(nv["last"])
        self.assertRegex(nv["source_observed_at"], r"\.\d{9}Z$")

        st, o = await self.get(f"/v1/options?contracts={C1}")
        oc = o["options"][C1]
        self.assertEqual(oc["feed"], "alpaca-opra")
        self.assertFalse(oc["delayed"])
        self.assertRegex(oc["source_observed_at"], r"\.\d{9}Z$")  # decoded from msgpack Timestamp ext
        self.assertLess(oc["source_age_s"], 2)

        # options were sent as msgpack, auth as msgpack too; auth frames carried the keys
        self.assertTrue(any(a["key"] == GOOD_KEY for a in self.fake.auth_messages))

        # dynamic resubscribe: swap C2 -> C3
        p = self.root / "options-subs.json"
        p.write_text(json.dumps([C1, C3]))
        os.utime(p, (time.time() + 2, time.time() + 2))
        self.assertTrue(await wait_for(lambda: col.options.subscribed == {C1, C3}), col.options.subscribed)
        self.assertTrue(await wait_for(lambda: C3 in col.cache.rows["option"]))
        st, o = await self.get(f"/v1/options?contracts={C2},{C3}")
        self.assertEqual(o["options"][C2]["feed_status"], "unsubscribed")
        self.assertEqual(o["options"][C3]["feed_status"], "ok")

        # server drops every socket -> auto reconnect + resubscribe
        before = (col.stocks.connect_count, col.options.connect_count)
        await self.fake.drop_all()
        self.assertTrue(await wait_for(lambda: col.stocks.connect_count > before[0] and col.options.connect_count > before[1]))
        self.assertTrue(await wait_for(lambda: col.status() == "ok" and len(col.stocks.subscribed) == 20 and col.options.subscribed == {C1, C3}))
        mark = time.time()
        self.assertTrue(await wait_for(lambda: col.cache.rows["equity"]["NVDA"]["_recv"] > mark))
        self.assertGreaterEqual(col.stocks.reconnects, 1)

        # snapshot file
        await asyncio.sleep(0.5)
        snap = json.loads((self.root / "cache" / "quotes.json").read_text())
        self.assertEqual(len(snap["equities"]), 20)
        self.assertIn(C1, snap["options"])
        self.assertGreater(snap["collector"]["cache"]["lag"]["equity"]["n"], 0)
        self.assert_no_secrets_in_logs()


class SipNotEntitledFallsBackToIex(FakeFeedTests):
    entitled_stock = ("iex",)
    options = []

    async def test_fallback(self):
        col = self.col
        self.assertTrue(await wait_for(lambda: col.stocks.connected), col.stocks.health())
        h = col.health()
        self.assertEqual(h["stocks"]["feed"], "iex")
        self.assertTrue(h["stocks"]["fallback_active"])
        self.assertTrue(await wait_for(lambda: "NVDA" in col.cache.rows["equity"]))
        self.assertEqual(col.cache.rows["equity"]["NVDA"]["feed"], "alpaca-iex")
        self.assertEqual(self.fake.connections.get("stock/sip"), 1)
        # empty options list: options socket still connects (entitlement check) with 0 subs
        self.assertTrue(await wait_for(lambda: col.options.connected))
        self.assertEqual(col.health()["options"]["subscribed_count"], 0)
        self.assertEqual(col.status(), "ok")


class BadKeys(FakeFeedTests):
    secret = "WRONGSECRET999"
    options = []

    async def test_auth_failed(self):
        col = self.col
        self.assertTrue(await wait_for(lambda: col.status() == "auth_failed"), col.health())
        st, h = await self.get("/v1/health", auth=False)
        self.assertEqual(h["status"], "auth_failed")
        self.assertIn("402", h["stocks"]["last_error"])
        await asyncio.sleep(0.3)
        text = (self.root / "logs" / "collector.log").read_text()
        self.assertNotIn("WRONGSECRET999", text)
        self.assertNotIn(GOOD_KEY, text)


class OptionCap(FakeFeedTests):
    options = [f"NVDA261016C{k:08d}" for k in range(100000, 100000 + 1005 * 500, 500)]

    async def test_cap_1000(self):
        col = self.col
        self.assertTrue(await wait_for(lambda: len(col.options.subscribed) == 1000, timeout=10), len(col.options.subscribed))
        h = col.health()
        self.assertEqual(h["subscriptions"]["options"]["truncated"], 5)
        self.assertEqual(h["options"]["desired_count"], 1000)
        sizes = [len(m.get("quotes", [])) for m in self.fake.sub_messages if m["kind"] == "option" and m["action"] == "subscribe"]
        self.assertTrue(all(s <= 200 for s in sizes), sizes)


class KeysArriveLater(FakeFeedTests):
    """Start in placeholder mode (no keys), then drop keys in: feeds start without restart."""

    async def asyncSetUp(self):
        self.key_hold = None
        await super().asyncSetUp()

    async def test_placeholder_then_keys(self):
        # remove keys right after startup is racy; instead build a fresh collector without keys
        self.col._stop.set()
        await asyncio.wait_for(self.task, 5)
        for n in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
            (self.root / "secrets" / n).unlink()
        self.col = Collector(self.cfg)
        self.task = asyncio.create_task(self.col.run())
        self.assertTrue(await wait_for(lambda: self.col._runner is not None))
        st, h = await self.get("/v1/health", auth=False)
        self.assertEqual(h["status"], "no_keys")
        self.assertIsNone(self.col.stocks._task)
        (self.root / "secrets" / "APCA_API_KEY_ID").write_text(GOOD_KEY)
        (self.root / "secrets" / "APCA_API_SECRET_KEY").write_text(GOOD_SECRET)
        self.assertTrue(await wait_for(lambda: self.col.status() == "ok"), self.col.health())


if __name__ == "__main__":
    unittest.main()


# 2026-10-07 (Wed) 23:00 UTC = 19:00 ET (SIP extended); 2026-10-08 01:00 UTC = 21:00 ET (overnight)
DAY_T = 1791414000.0
NIGHT_T = 1791421200.0


class OvernightSchedule(FakeFeedTests):
    """One stock socket that moves sip -> overnight -> sip on the ET session schedule."""

    entitled_stock = ("sip", "iex", "overnight")
    options = []

    def extra_config(self):
        # overnight lives under /v1beta1 on the same fake server (JSON, like the real one)
        return {"stock_overnight_feed": "overnight", "overnight_ws_base": f"ws://127.0.0.1:{self.fport}/v1beta1"}

    async def asyncSetUp(self):
        self.fake_clock = DAY_T
        await super().asyncSetUp()

    def configure_collector(self, col):
        col.clock = lambda: self.fake_clock

    async def test_switch_single_connection(self):
        col = self.col
        # stocks stream built in start(); point its overnight route at the fake server
        self.assertTrue(await wait_for(lambda: col.stocks is not None))
        self.assertTrue(await wait_for(lambda: col.stocks.connected and len(col.stocks.subscribed) == 20), col.stocks.health())
        self.assertEqual(col.stocks.current_feed, "sip")
        self.assertTrue(col.stocks.url().endswith("/v2/sip"))
        self.assertTrue(await wait_for(lambda: col.cache.rows["equity"].get("NVDA", {}).get("stream_feed") == "sip"))
        h = col.health()
        self.assertEqual(h["stock_schedule"]["scheduled_feed"], "sip")
        self.assertIsNotNone(h["stock_schedule"]["next_switch_at"])

        # 8 PM ET passes -> same socket moves to overnight, resubscribes the same 20, rows tagged overnight
        self.fake_clock = NIGHT_T
        self.assertTrue(await wait_for(lambda: col.stocks.current_feed == "overnight" and col.stocks.connected and len(col.stocks.subscribed) == 20, timeout=8), col.stocks.health())
        self.assertTrue(col.stocks.url().endswith("/v1beta1/overnight"))
        self.assertIsNone(col.stocks.fallback_feed)  # no iex substitute overnight
        mark = time.time()
        self.assertTrue(await wait_for(lambda: col.cache.rows["equity"]["NVDA"]["_recv"] > mark and col.cache.rows["equity"]["NVDA"]["stream_feed"] == "overnight"))
        st, q = await self.get("/v1/quotes?symbols=NVDA")
        nv = q["quotes"]["NVDA"]
        self.assertEqual(nv["feed"], "alpaca-overnight")
        self.assertEqual(nv["venue_scope"], "overnight")
        self.assertEqual(nv["stream_feed"], "overnight")
        self.assertEqual(nv["quote_feed"], "overnight")
        self.assertEqual(nv["trade_feed"], "overnight")
        self.assertEqual(nv["feed_status"], "ok")
        self.assertFalse(nv["delayed"])
        self.assertEqual(q["feed"]["feed"], "overnight")
        self.assertEqual(self.fake.connections.get("stock/overnight"), 1)

        # 4 AM ET -> back to sip
        self.fake_clock = DAY_T + 86400  # Thu 19:00 ET
        self.assertTrue(await wait_for(lambda: col.stocks.current_feed == "sip" and col.stocks.connected and len(col.stocks.subscribed) == 20, timeout=8))
        self.assertEqual(self.fake.connections.get("stock/sip"), 2)
        self.assertEqual(col.stocks.feed_switches, 2)
        # never more than one stock socket open at once (Alpaca connection limit)
        self.assertEqual(self.fake.max_active["stock"], 1)
        self.assertEqual(col.status(), "ok")
        self.assert_no_secrets_in_logs()


class OvernightNotEntitled(FakeFeedTests):
    """409 on overnight must not crash or fall back to iex; health shows the error and it retries."""

    entitled_stock = ("sip", "iex")
    options = []

    def extra_config(self):
        return {"stock_overnight_feed": "overnight", "overnight_ws_base": f"ws://127.0.0.1:{self.fport}/v1beta1"}

    def configure_collector(self, col):
        col.clock = lambda: NIGHT_T

    async def test_overnight_409(self):
        col = self.col
        self.assertTrue(await wait_for(lambda: col.stocks is not None))
        self.assertTrue(await wait_for(lambda: (col.stocks.last_error or "").find("409") >= 0, timeout=8), col.stocks.health())
        self.assertEqual(col.stocks.current_feed, "overnight")
        self.assertFalse(col.stocks.connected)
        self.assertEqual(self.fake.connections.get("stock/iex"), None)
