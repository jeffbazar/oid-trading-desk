#!/usr/bin/env bash
# start | stop | restart | status | once - box-side 5m/15m bars + RVOL poller (quotes/mini_bars.py loop).
# Primary Alpaca SIP bars via mini /v1/bars; RH 5minute fallback is agent-ingested (docs/BARS-RVOL.md).
# Research/paper only. Writes cache/bars/. Never prints the token.
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
PIDF="$OID/cache/bars/bars-poller.pid"
LOG="$OID/cache/bars/bars-poller.log"
mkdir -p "$OID/cache/bars"
running() {
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q mini_bars.py
}
case "${1:-status}" in
  start)
    if running; then echo "bars-poller already running pid=$(cat "$PIDF")"; exit 0; fi
    nohup "$PY" "$OID/quotes/mini_bars.py" loop >>"$LOG" 2>&1 < /dev/null &
    sleep 1.5
    if running; then echo "bars-poller started pid=$(cat "$PIDF")"; else echo "bars-poller FAILED to start; see $LOG"; exit 1; fi ;;
  stop)
    if running; then kill "$(cat "$PIDF")"; for _ in 1 2 3 4 5 6; do running || break; sleep 0.5; done
      running && kill -9 "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "bars-poller stopped"
    else rm -f "$PIDF"; echo "bars-poller not running"; fi ;;
  restart) "$0" stop; "$0" start ;;
  once) "$PY" "$OID/quotes/mini_bars.py" refresh ;;
  status)
    if running; then echo "bars-poller running pid=$(cat "$PIDF")"; rc=0; else echo "bars-poller NOT running"; rc=3; fi
    "$PY" "$OID/quotes/mini_bars.py" status
    tail -n 3 "$LOG" 2>/dev/null | sed 's/^/log: /'
    exit $rc ;;
  *) echo "usage: $0 start|stop|restart|status|once"; exit 2 ;;
esac
