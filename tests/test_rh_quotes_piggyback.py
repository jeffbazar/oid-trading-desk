#!/usr/bin/env python3
"""Unit-ish checks for Duplicates #2 rh-quotes piggyback (no RH network calls)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "market-data"))
sys.path.insert(0, str(OID / "dashboard"))

import cache_io  # noqa: E402
from cache_io import extract_rh_quote_map, piggyback_rh_quotes, write_feed  # noqa: E402


class PiggybackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.latest = Path(self._tmpdir.name)
        self._orig = cache_io.LATEST_DIR
        cache_io.LATEST_DIR = self.latest

    def tearDown(self) -> None:
        cache_io.LATEST_DIR = self._orig
        self._tmpdir.cleanup()

    def _write_quotes(self, symbols: dict[str, dict], *, age_s: float = 30.0, writer: str = "refresh_marks.py"):
        as_of = datetime.now(timezone.utc) - timedelta(seconds=age_s)
        payload = {
            "as_of_pt": "test",
            "quotes": symbols,
            "count": len(symbols),
            "source": "test",
        }
        return write_feed(
            "rh-quotes",
            source="test",
            writer=writer,
            symbols=sorted(symbols.keys()),
            payload=payload,
            ttl_seconds=120,
            as_of=as_of,
        )

    def test_extract_nested_quotes(self):
        payload = {
            "quotes": {
                "SPY": {"last": 100.0, "previous_close": 99.0, "bid": 99.9, "ask": 100.1},
                "QQQ": {"last_trade_price": 200.0, "adjusted_previous_close": 198.0},
            },
            "count": 2,
        }
        m = extract_rh_quote_map(payload)
        self.assertEqual(set(m), {"SPY", "QQQ"})
        self.assertEqual(m["SPY"]["last"], 100.0)
        self.assertEqual(m["QQQ"]["prev_close"], 198.0)

    def test_fresh_reuse_no_missing(self):
        self._write_quotes(
            {
                "SPY": {"last": 1.0, "previous_close": 1.0},
                "QQQ": {"last": 2.0, "previous_close": 2.0},
            },
            age_s=10,
        )
        pb = piggyback_rh_quotes(["SPY", "QQQ"], ttl_seconds=120)
        self.assertTrue(pb["fresh"])
        self.assertTrue(pb["reused"])
        self.assertEqual(pb["covered"], ["SPY", "QQQ"])
        self.assertEqual(pb["missing"], [])
        self.assertEqual(pb["writer"], "refresh_marks.py")

    def test_partial_coverage_lists_missing(self):
        self._write_quotes({"SPY": {"last": 1.0, "previous_close": 1.0}}, age_s=5)
        pb = piggyback_rh_quotes(["SPY", "DIA", "RSP"], ttl_seconds=120)
        self.assertTrue(pb["fresh"])
        self.assertEqual(pb["covered"], ["SPY"])
        self.assertEqual(pb["missing"], ["DIA", "RSP"])

    def test_stale_is_miss(self):
        self._write_quotes({"SPY": {"last": 1.0, "previous_close": 1.0}}, age_s=500)
        pb = piggyback_rh_quotes(["SPY"], ttl_seconds=120)
        self.assertFalse(pb["fresh"])
        self.assertEqual(pb["missing"], ["SPY"])
        self.assertEqual(pb["quotes"], {})


if __name__ == "__main__":
    unittest.main()
