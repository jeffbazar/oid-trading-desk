"""Tiny stdlib HTTP GET helper (no proxy; injectable for tests). Never logs headers or keys."""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable, Optional

Opener = Callable[[urllib.request.Request, float], bytes]


def _default_open(req: urllib.request.Request, timeout: float) -> bytes:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as fh:
        return fh.read()


_OPENER: Opener = _default_open


def set_opener(fn: Optional[Opener]) -> None:
    global _OPENER
    _OPENER = fn or _default_open


def get_bytes(url: str, headers: Optional[dict] = None, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "oid-mini-desk/0.1", **(headers or {})})
    return _OPENER(req, timeout)


def get_json(url: str, headers: Optional[dict] = None, timeout: float = 15.0) -> Any:
    return json.loads(get_bytes(url, headers, timeout))
