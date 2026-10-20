#!/usr/bin/env bash
# start | stop | restart | status | once — extended-hours (PRE / AH / OVERNIGHT) blotter publisher.
# rebuild.py -> publish.sh every 5 min to swift-dune-cs3e only. Files only, no RH API calls.
# Started/kept alive by scripts/mini-link-up.sh (and its --watch watchdog).
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
PIDF="$OID/cache/extended-publisher.pid"
LOG="$OID/cache/extended-publisher.log"
STATE="$OID/cache/extended-publisher.json"
mkdir -p "$OID/cache"

running() {
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q extended_publisher.py
}

case "${1:-status}" in
  start)
    if running; then echo "extended-publisher already running pid=$(cat "$PIDF")"; exit 0; fi
    nohup "$PY" "$OID/scripts/extended_publisher.py" >>"$LOG" 2>&1 < /dev/null &
    sleep 1.5
    if running; then echo "extended-publisher started pid=$(cat "$PIDF")"; else echo "extended-publisher FAILED to start; see $LOG"; exit 1; fi
    ;;
  stop)
    if running; then kill "$(cat "$PIDF")"; for _ in $(seq 1 20); do running || break; sleep 0.5; done
      running && kill -9 "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "extended-publisher stopped"
    else rm -f "$PIDF"; echo "extended-publisher not running"; fi
    ;;
  restart) "$0" stop; "$0" start ;;
  once) shift; "$PY" "$OID/scripts/extended_publisher.py" --once "$@" ;;
  status)
    if running; then echo "extended-publisher running pid=$(cat "$PIDF")"; rc=0; else echo "extended-publisher NOT running"; rc=3; fi
    [ -f "$STATE" ] && "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("last: %s session=%s ok=%s elapsed=%ss next=%s ok_count=%s fail_count=%s err=%s" % (d.get("started_pt"), d.get("session"), d.get("ok"), d.get("elapsed_s"), d.get("next_at_pt"), d.get("ok_count"), d.get("fail_count"), d.get("error")))' "$STATE"
    tail -n 4 "$LOG" 2>/dev/null | sed 's/^/log: /'
    exit $rc
    ;;
  *) echo "usage: $0 start|stop|restart|status|once [--force]"; exit 2 ;;
esac
