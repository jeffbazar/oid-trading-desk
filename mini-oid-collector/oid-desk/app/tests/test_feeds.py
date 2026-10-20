import io
import json
import time
import urllib.request
from datetime import datetime, timedelta

from oid_desk import edgar_form4, macro_public, marks, net, util, vix

from .base import MiniCase


def fake_opener(routes):
    def op(req: urllib.request.Request, timeout: float) -> bytes:
        for frag, body in routes.items():
            if frag in req.full_url:
                if isinstance(body, Exception):
                    raise body
                return body if isinstance(body, bytes) else json.dumps(body).encode()
        raise OSError("no route " + req.full_url)
    return op


class MarksTest(MiniCase):
    def test_mini_fresh_wins_snapshot_fills_prevclose_premarket(self):
        mini = {"quotes": {"NVDA": {"fresh": True, "last": 231.0, "bid": 230.9, "ask": 231.1, "trade_time": "t1"},
                           "AMD": {"fresh": False, "last": 1.0}}}
        snaps = {"NVDA": {"prevDailyBar": {"c": 228.0, "t": "2026-10-08T04:00:00Z"},
                          "dailyBar": {"c": 229.5, "t": "2026-10-09T04:00:00Z"}},
                 "AMD": {"latestTrade": {"p": 150.0, "t": "t2"}, "latestQuote": {"bp": 149.9, "ap": 150.1},
                         "prevDailyBar": {"c": 148.0, "t": "2026-10-09T04:00:00Z"},
                         "dailyBar": {"c": 151.0, "t": "2026-10-12T04:00:00Z"}}}
        out, counts = marks.build_equity_payload(["NVDA", "AMD", "ZZZ"], mini, snaps, today_et="2026-10-12")
        self.assertEqual(counts, {"mini": 1, "snapshot": 1, "missing": 1})
        self.assertEqual(out["NVDA"]["last_trade_price"], 231.0)
        self.assertEqual(out["NVDA"]["adjusted_previous_close"], 229.5)  # premarket: dailyBar is prior session
        self.assertEqual(out["AMD"]["adjusted_previous_close"], 148.0)   # in session: prevDailyBar
        self.assertEqual(out["AMD"]["bid_price"], 149.9)

    def test_payload_is_accepted_by_desk_normalizer(self):
        import sys
        from pathlib import Path
        desk_dash = Path(__file__).resolve().parents[2] / "dashboard"
        if not (desk_dash / "refresh_marks.py").exists():
            desk_dash = Path(__file__).resolve().parents[2] / "desk" / "dashboard"
        if not (desk_dash / "refresh_marks.py").exists():
            self.skipTest("desk tree not adjacent")
        sys.path.insert(0, str(desk_dash))
        sys.path.insert(0, str(desk_dash.parent / "market-data"))
        sys.path.insert(0, str(desk_dash.parent / "paper-trades"))
        sys.path.insert(0, str(desk_dash.parent / "quotes"))
        import refresh_marks
        out, _ = marks.build_equity_payload(["AMD"], {}, {"AMD": {"latestTrade": {"p": 150.0, "t": "2026-10-12T14:00:00Z"},
                                                               "latestQuote": {"bp": 149.9, "ap": 150.1},
                                                               "prevDailyBar": {"c": 148.0, "t": "2026-10-09T04:00:00Z"},
                                                               "dailyBar": {"c": 151.0, "t": "2026-10-12T04:00:00Z"}}},
                                            today_et="2026-10-12")
        n = refresh_marks.normalize_equity_quotes(out)
        self.assertEqual(n["AMD"]["last"], 150.0)
        self.assertEqual(n["AMD"]["prev_close"], 148.0)
        self.assertEqual(n["AMD"]["bid"], 149.9)


class VixTest(MiniCase):
    def test_agent_rh_default_then_fred_fallback(self):
        util.write_feed("vix-agent", source="rh", writer="t", symbols=["VIX"], payload={"value": 19.5, "prev_close": 18.0},
                        ttl_seconds=600)
        r = vix.get_vix({"source": "agent_rh", "fallbacks": ["fred"], "agent_max_age_s": 5400})
        self.assertEqual((r["provider"], r["value"], r["fallback_used"]), ("agent_rh", 19.5, False))
        (self.desk / "market-data" / "latest" / "vix-agent.json").unlink()
        net.set_opener(fake_opener({"VIXCLS": b"observation_date,VIXCLS\n2026-10-08,17.1\n2026-10-09,18.2\n"}))
        r = vix.get_vix({"source": "agent_rh", "fallbacks": ["fred"]})
        self.assertEqual((r["provider"], r["value"], r["prev_close"], r["fallback_used"]), ("fred", 18.2, 17.1, True))
        net.set_opener(fake_opener({"cdn.cboe.com": {"data": {"current_price": 20.1, "prev_day_close": 19.0}}}))
        r = vix.get_vix({"source": "cboe_delayed", "fallbacks": []})
        self.assertEqual((r["provider"], r["value"]), ("cboe_delayed", 20.1))
        net.set_opener(fake_opener({}))
        r = vix.get_vix({"source": "agent_rh", "fallbacks": ["fred"]})
        self.assertIsNone(r["value"])
        self.assertEqual(set(r["errors"]), {"agent_rh", "fred"})


class MacroTest(MiniCase):
    def test_fred_and_eia_skip(self):
        net.set_opener(fake_opener({"BAMLH0A0HYM2": b"d,v\n2026-10-08,2.90\n2026-10-09,2.95\n",
                                    "DGS10": b"d,v\n2026-10-08,4.10\n2026-10-09,.\n"}))
        f = macro_public.fred_block({"hy_oas": "BAMLH0A0HYM2", "us10y": "DGS10", "wti_spot": "DCOILWTICO"})
        self.assertEqual(f["hy_oas"]["value"], 2.95)
        self.assertEqual(f["hy_oas"]["chg"], 0.05)
        self.assertEqual(f["us10y"]["value"], 4.10)  # '.' (holiday) rows skipped
        self.assertIn("error", f["wti_spot"])
        self.assertEqual(macro_public.eia_block({"x": "WCESTUS1"}), {"skipped": "no EIA_API_KEY on the mini"})
        self.secret("EIA_API_KEY", "k")
        net.set_opener(fake_opener({"api.eia.gov": {"response": {"data": [{"period": "2026-10-02", "value": "420000", "units": "MBBL"},
                                                                          {"period": "2026-09-25", "value": "421500"}]}}}))
        e = macro_public.eia_block({"crude": "WCESTUS1"})
        self.assertEqual(e["crude"]["chg"], -1500.0)


class EdgarTest(MiniCase):
    def test_user_agent_required(self):
        with self.assertRaises(RuntimeError):
            edgar_form4.user_agent({"sec_user_agent": "OID desk research SET-ME@example.com"})
        self.assertEqual(edgar_form4.user_agent({"sec_user_agent": "OID research a@b.com"}), "OID research a@b.com")

    def test_recent_filings_filter(self):
        sub = {"cik": "1045810", "filings": {"recent": {
            "form": ["4", "8-K", "4", "10-Q"], "filingDate": ["2026-10-09", "2026-10-08", "2026-09-01", "2026-10-09"],
            "accessionNumber": ["0001-26-1", "0001-26-2", "0001-26-3", "0001-26-4"],
            "primaryDocument": ["x.xml", "y.htm", "z.xml", "q.htm"], "acceptanceDateTime": ["a", "b", "c", "d"],
            "items": ["", "2.02", "", ""]}}}
        f = edgar_form4.recent_filings(sub, {"4", "8-K"}, "2026-10-07")
        self.assertEqual([x["form"] for x in f], ["4", "8-K"])
        self.assertEqual(f[1]["items"], "2.02")
        self.assertTrue(f[0]["url"].startswith("https://www.sec.gov/Archives/edgar/data/1045810/0001261/"))

    def test_run_with_fake_sec(self):
        net.set_opener(fake_opener({"company_tickers": {"0": {"ticker": "NVDA", "cik_str": 1045810}},
                                    "CIK0001045810": {"cik": "1045810", "filings": {"recent": {
                                        "form": ["4"], "filingDate": [datetime.now(util.ET).strftime("%Y-%m-%d")],
                                        "accessionNumber": ["0001-26-9"], "primaryDocument": ["f.xml"]}}}}))
        p = edgar_form4.run({"sec_user_agent": "t a@b.com", "forms": ["4"], "universe_extra": ["NVDA", "SPY", "FAKE"]})
        self.assertEqual(p["counts"]["form4"], 1)
        self.assertIn("FAKE", p["no_cik"])
        self.assertNotIn("SPY", p["symbols"])

    def test_due_slots(self):
        cfg = {"due_et": ["08:15"]}
        mon = datetime(2026, 10, 12, 8, 20, tzinfo=util.ET)
        self.assertTrue(edgar_form4.due(cfg, mon))
        self.assertFalse(edgar_form4.due(cfg, mon.replace(hour=10)))
        self.assertFalse(edgar_form4.due(cfg, mon - timedelta(days=2)))  # Saturday
        util.write_feed("premarket-edgar-mini", source="s", writer="w", symbols=[], payload={"slot": "2026-10-12 08:15"},
                        ttl_seconds=1)
        self.assertFalse(edgar_form4.due(cfg, mon))
