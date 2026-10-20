#!/usr/bin/env python3
"""Live elevate/invalidate quote gate (mandate 'live RH <=120 s'), both paths coded.

Policy config/live-gate.json: accept_mini (default true, Jeffrey decision pending sign-off), max_age_s 120,
prefer mini|rh, require_rh_for_live_agentic. A quote passes when its age <= max_age_s:
  mini  cache/mini-quotes.json row (Alpaca SIP via Mac mini): age = row age_s at write + file age
  rh    market-data/latest/rh-quotes.json (Rose's RH read): age = now - venue trade time (fallback: file as_of)
accept_mini=false -> RH only (the original mandate). --live-agentic + require_rh_for_live_agentic -> RH only.

  python3 quotes/live_gate.py check NVDA AMZN [--live-agentic] [--json]
exit 0 = every symbol has a passing live quote; 1 = at least one fails (re-pull RH live before elevating).
Research / paper only: this decides nothing on its own and never places orders.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

OID = Path(__file__).resolve().parents[1]
POLICY = OID / "config" / "live-gate.json"
MINI = OID / "cache" / "mini-quotes.json"
RH = OID / "market-data" / "latest" / "rh-quotes.json"
DEFAULT_POLICY = {"accept_mini": True, "max_age_s": 120, "prefer": "mini", "require_rh_for_live_agentic": False}


def _read(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _iso_epoch(s: Any) -> Optional[float]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def policy(path: Path = POLICY) -> dict:
    p = dict(DEFAULT_POLICY)
    p.update({k: v for k, v in (_read(path) or {}).items() if not k.startswith("_")})
    return p


def mini_quote(sym: str, now: float, mini_path: Path = MINI) -> Optional[dict]:
    d = _read(mini_path) or {}
    row = (d.get("quotes") or {}).get(sym)
    if not row or row.get("source") is None or row.get("age_s") is None:
        return None
    if row.get("source") != "mini":
        return None  # rh-quotes fallback rows inside the mini cache are not a mini quote
    file_age = max(0.0, now - float(d.get("written_epoch") or 0))
    price = row.get("last") or row.get("mid")
    return {"source": "mini", "age_s": round(float(row["age_s"]) + file_age, 1), "price": price,
            "bid": row.get("bid"), "ask": row.get("ask")}


def rh_quote(sym: str, now: float, rh_path: Path = RH) -> Optional[dict]:
    d = _read(rh_path) or {}
    row = ((d.get("payload") or {}).get("quotes") or {}).get(sym)
    if not row:
        return None
    ts = _iso_epoch(row.get("venue_last_trade_time")) or _iso_epoch(d.get("as_of"))
    if ts is None:
        return None
    return {"source": "rh", "age_s": round(now - ts, 1), "price": row.get("last"), "bid": row.get("bid"),
            "ask": row.get("ask")}


def check(symbols: list[str], *, live_agentic: bool = False, now: Optional[float] = None, pol: Optional[dict] = None,
          mini_path: Path = MINI, rh_path: Path = RH) -> dict[str, dict]:
    now = now or time.time()
    pol = pol or policy()
    allow_mini = bool(pol["accept_mini"]) and not (live_agentic and pol.get("require_rh_for_live_agentic"))
    order = ["mini", "rh"] if pol.get("prefer", "mini") == "mini" else ["rh", "mini"]
    if not allow_mini:
        order = ["rh"]
    out = {}
    for s in (x.upper() for x in symbols):
        tried = []
        res = None
        for src in order:
            q = mini_quote(s, now, mini_path) if src == "mini" else rh_quote(s, now, rh_path)
            if q is None:
                tried.append(f"{src}:none")
                continue
            if q["age_s"] <= float(pol["max_age_s"]):
                res = {"ok": True, **q}
                break
            tried.append(f"{src}:age {q['age_s']}s")
        out[s] = res or {"ok": False, "source": None, "reason": "; ".join(tried) or "no quote",
                         "action": "pull live RH get_equity_quotes before elevating/invalidating"}
        out[s]["policy"] = {"accept_mini": allow_mini, "max_age_s": pol["max_age_s"]}
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID live quote gate")
    ap.add_argument("cmd", choices=["check", "policy"])
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--live-agentic", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "policy":
        print(json.dumps(policy(), indent=1))
        return 0
    r = check(a.symbols, live_agentic=a.live_agentic)
    print(json.dumps(r, indent=1))
    return 0 if r and all(v["ok"] for v in r.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
