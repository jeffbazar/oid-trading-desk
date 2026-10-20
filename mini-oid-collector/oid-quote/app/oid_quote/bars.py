"""GET /v1/bars - Alpaca historical stock bars (SIP) proxied for the OID box (bars v1, 2026-10-10).

Data-only: calls https://data.alpaca.markets/v2/stocks/bars (market data REST) with the mini's
keys; keys never leave the mini and are never logged or returned. Bearer token required.

Query: symbols=NVDA,META (<=30) · timeframe=1Min|5Min|15Min (default 5Min) · start / end RFC3339
(range <= 45 days) · feed=sip|iex (default sip) · adjustment=raw|split (default raw).
Response: {"as_of", "feed", "timeframe", "bars": {SYM: [{t,o,h,l,c,v,n,vw}]}, "source": "alpaca-<feed>-rest"}.
Small in-process TTL cache (30 s when the range touches the last hour, 6 h otherwise).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import aiohttp
from aiohttp import web

BARS_URL = os.environ.get("OID_ALPACA_BARS_URL", "https://data.alpaca.markets/v2/stocks/bars")
TIMEFRAMES = {"1Min", "5Min", "15Min"}
FEEDS = {"sip", "iex"}
MAX_SYMBOLS = 30
MAX_RANGE = timedelta(days=45)
MAX_PAGES = 60


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BarsProxy:
    def __init__(self, keys_provider: Callable[[], tuple[str, str] | None], url: str = BARS_URL):
        self.keys_provider = keys_provider
        self.url = url
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self.stats: dict[str, Any] = {"requests": 0, "upstream_calls": 0, "cache_hits": 0, "last_error": None, "last_at": None}

    async def fetch(self, symbols: list[str], timeframe: str, start: datetime, end: datetime,
                    feed: str = "sip", adjustment: str = "raw", session: aiohttp.ClientSession | None = None) -> dict:
        keys = self.keys_provider()
        if not keys:
            raise PermissionError("no_keys")
        key = (tuple(symbols), timeframe, _iso(start), _iso(end), feed, adjustment)
        hit = self._cache.get(key)
        if hit and hit[0] > time.time():
            self.stats["cache_hits"] += 1
            return hit[1]
        headers = {"APCA-API-KEY-ID": keys[0], "APCA-API-SECRET-KEY": keys[1], "Accept": "application/json"}
        params = {"symbols": ",".join(symbols), "timeframe": timeframe, "start": _iso(start), "end": _iso(end),
                  "feed": feed, "adjustment": adjustment, "limit": "10000", "sort": "asc"}
        out: dict[str, list] = {s: [] for s in symbols}
        own = session is None
        sess = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        try:
            token = None
            for _ in range(MAX_PAGES):
                p = dict(params)
                if token:
                    p["page_token"] = token
                self.stats["upstream_calls"] += 1
                async with sess.get(self.url, params=p, headers=headers) as resp:
                    if resp.status != 200:
                        self.stats["last_error"] = f"HTTP {resp.status}"
                        raise RuntimeError(f"alpaca bars HTTP {resp.status}")
                    body = await resp.json(content_type=None)
                for sym, rows in ((body or {}).get("bars") or {}).items():
                    out.setdefault(sym, []).extend(
                        {k: r.get(k) for k in ("t", "o", "h", "l", "c", "v", "n", "vw")} for r in rows or [])
                token = (body or {}).get("next_page_token")
                if not token:
                    break
        finally:
            if own:
                await sess.close()
        res = {"feed": feed, "timeframe": timeframe, "start": _iso(start), "end": _iso(end),
               "adjustment": adjustment, "source": f"alpaca-{feed}-rest", "bars": out,
               "counts": {s: len(v) for s, v in out.items()}}
        recent = end > datetime.now(timezone.utc) - timedelta(hours=1)
        t_now = time.time()  # drop expired entries first so a 144-symbol backfill does not pin ~200 big responses in RAM
        for k in [k for k, v in self._cache.items() if v[0] <= t_now]:
            self._cache.pop(k, None)
        self._cache[key] = (time.time() + (30 if recent else 6 * 3600), res)
        if len(self._cache) > 200:
            for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:100]:
                self._cache.pop(k, None)
        self.stats["last_error"] = None
        self.stats["last_at"] = datetime.now(timezone.utc).isoformat()
        return res


def register_bars(app: web.Application, collector: Any, auth: Callable, as_json: Callable) -> BarsProxy:
    """Additive route hook: GET /v1/bars (Bearer). Called from api.build_app."""
    proxy = BarsProxy(collector.keys_provider)
    collector.bars_proxy = proxy

    async def bars(request: web.Request) -> web.Response:
        denied = auth(request)
        if denied is not None:
            return denied
        proxy.stats["requests"] += 1
        q = request.query
        syms: list[str] = []
        for raw in q.getall("symbols", []) + q.getall("symbol", []):
            syms.extend(s.strip().upper() for s in raw.split(",") if s.strip())
        syms = list(dict.fromkeys(syms))
        if not syms or len(syms) > MAX_SYMBOLS:
            return as_json({"error": "bad_symbols", "detail": f"1..{MAX_SYMBOLS} symbols"}, 400)
        tf = q.get("timeframe", "5Min")
        feed = q.get("feed", "sip")
        adj = q.get("adjustment", "raw")
        if tf not in TIMEFRAMES or feed not in FEEDS or adj not in ("raw", "split"):
            return as_json({"error": "bad_params", "detail": f"timeframe {sorted(TIMEFRAMES)}, feed {sorted(FEEDS)}"}, 400)
        end = _parse(q.get("end")) or datetime.now(timezone.utc)
        start = _parse(q.get("start")) or (end - timedelta(days=1))
        if start >= end or end - start > MAX_RANGE:
            return as_json({"error": "bad_range", "detail": "start < end, range <= 45 days"}, 400)
        try:
            res = await proxy.fetch(syms, tf, start, end, feed, adj)
        except PermissionError:
            return as_json({"error": "no_keys"}, 503)
        except Exception as e:  # upstream / network; never echo headers
            proxy.stats["last_error"] = str(e)[:120] if "HTTP" in str(e) else type(e).__name__
            return as_json({"error": "upstream", "detail": proxy.stats["last_error"]}, 502)
        return as_json({"as_of": datetime.now().astimezone().isoformat(timespec="milliseconds"), **res})

    app.router.add_get("/v1/bars", bars)
    return proxy
