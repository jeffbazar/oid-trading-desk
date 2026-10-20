import hashlib
import json
import threading
import urllib.error
import urllib.request

from oid_desk import api

from .base import MiniCase


class ApiTest(MiniCase):
    def setUp(self):
        super().setUp()
        self.secret("OID_QUOTE_TOKEN", "readtok")
        self.secret("OID_DESK_WRITE_TOKEN", "writetok")
        self.put("market-data/latest/uw-net-prem.json", {"as_of": "2026-10-12T14:00:00Z", "payload": {"x": 1}})
        self.put("chart-bot/whale-flow/latest/summary.json", {"generated_pt": "now"})
        self.put("market-data/latest/fa-focus-levels.json", {"levels": {"NVDA": {"call_wall": 230}}})
        self.put("market-data/latest/secret-ish.json", {"not": "in catalog"})
        self.httpd = api.serve("127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def req(self, path, tok=None, data=None):
        h = {"Authorization": f"Bearer {tok}"} if tok else {}
        if data is not None:
            data = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=h, data=data,
                                   method="POST" if data is not None else "GET")
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with op.open(r, timeout=5) as fh:
                return fh.status, fh.read(), dict(fh.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_health_open_and_no_secret_values(self):
        code, body, _ = self.req("/v1/health")
        self.assertEqual(code, 200)
        self.assertNotIn(b"readtok", body)
        self.assertNotIn(b"writetok", body)
        self.assertTrue(json.loads(body)["keys_present"]["OID_QUOTE_TOKEN"])

    def test_auth_required(self):
        self.assertEqual(self.req("/v1/feeds")[0], 401)
        self.assertEqual(self.req("/v1/feeds", "wrong")[0], 401)
        self.assertEqual(self.req("/v1/feeds", "writetok")[0], 401)  # write token is not a read token

    def test_manifest_and_feed_sha(self):
        code, body, _ = self.req("/v1/feeds", "readtok")
        feeds = {f["name"]: f for f in json.loads(body)["feeds"]}
        self.assertIn("market-data/latest/uw-net-prem.json", feeds)
        self.assertIn("chart-bot/whale-flow/latest/summary.json", feeds)
        self.assertNotIn("market-data/latest/secret-ish.json", feeds)
        self.assertEqual(feeds["market-data/latest/uw-net-prem.json"]["as_of"], "2026-10-12T14:00:00Z")
        code, raw, hdr = self.req("/v1/feed?name=market-data/latest/uw-net-prem.json", "readtok")
        self.assertEqual(code, 200)
        self.assertEqual(hdr["X-OID-SHA256"], hashlib.sha256(raw).hexdigest())
        code, _, _ = self.req("/v1/feeds?group=fa", "readtok")
        self.assertEqual(code, 200)

    def test_feed_not_in_catalog_or_traversal(self):
        for n in ("market-data/latest/secret-ish.json", "../secrets/OID_QUOTE_TOKEN", "/etc/passwd"):
            self.assertEqual(self.req(f"/v1/feed?name={n}", "readtok")[0], 404)

    def test_group_route(self):
        code, body, _ = self.req("/v1/walls", "readtok")
        self.assertEqual(json.loads(body)["files"]["market-data/latest/fa-focus-levels.json"]["levels"]["NVDA"]["call_wall"], 230)

    def test_desk_state_write_with_override(self):
        (self.root / "overrides" / "focus-watch.json").write_text(json.dumps({"fa_refresh": {"daily_budget": 250}}))
        files = {"paper-trades/trades.json": {"trades": [1]},
                 "config/focus-watch.json": {"fa_refresh": {"daily_budget": 900, "interval_min": 5}},
                 "config/evil.json": {"x": 1}}
        self.assertEqual(self.req("/v1/desk-state", "readtok", {"files": files})[0], 401)
        code, body, _ = self.req("/v1/desk-state", "writetok", {"files": files})
        self.assertEqual(code, 207)
        res = json.loads(body)
        self.assertEqual(res["rejected"], {"config/evil.json": "not_allowed"})
        fw = json.loads((self.desk / "config" / "focus-watch.json").read_text())
        self.assertEqual(fw["fa_refresh"], {"daily_budget": 250, "interval_min": 5})
        self.assertFalse((self.desk / "config" / "evil.json").exists())

    def test_token_handoff_once(self):
        self.assertEqual(self.req("/v1/desk-write-token", "readtok")[0], 404)
        import time
        from oid_desk import util
        util.atomic_write_json(self.root / "state" / "token-handoff.json", {"expires_epoch": time.time() + 60})
        code, body, _ = self.req("/v1/desk-write-token", "readtok")
        self.assertEqual((code, json.loads(body)["value"]), (200, "writetok"))
        self.assertEqual(self.req("/v1/desk-write-token", "readtok")[0], 404)
