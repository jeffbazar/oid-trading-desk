"""Meaningful local-server integration tests; no network collection or real trades."""

import csv
import http.client
import io
import json
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import server


class DeskServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for folder in ("data", "public", "docs", "prompts", "scripts"):
            (self.root / folder).mkdir()
        (self.root / "public" / "index.html").write_text("<h1>Paper desk</h1>")
        (self.root / "docs" / "changes.json").write_text('[{"id":"initial"}]')
        (self.root / "docs" / "source-registry.json").write_text('{"feeds":[]}')
        (self.root / "docs" / "guide.txt").write_text("copy-ready guide")
        (self.root / "prompts" / server.PROMPTS["rose"]).write_text("You are Rose. Paper review only.")
        self.write_snapshot()
        self.start_server()

    def write_snapshot(self, snapshot_id="source-1", extra=None):
        value = {
            "schema_version": "1.0", "snapshot_id": snapshot_id,
            "imported_at": "2026-10-04T20:00:00Z",
            "observed": {"marks_at": "Oct 2, 1:02 PM PT"},
            "closed_trades": [{
                "id": "trade-1", "headers": ["Trader", "PnL", "Reason"],
                "cells": [{"text": "Hal"}, {"text": "−$64"}, {"text": 'Published, "source"', "title": "Full source rationale"}],
                "source_page": "index", "section_id": "recently-closed",
            }],
            "positions": {"rose": [{"id": "held-1"}], "hal": []},
            "watches": [{"id": "watch-1"}],
            "pages": [{"key": "chart", "sections": [{"id": "signals", "rows": [{"id": "chart-row-1", "cells": [{"text": "QQQ"}]}]}]}],
        }
        if extra:
            value.update(extra)
        tmp = self.root / "data" / "incoming.json"
        tmp.write_text(json.dumps(value), encoding="utf-8")
        tmp.replace(self.root / "data" / "snapshot.json")
        return value

    def start_server(self):
        self.http = server.create_server(self.root, port=0)
        self.thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.http.server_port
        self.origin = "http://127.0.0.1:" + str(self.port)

    def stop_server(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)

    def tearDown(self):
        self.stop_server()
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        request_headers = dict(headers or {})
        body = raw
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("Origin", self.origin)
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def review(self, request_id="request-001", **changes):
        value = {"client_request_id": request_id, "trade_id": "trade-1", "status": "reviewed", "note": "Paper source reviewed; no execution."}
        value.update(changes)
        return value

    def test_snapshot_etag_and_separate_server_clock(self):
        status, headers, raw = self.request("/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(raw, (self.root / "data" / "snapshot.json").read_bytes())
        self.assertEqual(json.loads(raw)["observed"]["marks_at"], "Oct 2, 1:02 PM PT")
        self.assertIn("X-Server-Time", headers)
        self.assertEqual(headers["X-Snapshot-Revision"], "1")
        status, second, raw = self.request("/api/snapshot", headers={"If-None-Match": headers["ETag"]})
        self.assertEqual(status, 304)
        self.assertEqual(raw, b"")
        self.assertIn("X-Server-Time", second)
        self.write_snapshot("source-2")
        status, changed, raw = self.request("/api/snapshot", headers={"If-None-Match": headers["ETag"]})
        self.assertEqual(status, 200)
        self.assertNotEqual(changed["ETag"], headers["ETag"])
        self.assertEqual(changed["X-Snapshot-Revision"], "2")

    def test_health_and_absent_or_invalid_snapshot(self):
        status, _, body = self.request("/api/health")
        self.assertEqual(status, 200)
        health = json.loads(body)
        self.assertTrue(health["snapshot_available"])
        self.assertFalse(health["execution_enabled"])
        self.assertFalse(health["market_collection_enabled"])
        (self.root / "data" / "snapshot.json").unlink()
        status, _, body = self.request("/api/snapshot")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"], "snapshot_unavailable")
        (self.root / "data" / "snapshot.json").write_text('{"bad":NaN}')
        self.assertEqual(self.request("/api/snapshot")[0], 503)
        self.write_snapshot("restored")
        self.assertEqual(self.request("/api/snapshot")[0], 200)

    def test_review_persistence_idempotency_history_and_pagination(self):
        before = (self.root / "data" / "snapshot.json").read_bytes()
        status, _, body = self.request("/api/reviews", "POST", self.review())
        first = json.loads(body)
        self.assertEqual(status, 201)
        self.assertFalse(first["idempotent"])
        self.assertEqual(first["revision"], 1)
        self.assertEqual(first["review"]["snapshot_revision"], 1)
        self.assertEqual(first["review"]["snapshot_id"], "source-1")
        reordered = dict(reversed(list(self.review().items())))
        status, _, body = self.request("/api/reviews", "POST", reordered)
        retry = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(retry["idempotent"])
        self.assertEqual(retry["review"], first["review"])
        self.assertEqual(self.request("/api/reviews", "POST", self.review(note="different"))[0], 409)
        self.assertEqual(self.request("/api/reviews", "POST", self.review("request-002", status="hold"))[0], 201)
        status, _, body = self.request("/api/reviews?limit=1")
        listing = json.loads(body)
        self.assertEqual(listing["next_cursor"], 1)
        self.assertEqual(listing["latest_by_trade"]["trade-1"]["status"], "hold")
        self.assertEqual(listing["revision"], 2)
        second_page = json.loads(self.request("/api/reviews?cursor=1&limit=1")[2])
        self.assertEqual(second_page["reviews"][0]["id"], 2)
        self.assertIsNone(second_page["next_cursor"])
        self.assertEqual(before, (self.root / "data" / "snapshot.json").read_bytes())
        self.stop_server()
        self.start_server()
        persisted = json.loads(self.request("/api/reviews")[2])
        self.assertEqual(len(persisted["reviews"]), 2)
        self.assertEqual(persisted["revision"], 2)
        health = json.loads(self.request("/api/health")[2])
        self.assertEqual(health["snapshot_revision"], 1)

    def test_simultaneous_review_retry_is_one_record(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(lambda _: self.request("/api/reviews", "POST", self.review())[0], range(12)))
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(200), 11)
        data = json.loads(self.request("/api/reviews")[2])
        self.assertEqual(len(data["reviews"]), 1)
        self.assertEqual(data["revision"], 1)

    def test_chart_row_and_inspected_snapshot_guard(self):
        payload = self.review(trade_id="chart-row-1", snapshot_id="source-1")
        status, _, body = self.request("/api/reviews", "POST", payload)
        first = json.loads(body)
        self.assertEqual(status, 201)
        self.assertEqual(first["review"]["trade_id"], "chart-row-1")
        self.assertEqual(first["review"]["snapshot_id"], "source-1")
        self.assertEqual(self.request("/api/reviews", "POST", self.review("request-unknown", trade_id="invented-row", snapshot_id="source-1"))[0], 422)
        self.write_snapshot("source-2")
        status, _, body = self.request("/api/reviews", "POST", self.review("request-stale", trade_id="chart-row-1", snapshot_id="source-1"))
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["error"], "snapshot_changed")
        # A completed idempotent retry retains its original inspected context.
        status, _, body = self.request("/api/reviews", "POST", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["review"], first["review"])
        fresh = self.review("request-fresh", trade_id="chart-row-1", snapshot_id="source-2")
        status, _, body = self.request("/api/reviews", "POST", fresh)
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["review"]["snapshot_revision"], 2)
        self.assertEqual(json.loads(self.request("/api/reviews")[2])["revision"], 2)

    def test_same_origin_and_body_validation_reject_writes(self):
        for origin in ("https://evil.example", "null", ""):
            self.assertEqual(self.request("/api/reviews", "POST", self.review(), headers={"Origin": origin})[0], 403)
        self.assertEqual(self.request("/api/reviews", "POST", self.review(), headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("/api/health", headers={"Host": "evil.example:" + str(self.port)})[0], 403)
        self.assertEqual(self.request("/api/reviews", "POST", raw=b"{}", headers={"Origin": self.origin, "Content-Type": "text/plain"})[0], 415)
        for changes in ({"status": "execute"}, {"trade_id": "unknown"}, {"note": "x" * 4001}, {"note": "bad\x00note"}, {"client_request_id": "bad"}, {"quantity": 10}):
            self.assertEqual(self.request("/api/reviews", "POST", self.review(**changes))[0], 422)
        self.assertEqual(self.request("/api/reviews", "POST", raw=b"{broken", headers={"Origin": self.origin, "Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("/api/reviews", "POST", raw=b"x" * 32769, headers={"Origin": self.origin, "Content-Type": "application/json"})[0], 413)
        self.assertEqual(json.loads(self.request("/api/reviews")[2])["revision"], 0)
        for verb in ("PUT", "PATCH", "DELETE", "OPTIONS"):
            self.assertEqual(self.request("/api/trades", verb)[0], 405)
        self.assertEqual(self.request("/api/orders", "POST", {})[0], 404)

    def test_static_traversal_symlinks_and_allowlisted_downloads(self):
        self.assertEqual(self.request("/")[0], 200)
        (self.root / "public" / "escape.txt").symlink_to(self.root / "docs" / "guide.txt")
        for path in ("/../docs/guide.txt", "/%2e%2e/docs/guide.txt", "/%2e%2e%2fdocs%2fguide.txt", "/escape.txt", "/data/reviews.sqlite3", "/.hidden", "/downloads/../data/snapshot.json"):
            self.assertEqual(self.request(path)[0], 404, path)
        status, headers, body = self.request("/api/download/guide.txt")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(body, b"copy-ready guide")
        self.assertEqual(self.request("/downloads/guide.txt")[0], 200)
        self.assertEqual(self.request("/api/download/reviews.sqlite3")[0], 404)
        prompt = json.loads(self.request("/api/prompt/rose")[2])
        self.assertEqual(prompt["bot"], "rose")
        self.assertIn("Paper review", prompt["text"])
        self.assertEqual(self.request("/api/prompt/unknown")[0], 404)
        self.assertEqual(json.loads(self.request("/api/changes")[2]), [{"id": "initial"}])
        self.assertEqual(json.loads(self.request("/api/registry")[2]), {"feeds": []})

    def test_csv_preserves_reported_cells_without_pnl_correction(self):
        status, headers, body = self.request("/api/export/trades.csv")
        self.assertEqual(status, 200)
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
        self.assertEqual(rows[0]["PnL"], "−$64")
        self.assertEqual(rows[0]["Reason"], 'Published, "source"')
        self.assertEqual(rows[0]["Reason [source title]"], "Full source rationale")
        self.assertEqual(rows[0]["source_row_id"], "trade-1")
        self.assertIn("reported-closed-trades.csv", headers["Content-Disposition"])

    def read_sse_packet(self, response):
        fields = {}
        while True:
            line = response.fp.readline().decode().rstrip("\r\n")
            if not line:
                return fields
            if ":" in line and not line.startswith(":"):
                key, value = line.split(":", 1)
                fields[key] = value.lstrip()

    def test_sse_replay_revision_and_next_review_event(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/events", headers={"Last-Event-ID": "0"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.read_sse_packet(response)  # connection comment / retry, not a market event
        packet = self.read_sse_packet(response)
        self.assertEqual(packet["event"], "snapshot")
        self.assertEqual(json.loads(packet["data"])["snapshot_id"], "source-1")
        self.request("/api/reviews", "POST", self.review())
        packet = self.read_sse_packet(response)
        self.assertEqual(packet["event"], "reviews")
        self.assertEqual(json.loads(packet["data"])["revision"], 1)
        cursor = packet["id"]
        self.write_snapshot("source-2")
        packet = self.read_sse_packet(response)
        self.assertEqual(packet["event"], "snapshot")
        self.assertEqual(json.loads(packet["data"])["revision"], 2)
        response.close()
        conn.close()
        replay = self.http.state.events_after(int(cursor))
        self.assertEqual(replay[0]["kind"], "snapshot")
        self.assertEqual(self.request("/api/events?cursor=999")[0], 400)

    def test_manual_sync_lock_success_failure_and_timeout(self):
        (self.root / "scripts" / "import_snapshot.py").write_text("# mocked importer")
        self.assertEqual(self.request("/api/sync", "POST", {"execute": True})[0], 422)
        self.http.state.sync_lock.acquire()
        try:
            self.assertEqual(self.request("/api/sync", "POST", {})[0], 409)
        finally:
            self.http.state.sync_lock.release()
        def imported(*args, **kwargs):
            self.assertEqual(args[0][-1], "--fetch")
            self.assertEqual(kwargs["timeout"], 90)
            self.write_snapshot("manual-import")
            return subprocess.CompletedProcess(args[0], 0, "Imported all sources", "")
        with patch("server.subprocess.run", side_effect=imported):
            status, _, body = self.request("/api/sync", "POST", {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["snapshot_id"], "manual-import")
        before = (self.root / "data" / "snapshot.json").read_bytes()
        with patch("server.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "HTTP 502 on one source; no import committed")):
            status, _, body = self.request("/api/sync", "POST", {})
        self.assertEqual(status, 502)
        self.assertIn("HTTP 502", json.loads(body)["message"])
        self.assertEqual(before, (self.root / "data" / "snapshot.json").read_bytes())
        with patch("server.subprocess.run", side_effect=subprocess.TimeoutExpired("import", 90)):
            self.assertEqual(self.request("/api/sync", "POST", {})[0], 504)
        self.assertFalse(self.http.state.sync_running)
        self.assertFalse(self.http.state.sync_lock.locked())

    def test_nonloopback_listen_rejected(self):
        with self.assertRaises(ValueError):
            server.create_server(self.root, host="0.0.0.0", port=0)
        with self.assertRaises(ValueError):
            server.create_server(self.root, host="example.com", port=0)


if __name__ == "__main__":
    unittest.main()
