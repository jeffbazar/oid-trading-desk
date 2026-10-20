#!/usr/bin/env bash
# start | stop | status | restart | once — box-side 5s mini quote poller.
# Research/paper only. Writes cache/mini-quotes.json. Never prints the token.
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
PIDF="$OID/cache/mini-poller.pid"
LOG="$OID/cache/mini-poller.log"
CACHE="$OID/cache/mini-quotes.json"
mkdir -p "$OID/cache"

running() {
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q mini_poller.py
}

case "${1:-status}" in
  start)
    if running; then echo "mini-poller already running pid=$(cat "$PIDF")"; exit 0; fi
    nohup "$PY" "$OID/quotes/mini_poller.py" >>"$LOG" 2>&1 < /dev/null &
    sleep 1.5
    if running; then echo "mini-poller started pid=$(cat "$PIDF")"; else echo "mini-poller FAILED to start; see $LOG"; exit 1; fi
    ;;
  stop)
    if running; then kill "$(cat "$PIDF")"; for _ in 1 2 3 4 5 6; do running || break; sleep 0.5; done
      running && kill -9 "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "mini-poller stopped"
    else rm -f "$PIDF"; echo "mini-poller not running"; fi
    ;;
  restart) "$0" stop; "$0" start ;;
  once) "$PY" "$OID/quotes/mini_poller.py" --once ;;
  status)
    if running; then echo "mini-poller running pid=$(cat "$PIDF")"; rc=0; else echo "mini-poller NOT running"; rc=3; fi
    "$PY" - "$CACHE" <<'PY'
import json, sys, time
p = sys.argv[1]
try:
    r = json.load(open(p))
except Exception as e:
    print(f"cache: unavailable ({type(e).__name__})"); sys.exit(0)
age = time.time() - float(r.get("written_epoch") or 0)
m = r.get("mini") or {}
print(f"cache: {p} written {age:.1f}s ago ({r.get('as_of_pt')}) session={r.get('session')} max_age={r.get('max_age_s')}s")
print(f"mini: ok={m.get('ok')} http={m.get('http_status')} latency={m.get('latency_ms')}ms collector={m.get('collector_status')} "
      f"feed={(m.get('stocks_feed') or {}).get('feed')}/{(m.get('stocks_feed') or {}).get('state')} err={m.get('error')}")
print(f"symbols: mini={len(r.get('from_mini') or [])} rh={len(r.get('from_rh') or [])} unresolved={len(r.get('unresolved') or [])}")
for s, q in (r.get("quotes") or {}).items():
    if q.get("source"):
        print(f"  {s:5} {q.get('source'):9} last={q.get('last')} bid={q.get('bid')} ask={q.get('ask')} age={q.get('age_s')}s")
PY
    tail -n 3 "$LOG" 2>/dev/null | sed 's/^/log: /'
    exit $rc
    ;;
  *) echo "usage: $0 start|stop|restart|status|once"; exit 2 ;;
esac
