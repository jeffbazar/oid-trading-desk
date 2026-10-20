"""WIDE tier (2026-10-20): sector-watch names ride the same stock socket as trades only (no quotes), stay out of the
quote cache and the default /v1/live-volume view, and show up under ?tier=wide."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))

import asyncio
import json
import unittest

import aiohttp

from oid_quote.app import Collector, setup_logging

from .fake_alpaca import GOOD_KEY, GOOD_SECRET, FakeAlpaca
from .helpers import clear_env, fast_config, free_port, make_root
from .test_fake_feed import TOKEN, wait_for


class WideTier(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_env()
        self.fake = FakeAlpaca(entitled_stock_feeds=("sip", "iex"))
        fport = await self.fake.start()
        self.root = make_root(token=TOKEN, options=[])
        (self.root / "secrets" / "APCA_API_KEY_ID").write_text(GOOD_KEY + "\n")
        (self.root / "secrets" / "APCA_API_SECRET_KEY").write_text(GOOD_SECRET + "\n")
        (self.root / "stream-quote-allowlist.json").write_text(json.dumps({"underlyings": ["SPY", "NVDA"]}))
        # NVDA is core -> must be dropped from wide
        (self.root / "wide-allowlist.json").write_text(json.dumps({"symbols": ["XOM", "SOFI", "NVDA"]}))
        self.port = free_port()
        self.cfg = fast_config(self.root, self.port, stocks_ws_base=f"ws://127.0.0.1:{fport}/v2",
                               options_ws_base=f"ws://127.0.0.1:{fport}/v1beta1", enable_options=False,
                               wide_archive_dir=str(self.root / "archive-wide"),
                               wide_store_dir=str(self.root / "cache" / "bars-wide" / "store"))
        setup_logging(self.cfg)
        self.col = Collector(self.cfg)
        self.task = asyncio.create_task(self.col.run())
        self.http = aiohttp.ClientSession()
        self.base = f"http://127.0.0.1:{self.port}"
        self.h = {"Authorization": f"Bearer {TOKEN}"}

    async def asyncTearDown(self):
        await self.http.close()
        self.col._stop.set()
        await asyncio.wait_for(self.task, 5)
        await self.fake.stop()

    async def test_wide_trades_only_and_separate_view(self):
        self.assertEqual(self.col.wide_symbols(), ["XOM", "SOFI"])
        ok = await wait_for(lambda: self.col.livevol_wide is not None and {"XOM", "SOFI"} <= set(self.col.livevol_wide.eq), 8)
        self.assertTrue(ok)
        subs = [m for m in self.fake.sub_messages if m["kind"] == "stock" and m["action"] == "subscribe"]
        wide_msgs = [m for m in subs if "XOM" in (m.get("trades") or [])]
        self.assertTrue(wide_msgs)
        for m in wide_msgs:
            self.assertNotIn("XOM", m.get("quotes") or [])
        # core quotes never include wide names
        self.assertFalse(any("XOM" in (m.get("quotes") or []) for m in subs))
        # quote cache / default view stay core-only
        self.assertNotIn("XOM", self.col.cache.symbols("equity"))
        async with self.http.get(self.base + "/v1/live-volume", headers=self.h) as r:
            core = await r.json()
        self.assertNotIn("XOM", core["symbols"])
        self.assertIn("SPY", core["symbols"])
        async with self.http.get(self.base + "/v1/live-volume?tier=wide", headers=self.h) as r:
            wide = await r.json()
        self.assertEqual(wide["tier"], "wide")
        self.assertIn("XOM", wide["symbols"])
        self.assertNotIn("SPY", wide["symbols"])
        self.assertNotIn("NVDA", wide["symbols"])
        async with self.http.get(self.base + "/v1/health") as r:
            h = await r.json()
        self.assertEqual(h["wide"]["symbols"], 2)
        self.assertEqual(h["stocks"]["wide"]["subscribed_trades"], 2)
        self.assertEqual(h["stocks"]["desired_count"], 2)

    async def test_wide_list_reload(self):
        await wait_for(lambda: self.col.stocks and len(self.col.stocks.requested_wide) == 2, 8)
        (self.root / "wide-allowlist.json").write_text(json.dumps({"symbols": ["XOM"]}))
        ok = await wait_for(lambda: self.col.stocks.requested_wide == {"XOM"}, 8)
        self.assertTrue(ok)
        unsub = lambda: [m for m in self.fake.sub_messages if m["action"] == "unsubscribe" and "SOFI" in (m.get("trades") or [])]
        self.assertTrue(await wait_for(lambda: bool(unsub()), 5))
        self.assertNotIn("quotes", unsub()[0])  # wide unsubscribe never touches the quotes channel

    def test_prune_archive_only_wide_root(self):
        lw = self.col.livevol_wide
        old = lw.v5.root / "volume_5s" / "date=2020-01-02"
        old.mkdir(parents=True)
        (old / "part.jsonl").write_text("{}\n")
        new = lw.v5.root / "volume_5s" / "date=2999-01-01"
        new.mkdir(parents=True)
        self.assertEqual(lw.prune_archive(21), 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertEqual(self.col.livevol.prune_archive(21), 0)  # core tier never prunes


if __name__ == "__main__":
    unittest.main()
