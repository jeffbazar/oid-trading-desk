"""vol_surge unit tests (stdlib only; python3.9+). Run: python3 -m unittest discover -s tests"""
import json, sys, tempfile, time, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import oid_triggers as ot


def live_payload(**over):
    row = {"last": 101.0, "px_60s_ago": 99.5, "px_30s_ago": 100.0, "px_10s_ago": 100.8, "rvol_1m": 3.4, "pace_rvol_10s": 5.0,
           "vol_60s": 90000, "vol_10s": 30000, "norm_1m": 26000, "lag_s": 0.2, "last_age_s": 0.4,
           "ref_high_5m": 100.5, "ref_low_5m": 97.0, "day_high": 101.0, "day_low": 97.0, "last_trade_pt": "x"}
    row.update(over.pop("row", {}))
    p = {"rth_slot": 60, "half_day": False, "stream": {"connected": True, "last_data_age_s": 0.3},
         "norms": {"current": True}, "symbols": {"AMD": row}}
    p.update(over)
    return p


class VS(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "desk/market-data/latest").mkdir(parents=True)
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (self.tmp / "desk/market-data/latest/fa-levels.json").write_text(json.dumps(
            {"payload": {"levels": {"AMD": {"call_wall": 100.0, "put_wall": 90.0, "gamma_flip": 95.0, "as_of": now_iso}}}}))
        self.cfg = json.loads((HERE / "config.json").read_text())
        self.vs = ot.VolSurge(self.tmp / "desk", self.tmp, self.cfg, dry=True)
        self.vs.refresh_desk(time.time(), force=True)

    def test_fires_wall_and_day_high_once(self):
        self.assertIsNone(self.vs.check(live_payload()))
        lv = sorted(e["details"]["level"] for e in self.vs.events)
        self.assertEqual(lv, ["call_wall", "day_high"])
        self.assertTrue(all(e["dry_run"] for e in self.vs.events))
        self.vs.events = []
        self.vs.check(live_payload())
        self.assertEqual(self.vs.events, [])  # deduped

    def test_gates(self):
        self.assertEqual(self.vs.check(live_payload(rth_slot=1)), "open_skip")
        self.assertEqual(self.vs.check(live_payload(rth_slot=-1)), "off_rth")
        self.assertEqual(self.vs.check(live_payload(half_day=True)), "half_day")
        self.assertEqual(self.vs.check(live_payload(stream={"connected": True, "last_data_age_s": 9})), "stream_stale")
        self.assertEqual(self.vs.check(live_payload(norms={"current": False})), "norms_not_current")
        self.vs.check(live_payload(row={"rvol_1m": 2.5}))
        self.vs.check(live_payload(row={"vol_60s": 1000}))
        self.vs.check(live_payload(row={"lag_s": 6.0}))
        self.vs.check(live_payload(row={"last": 100.01}))  # inside the 2 bps buffer, not above day-high ref
        self.assertEqual(self.vs.events, [])

    def test_thin_name_floor(self):
        # 3,000 shares in 60 s: below the 20k default; fires when the name's median minute norm is ~800 (floor 2,000)
        self.vs.check(live_payload(row={"vol_60s": 3000, "norm_1m": 800}))
        self.assertEqual(self.vs.events, [])
        self.vs.check(live_payload(row={"vol_60s": 3000, "norm_1m": 800, "norm_median_1m": 800}))
        self.assertIn("day_high", [e["details"]["level"] for e in self.vs.events])
        self.vs.events = []; self.vs.st["fired"] = {}
        self.vs.check(live_payload(row={"vol_60s": 1500, "norm_1m": 400, "norm_median_1m": 400}))
        self.assertEqual(self.vs.events, [])  # never below min_shares_floor_low

    def test_down_break_and_stale_walls(self):
        old = "2026-01-01T00:00:00Z"
        (self.tmp / "desk/market-data/latest/fa-levels.json").write_text(json.dumps(
            {"payload": {"levels": {"AMD": {"call_wall": 100.0, "put_wall": 96.0, "gamma_flip": 95.0, "as_of": old}}}}))
        self.vs.refresh_desk(time.time(), force=True)
        self.vs.check(live_payload(row={"last": 96.5, "px_60s_ago": 98.0, "ref_low_5m": 97.0}))
        self.assertEqual([e["details"]["level"] for e in self.vs.events], ["day_low"])  # stale walls ignored

    def test_flush_dry_never_posts(self):
        self.vs.check(live_payload())
        called = []
        orig = ot.send
        ot.send = lambda *a, **k: called.append(1)
        try:
            n, st = ot.vol_surge_flush(self.vs, self.tmp, str(self.tmp / "nope.env"), True, ot.vs_cfg(self.cfg))
        finally:
            ot.send = orig
        self.assertEqual((n, st, called), (2, None, []))
        rows = [json.loads(x) for x in (self.tmp / "events.jsonl").read_text().splitlines()]
        self.assertTrue(all(r["dry_run"] and r["event_type"] == "vol_surge" for r in rows))

    def test_live_flag_requires_global_live(self):
        cfg = dict(self.cfg); cfg["vol_surge"] = dict(cfg["vol_surge"], live=True)
        self.vs.cfg = cfg
        self.vs.check(live_payload())
        n, st = ot.vol_surge_flush(self.vs, self.tmp, str(self.tmp / "nope.env"), False, ot.vs_cfg(cfg))
        self.assertIsNone(st)  # global dry -> no post attempt
        self.vs.events = [{"event_type": "vol_surge", "symbol": "AMD", "seat_id": None, "details": {}, "data_stamp": None}]
        n, st = ot.vol_surge_flush(self.vs, self.tmp, str(self.tmp / "nope.env"), True, ot.vs_cfg(cfg))
        self.assertTrue(str(st).startswith("not_sent:"))  # would post; env missing

    def _env(self):
        e = self.tmp / "wh.env"
        e.write_text("OID_WEBHOOK_URL=http://example.invalid/hook\nOID_WEBHOOK_KEY=dummy\n"); e.chmod(0o600)
        return str(e)

    def test_notify_dry_payload_cap_dedupe(self):
        cfg = dict(self.cfg); cfg["vol_surge"] = dict(cfg["vol_surge"], live=False, notify_dry=True, notify_max_per_day=2, notify_dedupe_min=5)
        self.vs.cfg = cfg; vc = ot.vs_cfg(cfg); env = self._env()
        sent = []
        orig = ot.send
        ot.send = lambda body, env, timeout=15: sent.append(body) or 200
        try:
            t0 = 1_800_000_000.0
            mk = lambda sym, d="up": {"event_type": "vol_surge", "symbol": sym, "seat_id": None, "engine_pt": "x", "data_stamp": "y",
                                      "details": {"dir": d, "rvol_1m": 3.4, "last": 101.0, "level": "day_high", "level_price": 100.5}}
            r = ot.vol_surge_notify(self.vs, self.tmp, env, vc, [mk("AMD"), mk("AMD")], now=t0, sync=True)
            self.assertEqual(r, {0: 200, 1: "same_tick"})
            r = ot.vol_surge_notify(self.vs, self.tmp, env, vc, [mk("AMD")], now=t0 + 120, sync=True)
            self.assertEqual(r, {0: "dedupe"})
            r = ot.vol_surge_notify(self.vs, self.tmp, env, vc, [mk("NVDA", "down")], now=t0 + 130, sync=True)
            self.assertEqual(r, {0: 200})
            r = ot.vol_surge_notify(self.vs, self.tmp, env, vc, [mk("META")], now=t0 + 400, sync=True)
            self.assertEqual(r, {0: "cap"})
        finally:
            ot.send = orig
        b = sent[1]
        self.assertEqual((b["event_type"], b["ticker"], b["direction"], b["rvol"], b["price"], b["dry_run"], b["trade_action"], b["test"]),
                         ("vol_surge", "NVDA", "down", 3.4, 101.0, True, "none", False))
        self.assertNotIn("dummy", json.dumps(sent) + (self.tmp / "notify.jsonl").read_text())

    def test_notify_off_and_live_unchanged(self):
        sent = []
        orig = ot.send
        ot.send = lambda body, env, timeout=15: sent.append(body) or 200
        try:
            cfg = dict(self.cfg); cfg["vol_surge"] = dict(cfg["vol_surge"], live=False, notify_dry=False)
            self.vs.cfg = cfg; self.vs.check(live_payload())
            n, st = ot.vol_surge_flush(self.vs, self.tmp, self._env(), True, ot.vs_cfg(cfg))
            self.assertEqual((n, st, sent), (2, None, []))  # notify off -> dry never posts (old behaviour)
            cfg["vol_surge"] = dict(cfg["vol_surge"], notify_dry=True)
            self.vs.cfg = cfg; self.vs.st["fired"] = {}; self.vs.check(live_payload())
            n, st = ot.vol_surge_flush(self.vs, self.tmp, self._env(), True, ot.vs_cfg(cfg))
            time.sleep(0.3)
            self.assertEqual((n, st, len(sent)), (2, None, 1))  # one post per ticker per tick; status None (not a live send)
            rows = [json.loads(x) for x in (self.tmp / "events.jsonl").read_text().splitlines()][-2:]
            self.assertTrue(all(r["dry_run"] and "sent_status" not in r for r in rows))
            self.assertEqual(sorted(r["notify_status"] for r in rows), ["queued", "same_tick"])
        finally:
            ot.send = orig


if __name__ == "__main__":
    unittest.main()
