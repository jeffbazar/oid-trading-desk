"""Real-time VIX on the mini (Jeffrey 2026-10-14, arch review R4). launchd interval job, 120 s.

GET https://lab.flashalpha.com/stockquote/VIX (FlashAlpha index feed, ~15 s cache on Growth) with FLASHALPHA_API_KEY
(env from run-job.sh; never logged). Writes market-data/latest/vix-live.json. Skips the call when the market is
closed (keeps the last value; status ignores it then). ~200 calls per RTH day of the 2,500/day quota.
oid_desk.vix provider "flashalpha_live" reads this file; FRED stays a labelled fallback.
Kill switch: oidctl disable vix-live (or touch flags/vix-live.disabled) -> vix falls through to agent_rh/cboe/fred.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from . import util

JOB = "vix-live"
URL = "https://lab.flashalpha.com/stockquote/VIX"


def fetch() -> dict:
    key = os.environ.get("FLASHALPHA_API_KEY") or util.read_secret("FLASHALPHA_API_KEY")
    if not key:
        raise RuntimeError("FLASHALPHA_API_KEY missing")
    req = urllib.request.Request(URL, headers={"X-Api-Key": key, "User-Agent": "oid-mini-vix/1"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10) as r:
        d = json.load(r)
        remaining = r.headers.get("X-RateLimit-Remaining")
    return {"value": d.get("lastPrice") or d.get("mid"), "bid": d.get("bid"), "ask": d.get("ask"),
            "last_update": d.get("lastUpdate"), "index_feed_as_of": (d.get("data_as_of") or {}).get("index_feed"),
            "quota_remaining": remaining}


def main(argv: Optional[list[str]] = None) -> int:
    sess = util.session()
    if sess == "closed":
        print(json.dumps({"skipped": "closed"}))
        return 0
    try:
        p = fetch()
        err = None if p.get("value") else "no value"
    except Exception as e:  # noqa: BLE001
        p, err = {}, f"{type(e).__name__}"
    if err:
        util.log(JOB, f"fetch failed: {err}")
        print(json.dumps({"error": err}))
        return 0  # keep the old file; status marks it stale by heartbeat age
    util.write_feed("vix-live", source="FlashAlpha /stockquote/VIX (real-time index feed)", writer="mini:oid_desk.vix_live",
                    symbols=["VIX"], payload=dict(p, session=sess), ttl_seconds=600)
    print(json.dumps({"vix": p.get("value"), "session": sess}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
