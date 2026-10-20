import os as _os, tempfile as _tf; _os.environ.setdefault("OID_DATA_ROOT", _tf.mkdtemp(prefix="oid-test-data-"))  # never touch ~/oid-data in tests
import json
import logging
import tempfile
import time
import unittest
from pathlib import Path

import msgpack

from oid_quote.cache import QuoteCache, feed_meta_for
from oid_quote.config import APP_DIR
from oid_quote.credentials import RedactFilter, TokenStore, load_alpaca_keys
from oid_quote.subs import FileSubs
from oid_quote.timeutil import coerce_ts, in_overnight_window, next_feed_switch_at, parse_rfc3339, scheduled_stock_feed, session_for

from .helpers import clear_env


class TimeTests(unittest.TestCase):
    def test_rfc3339_nanoseconds(self):
        e, iso = parse_rfc3339("2024-03-11T13:35:35.13312256Z")
        self.assertAlmostEqual(e, 1710164135.13312256, places=5)
        self.assertEqual(iso, "2024-03-11T13:35:35.13312256Z")

    def test_rfc3339_offset(self):
        e, _ = parse_rfc3339("2024-03-11T09:35:35.5-04:00")
        self.assertAlmostEqual(e, 1710164135.5, places=5)

    def test_msgpack_timestamp(self):
        ts = msgpack.Timestamp.from_unix_nano(1710164135133122560)
        rt = msgpack.unpackb(msgpack.packb(ts))
        e, iso = coerce_ts(rt)
        self.assertAlmostEqual(e, 1710164135.13312256, places=5)
        self.assertEqual(iso, "2024-03-11T13:35:35.133122560Z")

    def test_session(self):
        # 2026-10-07 is a Wednesday. 14:00 UTC = 10:00 ET (RTH); 12:00 UTC = 08:00 ET (pre); 02:00 UTC = 22:00 ET prev day (closed)
        self.assertEqual(session_for(parse_rfc3339("2026-10-07T14:00:00Z")[0]), "RTH")
        self.assertEqual(session_for(parse_rfc3339("2026-10-07T12:00:00Z")[0]), "extended")
        self.assertEqual(session_for(parse_rfc3339("2026-10-07T02:00:00Z")[0]), "overnight")  # Tue 22:00 ET
        self.assertEqual(session_for(parse_rfc3339("2026-10-10T15:00:00Z")[0]), "closed")  # Saturday
        self.assertEqual(session_for(parse_rfc3339("2026-10-10T02:00:00Z")[0]), "closed")  # Fri 22:00 ET: no overnight
        self.assertEqual(session_for(parse_rfc3339("2026-10-12T01:00:00Z")[0]), "overnight")  # Sun 21:00 ET

    def test_overnight_window_and_schedule(self):
        def ts(s):
            return parse_rfc3339(s)[0]

        cases = {
            "2026-10-07T23:59:00Z": False,  # Wed 19:59 ET (SIP after-hours)
            "2026-10-08T00:00:00Z": True,  # Wed 20:00 ET
            "2026-10-08T07:59:00Z": True,  # Thu 03:59 ET
            "2026-10-08T08:00:00Z": False,  # Thu 04:00 ET (premarket on SIP)
            "2026-10-08T14:00:00Z": False,  # Thu 10:00 ET RTH
            "2026-10-10T00:30:00Z": False,  # Fri 20:30 ET: no Fri-night session
            "2026-10-10T07:00:00Z": False,  # Sat 03:00 ET
            "2026-10-11T23:59:00Z": False,  # Sun 19:59 ET
            "2026-10-12T00:00:00Z": True,  # Sun 20:00 ET
            "2026-10-09T07:30:00Z": True,  # Fri 03:30 ET (Thu-night session)
        }
        for s, want in cases.items():
            self.assertEqual(in_overnight_window(ts(s)), want, s)
            self.assertEqual(scheduled_stock_feed(ts(s), "sip", "overnight"), "overnight" if want else "sip", s)
            self.assertEqual(scheduled_stock_feed(ts(s), "sip", None), "sip", s)
        # next switch: Wed 19:00 ET -> Wed 20:00 ET; Wed 21:00 ET -> Thu 04:00 ET; Fri 21:00 ET -> Sun 20:00 ET
        self.assertEqual(next_feed_switch_at(ts("2026-10-07T23:00:00Z"), "sip", "overnight"), ts("2026-10-08T00:00:00Z"))
        self.assertEqual(next_feed_switch_at(ts("2026-10-08T01:00:00Z"), "sip", "overnight"), ts("2026-10-08T08:00:00Z"))
        self.assertEqual(next_feed_switch_at(ts("2026-10-10T01:00:00Z"), "sip", "overnight"), ts("2026-10-12T00:00:00Z"))
        self.assertIsNone(next_feed_switch_at(ts("2026-10-10T01:00:00Z"), "sip", None))

    def test_config_overnight_default_and_off(self):
        import tempfile

        from oid_quote.config import load_config

        root = tempfile.mkdtemp()
        cfg = load_config(root=root)
        self.assertEqual(cfg.stock_overnight_feed, "overnight")
        self.assertTrue(cfg.overnight_ws_base.endswith("/v1beta1"))
        self.assertIsNone(load_config(root=root, overrides={"stock_overnight_feed": "off"}).stock_overnight_feed)
        with self.assertRaises(ValueError):
            load_config(root=root, overrides={"stock_overnight_feed": "bogus"})


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.c = QuoteCache(stale_after_s=120)
        self.sip = feed_meta_for("equity", "sip")
        self.opra = feed_meta_for("option", "opra")

    def test_quote_trade_merge_and_view(self):
        t0 = time.time()
        src = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t0 - 1)) + ".500000000Z"
        self.c.apply_quote("equity", {"T": "q", "S": "NVDA", "bp": 190.1, "bs": 3, "ap": 190.12, "as": 5, "bx": "Q", "ax": "P", "c": ["R"], "z": "C", "t": src}, self.sip, t0)
        self.c.apply_trade("equity", {"T": "t", "S": "NVDA", "p": 190.11, "s": 100, "x": "D", "c": ["@"], "t": src}, self.sip, t0)
        v = self.c.view("equity", "NVDA", True, lambda s: True, t0 + 1)
        self.assertEqual(v["instrument_id"], "NVDA")
        self.assertEqual((v["bid"], v["ask"], v["bid_size"], v["ask_size"]), (190.1, 190.12, 3, 5))
        self.assertEqual((v["last"], v["last_size"]), (190.11, 100))
        self.assertEqual(v["feed"], "alpaca-sip")
        self.assertEqual(v["venue_scope"], "consolidated")
        self.assertFalse(v["delayed"])
        self.assertEqual(v["feed_status"], "ok")
        self.assertEqual(v["source_observed_at"], src)
        self.assertTrue(v["received_at"].endswith(("-07:00", "-08:00")))  # PT-aware
        self.assertGreater(v["source_age_s"], 1.0)
        self.assertEqual(v["updates"], 2)
        self.assertNotIn("_recv", v)
        self.assertEqual(self.c.lag["equity"].n, 2)
        self.assertEqual((v["stream_feed"], v["quote_feed"], v["trade_feed"]), ("sip", "sip", "sip"))

    def test_overnight_tags_per_channel(self):
        night = feed_meta_for("equity", "overnight")
        self.assertEqual((night.feed, night.venue_scope, night.delayed, night.stream_feed), ("alpaca-overnight", "overnight", False, "overnight"))
        t0 = time.time()
        src = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t0 - 1)) + ".000000000Z"
        self.c.apply_trade("equity", {"T": "t", "S": "NVDA", "p": 190.0, "s": 5, "x": "D", "t": src}, self.sip, t0)
        self.c.apply_quote("equity", {"T": "q", "S": "NVDA", "bp": 190.2, "ap": 190.3, "bx": "B", "ax": "B", "t": src}, night, t0 + 0.5)
        v = self.c.view("equity", "NVDA", True, lambda s: True, t0 + 1)
        self.assertEqual(v["stream_feed"], "overnight")  # newest write
        self.assertEqual(v["quote_feed"], "overnight")
        self.assertEqual(v["trade_feed"], "sip")  # last trade still from the day feed until an overnight print
        self.assertEqual(v["feed"], "alpaca-overnight")

    def test_out_of_order_quote_ignored(self):
        self.c.apply_quote("equity", {"S": "SPY", "bp": 2, "ap": 3, "t": "2026-10-07T14:00:01Z"}, self.sip)
        self.c.apply_quote("equity", {"S": "SPY", "bp": 1, "ap": 9, "t": "2026-10-07T14:00:00Z"}, self.sip)
        self.assertEqual(self.c.rows["equity"]["SPY"]["bid"], 2)

    def test_status_variants(self):
        t0 = time.time()
        self.c.apply_quote("option", {"S": "NVDA261016C00190000", "bp": 1, "ap": 1.1, "t": "2026-10-07T14:00:00Z"}, self.opra, t0)
        v = lambda **kw: self.c.view("option", "NVDA261016C00190000", kw.get("conn", True), kw.get("sub", lambda s: True), kw.get("t", t0))
        self.assertEqual(v()["contract_id"], "NVDA261016C00190000")
        self.assertEqual(v()["feed"], "alpaca-opra")
        self.assertEqual(v()["venue_scope"], "OPRA")
        self.assertEqual(v()["feed_status"], "ok")
        self.assertEqual(v(t=t0 + 121)["feed_status"], "stale")
        self.assertEqual(v(conn=False)["feed_status"], "disconnected")
        self.assertEqual(v(sub=lambda s: False)["feed_status"], "unsubscribed")
        self.assertIsNone(self.c.view("option", "NOPE", True, lambda s: True))

    def test_indicative_marked_delayed(self):
        self.assertTrue(feed_meta_for("option", "indicative").delayed)
        self.assertEqual(feed_meta_for("equity", "iex").venue_scope, "iex")

    def test_prune(self):
        self.c.apply_quote("option", {"S": "A", "bp": 1, "ap": 2}, self.opra, 0)
        self.c.apply_quote("option", {"S": "B", "bp": 1, "ap": 2}, self.opra, 0)
        self.assertEqual(self.c.prune("option", {"A"}, 10, t=100), 1)
        self.assertEqual(self.c.symbols("option"), ["A"])


class SubsTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_default_allowlist_is_core20(self):
        fs = FileSubs(APP_DIR / "stream-quote-allowlist.json", "stock")
        self.assertTrue(fs.reload_if_changed())
        self.assertEqual(len(fs.symbols), 20)
        self.assertEqual(fs.symbols[:3], ["SPY", "QQQ", "NVDA"])
        for deferred in ("GOOGL", "SNDK", "CBRS"):
            self.assertNotIn(deferred, fs.symbols)

    def test_options_list_validation_cap_and_bad_json(self):
        p = self.d / "options-subs.json"
        contracts = [f"NVDA261016C{strike:08d}" for strike in range(100000, 100000 + 1005 * 1000, 1000)]
        p.write_text(json.dumps(contracts + ["garbage", "nvda261016p00180000", "NVDA261016C00100000"]))
        fs = FileSubs(p, "option", cap=1000)
        fs.reload_if_changed()
        self.assertEqual(len(fs.symbols), 1000)
        h = fs.health()
        self.assertEqual(h["truncated"], 6)  # 1005 + lowercased valid one = 1006 unique
        self.assertEqual(h["invalid"], ["garbage"])
        # bad JSON keeps previous
        time.sleep(0.01)
        p.write_text("{not json")
        import os
        os.utime(p, (time.time() + 5, time.time() + 5))
        self.assertFalse(fs.reload_if_changed())
        self.assertEqual(len(fs.symbols), 1000)
        self.assertIsNotNone(fs.health()["error"])

    def test_options_dict_form_and_empty(self):
        p = self.d / "o.json"
        p.write_text(json.dumps({"contracts": ["SPY261009P00650000", {"symbol": "O:QQQ261009C00600000"}]}))
        fs = FileSubs(p, "option", cap=1000)
        fs.reload_if_changed()
        self.assertEqual(fs.symbols, ["SPY261009P00650000", "QQQ261009C00600000"])
        p2 = self.d / "empty.json"
        p2.write_text("")
        fs2 = FileSubs(p2, "option", cap=1000)
        fs2.reload_if_changed()
        self.assertEqual(fs2.symbols, [])
        fs3 = FileSubs(self.d / "missing.json", "option", cap=1000)
        fs3.reload_if_changed()
        self.assertEqual(fs3.symbols, [])
        self.assertIsNone(fs3.health()["error"])


class CredentialTests(unittest.TestCase):
    def setUp(self):
        clear_env()
        self.d = Path(tempfile.mkdtemp())

    def test_keys_from_files_and_missing(self):
        self.assertIsNone(load_alpaca_keys(self.d))
        (self.d / "APCA_API_KEY_ID").write_text("AKFILEKEY\n")
        self.assertIsNone(load_alpaca_keys(self.d))
        (self.d / "APCA_API_SECRET_KEY").write_text("  filesecret123 \n")
        self.assertEqual(load_alpaca_keys(self.d), ("AKFILEKEY", "filesecret123"))

    def test_token_check(self):
        ts = TokenStore(self.d)
        self.assertEqual(ts.check("Bearer x"), "unconfigured")
        (self.d / "OID_QUOTE_TOKEN").write_text("tok-123456789\n")
        self.assertEqual(ts.check(None), "missing")
        self.assertEqual(ts.check("Basic abc"), "missing")
        self.assertEqual(ts.check("Bearer wrong"), "invalid")
        self.assertEqual(ts.check("Bearer tok-123456789"), "ok")
        self.assertEqual(ts.check("bearer tok-123456789"), "ok")

    def test_redact_filter(self):
        RedactFilter.add_secret("SUPERSECRETVALUE")
        rec = logging.LogRecord("x", logging.INFO, __file__, 1, "auth with %s", ("SUPERSECRETVALUE",), None)
        RedactFilter().filter(rec)
        self.assertEqual(rec.getMessage(), "auth with [REDACTED]")


if __name__ == "__main__":
    unittest.main()
