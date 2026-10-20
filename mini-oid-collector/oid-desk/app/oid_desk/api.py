"""OID mini data API (stdlib, :8788). Read-only feeds for the box mirror + POST /v1/desk-state.

GET  /v1/health                      open: version, job flags, key presence (booleans only)
GET  /v1/feeds[?group=uw,fa]         read token: manifest [{name, group, size, mtime, sha256, as_of}]
GET  /v1/feed?name=<desk-rel path>   read token: raw bytes of one catalog file (X-OID-SHA256 header)
GET  /v1/walls | /v1/flow | /v1/marks | /v1/macro | /v1/filings | /v1/status | /v1/bars-summary   read token: grouped JSON
GET  /v1/archive/tables|schema|rows|bars  archive read token (~/oid-data/secrets/OID_ARCHIVE_READ_TOKEN) only; oid_archive.api_routes
GET  /v1/desk-write-token            OID_QUOTE_TOKEN only: one-time write-token handoff to the box (oidctl token-handoff)
GET  /v1/read-token-handoff?name=N   no bearer; header X-OID-Handoff-Code; armed by `oidctl read-token handoff N --from IP`,
                                     answers once, only from that IP (see tokens.py)
POST /v1/desk-state                  write token: {"files": {"<desk-rel>": <json>, ...}} -> atomic writes
                                     (allow-list = catalog desk_state; <root>/overrides/<basename> deep-merged)
Read tokens = secrets/OID_QUOTE_TOKEN (box mirror) + named GET-only tokens secrets/read-tokens/<name> (revocable;
`oidctl read-token add|revoke|list`). Write token = secrets/OID_DESK_WRITE_TOKEN (never accepted for reads).
Tokens and vendor keys are never returned or logged. Research / paper only: no broker or order code here.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from . import __version__, catalog, tokens, util

GROUP_ROUTES = {"/v1/walls": ["fa"], "/v1/flow": ["uw"], "/v1/marks": ["marks"], "/v1/macro": ["macro"],
                "/v1/filings": ["edgar"], "/v1/status": ["status"], "/v1/bars-summary": ["bars"]}
KEY_NAMES = ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "OID_QUOTE_TOKEN", "OID_DESK_WRITE_TOKEN",
             "FLASHALPHA_API_KEY", "UW_API_KEY", "HERENOW_API_KEY", "EIA_API_KEY", "BENZINGA_API_TOKEN"]
MAX_GROUP_FILE = 3_000_000
NAMED_DENY = {"/v1/desk-write-token", "/v1/read-token-handoff"}


def _token(name: str) -> Optional[str]:
    p = util.secrets_dir() / name
    try:
        v = p.read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        return None


def check_bearer(header: Optional[str], name: str) -> str:
    tok = _token(name)
    if not tok:
        return "unconfigured"
    if not header or not header.startswith("Bearer "):
        return "denied"
    return "ok" if hmac.compare_digest(header[7:].strip().encode(), tok.encode()) else "denied"


def deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base.get(k), v) if k in base else v
        return out
    return over


def strip_doc(ov: Any) -> Any:
    """Override files carry their own _doc; never let it replace the target's top-level keys."""
    if isinstance(ov, dict):
        return {k: v for k, v in ov.items() if not k.startswith("_")}
    return ov


def apply_desk_state(files: dict, cat: dict) -> dict:
    d = util.desk()
    written, rejected = [], {}
    for rel, obj in files.items():
        if not catalog.desk_state_allowed(cat, rel):
            rejected[rel] = "not_allowed"
            continue
        ov = strip_doc(util.read_json(util.root() / "overrides" / Path(rel).name))
        if ov is not None:
            obj = deep_merge(obj, ov)
        target = d / rel
        if target.exists():
            prev = target.with_name(target.name + ".prev")
            try:
                prev.write_bytes(target.read_bytes())
            except OSError:
                pass
        util.atomic_write_json(target, obj)
        written.append(rel)
    util.atomic_write_json(util.root() / "state" / "desk-state-last.json",
                           {"at_pt": util.now_pt_str(), "written": written, "rejected": rejected})
    return {"ok": not rejected, "written": written, "rejected": rejected}


def token_handoff() -> tuple[int, Any]:
    """One-time write-token handoff to the box mirror (read-token auth, over Tailscale).

    Armed only by `oidctl token-handoff --minutes N` (writes <root>/state/token-handoff.json with an expiry).
    Served at most once, then disarmed. Avoids ever pasting the token into chat or a terminal.
    """
    f = util.root() / "state" / "token-handoff.json"
    st = util.read_json(f) or {}
    if not st or time.time() > float(st.get("expires_epoch") or 0):
        f.unlink(missing_ok=True)
        return 404, {"error": "handoff_not_armed"}
    tok = _token("OID_DESK_WRITE_TOKEN")
    f.unlink(missing_ok=True)
    if not tok:
        return 503, {"error": "token_not_configured"}
    return 200, {"name": "OID_DESK_WRITE_TOKEN", "value": tok}


def health() -> dict:
    r = util.root()
    flags = sorted(p.stem for p in (r / "flags").glob("*.disabled")) if (r / "flags").exists() else []
    return {"service": "oid-mini-desk-api", "version": __version__, "at_pt": util.now_pt_str(),
            "desk": str(util.desk()), "disabled_jobs": flags,
            "keys_present": {k: bool(_token(k)) for k in KEY_NAMES}, "named_read_tokens": len(tokens.names())}


class Handler(BaseHTTPRequestHandler):
    server_version = "oid-mini-desk/" + __version__
    cat_cache: dict[str, Any] = {"at": 0.0, "cat": None}
    lock = threading.Lock()

    def log_message(self, fmt: str, *args: Any) -> None:  # no request logging (headers carry tokens)
        return

    def _cat(self) -> dict:
        with self.lock:
            if time.time() - self.cat_cache["at"] > 10 or self.cat_cache["cat"] is None:
                self.cat_cache["cat"] = catalog.load()
                self.cat_cache["at"] = time.time()
            return self.cat_cache["cat"]

    def _send(self, code: int, body: Any, *, raw: Optional[bytes] = None, ctype: str = "application/json",
              headers: Optional[dict] = None) -> None:
        data = raw if raw is not None else (json.dumps(body, default=str) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _auth(self, name: str) -> bool:
        res = check_bearer(self.headers.get("Authorization"), name)
        if res == "ok":
            return True
        if res == "unconfigured":
            self._send(503, {"error": "token_not_configured", "token": name})
        else:
            self._send(401, {"error": "unauthorized"}, headers={"WWW-Authenticate": 'Bearer realm="oid-mini-desk"'})
        return False

    def _read_auth(self, path: str) -> bool:
        """OID_QUOTE_TOKEN (primary), else a named GET-only read token (not for privileged paths)."""
        hdr = self.headers.get("Authorization")
        res = check_bearer(hdr, "OID_QUOTE_TOKEN")
        if res == "ok":
            return True
        named = tokens.match(hdr)
        if named:
            if path in NAMED_DENY:
                self._send(403, {"error": "forbidden_for_named_read_token"})
                return False
            tokens.note_use(named, tokens.source_ip(*self.client_address[:2]) or self.client_address[0])
            return True
        if res == "unconfigured" and not tokens.names():
            self._send(503, {"error": "token_not_configured", "token": "OID_QUOTE_TOKEN"})
        else:
            self._send(401, {"error": "unauthorized"}, headers={"WWW-Authenticate": 'Bearer realm="oid-mini-desk"'})
        return False

    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/v1/health"):
                return self._send(200, health())
            if u.path == "/v1/read-token-handoff":
                name = (q.get("name") or [""])[0]
                code, body = tokens.serve_handoff(name, self.headers.get("X-OID-Handoff-Code"),
                                                  self.client_address[0], self.client_address[1])
                return self._send(code, body)
            if u.path.startswith("/v1/archive/"):  # 2026-10-18: read-only archive routes, own token (SCHEMAS.md §10)
                try:
                    from oid_archive import api_routes
                except ImportError:
                    return self._send(503, {"error": "archive_not_installed"})
                code, body, ctype = api_routes.handle(u.path, q, self.headers.get("Authorization"))
                if isinstance(body, (bytes, bytearray)):
                    return self._send(code, None, raw=bytes(body), ctype=ctype)
                return self._send(code, body)
            if not self._read_auth(u.path):
                return None
            cat = self._cat()
            if u.path == "/v1/feeds":
                groups = [g for v in q.get("group", []) for g in v.split(",") if g] or None
                return self._send(200, {"at_pt": util.now_pt_str(), "feeds": catalog.manifest(cat, groups=groups)})
            if u.path == "/v1/feed":
                name = (q.get("name") or [""])[0]
                allowed = catalog.expand(cat)
                if name not in allowed:
                    return self._send(404, {"error": "unknown_feed"})
                p = util.desk() / name
                data = p.read_bytes()
                import hashlib
                return self._send(200, None, raw=data, ctype="application/octet-stream",
                                  headers={"X-OID-SHA256": hashlib.sha256(data).hexdigest(),
                                           "X-OID-Group": allowed[name], "X-OID-Mtime": str(p.stat().st_mtime)})
            if u.path == "/v1/desk-write-token":
                with self.lock:
                    code, body = token_handoff()
                return self._send(code, body)
            if u.path in GROUP_ROUTES:
                out = {}
                for rel in catalog.expand(cat, groups=GROUP_ROUTES[u.path]):
                    p = util.desk() / rel
                    if p.suffix == ".json" and p.stat().st_size <= MAX_GROUP_FILE:
                        out[rel] = util.read_json(p)
                return self._send(200, {"at_pt": util.now_pt_str(), "files": out})
            return self._send(404, {"error": "not_found"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": type(e).__name__})

    def do_POST(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        if u.path != "/v1/desk-state":
            return self._send(404, {"error": "not_found"})
        if not self._auth("OID_DESK_WRITE_TOKEN"):
            return None
        cat = self._cat()
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > int(cat.get("desk_state_max_bytes", 4_000_000)):
            return self._send(413, {"error": "bad_size"})
        try:
            body = json.loads(self.rfile.read(n))
            files = body.get("files")
            assert isinstance(files, dict) and files
        except Exception:  # noqa: BLE001
            return self._send(400, {"error": "bad_json"})
        res = apply_desk_state(files, cat)
        return self._send(200 if res["ok"] else 207, res)


def serve(host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini data API")
    ap.add_argument("--host", default=os.environ.get("OID_DESK_API_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("OID_DESK_API_PORT", "8788")))
    a = ap.parse_args(argv)
    catalog.load()  # fail fast on a bad catalog
    util.log("data-api", f"listening {a.host}:{a.port} v{__version__}")
    serve(a.host, a.port).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
