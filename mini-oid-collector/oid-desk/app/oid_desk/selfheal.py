"""OID mini self-heal (PROPOSAL 2026-10-14, not installed). launchd interval job, 60 s.

Detects stale-but-alive daemons and a connected-but-silent quote collector and restarts them locally with
`launchctl kickstart -k`, with no Grok Bot routine in the loop. Also checks that the alerts job itself is alive.

Rules (all must hold before a restart):
  * session is rth or ext (never restarts while closed), job enabled, not disabled by flag
  * daemon job: mini-status row state == "stale" for STRIKES consecutive checks (launchd "down" is
    already handled by KeepAlive; we do not fight it)
  * collector: /v1/health reachable but stocks.last_data_age_s (rth) > COLLECTOR_SILENT_S, or health
    unreachable, for STRIKES checks -> kickstart com.oid.quote-collector
  * budget: at most MAX_RESTARTS per job per WINDOW_S; past that we stop and raise "selfheal-giveup"
Every action is written to state/selfheal-events.jsonl; alerts.py turns new events into webhook posts.
Writes heartbeat state/selfheal-state.json each run (alerts.py watches it; this job watches alerts-state.json).
Kill switch: touch ~/oid-desk/flags/selfheal.disabled  (run-job.sh then exits 0).  --dry = decide, don't act.
No secrets read. Never touches Robinhood, orders, or anything off-box.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from typing import Optional

from . import jobs as J
from . import util

JOB = "selfheal"
STRIKES = 3
MAX_RESTARTS = 3
WINDOW_S = 1800
COLLECTOR_SILENT_S = 30
COLLECTOR_LABEL = "com.oid.quote-collector"
HEALTH = "http://127.0.0.1:8787/v1/health"
ALERTS_MAX_AGE = 300           # alerts-state.json must be rewritten at least every 5 min
NEVER_RESTART = {"data-api", "benzinga", "publish"}  # data-api serves the box mirror; restart by hand only


def _health() -> Optional[dict]:
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(HEALTH, timeout=3) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _kick(label: str, dry: bool) -> int:
    if dry:
        return 0
    return subprocess.call(["launchctl", "kickstart", "-k", f"{J.domain()}/{label}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _event(ev: dict, dry: bool = False) -> None:
    if dry:
        return
    p = util.root() / "state" / "selfheal-events.jsonl"
    with open(p, "a") as fh:
        fh.write(json.dumps(ev) + "\n")


def candidates(sess: str) -> dict[str, tuple[str, str]]:
    """name -> (launchd label, reason) for things that look stuck right now."""
    out: dict[str, tuple[str, str]] = {}
    reg = J.load()
    st = util.read_json(util.desk() / "market-data" / "latest" / "mini-status.json") or {}
    for r in (st.get("payload") or {}).get("jobs") or []:
        j = r.get("job")
        spec = reg["jobs"].get(j) or {}
        if (r.get("enabled") and r.get("state") == "stale" and spec.get("kind") == "daemon"
                and j not in NEVER_RESTART and (r.get("launchd") or {}).get("running")):
            out[j] = (J.label(reg, j), f"stale age={r.get('age_s')}s ttl={r.get('ttl_s')}s while running")
    h = _health()
    if h is None:
        out["collector"] = (COLLECTOR_LABEL, "/v1/health unreachable")
    elif sess == "rth":
        age = (h.get("stocks") or {}).get("last_data_age_s")
        if age is None or age > COLLECTOR_SILENT_S:
            out["collector"] = (COLLECTOR_LABEL, f"stocks stream silent {age}s (state={(h.get('stocks') or {}).get('state')})")
    a = util.root() / "state" / "alerts-state.json"
    if not a.exists() or time.time() - a.stat().st_mtime > ALERTS_MAX_AGE:
        out["alerts"] = (J.label(reg, "alerts"), "alerts job not running (alerts-state.json old)")
    return out


def tick(dry: bool = False) -> dict:
    sf = util.root() / "state" / "selfheal-state.json"
    st = util.read_json(sf) or {}
    now = time.time()
    sess = util.session()
    acted = []
    cur = candidates(sess) if util.ext_bucket(sess) in ("rth", "ext") else {}
    for name in list(st.get("strikes", {})):
        if name not in cur:
            st["strikes"].pop(name)
    for name, (label, why) in cur.items():
        n = st.setdefault("strikes", {}).get(name, 0) + 1
        st["strikes"][name] = n
        if n < STRIKES:
            continue
        hist = [t for t in st.setdefault("restarts", {}).get(name, []) if now - t < WINDOW_S]
        if len(hist) >= MAX_RESTARTS:
            if not st.setdefault("gaveup", {}).get(name):
                st["gaveup"][name] = now
                _event({"source": f"mini:selfheal:{name}", "status": "giveup", "detail": f"{why}; {len(hist)} restarts in 30 min, stopped", "ts": util.now_pt_str()}, dry)
            continue
        rc = _kick(label, dry)
        hist.append(now)
        st["restarts"][name] = hist
        st["strikes"][name] = 0
        st.get("gaveup", {}).pop(name, None)
        ev = {"source": f"mini:selfheal:{name}", "status": "restarted", "detail": f"{why}; kickstart rc={rc}", "ts": util.now_pt_str()}
        _event(ev, dry)
        util.log(JOB, f"restart {name} ({label}): {why} rc={rc}{' DRY' if dry else ''}")
        acted.append(ev)
    st["at"], st["session"] = now, sess
    if not dry:
        util.atomic_write_json(sf, st)
    return {"session": sess, "candidates": {k: v[1] for k, v in cur.items()}, "acted": acted}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OID mini self-heal")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    print(json.dumps(tick(dry=a.dry)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
