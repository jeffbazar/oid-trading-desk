"""Alpaca market-data REST (data.alpaca.markets, data-only) for backfill / reconcile. Paged, rate-limited, every
call logged to fetch_log. Keys come from env APCA_API_KEY_ID/APCA_API_SECRET_KEY or the mini secrets files and are
never logged, printed or written anywhere."""
from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from .common import JsonlWriter, common, iso_ns, now_ns

BASE = os.environ.get("OID_ALPACA_DATA_URL", "https://data.alpaca.markets")
KEY_DIR = os.environ.get("OID_ALPACA_SECRETS_DIR", "~/oid-quote/secrets")


def _keys() -> tuple[str, str]:
    k, s = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    if not (k and s):
        d = Path(KEY_DIR).expanduser()
        try:
            k, s = (d / "APCA_API_KEY_ID").read_text().strip(), (d / "APCA_API_SECRET_KEY").read_text().strip()
        except OSError:
            k = s = None
    if not (k and s):
        raise RuntimeError("alpaca keys missing")
    return k, s


class Client:
    def __init__(self, component: str, max_per_min: int = 150, fetch_log: Optional[JsonlWriter] = None,
                 opener: Optional[Callable] = None, sleep: Callable[[float], None] = time.sleep):
        self.component, self.max_per_min = component, max_per_min
        self.flog = fetch_log
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self.calls: list[float] = []
        self.n_calls = 0
        self.bytes = 0
        self.last_rl: dict[str, Any] = {}

    def _throttle(self) -> None:
        t = time.time()
        self.calls = [c for c in self.calls if t - c < 60]
        if len(self.calls) >= self.max_per_min:
            self.sleep(max(0.05, 60 - (t - self.calls[0])))
        rem, reset = self.last_rl.get("remaining"), self.last_rl.get("reset")
        if rem is not None and rem < 50 and reset:  # well under Alpaca's limit: back off to the reset
            self.sleep(min(60.0, max(0.5, reset - time.time())))

    def get(self, path: str, params: dict[str, Any], symbols: str = "", retries: int = 4) -> dict[str, Any]:
        url = f"{BASE}{path}?{urlencode(params)}"
        k, s = _keys()
        last_err = None
        for attempt in range(retries + 1):
            self._throttle()
            started = now_ns()
            self.calls.append(time.time())
            self.n_calls += 1
            status, body, hdrs, err_class, err_msg = None, None, {}, None, None
            try:
                req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s,
                                                           "Accept": "application/json", "Accept-Encoding": "gzip"})
                with self.opener(req, timeout=30) as r:
                    status, hdrs = r.status, {k.lower(): v for k, v in r.headers.items()}
                    raw = r.read()
                    if hdrs.get("content-encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    body = raw
            except urllib.error.HTTPError as e:
                status, hdrs = e.code, {k.lower(): v for k, v in (e.headers or {}).items()}
                err_class, err_msg = ("auth" if e.code in (401, 403) else "http"), f"HTTP {e.code}"
            except Exception as e:  # noqa: BLE001
                err_class, err_msg = ("timeout" if "timed out" in str(e).lower() else "http"), type(e).__name__
            fin = now_ns()
            rl = {"limit": _int(hdrs.get("x-ratelimit-limit")), "remaining": _int(hdrs.get("x-ratelimit-remaining")),
                  "reset": _int(hdrs.get("x-ratelimit-reset"))}
            self.last_rl = rl
            data, n_items = None, None
            if body is not None:
                self.bytes += len(body)
                try:
                    data = json.loads(body)
                    bars = data.get("bars")
                    n_items = sum(len(v) for v in bars.values()) if isinstance(bars, dict) else (len(bars) if isinstance(bars, list) else None)
                except ValueError:
                    err_class, err_msg = "parse", "bad json"
            self._log(path, params, symbols, started, fin, status, n_items, len(body or b""), rl, err_class, err_msg)
            if data is not None and err_class is None:
                return data
            last_err = err_msg
            if status in (401, 403, 422, 400):
                break
            self.sleep(min(30.0, 2.0 ** attempt))
        raise RuntimeError(f"alpaca GET {path} failed: {last_err}")

    def _log(self, path, params, symbols, started, fin, status, n_items, nbytes, rl, err_class, err_msg) -> None:
        if not self.flog:
            return
        safe = {k: v for k, v in params.items() if k not in ("page_token",)}
        if "page_token" in params:
            safe["page_token"] = "<set>"
        row = {"fetch_id": f"{self.component}-{started}", "component": self.component,
               "endpoint": f"data.alpaca.markets{path}", "method": "GET", "params_redacted": json.dumps(safe, sort_keys=True),
               "surge_id": None, "symbols": symbols, "started_ns": started, "started_iso": iso_ns(started),
               "finished_ns": fin, "latency_ms": (fin - started) / 1e6, "http_status": status, "n_items": n_items,
               "bytes": nbytes, "rate_limit_limit": rl["limit"], "rate_limit_remaining": rl["remaining"],
               "rate_limit_reset_ns": rl["reset"] * 1_000_000_000 if rl["reset"] else None, "est_cost_usd": 0.0,
               "error_class": err_class, "error_msg": (err_msg or None) and err_msg[:300]}
        row.update(common(started, fin))
        self.flog.write([row])

    def bars(self, symbols: list[str], timeframe: str, start_iso: str, end_iso: str, adjustment: str = "raw",
             feed: str = "sip", max_pages: int = 500) -> dict[str, list[dict[str, Any]]]:
        """All pages of /v2/stocks/bars for the symbols. Returns {SYM: [bar, ...]} (Alpaca t,o,h,l,c,v,n,vw)."""
        out: dict[str, list] = {}
        params = {"symbols": ",".join(symbols), "timeframe": timeframe, "start": start_iso, "end": end_iso,
                  "adjustment": adjustment, "feed": feed, "limit": 10000, "sort": "asc"}
        for _ in range(max_pages):
            d = self.get("/v2/stocks/bars", params, symbols=",".join(symbols) if len(symbols) <= 5 else f"{len(symbols)} symbols")
            for sym, bs in (d.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bs or [])
            tok = d.get("next_page_token")
            if not tok:
                return out
            params = dict(params, page_token=tok)
        raise RuntimeError("too many pages")


def _int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
