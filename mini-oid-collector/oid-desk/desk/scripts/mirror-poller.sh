#!/usr/bin/env bash
# start | stop | restart | status | once — box read-only mirror of the Mac mini desk feeds (quotes/mirror_poller.py).
# Research / paper only. Not started by default: the mini-link watchdog keeps it up only when
# cache/mirror-poller.enabled exists (runbook phase 2). Kill switch for pulls: touch cache/mirror.disabled.
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
PIDF="$OID/cache/mirror-poller.pid"
LOG="$OID/cache/mirror-poller.log"
mkdir -p "$OID/cache"
running() {
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && ps -o args= -p "$p" 2>/dev/null | grep -q mirror_poller.py
}
case "${1:-status}" in
  start)
    if running; then echo "mirror-poller already running pid=$(cat "$PIDF")"; exit 0; fi
    nohup nice -n 5 "$PY" -u "$OID/quotes/mirror_poller.py" loop >>"$LOG" 2>&1 < /dev/null &
    sleep 1.5
    if running; then echo "mirror-poller started pid=$(cat "$PIDF")"; else echo "mirror-poller FAILED to start; see $LOG"; exit 1; fi ;;
  stop)
    if running; then kill "$(cat "$PIDF")"; for _ in 1 2 3 4 5 6; do running || break; sleep 0.5; done
      running && kill -9 "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "mirror-poller stopped"
    else rm -f "$PIDF"; echo "mirror-poller not running"; fi ;;
  restart) "$0" stop; "$0" start ;;
  once) "$PY" "$OID/quotes/mirror_poller.py" once ;;
  status)
    if running; then echo "mirror-poller running pid=$(cat "$PIDF")"; rc=0; else echo "mirror-poller NOT running"; rc=3; fi
    "$PY" "$OID/quotes/mirror_poller.py" status | head -40
    exit $rc ;;
  *) echo "usage: $0 start|stop|restart|status|once"; exit 2 ;;
esac
