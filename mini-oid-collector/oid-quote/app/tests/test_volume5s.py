"""v0.5.0 volume_5s writer + live bars_1m archive sink (SCHEMAS.md v1 §2, §4)."""
import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from oid_quote.livevol import LiveVolume

from .test_livevol import Cfg, trade

NS = 1_000_000_000
OPEN = dt.datetime(2026, 10, 16, 13, 30, 0, tzinfo=dt.timezone.utc).timestamp()  # Fri 09:30:00 ET


class Subs:
    def __init__(self, syms):
        self.symbols = syms


class Stocks:
    def __init__(self):
        self.connected, self.current_feed = True, "sip"


class FakeCollector:
    def __init__(self, syms):
        self.stocks_subs, self.stocks = Subs(syms), Stocks()


def rows(root, table):
    out = []
    for p in sorted((Path(root) / table).rglob("*.jsonl")):
        out += [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return out


class V5(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "oid-data").mkdir()
        cfg = Cfg(self.tmp)
        cfg.archive_dir = str(self.tmp / "oid-data/archive")
        self.col = FakeCollector(["AMD", "NVDA"])
        self.lv = LiveVolume(cfg, self.col)
        self.lv.v5.t0 = OPEN - 1  # process "started" just before the open
        self.root = self.tmp / "oid-data/archive"

    def feed(self, sym, e, p, s, c=("@",), recv=None):
        self.lv.on_trade("equity", trade(sym, e, p, s, c), recv if recv is not None else e + 0.1)

    def test_dense_rth_buckets_and_fields(self):
        self.lv.tick(OPEN - 1)  # init watermark
        self.feed("AMD", OPEN + 0.5, 100.0, 100)
        self.feed("AMD", OPEN + 1.0, 101.0, 300)
        self.feed("AMD", OPEN + 2.0, 99.0, 50, c=("@", "I"))   # odd lot: volume yes, price no
        self.feed("AMD", OPEN + 3.0, 98.0, 10_000, c=("Q",))    # official open re-report: excluded from volume
        self.feed("AMD", OPEN + 6.0, 102.0, 200)
        self.lv.tick(OPEN + 7.9)
        self.assertEqual(rows(self.root, "volume_5s"), [])      # bucket end + 3 s not reached yet
        self.lv.tick(OPEN + 8.0)
        r = rows(self.root, "volume_5s")
        self.assertEqual(sorted(x["symbol"] for x in r), ["AMD", "NVDA"])  # dense: NVDA row with 0
        a = [x for x in r if x["symbol"] == "AMD"][0]
        n = [x for x in r if x["symbol"] == "NVDA"][0]
        self.assertEqual(a["bucket_start_ns"], int(OPEN) * NS)
        self.assertEqual(a["bucket_end_ns"] - a["bucket_start_ns"], 5 * NS)
        self.assertEqual((a["session"], a["volume"], a["trade_count"]), ("rth", 450, 3))
        self.assertEqual((a["open"], a["high"], a["low"], a["close"]), (100.0, 101.0, 100.0, 101.0))
        self.assertAlmostEqual(a["vwap"], (100 * 100 + 300 * 101 + 50 * 99) / 450)
        self.assertEqual((n["volume"], n["trade_count"], n["open"], n["vwap"]), (0, 0, None, None))
        self.assertTrue(a["stream_ok"]); self.assertEqual(a["stream_feed"], "sip")
        self.assertIsNone(a["rvol_1m_at_end"])  # no norms built in this test
        self.assertEqual(a["schema_version"], "v1"); self.assertTrue(a["writer"].startswith("oid-quote@0.5"))
        self.assertTrue(a["bucket_start_iso"].endswith("Z")); self.assertEqual(a["event_ts_ns"], a["bucket_start_ns"])
        f = list((self.root / "volume_5s").rglob("*.jsonl"))[0]
        self.assertEqual(f.parent.name, "date=2026-10-16"); self.assertEqual(f.name, "part-oid-quote-1.jsonl")

    def test_late_prints_and_cancel(self):
        self.lv.tick(OPEN - 1)
        self.feed("AMD", OPEN + 1, 100.0, 100)
        self.feed("AMD", OPEN + 2, 100.0, 500)
        self.lv.on_cancel("equity", {"T": "x", "S": "AMD", "t": trade("AMD", OPEN + 2, 100.0, 500)["t"], "p": 100.0, "s": 500, "c": ["@"]}, OPEN + 3)
        self.lv.tick(OPEN + 8)
        self.feed("AMD", OPEN + 4, 100.0, 77, recv=OPEN + 9)  # bucket already written -> late
        self.feed("AMD", OPEN + 6, 100.0, 10, recv=OPEN + 12)  # lag 6 s -> stream_ok false
        self.lv.tick(OPEN + 13)
        r = [x for x in rows(self.root, "volume_5s") if x["symbol"] == "AMD"]
        self.assertEqual(r[0]["volume"], 100)          # cancel applied while open
        self.assertEqual(r[1]["late_prints"], 1)
        self.assertEqual(r[1]["volume"], 10)
        self.assertFalse(r[1]["stream_ok"])

    def test_holiday_waits_then_skips_and_disconnect_flag(self):
        self.lv.tick(OPEN - 1)
        self.lv.tick(OPEN + 60)
        self.assertEqual(rows(self.root, "volume_5s"), [])   # held: no RTH print yet
        self.lv.tick(OPEN + 601)
        self.assertEqual(rows(self.root, "volume_5s"), [])   # treated as closed after 10 min
        # pre-market is sparse
        pre = OPEN - 3600
        lv2 = LiveVolume(self.lv.cfg, self.col); lv2.v5.t0 = pre - 1
        lv2.tick(pre - 1)
        lv2.on_trade("equity", trade("NVDA", pre + 1, 180.0, 5), pre + 1.1)
        self.col.stocks.connected = False
        lv2.tick(pre + 1.5)
        self.col.stocks.connected = True
        lv2.tick(pre + 20)
        r = rows(self.root, "volume_5s")
        self.assertEqual([(x["symbol"], x["session"], x["volume"]) for x in r], [("NVDA", "pre", 5)])
        self.assertFalse(r[0]["stream_ok"])

    def test_inert_without_data_root(self):
        cfg = Cfg(self.tmp)
        cfg.archive_dir = str(self.tmp / "missing/archive")
        lv = LiveVolume(cfg, self.col)
        lv.tick(OPEN - 1); self.feed  # noqa
        lv.on_trade("equity", trade("AMD", OPEN + 1, 100.0, 5), OPEN + 1.1)
        lv.tick(OPEN + 20)
        self.assertFalse((self.tmp / "missing").exists())
        self.assertFalse(lv.health()["volume_5s"]["enabled"])

    def test_bars_1m_sink(self):
        self.lv.tick(OPEN - 1)
        for i in range(5):
            self.feed("AMD", OPEN + i * 10, 100.0 + i, 100)
        bar = {"T": "b", "S": "AMD", "t": trade("AMD", OPEN, 1, 1)["t"].replace(".500000", ".000000"),
               "o": 100.0, "h": 104.0, "l": 100.0, "c": 104.0, "v": 500, "n": 5, "vw": 102.0}
        bar["t"] = dt.datetime.fromtimestamp(OPEN, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.lv.on_bar("equity", bar, OPEN + 61)
        self.lv.tick(OPEN + 62)
        self.lv.on_bar("equity", dict(bar, v=490), OPEN + 70, updated=True)
        self.lv.tick(OPEN + 71)
        b = rows(self.root, "bars_1m")
        self.assertEqual([(x["src"], x["volume"]) for x in b], [("alpaca-ws", 500), ("alpaca-ws-updated", 490)])
        self.assertEqual((b[0]["session"], b[0]["final"], b[0]["timeframe"], b[0]["adjustment"]), ("rth", False, "1m", "raw"))
        pre_bar = dict(bar, t=dt.datetime.fromtimestamp(OPEN - 600, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.lv.on_bar("equity", pre_bar, OPEN - 530)
        self.assertEqual(rows(self.root, "bars_1m")[-1]["session"], "pre")


if __name__ == "__main__":
    unittest.main()


class V5Overnight(V5):
    def test_overnight_and_stale_prints_not_late(self):
        night = OPEN + 12 * 3600  # 21:30 ET
        self.lv.v5.t0 = night
        self.lv.tick(night)
        self.feed("AMD", night - 30, 100.0, 5)           # overnight, before watermark
        self.feed("AMD", OPEN + 60, 100.0, 5)            # RTH print hours old
        self.lv.tick(night + 30)
        self.assertEqual(self.lv.v5.stats["late_prints"], 0)
        self.assertEqual(rows(self.root, "volume_5s"), [])
