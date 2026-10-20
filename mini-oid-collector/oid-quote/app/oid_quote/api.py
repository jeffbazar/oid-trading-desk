"""HTTP API (aiohttp): /v1/health (open), /v1/quotes and /v1/options (Bearer token)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import web

from . import __version__
from .timeutil import now, now_pt_iso

if TYPE_CHECKING:
    from .app import Collector

MAX_SYMBOLS_PER_REQUEST = 1000


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


def _parse_symbols(request: web.Request, *names: str) -> list[str] | None:
    vals: list[str] = []
    for n in names:
        for raw in request.query.getall(n, []):
            vals.extend(p.strip().upper() for p in raw.split(",") if p.strip())
    if not vals:
        return None
    seen: set[str] = set()
    out = [v for v in vals if not (v in seen or seen.add(v))]
    return out[:MAX_SYMBOLS_PER_REQUEST]


def build_app(collector: "Collector") -> web.Application:
    app = web.Application()

    def _auth(request: web.Request) -> web.Response | None:
        res = collector.tokens.check(request.headers.get("Authorization"))
        if res == "ok":
            return None
        if res == "unconfigured":
            return _json({"error": "token_not_configured", "detail": "create <root>/secrets/OID_QUOTE_TOKEN"}, 503)
        resp = _json({"error": "unauthorized"}, 401)
        resp.headers["WWW-Authenticate"] = 'Bearer realm="oid-quote"'
        return resp

    async def health(request: web.Request) -> web.Response:
        return _json(collector.health())

    async def _rows(request: web.Request, kind: str, params: tuple[str, ...]) -> web.Response:
        denied = _auth(request)
        if denied is not None:
            return denied
        stream = collector.stream_for(kind)
        wanted = _parse_symbols(request, *params)
        t = now()
        connected = bool(stream and stream.connected)
        is_sub = stream.is_subscribed if stream else (lambda s: False)
        symbols = wanted if wanted is not None else collector.cache.symbols(kind)
        rows: dict[str, Any] = {}
        missing: list[str] = []
        for s in symbols:
            v = collector.cache.view(kind, s, connected, is_sub, t)
            if v is None:
                missing.append(s)
            else:
                rows[s] = v
        key = "options" if kind == "option" else "quotes"
        return _json(
            {
                "as_of": now_pt_iso(),
                "status": collector.status(),
                "feed": stream.health(t) if stream else None,
                "count": len(rows),
                key: rows,
                "missing": missing,
            }
        )

    async def quotes(request: web.Request) -> web.Response:
        return await _rows(request, "equity", ("symbols", "symbol"))

    async def options(request: web.Request) -> web.Response:
        return await _rows(request, "option", ("contracts", "symbols", "contract"))

    async def get_option_subs(request: web.Request) -> web.Response:
        denied = _auth(request)
        if denied is not None:
            return denied
        return _json(collector.option_subs_view())

    async def put_option_subs(request: web.Request) -> web.Response:
        """v0.3.0: replace the OCC subscription list (same validation/cap as options-subs.json)."""
        denied = _auth(request)
        if denied is not None:
            return denied
        if request.content_length is not None and request.content_length > 256_000:
            return _json({"error": "payload_too_large"}, 413)
        try:
            data = await request.json()
        except Exception:
            return _json({"error": "bad_json"}, 400)
        source = request.headers.get("X-OID-Client") or (data.get("source") if isinstance(data, dict) else None)
        try:
            res = collector.set_option_subs(data, source=str(source) if source else None)
        except ValueError as e:
            return _json({"error": "bad_payload", "detail": str(e)[:200]}, 400)
        return _json(res)

    async def live_volume(request: web.Request) -> web.Response:
        """live volume v1 (2026-10-18): rolling 1s/10s/30s/60s SIP print volume, rvol vs same-minute norm,
        partial + last closed 1-min bar, day high/low; options section = held OPRA contracts."""
        denied = _auth(request)
        if denied is not None:
            return denied
        if getattr(collector, "livevol", None) is None:
            return _json({"error": "live_volume_disabled"}, 404)
        syms = _parse_symbols(request, "symbols", "symbol")
        occs = _parse_symbols(request, "contracts", "contract")
        detail = request.query.get("detail", "0") in ("1", "true", "yes")
        out = collector.live_volume_view(syms, occs, detail)
        try:
            n_ev = int(request.query.get("events", "0") or 0)
        except ValueError:
            n_ev = 0
        if n_ev > 0:
            from .livevol import read_vol_surge
            out["vol_surge"] = read_vol_surge(collector.cfg.vol_surge_state_dir, min(n_ev, 200))
        return _json(out)

    async def root(request: web.Request) -> web.Response:
        return _json({"service": "oid-quote-collector", "version": __version__, "endpoints": ["/v1/health", "/v1/quotes?symbols=", "/v1/options?contracts=", "GET|PUT /v1/options/subs", "/v1/bars?symbols=&timeframe=5Min&start=&end=", "/v1/live-volume?symbols=&contracts=&detail=1&events=20"]})

    app.router.add_get("/", root)
    app.router.add_get("/v1/health", health)
    app.router.add_get("/v1/quotes", quotes)
    app.router.add_get("/v1/options", options)
    app.router.add_get("/v1/options/subs", get_option_subs)
    app.router.add_put("/v1/options/subs", put_option_subs)
    app.router.add_post("/v1/options/subs", put_option_subs)
    app.router.add_get("/v1/live-volume", live_volume)
    from .bars import register_bars  # bars v1 (2026-10-10): GET /v1/bars, additive

    register_bars(app, collector, _auth, _json)
    return app
