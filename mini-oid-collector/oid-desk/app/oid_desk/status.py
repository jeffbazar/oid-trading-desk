"""Mini source status + alarm (the mini half of the Data Sources tab). Writes market-data/latest/mini-status.json.

Per job: enabled flag, launchd state (darwin), heartbeat file age vs TTL for the current session bucket.
Plus the quote collector /v1/health. alarm = any ENABLED job down/stale or collector not ok.
Disabled jobs never alarm (shadow/cutover state is explicit).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from typing import Any, Optional

from . import jobs as J
from . import util

COLLECTOR_HEALTH = "http://127.0.0.1:8787/v1/health"


def collector_health(url: str = COLLECTOR_HEALTH, timeout: float = 3.0) -> dict:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as fh:
            h = json.load(fh)
        age = (h.get("stocks") or {}).get("last_data_age_s")  # PROPOSAL: "connected but silent" is not ok in RTH
        ok = h.get("status") == "ok" and not (util.session() == "rth" and (age is None or age > 30))
        return {"ok": ok, "status": h.get("status") if ok or h.get("status") != "ok" else f"silent:{age}s",
                "version": h.get("version"), "stocks_data_age_s": age}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": f"unreachable:{type(e).__name__}", "version": None}


def evaluate(reg: dict, *, sess: Optional[str] = None, now: Optional[float] = None,
             collector: Optional[dict] = None) -> dict:
    sess = sess or util.session()
    bucket = util.ext_bucket(sess)
    now = now or time.time()
    rows = []
    alarm_reasons = []
    for job, spec in reg["jobs"].items():
        enabled = J.is_enabled(job)
        ld = J.launchd_state(reg, job) if enabled else {"loaded": None, "running": None, "pid": None, "last_exit": None}
        hb = spec.get("heartbeat")
        ttl = (spec.get("ttl") or {}).get(bucket)
        age = None
        if hb:
            p = util.desk() / hb
            if p.exists():
                age = round(now - p.stat().st_mtime, 1)
        state = "disabled"
        if enabled:
            state = "ok"
            if spec["kind"] == "daemon" and ld.get("running") is False:
                state = "down"
            elif job == "edgar":  # 10/14 arch R: same ET-slot logic as alerts.py (TTL 7200 s gave false stale)
                try:
                    from .alerts import edgar_state
                    state = "ok" if edgar_state()[0] == "ok" else "stale"
                except Exception:  # noqa: BLE001
                    state = "stale" if (hb and ttl is not None and (age is None or age > ttl)) else "ok"
            elif hb and ttl is not None and (age is None or age > ttl):
                state = "stale"
            if state != "ok":
                alarm_reasons.append(f"{job}:{state}")
        rows.append({"job": job, "group": spec.get("group"), "enabled": enabled, "state": state,
                     "heartbeat": hb, "age_s": age, "ttl_s": ttl, "launchd": ld, "desc": spec.get("desc"),
                     "hold": spec.get("hold")})
    col = collector if collector is not None else collector_health()
    if not col.get("ok") and sess != "closed":
        alarm_reasons.append(f"collector:{col.get('status')}")
    return {"session": sess, "bucket": bucket, "at_pt": util.now_pt_str(now), "collector": col,
            "alarm": bool(alarm_reasons), "alarm_reasons": alarm_reasons, "jobs": rows}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini status")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    reg = J.load()
    res = evaluate(reg)
    if a.write:
        util.write_feed("mini-status", source="mini launchd + heartbeat files + collector /v1/health",
                        writer="mini:oid_desk.status", symbols=[], payload=res, ttl_seconds=180)
    print(json.dumps({"alarm": res["alarm"], "reasons": res["alarm_reasons"], "session": res["session"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
