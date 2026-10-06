"""Rh-quotes piggyback: Rose writes, tape and support-map only read."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "market-data"))

import cache_io
from dashboard import (
    docs_pages,
    live_refresh,
    rebuild,
    refresh_marks,
    refresh_market_tape,
    refresh_support_map,
    support_notify_diff,
)

NOW = datetime(2026, 10, 5, 20, 43, tzinfo=timezone.utc)
LATER = NOW + timedelta(seconds=30)
STALE = NOW + timedelta(seconds=121)


def _quote(symbol, last, previous):
    return {
        "symbol": symbol,
        "last_trade_price": str(last),
        "previous_close": str(previous),
    }


class ExtractTests(unittest.TestCase):
    def test_envelope_list_and_double_wrap(self):
        envelope = {
            "feed": "rh-quotes",
            "writer": "refresh_marks.py",
            "ttl_seconds": 120,
            "payload": {"quotes": {"nvda": _quote("nvda", "237.5", "230")}},
        }
        mapped = cache_io.extract_rh_quote_map(envelope)
        self.assertAlmostEqual(mapped["NVDA"]["last"], 237.5)
        self.assertAlmostEqual(mapped["NVDA"]["day_pct"], (237.5 - 230) / 230 * 100)

        as_list = cache_io.extract_rh_quote_map([_quote("spy", "1.5", "1.0")])
        self.assertEqual(set(as_list), {"SPY"})

        wrapped = {"payload": {"quotes": {"results": [_quote("DIA", "512", "510")]}}}
        self.assertAlmostEqual(cache_io.extract_rh_quote_map(wrapped)["DIA"]["last"], 512)

    def test_strips_secret_keys(self):
        mapped = cache_io.extract_rh_quote_map({
            "symbol": "SPY",
            "last_trade_price": "1",
            "access_token": "sekrit-token-value",
            "password": "nope",
        })
        self.assertNotIn("access_token", mapped["SPY"])
        self.assertNotIn("sekrit-token-value", json.dumps(mapped))


class PiggybackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, quotes, *, now=NOW, error=None, ttl=120):
        return cache_io.write_feed(
            "rh-quotes",
            {"quotes": quotes},
            writer="refresh_marks.py",
            owner="rose",
            ttl_seconds=ttl,
            source="fixture",
            error=error,
            root=self.root,
            now=now,
        )

    def test_fresh_partial_and_refuses_other_writers(self):
        self._write({"SPY": _quote("SPY", "500", "490"), "QQQ": _quote("QQQ", "400", "390")})
        hit = cache_io.piggyback_rh_quotes(["spy", "DIA"], root=self.root, now=LATER)
        self.assertTrue(hit["fresh"])
        self.assertEqual(hit["covered"], ["SPY"])
        self.assertEqual(hit["missing"], ["DIA"])
        self.assertFalse(hit["rh_quotes_write"])
        self.assertIsNone(cache_io.read_fresh("rh-quotes", ttl=120, root=self.root, now=STALE))
        stale = cache_io.piggyback_rh_quotes(["SPY"], root=self.root, now=STALE)
        self.assertEqual(stale["reason"], "stale")
        self.assertEqual(stale["quotes"], {})

        self._write({"SPY": _quote("SPY", "1", "1")}, error="vendor down")
        erred = cache_io.piggyback_rh_quotes(["SPY"], root=self.root, now=LATER)
        self.assertEqual(erred["reason"], "error")
        self.assertFalse(cache_io.is_fresh(cache_io.read_record("rh-quotes", root=self.root), ttl=120, now=LATER))

        with self.assertRaises(PermissionError):
            cache_io.write_feed(
                "rh-quotes",
                {"quotes": {}},
                writer="refresh_market_tape.py",
                owner="rose",
                root=self.root,
                now=NOW,
            )

    def test_miss_when_file_absent(self):
        missed = cache_io.piggyback_rh_quotes(["SPY"], root=self.root, now=NOW)
        self.assertEqual(missed["reason"], "miss")
        self.assertEqual(missed["missing"], ["SPY"])


class MarketTapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        cache_io.write_feed(
            "rh-quotes",
            {"quotes": {"SPY": _quote("SPY", "100", "90"), "QQQ": _quote("QQQ", "50", "40")}},
            writer="refresh_marks.py",
            owner="rose",
            ttl_seconds=120,
            source="fixture",
            root=self.root,
            now=NOW,
        )
        self.quotes_path = Path(self.root) / "misses.json"
        self.quotes_path.write_text(json.dumps({
            "results": [
                _quote("SPY", "999", "90"),
                _quote("DIA", "512", "510"),
            ]
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _rh_bytes(self):
        return (Path(self.root) / "market-data" / "latest" / "rh-quotes.json").read_bytes()

    def test_file_fills_misses_and_does_not_override_or_write_rh(self):
        before = self._rh_bytes()
        payload = refresh_market_tape.run(
            root=self.root,
            now=LATER,
            equity_quotes_file=self.quotes_path,
            dry_run=True,
        )
        self.assertEqual(self._rh_bytes(), before)
        by_symbol = {row["symbol"]: row for row in payload["strip"]}
        self.assertEqual(by_symbol["SPY"]["from"], "rh-quotes")
        self.assertAlmostEqual(by_symbol["SPY"]["last"], 100)
        self.assertEqual(by_symbol["DIA"]["from"], "equity-quotes-file")
        self.assertAlmostEqual(by_symbol["DIA"]["last"], 512)
        self.assertIn("RSP", payload["missing"])
        self.assertFalse(payload["written"])
        self.assertFalse((Path(self.root) / "market-data" / "latest" / "market-tape.json").exists())

    def test_check_piggyback_cli_writes_nothing(self):
        cache_io.write_feed(
            "rh-quotes",
            {"quotes": {"SPY": _quote("SPY", "100", "90"), "QQQ": _quote("QQQ", "50", "40")}},
            writer="refresh_marks.py",
            owner="rose",
            ttl_seconds=120,
            source="fixture",
            root=self.root,
            now=datetime.now(timezone.utc),
        )
        before = self._rh_bytes()
        script = ROOT / "dashboard" / "refresh_market_tape.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--check-piggyback", "--root", self.root],
            check=True,
            capture_output=True,
            text=True,
        )
        body = json.loads(completed.stdout)
        self.assertTrue(body["ok"])
        self.assertIn("SPY", body["covered"])
        self.assertIn("DIA", body["missing"])
        self.assertFalse(body["rh_quotes_write"])
        self.assertEqual(self._rh_bytes(), before)
        self.assertFalse((Path(self.root) / "market-data" / "latest" / "market-tape.json").exists())

    def test_default_writes_tape_only(self):
        before = self._rh_bytes()
        payload = refresh_market_tape.run(root=self.root, now=LATER, write=True)
        self.assertTrue(payload["written"])
        self.assertEqual(self._rh_bytes(), before)
        tape = cache_io.read_record("market-tape", root=self.root)
        self.assertEqual(tape["writer"], "refresh_market_tape.py")
        self.assertEqual(tape["feed"], "market-tape")
        self.assertNotEqual(tape["feed"], "rh-quotes")


class SupportMapTests(unittest.TestCase):
    def test_book_is_the_union_and_distance_uses_cache(self):
        self.assertEqual(len(refresh_support_map.SUPPORT_SYMBOLS), 37)
        self.assertFalse(set(refresh_support_map.PRIMARY_SUPPORT) & set(refresh_support_map.EXTENDED_SUPPORT))
        self.assertIn("NVDA", refresh_support_map.PRIMARY_SUPPORT)

        with tempfile.TemporaryDirectory() as root:
            cache_io.write_feed(
                "rh-quotes",
                {"quotes": {"NVDA": _quote("NVDA", "235", "230")}},
                writer="refresh_marks.py",
                owner="rose",
                ttl_seconds=120,
                source="fixture",
                root=root,
                now=NOW,
            )
            walls = Path(root) / "walls.json"
            walls.write_text(json.dumps({"NVDA": {"put_wall": 230, "call_wall": 240}}), encoding="utf-8")
            misses = Path(root) / "misses.json"
            misses.write_text(json.dumps([_quote("NVDA", "1", "1"), _quote("SPY", "500", "490")]), encoding="utf-8")
            before = (Path(root) / "market-data" / "latest" / "rh-quotes.json").read_bytes()
            payload = refresh_support_map.run(
                root=root,
                now=LATER,
                equity_quotes_file=misses,
                walls_file=walls,
                dry_run=True,
            )
            self.assertEqual((Path(root) / "market-data" / "latest" / "rh-quotes.json").read_bytes(), before)
            nvda = next(row for row in payload["rows"] if row["symbol"] == "NVDA")
            spy = next(row for row in payload["rows"] if row["symbol"] == "SPY")
            self.assertEqual(nvda["book"], "primary")
            self.assertEqual(nvda["quote_from"], "rh-quotes")
            self.assertAlmostEqual(nvda["last"], 235)
            self.assertAlmostEqual(nvda["distance"], (235 - 230) / 230)
            self.assertFalse(nvda["elevate"])
            self.assertEqual(spy["quote_from"], "equity-quotes-file")
            self.assertTrue(payload["rh_quotes_write"] is False)


class MarksUnwrapTests(unittest.TestCase):
    def test_unwrap_and_sole_writer_envelope(self):
        raw = {"payload": {"quotes": {"results": [_quote("qqq", "10", "8")]}}}
        raw["access_token"] = "sekrit-token-value"
        self.assertEqual(set(refresh_marks.unwrap_equity_quotes(raw)), {"QQQ"})
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "quotes.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            record = refresh_marks.write_from_file(path, root=root, now=NOW)
            self.assertEqual(record["writer"], "refresh_marks.py")
            self.assertEqual(record["owner"], "rose")
            self.assertEqual(record["ttl_seconds"], 120)
            self.assertEqual(record["feed"], "rh-quotes")
            self.assertIn("QQQ", record["payload"]["quotes"])
            text = (Path(root) / "market-data" / "latest" / "rh-quotes.json").read_text(encoding="utf-8")
            self.assertNotIn("sekrit-token-value", text)
            self.assertTrue(cache_io.is_fresh(record, ttl=120, now=LATER))

            empty = Path(root) / "empty.json"
            empty.write_text("{}", encoding="utf-8")
            erred = refresh_marks.write_from_file(empty, root=root, now=NOW)
            self.assertEqual(erred["error"], "empty equity quotes file")
            self.assertFalse(cache_io.is_fresh(erred, ttl=120, now=LATER))


class LiveRefreshTests(unittest.TestCase):
    def test_tape_is_first_and_publish_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            cache_io.write_feed(
                "rh-quotes",
                {"quotes": {"SPY": _quote("SPY", "1", "1")}},
                writer="refresh_marks.py",
                owner="rose",
                ttl_seconds=120,
                source="fixture",
                root=root,
                now=NOW,
            )
            before = (Path(root) / "market-data" / "latest" / "rh-quotes.json").read_bytes()
            result = live_refresh.run_cache_first(root=root, now=LATER, with_support=True, write=True)
            self.assertEqual(result["steps"][0], "market-tape-piggyback")
            self.assertIn("support-map-piggyback", result["steps"])
            self.assertEqual(result["quote_pulls"], [])
            self.assertFalse(result["rh_quotes_written"])
            self.assertFalse(result["published"])
            self.assertEqual((Path(root) / "market-data" / "latest" / "rh-quotes.json").read_bytes(), before)
            self.assertTrue((Path(root) / "market-data" / "latest" / "market-tape.json").is_file())
            self.assertTrue((Path(root) / "market-data" / "latest" / "support-map.json").is_file())
            with self.assertRaises(RuntimeError):
                live_refresh.run_cache_first(root=root, publish=True)


class NotifyDiffTests(unittest.TestCase):
    def test_cross_under_and_no_rh_write(self):
        previous = {"rows": [{"symbol": "NVDA", "distance": 0.02, "put_wall": 230, "last": 234.6}]}
        current = {"rows": [{"symbol": "NVDA", "distance": -0.01, "put_wall": 230, "last": 227.7}]}
        events = support_notify_diff.diff_support(previous, current)
        self.assertEqual(events[0]["kind"], "crossed_under")
        self.assertFalse(events[0]["elevate"])
        text = support_notify_diff.format_notify(events)
        self.assertIn("NVDA", text)
        self.assertIn("Zero RH execution", text)
        self.assertEqual(support_notify_diff.diff_support({}, current)[0]["kind"], "baseline")

        with tempfile.TemporaryDirectory() as root:
            current_path = Path(root) / "current.json"
            previous_path = Path(root) / "previous.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            previous_path.write_text(json.dumps(previous), encoding="utf-8")
            result = support_notify_diff.run(previous_path, current_path, write_notify=True, root=root)
            self.assertFalse(result["rh_quotes_write"])
            self.assertFalse((Path(root) / "market-data" / "latest" / "rh-quotes.json").exists())
            self.assertTrue((Path(root) / "market-data" / "latest" / "support-map-notify.txt").is_file())


class DocsNavTests(unittest.TestCase):
    def test_architecture_and_setup_nav(self):
        nav = docs_pages.nav_html("architecture.html")
        self.assertIn('class="active" href="architecture.html"', nav)
        self.assertIn('href="setup.html"', nav)
        self.assertIn("Blotter", nav)
        injected = docs_pages.inject_nav('<body><div class="tabs"><a href="old.html">Old</a></div></body>', "setup.html")
        self.assertIn('class="active" href="setup.html"', injected)
        self.assertNotIn("old.html", injected)
        with tempfile.TemporaryDirectory() as out:
            result = rebuild.rebuild(out, root=ROOT, built_at="2026-10-05 5:43 PM PT")
            self.assertFalse(result["published"])
            self.assertIn("architecture.html", result["nav"])
            self.assertIn("setup.html", result["nav"])
            architecture = Path(result["architecture"]).read_text(encoding="utf-8")
            setup = Path(result["setup"]).read_text(encoding="utf-8")
            self.assertIn("piggyback_rh_quotes", architecture)
            self.assertIn("Cutover status", architecture)
            self.assertIn('class="active" href="architecture.html"', architecture)
            self.assertIn("Setup vs production", setup)
            self.assertIn("bold-tulip", setup)
            self.assertIn('class="active" href="setup.html"', setup)


class GitignoreTests(unittest.TestCase):
    def test_blocks_vendor_and_secrets(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            "market-data/latest/",
            "supply-chain.db",
            "secrets/",
            "tmp/",
            "paper-trades/",
            "oid-cutover-backup",
        ):
            self.assertIn(pattern, text)


class NoBrokerageTests(unittest.TestCase):
    def test_dashboard_modules_do_not_import_network_or_order_tools(self):
        banned_modules = {"urllib", "requests", "httpx", "socket", "subprocess"}
        banned_calls = {
            "place_equity_order",
            "place_option_order",
            "place_crypto_order",
            "cancel_equity_order",
            "cancel_option_order",
            "exercise_option",
            "get_equity_quotes",
        }
        dashboard = ROOT / "dashboard"
        for path in dashboard.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            calls = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
            self.assertFalse(imported & banned_modules, path.name)
            self.assertFalse(calls & banned_calls, path.name)


if __name__ == "__main__":
    unittest.main()
