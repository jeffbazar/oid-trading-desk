#!/usr/bin/env python3
"""Merge FlashAlpha get_flow_levels results into market-data/latest/fa-levels.json (research only).

Keeps every other symbol and the file's envelope (via market-data/cache_io.write_feed), rolls the
current call_wall/put_wall/gamma_flip into prior_* when they change, keeps the settled get_levels
values as settled_* for reference, and stamps per-symbol as_of/as_of_pt/freshness/oi_feed.
Holds an flock on market-data/latest/.fa-levels.lock while read-modify-writing.

  echo '[{flow_levels json}, ...]' | python3 quotes/fa_levels_merge.py --writer NAME
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "market-data"))
import cache_io  # noqa: E402

LEVELS = OID / "market-data" / "latest" / "fa-levels.json"
LOCK = OID / "market-data" / "latest" / ".fa-levels.lock"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def merge(results: list[dict], *, writer: str, source_note: str) -> dict:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            doc = json.loads(LEVELS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {"payload": {"levels": {}}, "symbols": []}
        payload = doc.get("payload") or {}
        levels = payload.setdefault("levels", {})
        merged = []
        for r in results:
            sym = str(r.get("symbol") or "").upper()
            cw, pw, fl = _f(r.get("live_call_wall")), _f(r.get("live_put_wall")), _f(r.get("live_gamma_flip"))
            if not sym or (cw is None and pw is None):
                continue
            old = levels.get(sym) or {}
            new = dict(old)
            if old.get("oi_feed") == "get_levels":  # remember settled-OI walls for reference
                for k in ("call_wall", "put_wall", "gamma_flip"):
                    if old.get(k) is not None:
                        new[f"settled_{k}"] = old.get(k)
                new["settled_as_of"] = old.get("as_of")
            for k, v in (("call_wall", cw), ("put_wall", pw), ("gamma_flip", fl)):
                if v is None:
                    continue
                if old.get(k) is not None and abs(float(old[k]) - v) > 1e-6:
                    new[f"prior_{k}"] = old[k]
                new[k] = round(v, 4) if k == "gamma_flip" else v
            asof = r.get("as_of") or datetime.now(timezone.utc).isoformat()
            dt = cache_io._parse_as_of(asof) or datetime.now(timezone.utc)
            new.update({
                "underlying_price": _f(r.get("underlying_price")),
                "gamma_flip_status": r.get("gamma_flip_status"),
                "max_pain": _f(r.get("live_max_pain")),
                "freshness": "FRESH",
                "as_of": dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "as_of_pt": cache_io.format_as_of_pt(dt),
                "oi_feed": "get_flow_levels",
                "flow_writer": writer,
            })
            levels[sym] = new
            merged.append(sym)
        if merged:
            refreshed = list(dict.fromkeys((payload.get("refreshed") or []) + merged))
            payload["refreshed"] = refreshed
            payload["focus_refresh"] = {"symbols": merged, "writer": writer,
                                        "as_of_pt": cache_io.format_as_of_pt()}
            syms = list(dict.fromkeys((doc.get("symbols") or []) + merged))
            src = doc.get("source") or "flashalpha"
            if "get_flow_levels" not in src:
                src = f"{src} · focus names via get_flow_levels"
            cache_io.write_feed("fa-levels", source=src, writer=writer, symbols=syms, payload=payload,
                                ttl_seconds=doc.get("ttl_seconds") or 600)
        return {"merged": merged, "note": source_note}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--writer", default="focus-refresh")
    a = ap.parse_args()
    data = json.load(sys.stdin)
    print(json.dumps(merge(data if isinstance(data, list) else [data], writer=a.writer, source_note="stdin")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
