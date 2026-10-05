#!/usr/bin/env python3
"""Local, read-only paper-trading desk with a separate review-note journal.

Run: python3 server.py
No market collector, execution client, third-party package, or notification sender.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import ipaddress
import json
import mimetypes
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parent
MAX_BODY = 32_768
MAX_NOTE = 4_000
STATUSES = frozenset({"reviewed", "needs-review", "hold"})
PROMPTS = {
    "rose": "01-rose-trader-prompt.txt",
    "hal": "02-hal-trader-prompt.txt",
    "macro": "03-macro-bot-prompt.txt",
    "chart": "04-chart-bot-prompt.txt",
    "news": "05-news-alerts-bot-prompt.txt",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def strict_json(raw):
    def reject_constant(value):
        raise ValueError("Invalid JSON numeric constant: " + value)
    return json.loads(raw, parse_constant=reject_constant)


class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


class DeskState:
    """One synchronized SQLite connection; durable revisions and append-only notes."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        self.sync_running = False
        self.last_sync = None
        self.snapshot = None
        self.snapshot_bytes = None
        self.snapshot_stat = None
        self.snapshot_error = "No imported snapshot is available."
        self.db = sqlite3.connect(self.root / "data" / "reviews.sqlite3", timeout=5, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO metadata VALUES ('snapshot_revision', '0');
            INSERT OR IGNORE INTO metadata VALUES ('reviews_revision', '0');
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_request_id TEXT NOT NULL UNIQUE,
                trade_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('reviewed','needs-review','hold')),
                note TEXT NOT NULL,
                created_at TEXT NOT NULL,
                snapshot_revision INTEGER NOT NULL DEFAULT 0,
                snapshot_id TEXT,
                payload_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS reviews_trade ON reviews(trade_id, id);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(reviews)")}
        # Earlier local journals remain readable; unknown historical context stays 0/null.
        if "snapshot_revision" not in columns:
            self.db.execute("ALTER TABLE reviews ADD COLUMN snapshot_revision INTEGER NOT NULL DEFAULT 0")
        if "snapshot_id" not in columns:
            self.db.execute("ALTER TABLE reviews ADD COLUMN snapshot_id TEXT")
        self.db.commit()
        self.load_snapshot()

    def close(self):
        with self.lock:
            self.db.close()

    def meta(self, key, default=""):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        self.db.execute("INSERT INTO metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def record_event(self, kind, revision, payload):
        self.db.execute("INSERT INTO events(kind,revision,payload,created_at) VALUES (?,?,?,?)", (kind, revision, json_bytes(payload).decode(), utc_now()))

    def load_snapshot(self):
        """Observe the local file, never refresh its upstream market sources."""
        with self.lock:
            path = self.root / "data" / "snapshot.json"
            try:
                stat = path.stat()
                stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
                if self.snapshot is not None and stamp == self.snapshot_stat:
                    return self.snapshot
                raw = path.read_bytes()
                parsed = strict_json(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("The snapshot must be a JSON object.")
            except (OSError, ValueError, UnicodeError) as exc:
                self.snapshot = self.snapshot_bytes = self.snapshot_stat = None
                self.snapshot_error = "No valid imported snapshot is available: " + str(exc)
                return None
            digest = hashlib.sha256(raw).hexdigest()
            with self.db:
                if digest != self.meta("snapshot_hash"):
                    revision = int(self.meta("snapshot_revision", "0")) + 1
                    self.set_meta("snapshot_hash", digest)
                    self.set_meta("snapshot_revision", revision)
                    self.record_event("snapshot", revision, {
                        "revision": revision, "snapshot_id": parsed.get("snapshot_id"),
                        "imported_at": parsed.get("imported_at"), "etag": '"' + digest + '"',
                    })
            self.snapshot, self.snapshot_bytes, self.snapshot_stat = parsed, raw, stamp
            self.snapshot_error = None
            return parsed

    def require_snapshot(self):
        value = self.load_snapshot()
        if value is None:
            raise APIError(503, "snapshot_unavailable", self.snapshot_error)
        return value

    def snapshot_response(self):
        with self.lock:
            self.require_snapshot()
            return self.snapshot_bytes, '"' + self.meta("snapshot_hash") + '"', int(self.meta("snapshot_revision", "0"))

    def health(self):
        with self.lock:
            snapshot = self.load_snapshot()
            return {
                "ok": True, "mode": "local-paper-review", "execution_enabled": False,
                "market_collection_enabled": False, "server_time": utc_now(),
                "snapshot_available": snapshot is not None,
                "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
                "imported_at": snapshot.get("imported_at") if snapshot else None,
                "observed": snapshot.get("observed", {}) if snapshot else {},
                "snapshot_revision": int(self.meta("snapshot_revision", "0")),
                "reviews_revision": int(self.meta("reviews_revision", "0")),
                "snapshot_error": self.snapshot_error,
                "sync_running": self.sync_running, "last_sync": self.last_sync,
            }

    @staticmethod
    def public_review(row):
        return {key: row[key] for key in ("id", "client_request_id", "trade_id", "status", "note", "created_at", "snapshot_revision", "snapshot_id")}

    def list_reviews(self, cursor=0, limit=500):
        with self.lock:
            rows = self.db.execute("SELECT * FROM reviews WHERE id>? ORDER BY id LIMIT ?", (cursor, limit + 1)).fetchall()
            visible = rows[:limit]
            latest = self.db.execute("SELECT r.* FROM reviews r JOIN (SELECT trade_id,MAX(id) id FROM reviews GROUP BY trade_id) x ON r.id=x.id ORDER BY r.id").fetchall()
            return {
                "reviews": [self.public_review(row) for row in visible],
                "latest_by_trade": {row["trade_id"]: self.public_review(row) for row in latest},
                "revision": int(self.meta("reviews_revision", "0")),
                "next_cursor": visible[-1]["id"] if len(rows) > limit else None,
            }

    def create_review(self, payload):
        required = {"client_request_id", "trade_id", "status", "note"}
        if not required.issubset(payload) or not set(payload).issubset(required | {"snapshot_id"}):
            raise APIError(422, "invalid_review", "Supply client_request_id, trade_id, status, and note; snapshot_id is the only optional field.")
        request_id, trade_id, status, note = (payload[k] for k in ("client_request_id", "trade_id", "status", "note"))
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:~-]{8,128}", request_id):
            raise APIError(422, "invalid_request_id", "client_request_id must contain 8–128 letters, numbers, or ._:~- characters.")
        if not isinstance(trade_id, str) or not trade_id or len(trade_id) > 200 or any(ord(ch) < 32 for ch in trade_id):
            raise APIError(422, "invalid_trade_id", "trade_id must be a nonempty source row ID of at most 200 characters.")
        if not isinstance(status, str) or status not in STATUSES:
            raise APIError(422, "invalid_status", "Status must be reviewed, needs-review, or hold.")
        if not isinstance(note, str) or len(note) > MAX_NOTE or any(ord(ch) < 32 and ch not in "\n\r\t" for ch in note):
            raise APIError(422, "invalid_note", "Note must contain at most 4,000 characters and no unsupported control characters.")
        if "snapshot_id" in payload and (not isinstance(payload["snapshot_id"], str) or not payload["snapshot_id"] or len(payload["snapshot_id"]) > 200):
            raise APIError(422, "invalid_snapshot_id", "Optional snapshot_id must be the nonempty ID of the snapshot you inspected.")
        # Sort keys so retries from differently ordered JSON objects are identical.
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.lock:
            existing = self.db.execute("SELECT * FROM reviews WHERE client_request_id=?", (request_id,)).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise APIError(409, "request_id_conflict", "This client_request_id already identifies a different review.")
                return {"review": self.public_review(existing), "revision": int(self.meta("reviews_revision", "0")), "idempotent": True}
            snapshot = self.require_snapshot()
            if "snapshot_id" in payload and payload["snapshot_id"] != snapshot.get("snapshot_id"):
                raise APIError(409, "snapshot_changed", "The imported snapshot changed after inspection. Reload it, inspect the row again, and save a new review.")
            collections = [snapshot.get("closed_trades", []), snapshot.get("watches", [])]
            positions = snapshot.get("positions", {})
            if isinstance(positions, dict):
                collections.extend(positions.values())
            for page in snapshot.get("pages", []):
                if isinstance(page, dict):
                    for section in page.get("sections", []):
                        if isinstance(section, dict):
                            collections.append(section.get("rows", []))
            known = {row.get("id") for rows in collections if isinstance(rows, list) for row in rows if isinstance(row, dict)}
            if trade_id not in known:
                raise APIError(422, "unknown_trade_id", "This source row ID is not in the current imported tables, trades, or watches.")
            with self.db:
                cursor = self.db.execute("INSERT INTO reviews(client_request_id,trade_id,status,note,created_at,snapshot_revision,snapshot_id,payload_hash) VALUES (?,?,?,?,?,?,?,?)", (request_id, trade_id, status, note, utc_now(), int(self.meta("snapshot_revision", "0")), snapshot.get("snapshot_id"), digest))
                revision = int(self.meta("reviews_revision", "0")) + 1
                self.set_meta("reviews_revision", revision)
                self.record_event("reviews", revision, {"revision": revision, "review_id": cursor.lastrowid, "trade_id": trade_id})
                row = self.db.execute("SELECT * FROM reviews WHERE id=?", (cursor.lastrowid,)).fetchone()
            return {"review": self.public_review(row), "revision": revision, "idempotent": False}

    def event_id(self):
        with self.lock:
            return self.db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]

    def events_after(self, cursor):
        with self.lock:
            return [dict(row) for row in self.db.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT 500", (cursor,))]

    def sync_public_site(self):
        if not self.sync_lock.acquire(blocking=False):
            raise APIError(409, "sync_in_progress", "A manual public-site sync is already running.")
        self.sync_running = True
        started_at = utc_now()
        try:
            script = self.root / "scripts" / "import_snapshot.py"
            if not script.is_file():
                raise APIError(503, "importer_unavailable", "scripts/import_snapshot.py is not available.")
            try:
                result = subprocess.run([sys.executable, str(script), "--fetch"], cwd=self.root, capture_output=True, text=True, timeout=90, check=False)
            except subprocess.TimeoutExpired:
                raise APIError(504, "sync_timeout", "The public-site import exceeded 90 seconds; check the last successfully imported snapshot.")
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()[-4_000:]
                raise APIError(502, "sync_failed", "The public-site import failed." + (" " + detail if detail else ""))
            with self.lock:
                snapshot = self.require_snapshot()
                response = {
                    "ok": True, "snapshot_id": snapshot.get("snapshot_id"),
                    "imported_at": snapshot.get("imported_at"),
                    "revision": int(self.meta("snapshot_revision", "0")),
                    "output": result.stdout.strip()[-4_000:],
                }
                self.last_sync = {"ok": True, "started_at": started_at, "finished_at": utc_now(), "snapshot_id": snapshot.get("snapshot_id")}
            return response
        except APIError as exc:
            self.last_sync = {"ok": False, "started_at": started_at, "finished_at": utc_now(), "error": exc.code}
            raise
        except OSError as exc:
            self.last_sync = {"ok": False, "started_at": started_at, "finished_at": utc_now(), "error": "sync_failed"}
            raise APIError(502, "sync_failed", "The importer could not be run: " + str(exc))
        finally:
            self.sync_running = False
            self.sync_lock.release()

    def trades_csv(self):
        snapshot = self.require_snapshot()
        rows = snapshot.get("closed_trades", [])
        if not isinstance(rows, list):
            raise APIError(503, "invalid_trades", "The snapshot closed_trades collection is invalid.")
        headers = ["source_page", "section_id", "source_row_id"]
        mapped = []
        for row in rows:
            source_headers, cells = row.get("headers", []), row.get("cells", [])
            values = {"source_page": row.get("source_page", ""), "section_id": row.get("section_id", ""), "source_row_id": row.get("id", "")}
            occurrences = {}
            for i, cell in enumerate(cells):
                header = str(source_headers[i]) if i < len(source_headers) else "Published column " + str(i + 1)
                occurrences[header] = occurrences.get(header, 0) + 1
                if occurrences[header] > 1:
                    header += " (" + str(occurrences[header]) + ")"
                if header in {"source_page", "section_id", "source_row_id"}:
                    header = "Published " + header
                values[header] = cell.get("text", "") if isinstance(cell, dict) else str(cell)
                if header not in headers:
                    headers.append(header)
                if isinstance(cell, dict) and cell.get("title"):
                    title_header = header + " [source title]"
                    values[title_header] = cell["title"]
                    if title_header not in headers:
                        headers.append(title_header)
            mapped.append(values)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(mapped)
        return output.getvalue().encode("utf-8-sig")


class DeskServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, root):
        self.state = DeskState(root)
        self.stop_event = threading.Event()
        super().__init__(address, DeskHandler)

    def server_close(self):
        self.stop_event.set()
        super().server_close()
        self.state.close()


class DeskHandler(BaseHTTPRequestHandler):
    server_version = "LocalPaperDesk/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # No request bodies or review-note contents in logs.
        sys.stderr.write("%s %s\n" % (utc_now(), fmt % args))

    def validate_host(self):
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit("http://" + host)
            allowed = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
            valid = allowed and len(self.headers.get_all("Host", [])) == 1 and parsed.port == self.server.server_port and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment
        except ValueError:
            valid = False
        if not valid:
            raise APIError(403, "invalid_host", "Use this server's loopback address and port.")

    def validate_origin(self):
        self.validate_host()
        expected = "http://" + self.headers.get("Host", "").lower()
        if len(self.headers.get_all("Origin", [])) != 1 or self.headers.get("Origin", "").lower() != expected or self.headers.get("Sec-Fetch-Site", "same-origin") not in {"same-origin", "none"}:
            raise APIError(403, "invalid_origin", "POST requests require this local page's same-origin Origin header.")

    def send_bytes(self, body, status=200, content_type="application/json; charset=utf-8", extra=None, head=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if extra and "ETag" in extra else "no-store")
        self.send_header("X-Server-Time", utc_now())
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if extra:
            for key, value in extra.items():
                self.send_header(key, str(value))
        self.end_headers()
        if not head and status != 304:
            self.wfile.write(body)

    def send_json(self, payload, status=200, extra=None, head=False):
        self.send_bytes(json_bytes(payload), status, extra=extra, head=head)

    def fail(self, exc, head=False):
        self.close_connection = True
        self.send_json({"error": exc.code, "message": exc.message}, exc.status, head=head)

    def read_json(self):
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "unsupported_transfer_encoding", "Use a bounded Content-Length JSON request.")
        if len(self.headers.get_all("Content-Length", [])) > 1:
            raise APIError(400, "ambiguous_length", "Supply one Content-Length header.")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise APIError(415, "json_required", "Content-Type must be application/json.")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise APIError(411, "length_required", "A valid Content-Length is required.")
        if length < 0 or length > MAX_BODY:
            raise APIError(413, "body_too_large", "Request body must be at most 32,768 bytes.")
        self.connection.settimeout(10)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            payload = strict_json(raw)
        except (ValueError, UnicodeError, TimeoutError, OSError):
            raise APIError(400, "invalid_json", "Supply one complete UTF-8 JSON object.")
        if not isinstance(payload, dict):
            raise APIError(400, "object_required", "The JSON body must be an object.")
        return payload

    @staticmethod
    def integer_parameter(query, key, default, maximum=None):
        values = query.get(key, [str(default)])
        if len(values) != 1 or not re.fullmatch(r"\d{1,18}", values[0]):
            raise APIError(400, "invalid_parameter", key + " must be one nonnegative integer.")
        value = int(values[0])
        if maximum is not None and (value < 1 or value > maximum):
            raise APIError(400, "invalid_parameter", key + " must be between 1 and " + str(maximum) + ".")
        return value

    def do_GET(self):
        self.get_response()

    def do_HEAD(self):
        self.get_response(head=True)

    def get_response(self, head=False):
        try:
            self.validate_host()
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            state = self.server.state
            if path == "/api/snapshot":
                raw, etag, revision = state.snapshot_response()
                headers = {"ETag": etag, "X-Snapshot-Revision": revision}
                if etag in [value.strip() for value in self.headers.get("If-None-Match", "").split(",")] or self.headers.get("If-None-Match") == "*":
                    self.send_bytes(b"", 304, extra=headers, head=head)
                else:
                    self.send_bytes(raw, extra=headers, head=head)
            elif path == "/api/health":
                self.send_json(state.health(), head=head)
            elif path == "/api/reviews":
                cursor = self.integer_parameter(query, "cursor", 0)
                limit = self.integer_parameter(query, "limit", 500, 1000)
                self.send_json(state.list_reviews(cursor, limit), head=head)
            elif path in {"/api/changes", "/api/registry"}:
                filename = "changes.json" if path.endswith("changes") else "source-registry.json"
                target = self.safe_file(state.root / "docs", filename)
                try:
                    value = strict_json(target.read_bytes())
                except (ValueError, UnicodeError):
                    raise APIError(503, "document_invalid", "The local document is not valid JSON.")
                self.send_json(value, head=head)
            elif path.startswith("/api/prompt/"):
                bot = path[len("/api/prompt/"):]
                if bot not in PROMPTS:
                    raise APIError(404, "prompt_not_found", "Unknown bot prompt.")
                filename = PROMPTS[bot]
                text = self.safe_file(state.root / "prompts", filename).read_text(encoding="utf-8")
                self.send_json({"bot": bot, "filename": filename, "text": text}, head=head)
            elif path.startswith("/api/download/") or path.startswith("/downloads/"):
                basename = path.split("/", 3)[-1] if path.startswith("/api/") else path[len("/downloads/"):]
                self.download(basename, head)
            elif path == "/api/export/trades.csv":
                self.send_bytes(state.trades_csv(), content_type="text/csv; charset=utf-8", extra={"Content-Disposition": 'attachment; filename="reported-closed-trades.csv"'}, head=head)
            elif path == "/api/events":
                if head:
                    self.send_bytes(b"", content_type="text/event-stream", head=True)
                else:
                    self.event_stream(query)
            elif path.startswith("/api/"):
                raise APIError(404, "not_found", "Unknown API endpoint.")
            else:
                target = self.safe_file(state.root / "public", "index.html" if path == "/" else path.lstrip("/"))
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
                    content_type += "; charset=utf-8"
                self.send_bytes(target.read_bytes(), content_type=content_type, head=head)
        except APIError as exc:
            self.fail(exc, head)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except (OSError, UnicodeError, ValueError, sqlite3.Error) as exc:
            sys.stderr.write("%s local read failed: %s\n" % (utc_now(), type(exc).__name__))
            self.fail(APIError(500, "local_read_failed", "The local resource could not be read."), head)

    def safe_file(self, base, relative):
        if "\x00" in relative or "\\" in relative or any(part.startswith(".") for part in Path(relative).parts):
            raise APIError(404, "not_found", "Local file not found.")
        base = base.resolve()
        target = (base / relative).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise APIError(404, "not_found", "Local file not found.")
        return target

    def download(self, basename, head=False):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", basename):
            raise APIError(404, "not_found", "Unknown download.")
        root = self.server.state.root
        targets = []
        if Path(basename).suffix in {".txt", ".json", ".md"}:
            if (root / "docs" / basename).is_file():
                targets.append(self.safe_file(root / "docs", basename))
        if basename.endswith("prompt.txt") and (root / "prompts" / basename).is_file():
            targets.append(self.safe_file(root / "prompts", basename))
        if len(targets) != 1:
            raise APIError(404, "not_found", "Unknown or ambiguous download.")
        content_type = "application/json; charset=utf-8" if basename.endswith(".json") else "text/plain; charset=utf-8"
        self.send_bytes(targets[0].read_bytes(), content_type=content_type, extra={"Content-Disposition": 'attachment; filename="' + basename + '"'}, head=head)

    def event_stream(self, query):
        state = self.server.state
        state.load_snapshot()
        last = self.headers.get("Last-Event-ID")
        if last is not None:
            cursor = self.integer_parameter({"cursor": [last]}, "cursor", 0)
        elif "cursor" in query:
            cursor = self.integer_parameter(query, "cursor", 0)
        else:
            cursor = state.event_id()
        if cursor > state.event_id():
            raise APIError(400, "invalid_cursor", "The event cursor is newer than this local journal.")
        self.connection.settimeout(10)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Server-Time", utc_now())
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(b": connected\nretry: 2000\n\n")
        self.wfile.flush()
        heartbeat = time.monotonic()
        try:
            while not self.server.stop_event.is_set():
                state.load_snapshot()
                for event in state.events_after(cursor):
                    packet = "id: %s\nevent: %s\ndata: %s\n\n" % (event["id"], event["kind"], event["payload"])
                    self.wfile.write(packet.encode("utf-8"))
                    self.wfile.flush()
                    cursor = event["id"]
                if time.monotonic() - heartbeat >= 15:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    heartbeat = time.monotonic()
                self.server.stop_event.wait(2)
        except (BrokenPipeError, ConnectionResetError, OSError, sqlite3.Error):
            return

    def do_POST(self):
        try:
            self.validate_origin()
            path = urlsplit(self.path).path
            if path not in {"/api/reviews", "/api/sync"}:
                raise APIError(404, "not_found", "Only local review notes and manual public-site sync accept POST.")
            payload = self.read_json()
            if path == "/api/reviews":
                result = self.server.state.create_review(payload)
                self.send_json(result, 200 if result["idempotent"] else 201)
            else:
                if payload:
                    raise APIError(422, "empty_body_required", "Manual sync accepts an empty JSON object only.")
                self.send_json(self.server.state.sync_public_site())
        except APIError as exc:
            self.fail(exc)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except (OSError, ValueError, sqlite3.Error) as exc:
            sys.stderr.write("%s local write failed: %s\n" % (utc_now(), type(exc).__name__))
            self.fail(APIError(500, "local_write_failed", "The local action could not be completed."))

    def do_OPTIONS(self):
        self.fail(APIError(405, "method_not_allowed", "Cross-origin requests are not enabled."))

    def do_PUT(self):
        self.fail(APIError(405, "method_not_allowed", "Trade mutation is not supported."))

    do_DELETE = do_PATCH = do_PUT


def create_server(root=ROOT, host="127.0.0.1", port=8768):
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("Only a loopback listen address is permitted.")
        except ValueError:
            raise ValueError("Only localhost or an explicit loopback IP address is permitted.")
    if host == "::1":
        class IPv6DeskServer(DeskServer):
            address_family = socket.AF_INET6
        return IPv6DeskServer((host, port), root)
    return DeskServer((host, port), root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="loopback listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    server = create_server(host=args.host, port=args.port)
    print("Local paper review desk: http://%s:%s (no execution; Ctrl+C to stop)" % (args.host, server.server_port), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
