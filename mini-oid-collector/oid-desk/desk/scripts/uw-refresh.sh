#!/usr/bin/env bash
# start | stop | restart | status | once | selftest | ensure
# OID box-side Unusual Whales refresher (Jeffrey 2026-10-10). Research / paper only - zero broker calls.
# Pulls UW REST directly (UW_API_KEY env, desk-injected secret) every ~4 min in RTH and writes
# market-data/latest/uw-market-tide.json, uw-net-prem.json, uw-flow-alerts.json. Config: config/uw-refresh.json.
# Watchdog: rides scripts/mini-link-up.sh --watch (opt out: touch cache/uw-refresh.disabled). The child
# inherits UW_API_KEY from whichever shell started the watchdog; if it is missing, start refuses (logged).
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
PIDF="$OID/cache/uw-refresh.pid"
LOG="$OID/cache/uw-refresh.log"
OUT="$OID/cache/uw-refresh.json"
mkdir -p "$OID/cache"

running() {
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q uw_refresh.py
}

case "${1:-status}" in
  start|ensure)
    if running; then echo "uw-refresh already running pid=$(cat "$PIDF")"; exit 0; fi
    if [ -z "${UW_API_KEY:-}" ]; then echo "uw-refresh NOT started: UW_API_KEY not set in this shell" | tee -a "$LOG" >&2; exit 1; fi
    nohup nice -n 5 "$PY" -u "$OID/quotes/uw_refresh.py" >>"$LOG" 2>&1 < /dev/null &
    sleep 1.5
    if running; then echo "uw-refresh started pid=$(cat "$PIDF")"; else echo "uw-refresh FAILED to start; see $LOG"; exit 1; fi
    ;;
  stop)
    if running; then kill "$(cat "$PIDF")"; for _ in 1 2 3 4 5 6 7 8; do running || break; sleep 0.5; done
      running && kill -9 "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "uw-refresh stopped"
    else rm -f "$PIDF"; echo "uw-refresh not running"; fi
    ;;
  restart) "$0" stop; "$0" start ;;
  once) "$PY" "$OID/quotes/uw_refresh.py" --once ;;
  selftest) "$PY" "$OID/quotes/uw_refresh.py" --selftest ;;
  status)
    if running; then p="$(cat "$PIDF")"; echo "uw-refresh running pid=$p rss=$(awk '/VmRSS/{print $2" "$3}' /proc/$p/status 2>/dev/null)"; rc=0
    else echo "uw-refresh NOT running"; rc=3; fi
    "$PY" - "$OUT" "$OID/market-data/latest" <<'PY'
import json, sys, time
from datetime import datetime
p, latest = sys.argv[1], sys.argv[2]
try:
    r = json.load(open(p))
    print(f"status: {r.get('state')} heartbeat={r.get('heartbeat_pt')} last_cycle={r.get('last_cycle_pt')} ({r.get('last_cycle_kind')}) "
          f"calls_today={r.get('calls_today')} last_error={r.get('last_error')} errs={len(r.get('last_errors') or [])}")
except Exception as e:
    print(f"status: unavailable ({type(e).__name__})")
for f in ("uw-market-tide", "uw-net-prem", "uw-flow-alerts"):
    try:
        d = json.load(open(f"{latest}/{f}.json"))
        age = time.time() - datetime.fromisoformat(d["as_of"].replace("Z", "+00:00")).timestamp()
        print(f"  {f:15} {d.get('as_of_pt')} age={age/60:.1f}m ttl={d.get('ttl_seconds')}s writer={d.get('writer')}")
    except Exception as e:
        print(f"  {f:15} unavailable ({type(e).__name__})")
PY
    tail -n 2 "$LOG" 2>/dev/null | sed 's/^/log: /'
    exit $rc
    ;;
  *) echo "usage: $0 start|stop|restart|status|once|selftest|ensure"; exit 2 ;;
esac
