"""Shared helpers. Paths come from env so the same code runs on the mini and in box tests.

OID_DESK_ROOT   install root (mini default ~/oid-desk)          -> flags/, launchd/, logs/, overrides/
OID_DESK_DIR    desk tree (default <root>/desk)                 -> same relative layout as the box desk
OID_SECRETS_DIR vendor secrets (default ~/oid-quote/secrets)    -> files read, never printed
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")


def root() -> Path:
    return Path(os.environ.get("OID_DESK_ROOT", str(Path.home() / "oid-desk"))).expanduser()


def desk() -> Path:
    return Path(os.environ.get("OID_DESK_DIR", str(root() / "desk"))).expanduser()


def secrets_dir() -> Path:
    return Path(os.environ.get("OID_SECRETS_DIR", str(Path.home() / "oid-quote" / "secrets"))).expanduser()


def read_secret(name: str) -> Optional[str]:
    """Env first (launchd wrapper exports it), then the secrets file. Never logged."""
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = secrets_dir() / name
    try:
        v = p.read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        return None


def now_pt_str(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else time.time(), PT)
    return dt.strftime("%Y-%m-%d %-I:%M:%S %p PT")


def utc_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, (json.dumps(obj, indent=1, default=str) + "\n").encode("utf-8"))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def desk_config(name: str) -> dict:
    d = read_json(desk() / "config" / name)
    return d if isinstance(d, dict) else {}


def session() -> str:
    """rth | pre | ah | overnight | closed via the desk's own calendar (quotes/mini_client.current_session)."""
    q = str(desk() / "quotes")
    if q not in sys.path:
        sys.path.insert(0, q)
    try:
        import mini_client  # type: ignore
        return mini_client.current_session()
    except Exception:  # noqa: BLE001
        return "closed"


def ext_bucket(sess: str) -> str:
    return "rth" if sess == "rth" else ("closed" if sess == "closed" else "ext")


def write_feed(feed: str, *, source: str, writer: str, symbols: list[str], payload: Any,
               ttl_seconds: int, error: Optional[str] = None) -> dict:
    """Same envelope as market-data/cache_io.write_feed, written into <desk>/market-data/latest/."""
    rec = {"as_of": utc_iso(), "as_of_pt": now_pt_str(), "source": source, "writer": writer, "feed": feed,
           "symbols": list(symbols or []), "ttl_seconds": ttl_seconds, "payload": payload, "error": error}
    atomic_write_json(desk() / "market-data" / "latest" / f"{feed}.json", rec)
    return rec


def log(job: str, msg: str) -> None:
    line = f"{now_pt_str()} [{job}] {msg}\n"
    try:
        d = root() / "logs"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{job}.log"
        if p.exists() and p.stat().st_size > 5_000_000:
            p.replace(p.with_suffix(".log.1"))
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    sys.stderr.write(line)
