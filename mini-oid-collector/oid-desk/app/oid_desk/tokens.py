"""Named, revocable, GET-only read tokens + one-time IP-bound handoff.

Files (values never printed or logged):
  <secrets>/read-tokens/<name>             token value, mode 600 (dir 700). Presence = active; revoke = delete.
  <root>/state/read-token-handoff/<name>.json   armed handoff: {from_ip, expires_epoch, code_sha256, failures} (600)
  <root>/state/read-tokens-usage.json      per-name last_used_pt / count / last_ip (no values)

Rules enforced by api.py:
  * named tokens authenticate GET read endpoints only (feeds, feed, group routes); never POST /v1/desk-state,
    never /v1/desk-write-token, never /v1/read-token-handoff.
  * OID_QUOTE_TOKEN stays the primary read token (box mirror); OID_DESK_WRITE_TOKEN is never a read token.
  * Tokens are re-read from disk on each request, so add/revoke take effect immediately (no restart).
Handoff: `oidctl read-token handoff <name> --from <tailscale ip>` prints a one-time code to whoever runs it.
GET /v1/read-token-handoff?name=<name> with header X-OID-Handoff-Code answers once, only from that IP, within
the window; 5 wrong codes disarm it. The code is useless after the token is fetched or the window closes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Optional

from . import util

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
MAX_FAILURES = 5
_lock = threading.Lock()


def tokens_dir() -> Path:
    return util.secrets_dir() / "read-tokens"


def handoff_dir() -> Path:
    return util.root() / "state" / "read-token-handoff"


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name or ""))


def _write_600(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def names() -> list[str]:
    d = tokens_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and valid_name(p.name))


def _value(name: str) -> Optional[str]:
    try:
        v = (tokens_dir() / name).read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        return None


def match(header: Optional[str]) -> Optional[str]:
    """Name of the named read token presented as 'Bearer <tok>', else None. Constant-time per candidate."""
    if not header or not header.startswith("Bearer "):
        return None
    got = header[7:].strip().encode()
    hit = None
    for n in names():
        v = _value(n)
        if v and hmac.compare_digest(got, v.encode()):
            hit = n
    return hit


def note_use(name: str, ip: str) -> None:
    f = util.root() / "state" / "read-tokens-usage.json"
    with _lock:
        st = util.read_json(f) or {}
        row = st.get(name) or {"count": 0}
        row.update(count=int(row.get("count", 0)) + 1, last_used_pt=util.now_pt_str(), last_ip=ip)
        st[name] = row
        try:
            util.atomic_write_json(f, st)
        except OSError:
            pass


def add(name: str, *, rotate: bool = False) -> str:
    if not valid_name(name):
        raise ValueError("bad name (a-z, 0-9, '-', 2-32 chars)")
    p = tokens_dir() / name
    if p.exists() and not rotate:
        raise FileExistsError(f"read token {name} exists (use --rotate to replace)")
    _write_600(p, (secrets.token_urlsafe(32) + "\n").encode())
    return f"read token {name} {'rotated' if rotate else 'created'} at {p} (600, value not printed)"


def revoke(name: str) -> str:
    if not valid_name(name):
        raise ValueError("bad name")
    p = tokens_dir() / name
    h = handoff_dir() / f"{name}.json"
    h.unlink(missing_ok=True)
    if not p.exists():
        return f"read token {name} not present (nothing to revoke)"
    try:  # best effort overwrite before unlink
        _write_600(p, b"revoked\n")
    finally:
        p.unlink(missing_ok=True)
    return f"read token {name} revoked (file removed; effective immediately)"


def listing() -> list[dict]:
    usage = util.read_json(util.root() / "state" / "read-tokens-usage.json") or {}
    out = []
    for n in names():
        st = (tokens_dir() / n).stat()
        h = util.read_json(handoff_dir() / f"{n}.json") or {}
        armed = bool(h) and time.time() < float(h.get("expires_epoch") or 0)
        out.append({"name": n, "created_pt": util.now_pt_str(st.st_mtime), "mode": oct(st.st_mode & 0o777),
                    "last_used_pt": (usage.get(n) or {}).get("last_used_pt"), "uses": (usage.get(n) or {}).get("count", 0),
                    "handoff_armed": armed, "handoff_from": h.get("from_ip") if armed else None})
    return out


def _sha(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def arm_handoff(name: str, from_ip: str, minutes: int = 30) -> str:
    """Arm a one-time handoff; returns the one-time code (show only to the operator)."""
    import ipaddress
    if name not in names():
        raise FileNotFoundError(f"read token {name} does not exist (oidctl read-token add {name})")
    ipaddress.ip_address(from_ip)  # raises on garbage
    minutes = max(1, min(int(minutes), 60))
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
    code = "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))  # ~80 bits
    import json
    _write_600(handoff_dir() / f"{name}.json", json.dumps(
        {"name": name, "from_ip": from_ip, "armed_pt": util.now_pt_str(), "expires_epoch": time.time() + minutes * 60,
         "code_sha256": _sha(code), "failures": 0}).encode())
    return code


def ts_socket() -> Path:
    return Path(os.environ.get("OID_TS_SOCKET", str(Path.home() / "oid-quote" / "tailscale" / "tailscaled.sock")))


def _whois_local(port: int, timeout: float = 2.0) -> Optional[str]:
    """Tailnet IPv4 of the peer behind a userspace-netstack proxied connection (seen locally as 127.0.0.1:port).

    Asks tailscaled's LocalAPI (unix socket) /localapi/v0/whois?addr=127.0.0.1:<port>; tailscaled maps its own
    loopback proxy connections back to the WireGuard-authenticated peer. None if unknown (=> deny)."""
    import json
    import socket
    sock = ts_socket()
    if not sock.exists():
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(sock))
        s.sendall((f"GET /localapi/v0/whois?addr=127.0.0.1:{int(port)} HTTP/1.0\r\nHost: local-tailscaled.sock\r\n"
                   "Sec-Tailscale: localapi\r\n\r\n").encode())
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        head, _, body = buf.partition(b"\r\n\r\n")
        if b" 200 " not in head.split(b"\r\n", 1)[0]:
            return None
        node = (json.loads(body) or {}).get("Node") or {}
        for a in node.get("Addresses") or []:
            ip = a.split("/")[0]
            if ip.count(".") == 3:
                return ip
    except (OSError, ValueError):
        return None
    return None


_WHOIS = _whois_local  # tests replace this


def source_ip(client_ip: str, client_port: int) -> Optional[str]:
    """Authenticated source for handoff checks: the tailnet peer IP. Loopback (userspace tailscaled proxy) is
    resolved via tailscaled whois; a direct 100.64.0.0/10 address is taken as is; anything else is None."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(client_ip.split("%")[0].replace("::ffff:", ""))
    except ValueError:
        return None
    if ip.is_loopback:
        return _WHOIS(client_port)
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return str(ip)
    return None


def serve_handoff(name: str, code: Optional[str], client_ip: str, client_port: int = 0) -> tuple[int, dict]:
    import json
    if not valid_name(name):
        return 404, {"error": "handoff_not_armed"}
    f = handoff_dir() / f"{name}.json"
    with _lock:
        st = util.read_json(f) or {}
        if not st or time.time() > float(st.get("expires_epoch") or 0):
            f.unlink(missing_ok=True)
            return 404, {"error": "handoff_not_armed"}
        src = source_ip(client_ip, client_port)
        if not src or src != st.get("from_ip"):
            return 403, {"error": "wrong_source"}
        if not code or not hmac.compare_digest(_sha(code), str(st.get("code_sha256"))):
            st["failures"] = int(st.get("failures", 0)) + 1
            if st["failures"] >= MAX_FAILURES:
                f.unlink(missing_ok=True)
                return 401, {"error": "bad_code", "disarmed": True}
            _write_600(f, json.dumps(st).encode())
            return 401, {"error": "bad_code"}
        tok = _value(name)
        f.unlink(missing_ok=True)  # single use, success or not
        if not tok:
            return 404, {"error": "token_missing"}
        util.log("data-api", f"read-token handoff served: {name} -> {src}")
        return 200, {"name": name, "value": tok}
