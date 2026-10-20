"""live volume v1 (2026-10-18): print roll-up, ws-bar priority, norms/rvol, persistence, /v1/live-volume."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests

import asyncio
import datetime as dt
import json
import unittest

import aiohttp

from oid_quote.app import Collector, setup_logging
from oid_quote.livevol import LiveVolume, SymRoll, et_parts

from .helpers import clear_env, fast_config, free_port, make_root

TOKEN = "test-token-abcdef123456"
T0 = dt.datetime(2026, 10, 16, 14, 0, 0, tzinfo=dt.timezone.utc).timestamp()  # 10:00:00 ET, slot 30


def iso(e):
    return dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def trade(sym, e, p, s, c=("@",)):
    return {"T": "t", "S": sym, "t": iso(e), "p": p, "s": s, "c": list(c), "x": "Q", "i": 1, "z": "C"}


class Cfg:
    def __init__(self, root):
        from pathlib import Path
        self.live_store_dir = str(Path(root) / "store")
        self.cache_dir = Path(root)
        self.norm_lookback = 20
        self.full_session_min_bars = 30
        self.min_norm_sessions = 5
        self.ws_bar_grace_s = 15.0
        self.half_days = ["2026-11-27"]
        self.backfill_calendar_days = 36


class RollTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.root = tempfile.mkdtemp()
        self.lv = LiveVolume(Cfg(self.root))

    def test_slot(self):
        self.assertEqual(et_parts(T0), ("2026-10-16", 30))
        self.assertEqual(et_parts(T0 - 31 * 60)[1], -1)

    def test_windows_and_conditions(self):
        lv = self.lv
        for i in range(60):
            lv.on_trade("equity", trade("NVDA", T0 + i, 200 + i * 0.01, 100), T0 + i + 0.05)
        lv.on_trade("equity", trade("NVDA", T0 + 59.5, 250.0, 5000, ("I",)), T0 + 59.6)  # odd lot: volume yes, price no
        lv.on_trade("equity", trade("NVDA", T0 + 59.6, 199.0, 9999, ("Q", "O")), T0 + 59.7)  # official open: no volume
        self.assertEqual(lv.view_symbol("NVDA", T0 + 59.9)["cur_bar"]["v"], 11000)
        t = T0 + 60.0
        v = lv.view_symbol("NVDA", t)
        self.assertEqual(v["vol_60s"], 60 * 100 + 5000)
        self.assertEqual(v["vol_10s"], 10 * 100 + 5000)
        self.assertEqual(v["last"], 200.59)
        self.assertAlmostEqual(v["lag_s"], 0.05, places=3)
        self.assertEqual(v["px_30s_ago"], round(200 + 30 * 0.01, 2))
        self.assertIsNone(v["cur_bar"])  # 10:01:00 -> minute 30 is closed
        self.assertEqual(v["day_high"], 200.59)

    def test_minute_close_ws_priority_and_persist(self):
        lv = self.lv
        for i in range(0, 60, 5):
            lv.on_trade("equity", trade("AMD", T0 + i, 500.0, 10), T0 + i)
        lv.on_trade("equity", trade("AMD", T0 + 61, 501.0, 10), T0 + 61)  # rolls minute 30 closed
        lv.tick(T0 + 62)
        r = lv.eq["AMD"]
        self.assertIn(int(T0), r.pending)
        lv.on_bar("equity", {"T": "b", "S": "AMD", "t": iso(T0).replace(".000000", ""), "o": 500, "h": 500.5, "l": 499.5, "c": 500, "v": 777, "n": 9, "vw": 500.01}, T0 + 62)
        lv.tick(T0 + 63)
        self.assertNotIn(int(T0), r.pending)
        f = next((lv.store_dir / "live").glob("AMD-1m-*.jsonl"))
        row = json.loads(f.read_text().splitlines()[0])
        self.assertEqual((row["v"], row["src"], row["slot"]), (777, "alpaca-sip-ws", 30))
        # no ws bar for minute 31 -> prints fallback after grace
        lv.tick(T0 + 120 + 1)  # closes minute 31
        lv.tick(T0 + 120 + 16)
        rows = [json.loads(x) for x in f.read_text().splitlines()]
        self.assertEqual(rows[-1]["src"], "prints")
        self.assertEqual(rows[-1]["v"], 10)

    def test_cancel_and_correction(self):
        lv = self.lv
        lv.on_trade("equity", trade("INTC", T0 + 5, 90.0, 1000), T0 + 5)
        lv.on_trade("equity", trade("INTC", T0 + 6, 90.0, 500000, ("@", "7")), T0 + 6)
        lv.on_cancel("equity", {"T": "x", "S": "INTC", "t": iso(T0 + 6), "p": 90.0, "s": 500000, "a": "C"}, T0 + 20)
        lv.on_cancel("equity", {"T": "c", "S": "INTC", "t": iso(T0 + 5), "op": 90.0, "os": 1000, "oc": ["@"], "cp": 90.0, "cs": 800, "cc": ["@"]}, T0 + 21)
        v = lv.view_symbol("INTC", T0 + 30)
        self.assertEqual((v["vol_60s"], v["cur_bar"]["v"], v["day_vol_rth"]), (800, 800, 800))

    def test_norms_and_rvol(self):
        lv = self.lv
        days = {}
        base = dt.date(2026, 9, 14)
        d = base
        while len(days) < 22:
            if d.weekday() < 5:
                days[d.isoformat()] = [1000.0] * 390
            d += dt.timedelta(days=1)
        days["2026-10-01"] = [1000.0] * 210 + [None] * 180  # half day -> excluded
        lv.build_norms({"NVDA": days}, "2026-10-16")
        self.assertEqual(lv.norm_meta["sessions"]["NVDA"]["n"], 20)
        self.assertNotIn("2026-10-01", lv.norm_meta["sessions"]["NVDA"]["range"])
        for i in range(60):
            lv.on_trade("equity", trade("NVDA", T0 + i, 200.0, 50 if i < 50 else 250), T0 + i)
        v = lv.view_symbol("NVDA", T0 + 60.0)
        self.assertEqual(v["vol_60s"], 50 * 50 + 10 * 250)
        self.assertAlmostEqual(v["rvol_1m"], 5.0, places=1)  # t=10:01:00 -> norm weight all on slot 30
        self.assertAlmostEqual(v["pace_rvol_10s"], 2500 * 6 / 1000, places=1)
        self.assertEqual(v["norm_median_1m"], 1000)
        self.assertEqual(v["day_norm_to_now"], 31000)  # 10:01:00 ET = 31 full minutes
        self.assertAlmostEqual(v["day_rvol"], 5000 / 31000, places=2)
        lv.last_session["NVDA"] = {"date": "2026-10-15", "close": 190.0, "high": 191, "low": 185, "volume": 390000, "complete": True}
        self.assertEqual(lv.view_symbol("NVDA", T0 + 60.0)["prev_close"], 190.0)
        ls = lv.view(["NVDA"], [], False, {}, T0 + 60.0)["last_session"]["NVDA"]
        self.assertEqual((ls["norm_day"], ls["day_rvol"]), (390000, 1.0))

    def test_options_roll(self):
        lv = self.lv
        occ = "META261023P00705000"
        lv.on_trade("option", {"T": "t", "S": occ, "t": iso(T0), "p": 23.5, "s": 4, "c": "I"}, T0)
        lv.on_trade("option", {"T": "t", "S": occ, "t": iso(T0 + 200), "p": 23.8, "s": 6, "c": "I"}, T0 + 200)
        v = lv.view_option(occ, T0 + 201)
        self.assertEqual((v["vol_60s"], v["vol_5m"], v["day_vol"], v["last"]), (6, 10, 10, 23.8))


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_env()
        self.root = make_root(token=TOKEN)
        self.port = free_port()
        self.cfg = fast_config(self.root, self.port)
        setup_logging(self.cfg)
        self.col = Collector(self.cfg)
        self.task = asyncio.create_task(self.col.run())
        self.http = aiohttp.ClientSession()
        for _ in range(100):
            try:
                async with self.http.get(f"http://127.0.0.1:{self.port}/v1/health") as r:
                    if r.status == 200:
                        break
            except aiohttp.ClientError:
                await asyncio.sleep(0.05)

    async def asyncTearDown(self):
        await self.http.close()
        self.col._stop.set()
        await asyncio.wait_for(self.task, 5)

    async def test_endpoint(self):
        import time
        t = time.time()
        self.col.livevol.on_trade("equity", trade("SPY", t - 1, 600.0, 300), t - 0.9)
        url = f"http://127.0.0.1:{self.port}/v1/live-volume?symbols=SPY,QQQ&detail=1"
        async with self.http.get(url) as r:
            self.assertEqual(r.status, 401)
        async with self.http.get(url, headers={"Authorization": f"Bearer {TOKEN}"}) as r:
            self.assertEqual(r.status, 200)
            body = await r.json()
        self.assertEqual(body["symbols"]["SPY"]["vol_60s"], 300)
        self.assertEqual(body["missing"], ["QQQ"])
        self.assertIn("seconds", body["symbols"]["SPY"])
        async with self.http.get(f"http://127.0.0.1:{self.port}/v1/health") as r:
            h = await r.json()
        self.assertIn("live_volume", h)


if __name__ == "__main__":
    unittest.main()


class ChannelTests(unittest.TestCase):
    def test_bars_only_on_sip(self):
        from oid_quote.cache import QuoteCache
        from oid_quote.feeds import AlpacaStream
        s = AlpacaStream("stocks", "equity", "ws://x/v2", "sip", "iex", "json", ["quotes", "trades"], QuoteCache(), lambda: None,
                         extra_channels=["bars", "updatedBars"], extra_channel_feeds=["sip", "iex"])
        self.assertEqual(s.active_channels(), ["quotes", "trades", "bars", "updatedBars"])
        s.current_feed = "overnight"
        self.assertEqual(s.active_channels(), ["quotes", "trades"])


class ReadVolSurgeTest(unittest.TestCase):
    def test_read_vol_surge(self):
        import json as _j
        import tempfile
        from pathlib import Path
        from oid_quote.livevol import read_vol_surge
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            (tmp_path / "volsurge-status.json").write_text(_j.dumps({"mode": "dry", "last_gate": "off_rth", "ticks": 3, "secret": "x"}))
            with open(tmp_path / "events.jsonl", "w") as f:
                f.write(_j.dumps({"event_type": "level_cross", "symbol": "AMD"}) + "\n")
                for i in range(5):
                    f.write(_j.dumps({"event_type": "vol_surge", "symbol": f"S{i}", "dry_run": True,
                                      "details": {"level": "day_low", "rvol_1m": 4.0 + i}}) + "\n")
                f.write("garbage\n")
            out = read_vol_surge(str(tmp_path), 3)
            self.assertEqual([e["symbol"] for e in out["events"]], ["S4", "S3", "S2"])
            self.assertTrue(out["events"][0]["dry_run"])
            self.assertEqual(out["events"][0]["rvol_1m"], 8.0)
            self.assertEqual(out["status"], {"mode": "dry", "last_gate": "off_rth", "ticks": 3})
            self.assertEqual(read_vol_surge(str(tmp_path / "nope"))["events"], [])
