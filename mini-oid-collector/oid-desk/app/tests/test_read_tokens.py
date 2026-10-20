import io
import json
import os
import stat
import time
from contextlib import redirect_stdout

from oid_desk import ctl, tokens, util

from .test_api import ApiTest


class ReadTokenTest(ApiTest):
    def setUp(self):
        super().setUp()
        self._whois = tokens._WHOIS
        self.peer = "100.111.60.56"
        tokens._WHOIS = lambda port: self.peer  # loopback test client = this tailnet peer

    def tearDown(self):
        tokens._WHOIS = self._whois
        super().tearDown()

    def named(self, name="research-mini"):
        tokens.add(name)
        return (self.secrets / "read-tokens" / name).read_text().strip()

    def test_named_token_get_only(self):
        tok = self.named()
        mode = stat.S_IMODE(os.stat(self.secrets / "read-tokens" / "research-mini").st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(self.req("/v1/feeds", tok)[0], 200)
        self.assertEqual(self.req("/v1/feed?name=market-data/latest/uw-net-prem.json", tok)[0], 200)
        self.assertEqual(self.req("/v1/walls", tok)[0], 200)
        # write paths refuse it
        self.assertEqual(self.req("/v1/desk-state", tok, {"files": {"paper-trades/trades.json": {}}})[0], 401)
        self.assertFalse((self.desk / "paper-trades" / "trades.json").exists())
        # privileged GETs refuse it (even when armed)
        util.atomic_write_json(self.root / "state" / "token-handoff.json", {"expires_epoch": time.time() + 60})
        self.assertEqual(self.req("/v1/desk-write-token", tok)[0], 403)
        self.assertTrue((self.root / "state" / "token-handoff.json").exists())  # not consumed
        # usage recorded without the value
        usage = (self.root / "state" / "read-tokens-usage.json").read_text()
        self.assertIn("research-mini", usage)
        self.assertNotIn(tok, usage)

    def test_quote_token_and_write_token_unchanged(self):
        self.named()
        self.assertEqual(self.req("/v1/feeds", "readtok")[0], 200)
        self.assertEqual(self.req("/v1/feeds", "writetok")[0], 401)

    def test_revoke_is_immediate(self):
        tok = self.named()
        self.assertEqual(self.req("/v1/feeds", tok)[0], 200)
        tokens.revoke("research-mini")
        self.assertEqual(self.req("/v1/feeds", tok)[0], 401)
        self.assertFalse((self.secrets / "read-tokens" / "research-mini").exists())

    def test_names_validated_and_no_dup(self):
        for bad in ("../x", "A", "x", "a/b", ""):
            with self.assertRaises(ValueError):
                tokens.add(bad)
        tokens.add("research-mini")
        with self.assertRaises(FileExistsError):
            tokens.add("research-mini")
        tokens.add("research-mini", rotate=True)

    def test_health_shows_count_not_names(self):
        self.named()
        body = self.req("/v1/health")[1]
        self.assertEqual(json.loads(body)["named_read_tokens"], 1)
        self.assertNotIn(b"research-mini", body)

    def hreq(self, name, code):
        import urllib.request, urllib.error
        h = {"X-OID-Handoff-Code": code} if code else {}
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/read-token-handoff?name={name}", headers=h)
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with op.open(r, timeout=5) as fh:
                return fh.status, json.loads(fh.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_handoff_once_ip_bound_code_checked(self):
        tok = self.named()
        self.assertEqual(self.hreq("research-mini", "X")[0], 404)  # not armed
        code = tokens.arm_handoff("research-mini", "100.111.60.56", 30)
        st = (self.root / "state" / "read-token-handoff" / "research-mini.json").read_text()
        self.assertNotIn(code, st)  # only the hash is stored
        self.assertNotIn(tok, st)
        self.assertEqual(self.hreq("research-mini", None)[0], 401)
        self.assertEqual(self.hreq("research-mini", "AAAA-AAAA-AAAA-AAAA")[0], 401)
        c, body = self.hreq("research-mini", code)
        self.assertEqual((c, body["value"]), (200, tok))
        self.assertEqual(self.hreq("research-mini", code)[0], 404)  # single use

    def test_handoff_wrong_ip_and_expiry_and_lockout(self):
        self.named()
        code = tokens.arm_handoff("research-mini", "100.120.2.95", 30)
        self.assertEqual(self.hreq("research-mini", code)[0], 403)  # we are 100.111.60.56
        f = self.root / "state" / "read-token-handoff" / "research-mini.json"
        st = json.loads(f.read_text()); st["expires_epoch"] = time.time() - 1; f.write_text(json.dumps(st))
        self.assertEqual(self.hreq("research-mini", code)[0], 404)
        code = tokens.arm_handoff("research-mini", "100.111.60.56", 30)
        for _ in range(tokens.MAX_FAILURES):
            self.hreq("research-mini", "WRONG")
        self.assertEqual(self.hreq("research-mini", code)[0], 404)  # disarmed after 5 failures

    def test_handoff_requires_existing_token_and_named_cannot_use_it(self):
        with self.assertRaises(FileNotFoundError):
            tokens.arm_handoff("research-mini", "127.0.0.1")
        tokens.add("ok-name")
        with self.assertRaises(ValueError):
            tokens.arm_handoff("ok-name", "not-an-ip")

    def test_unresolvable_loopback_and_lan_denied(self):
        self.named()
        code = tokens.arm_handoff("research-mini", "100.111.60.56", 30)
        self.peer = None  # local process on the mini, not a tailnet peer
        self.assertEqual(self.hreq("research-mini", code)[0], 403)
        self.assertIsNone(tokens.source_ip("192.168.1.20", 5000))
        self.assertEqual(tokens.source_ip("100.120.2.95", 5000), "100.120.2.95")

    def test_whois_parser_against_fake_localapi(self):
        import socket, tempfile, threading
        d = tempfile.mkdtemp()
        path = os.path.join(d, "ts.sock")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); srv.bind(path); srv.listen(1)
        seen = {}
        def run():
            c, _ = srv.accept(); seen["req"] = c.recv(4096)
            body = json.dumps({"Node": {"Addresses": ["fd7a:115c:a1e0::1/128", "100.120.2.95/32"]}}).encode()
            c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n" + body); c.close()
        threading.Thread(target=run, daemon=True).start()
        os.environ["OID_TS_SOCKET"] = path
        self.assertEqual(self._whois(54321), "100.120.2.95")
        self.assertIn(b"/localapi/v0/whois?addr=127.0.0.1:54321", seen["req"])
        srv.close()

    def test_ctl_never_prints_value(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(ctl.main(["read-token", "add", "research-mini"]), 0)
            self.assertEqual(ctl.main(["read-token", "list"]), 0)
            self.assertEqual(ctl.main(["read-token", "handoff", "research-mini", "--from", "100.120.2.95", "--minutes", "30"]), 0)
            self.assertEqual(ctl.main(["read-token", "list"]), 0)
            self.assertEqual(ctl.main(["read-token", "revoke", "research-mini"]), 0)
        tokval_gone = not (self.secrets / "read-tokens" / "research-mini").exists()
        s = out.getvalue()
        self.assertTrue(tokval_gone)
        self.assertIn("ONE-TIME CODE", s)
        self.assertIn("ARMED from 100.120.2.95", s)
        self.assertIn("revoked", s)
        self.assertFalse((self.root / "state" / "read-token-handoff" / "research-mini.json").exists())
