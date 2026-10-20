#!/usr/bin/env bash
# Whale Flow collector control (CB-WHALE-V1). Usage: bash run.sh start|stop|restart|status|ensure
# "ensure" = watchdog-friendly: starts only if not already running.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PID="$DIR/collector.pid"; LOG="$DIR/collector.log"
running(){ [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; }
start(){ if running; then echo "already running pid $(cat "$PID")"; return 0; fi
  [[ -n "${UW_API_KEY:-}" ]] || { echo "UW_API_KEY not set in this shell; not starting" >&2; return 1; }
  cd "$DIR" || return 1
  nohup nice -n 10 python3 -u whale_flow.py --loop >>"$LOG" 2>&1 &
  echo $! >"$PID"; sleep 1; running && echo "started pid $(cat "$PID")" || { echo "failed to start; see $LOG" >&2; return 1; }; }
stop(){ if running; then kill "$(cat "$PID")"; echo "stopped pid $(cat "$PID")"; else echo "not running"; fi; rm -f "$PID"; }
case "${1:-status}" in
  start|ensure) start;; stop) stop;; restart) stop; start;;
  status) if running; then echo "running pid $(cat "$PID")"; else echo "not running"; fi; cat "$DIR/status.json" 2>/dev/null;;
  *) echo "usage: $0 start|stop|restart|status|ensure"; exit 2;;
esac
