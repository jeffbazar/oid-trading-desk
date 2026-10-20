"""Pluggable VIX source. config/mini-desk.json "vix": {source, fallbacks, agent_max_age_s}.

agent_rh      market-data/latest/vix-agent.json (box: scripts/vix_agent_ingest.py from one RH get_index_quotes read,
              pushed to the mini via desk-state)                                     DEFAULT (Jeffrey 2026-10-10)
cboe_delayed  https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json (public, ~15 min delayed)
fred          FRED VIXCLS daily close (lagged 1 session)
Returns {"value", "prev_close", "as_of", "source", "delayed", "error"}.
"""
from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import net, util

CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"


def _agent_rh(cfg: dict) -> dict:
    rec = util.read_json(util.desk() / "market-data" / "latest" / "vix-agent.json")
    if not isinstance(rec, dict):
        return {"error": "vix-agent.json missing"}
    p = rec.get("payload") or {}
    try:
        as_of = datetime.strptime(rec["as_of"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (KeyError, ValueError):
        return {"error": "vix-agent.json bad as_of"}
    age = time.time() - as_of
    if age > float(cfg.get("agent_max_age_s", 5400)) and util.session() != "closed":
        return {"error": f"vix-agent.json stale {int(age)}s"}
    return {"value": p.get("value"), "prev_close": p.get("prev_close"), "as_of": rec["as_of"],
            "source": "robinhood get_index_quotes (agent read)", "delayed": False}


def _flashalpha_live(cfg: dict) -> dict:
    """10/14 arch R4: real-time VIX written every 120 s by oid_desk.vix_live (FlashAlpha index feed)."""
    rec = util.read_json(util.desk() / "market-data" / "latest" / "vix-live.json")
    if not isinstance(rec, dict) or not (rec.get("payload") or {}).get("value"):
        return {"error": "vix-live.json missing"}
    try:
        as_of = datetime.strptime(rec["as_of"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (KeyError, ValueError):
        return {"error": "vix-live.json bad as_of"}
    age = time.time() - as_of
    if age > float(cfg.get("live_max_age_s", 600)) and util.session() != "closed":
        return {"error": f"vix-live.json stale {int(age)}s"}
    p = rec["payload"]
    return {"value": p.get("value"), "prev_close": None, "as_of": rec["as_of"],
            "source": "FlashAlpha /stockquote/VIX (real-time)", "delayed": False}


def _cboe(cfg: dict) -> dict:
    d = net.get_json(CBOE_URL, timeout=10).get("data") or {}
    return {"value": d.get("current_price"), "prev_close": d.get("prev_day_close"),
            "as_of": d.get("last_trade_time"), "source": "cboe delayed quotes (public)", "delayed": True}


def fred_series(series_id: str) -> list[tuple[str, float]]:
    txt = net.get_bytes(FRED_CSV.format(id=series_id), timeout=15).decode("utf-8", "replace")
    out = []
    for row in csv.reader(io.StringIO(txt)):
        if len(row) >= 2 and row[0][:2] in ("19", "20"):
            try:
                out.append((row[0], float(row[1])))
            except ValueError:
                continue
    return out


def _fred(cfg: dict) -> dict:
    s = fred_series("VIXCLS")
    if not s:
        return {"error": "VIXCLS empty"}
    prev = s[-2][1] if len(s) > 1 else None
    return {"value": s[-1][1], "prev_close": prev, "as_of": s[-1][0], "source": "FRED VIXCLS (daily close)",
            "delayed": True}


PROVIDERS: dict[str, Callable[[dict], dict]] = {"flashalpha_live": _flashalpha_live, "agent_rh": _agent_rh, "cboe_delayed": _cboe, "fred": _fred}


def get_vix(cfg: Optional[dict] = None) -> dict:
    cfg = cfg if cfg is not None else (util.desk_config("mini-desk.json").get("vix") or {})
    order = [cfg.get("source", "agent_rh")] + [s for s in cfg.get("fallbacks", []) if s != cfg.get("source")]
    errors: dict[str, Any] = {}
    for name in order:
        fn = PROVIDERS.get(name)
        if fn is None:
            errors[name] = "unknown provider"
            continue
        try:
            r = fn(cfg)
        except Exception as e:  # noqa: BLE001
            r = {"error": f"{type(e).__name__}"}
        if not r.get("error") and r.get("value") is not None:
            r["provider"] = name
            r["fallback_used"] = name != order[0]
            r["errors"] = errors
            return r
        errors[name] = r.get("error") or "no value"
    return {"value": None, "provider": None, "error": "all VIX providers failed", "errors": errors}
