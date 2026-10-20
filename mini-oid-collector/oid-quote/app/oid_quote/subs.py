"""Subscription sources: stock allowlist (core-20) and dynamic options-subs.json (OCC symbols, cap 1000)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("oid_quote.subs")

STOCK_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
# OCC/Alpaca option symbol: ROOT(1-6) YYMMDD C|P STRIKE*1000 (8 digits), e.g. NVDA261016C00190000
OCC_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}\d{6}[CP]\d{8}$")


@dataclass
class SubsState:
    symbols: list[str] = field(default_factory=list)
    requested: int = 0
    invalid: list[str] = field(default_factory=list)
    truncated: int = 0
    error: str | None = None
    path: str = ""
    mtime: float | None = None


def _extract_list(data: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
    raise ValueError(f"expected a JSON list or an object with one of {list(keys)}")


def _normalize(raw: list[Any], pattern: re.Pattern[str]) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    good: list[str] = []
    bad: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("symbol") or item.get("contract_id") or item.get("occ")
        if not isinstance(item, str):
            bad.append(repr(item)[:40])
            continue
        s = item.strip().upper().replace(" ", "")
        if s.startswith("O:"):  # tolerate Polygon-style prefix
            s = s[2:]
        if not pattern.match(s):
            bad.append(item[:40])
            continue
        if s not in seen:
            seen.add(s)
            good.append(s)
    return good, bad


class FileSubs:
    """Re-reads a JSON subscription file when its mtime changes. Bad JSON keeps the previous good list."""

    def __init__(self, path: Path, kind: str, cap: int | None = None):
        self.path = path
        self.kind = kind  # "stock" | "option"
        self.cap = cap
        self.state = SubsState(path=str(path))
        self._missing = False

    def reload_if_changed(self) -> bool:
        try:
            m = self.path.stat().st_mtime
        except FileNotFoundError:
            if self._missing:
                return False
            self._missing = True
            changed = bool(self.state.symbols)
            self.state = SubsState(path=str(self.path), error="file not found" if self.kind == "stock" else None)
            if self.kind == "stock":
                log.warning("stock allowlist not found: %s", self.path)
            return changed
        self._missing = False
        if m == self.state.mtime:
            return False
        try:
            data = json.loads(self.path.read_text() or "[]")
            if self.kind == "stock":
                raw = _extract_list(data, ("underlyings", "symbols"))
                good, bad = _normalize(raw, STOCK_RE)
            else:
                raw = _extract_list(data, ("contracts", "symbols", "options"))
                good, bad = _normalize(raw, OCC_RE)
        except Exception as e:  # keep previous list
            self.state.mtime = m
            self.state.error = f"{type(e).__name__}: {e}"[:200]
            log.warning("could not parse %s (%s); keeping previous %d symbols", self.path, self.state.error, len(self.state.symbols))
            return False
        truncated = 0
        if self.cap is not None and len(good) > self.cap:
            truncated = len(good) - self.cap
            log.warning("%s: %d contracts exceeds cap %d; dropping last %d", self.path.name, len(good), self.cap, truncated)
            good = good[: self.cap]
        if bad:
            log.warning("%s: ignoring %d invalid symbols (e.g. %s)", self.path.name, len(bad), bad[:3])
        changed = good != self.state.symbols
        self.state = SubsState(symbols=good, requested=len(raw), invalid=bad[:20], truncated=truncated, error=None, path=str(self.path), mtime=m)
        if changed:
            log.info("%s subscriptions loaded from %s: %d symbols", self.kind, self.path, len(good))
        return changed

    @property
    def symbols(self) -> list[str]:
        return list(self.state.symbols)

    def health(self) -> dict[str, Any]:
        s = self.state
        return {"path": s.path, "count": len(s.symbols), "requested": s.requested, "invalid": s.invalid, "truncated": s.truncated, "error": s.error}


def normalize_option_list(data: Any, cap: int | None = None) -> tuple[list[str], list[str], int]:
    """Validate an options-subs payload (list or {contracts|symbols|options: [...]}) -> (good, invalid, truncated)."""
    raw = _extract_list(data, ("contracts", "symbols", "options"))
    good, bad = _normalize(raw, OCC_RE)
    truncated = 0
    if cap is not None and len(good) > cap:
        truncated = len(good) - cap
        good = good[:cap]
    return good, bad, truncated
