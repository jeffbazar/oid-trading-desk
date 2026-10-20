"""Alpaca market-data REST (data only: data.alpaca.markets). Keys from the mini secrets; never logged."""
from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlencode

from . import net, util

BASE = "https://data.alpaca.markets"


def _headers() -> dict:
    k, s = util.read_secret("APCA_API_KEY_ID"), util.read_secret("APCA_API_SECRET_KEY")
    if not k or not s:
        raise RuntimeError("alpaca keys missing")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def snapshots(symbols: Iterable[str], feed: str = "sip") -> dict[str, Any]:
    syms = sorted({s.upper() for s in symbols if s})
    out: dict[str, Any] = {}
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        url = f"{BASE}/v2/stocks/snapshots?" + urlencode({"symbols": ",".join(chunk), "feed": feed})
        d = net.get_json(url, headers=_headers(), timeout=15)
        out.update(d if isinstance(d, dict) else {})
    return out
