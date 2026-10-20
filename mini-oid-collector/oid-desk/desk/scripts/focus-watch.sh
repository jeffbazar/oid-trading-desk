#!/usr/bin/env bash
# start | stop | restart | status | once | selftest | --watch-start | --watch-stop | --watch-status
# OID 5s spot-vs-wall FOCUS watch (Jeffrey 2026-10-09). Research / paper only - zero execution,
# no FlashAlpha / broker calls (reads cache/mini-quotes.json + market-data/latest/fa-levels.json).
# Writes cache/focus-watch.json + cache/focus-watch-events.jsonl. Config: config/focus-watch.json.
# Watchdog: also rides scripts/mini-link-up.sh --watch (opt out: touch cache/focus-watch.disabled);
# the standalone --watch loop here is only needed if the mini-link watchdog is not running.
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
PIDF="$OID/cache/focus-watch.pid"
LOG="$OID/cache/focus-watch.log"
OUT="$OID/cache/focus-watch.json"
EVENTS="$OID/cache/focus-watch-events.jsonl"
WLOG="$OID/cache/focus-watch-watch.log"
WPID="$OID/cache/focus-watch-watch.pid"
mkdir -p "$OID/cache"

running() {
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q focus_watch.py
}

case "${1:-status}" in
  start)
    if running; then echo "focus-watch already running pid=$(cat "$PIDF")"; exit 0; fi
    nohup "$PY" "$OID/quotes/focus_watch.py" >>"$LOG" 2>&1 < /dev/null &
    sleep 1.5
    if running; then echo "focus-watch started pid=$(cat "$PIDF")"; else echo "focus-watch FAILED to start; see $LOG"; exit 1; fi
    ;;
  stop)
    if running; then kill "$(cat "$PIDF")"; for _ in 1 2 3 4 5 6; do running || break; sleep 0.5; done
      running && kill -9 "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "focus-watch stopped"
    else rm -f "$PIDF"; echo "focus-watch not running"; fi
    ;;
  restart) "$0" stop; "$0" start ;;
  once) "$PY" "$OID/quotes/focus_watch.py" --once ;;
  selftest) "$PY" "$OID/quotes/focus_watch.py" --selftest ;;
  status)
    if running; then p="$(cat "$PIDF")"; echo "focus-watch running pid=$p rss=$(awk '/VmRSS/{print $2" "$3}' /proc/$p/status 2>/dev/null)"; rc=0
    else echo "focus-watch NOT running"; rc=3; fi
    "$PY" - "$OUT" "$EVENTS" <<'PY'
import json, sys, time
p, ev = sys.argv[1], sys.argv[2]
try:
    r = json.load(open(p))
except Exception as e:
    print(f"out: unavailable ({type(e).__name__})"); sys.exit(0)
age = time.time() - float(r.get("written_epoch") or 0)
print(f"out: {p} written {age:.1f}s ago ({r.get('as_of_pt')}) state={r.get('state')} mini_age={r.get('mini_cache_age_s')}s focus={','.join(r.get('focus_symbols') or [])} events_today={r.get('events_today')}")
for s, q in (r.get("readings") or {}).items():
    lv = " | ".join(f"{l['name']} {l['price']} {l.get('dist_pct')}%" for l in q.get("levels") or [])
    print(f"  {s:5} spot={q.get('spot')} age={q.get('quote_age_s')}s flags={q.get('flags')} :: {lv}")
try:
    lines = open(ev).read().splitlines()[-5:]
    for l in lines:
        e = json.loads(l); print(f"  event {e['ts_pt']} {e['symbol']} {e['event']} {e.get('level')}@{e.get('level_price')} spot={e.get('spot')}")
except OSError:
    print("  events: none yet")
PY
    tail -n 2 "$LOG" 2>/dev/null | sed 's/^/log: /'
    exit $rc
    ;;
  --watch)
    echo $$ > "$WPID"
    trap 'rm -f "$WPID"; exit 0' TERM INT
    while true; do
      if [ ! -f "$OID/cache/focus-watch.disabled" ] && ! running; then
        echo "$(date '+%Y-%m-%d %-I:%M:%S %p PT') focus-watch down -> starting" >>"$WLOG"; "$0" start >>"$WLOG" 2>&1
      fi
      sleep "${OID_FOCUS_WATCH_S:-60}" & wait $!
    done
    ;;
  --watch-start)
    if [ -f "$WPID" ] && kill -0 "$(cat "$WPID")" 2>/dev/null; then echo "watchdog already running pid=$(cat "$WPID")"; exit 0; fi
    nohup "$0" --watch >/dev/null 2>&1 < /dev/null &
    sleep 1; echo "watchdog started pid=$(cat "$WPID" 2>/dev/null)"
    ;;
  --watch-stop)
    if [ -f "$WPID" ] && kill -0 "$(cat "$WPID")" 2>/dev/null; then kill "$(cat "$WPID")"; echo "watchdog stopped"; else echo "watchdog not running"; fi
    rm -f "$WPID"
    ;;
  --watch-status)
    if [ -f "$WPID" ] && kill -0 "$(cat "$WPID")" 2>/dev/null; then echo "watchdog running pid=$(cat "$WPID")"; else echo "watchdog NOT running"; fi
    tail -n 5 "$WLOG" 2>/dev/null
    ;;
  *) echo "usage: $0 start|stop|restart|status|once|selftest|--watch-start|--watch-stop|--watch-status"; exit 2 ;;
esac
