"""Secret loading. Values are never logged or printed; only presence is reported."""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path

KEY_ID = "APCA_API_KEY_ID"
SECRET_KEY = "APCA_API_SECRET_KEY"
TOKEN = "OID_QUOTE_TOKEN"


def _read_secret(secrets_dir: Path, name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    p = secrets_dir / name
    try:
        v = p.read_text().strip()
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return None
    return v or None


def load_alpaca_keys(secrets_dir: Path) -> tuple[str, str] | None:
    k = _read_secret(secrets_dir, KEY_ID)
    s = _read_secret(secrets_dir, SECRET_KEY)
    if not k or not s:
        return None
    return k, s


def key_presence(secrets_dir: Path) -> dict[str, bool]:
    return {
        KEY_ID: bool(_read_secret(secrets_dir, KEY_ID)),
        SECRET_KEY: bool(_read_secret(secrets_dir, SECRET_KEY)),
        TOKEN: bool(_read_secret(secrets_dir, TOKEN)),
    }


class TokenStore:
    """Bearer token from env or <secrets>/OID_QUOTE_TOKEN; file re-read when its mtime changes."""

    def __init__(self, secrets_dir: Path):
        self.path = secrets_dir / TOKEN
        self._mtime: float | None = None
        self._token: str | None = None

    def get(self) -> str | None:
        env = os.environ.get(TOKEN, "").strip()
        if env:
            return env
        try:
            m = self.path.stat().st_mtime
        except FileNotFoundError:
            self._token, self._mtime = None, None
            return None
        if m != self._mtime:
            self._token = _read_secret(self.path.parent, TOKEN)
            self._mtime = m
            if self._token:
                RedactFilter.add_secret(self._token)
        return self._token

    def check(self, auth_header: str | None) -> str:
        """Return 'ok', 'missing', 'invalid' or 'unconfigured'."""
        tok = self.get()
        if not tok:
            return "unconfigured"
        if not auth_header:
            return "missing"
        scheme, _, presented = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not presented:
            return "missing"
        return "ok" if hmac.compare_digest(presented.strip().encode(), tok.encode()) else "invalid"


class RedactFilter(logging.Filter):
    """Belt-and-braces: scrub any known secret value from every log record."""

    _secrets: set[str] = set()

    @classmethod
    def add_secret(cls, value: str | None) -> None:
        if value and len(value) >= 6:
            cls._secrets.add(value)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            msg = record.getMessage()
        except Exception:
            return True
        changed = False
        for s in self._secrets:
            if s in msg:
                msg = msg.replace(s, "[REDACTED]")
                changed = True
        if changed:
            record.msg, record.args = msg, ()
        if record.exc_text:
            for s in self._secrets:
                record.exc_text = record.exc_text.replace(s, "[REDACTED]")
        return True
