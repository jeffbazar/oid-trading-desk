#!/usr/bin/env bash
# Recovery / watchdog for the box -> Mac mini quote link.
#   scripts/mini-link-up.sh            one-shot: ensure tailscaled + mini-poller + extended-publisher + focus-watch + uw-refresh
#                                      + bars-poller + whale-flow (+ mirror-poller when cache/mirror-poller.enabled) are up
#                                      (+ dashboard/source_status.py --if-due: Data Sources tab / alarm)
#   scripts/mini-link-up.sh --watch    loop every ${OID_MINI_WATCH_S:-60}s (run under nohup)
#   scripts/mini-link-up.sh --watch-start | --watch-stop | --watch-status
#
# Restarts box tailscaled with the SAME flags it was first started with (userspace networking,
# SOCKS5 :1055, HTTP proxy :1056). Does NOT run `tailscale up`: node identity persists in the
# statedir. If the node is logged out (needs a new sign-in link), this script reports it and stops —
# re-auth needs Jeffrey. Never prints secrets.
set -u
OID="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS_DIR="${TS_DIR:-/home/box/tailscale}"
SOCK="$TS_DIR/tailscaled.sock"
STATE="$TS_DIR/state"
TSLOG="$TS_DIR/tailscaled.log"
WLOG="$OID/cache/mini-link-watch.log"
WPID="$OID/cache/mini-link-watch.pid"
MINI_IP="${OID_MINI_IP:-100.106.118.33}"
mkdir -p "$OID/cache"

ts() { date '+%Y-%m-%d %-I:%M:%S %p PT'; }
say() { echo "$(ts) $*"; }

tailscaled_running() { pgrep -u "$(id -u)" -f "tailscaled .*--socket=$SOCK" >/dev/null 2>&1; }

start_tailscaled() {
  say "tailscaled down -> starting (userspace, socks5 :1055, http :1056)"
  ( cd "$TS_DIR" && nohup ./tailscaled --tun=userspace-networking --socket="$SOCK" --statedir="$STATE" \
      --socks5-server=localhost:1055 --outbound-http-proxy-listen=localhost:1056 >>"$TSLOG" 2>&1 < /dev/null & )
  for _ in $(seq 1 20); do [ -S "$SOCK" ] && tailscaled_running && break; sleep 0.5; done
}

ensure_once() {
  local rc=0
  if ! tailscaled_running; then start_tailscaled; fi
  if ! tailscaled_running; then say "ERROR tailscaled failed to start; see $TSLOG"; return 2; fi
  # Wait for backend Running (state persists; no `tailscale up`)
  local st=""
  for _ in $(seq 1 20); do
    st="$("$TS_DIR/tailscale" --socket="$SOCK" status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState",""))' 2>/dev/null)"
    [ "$st" = "Running" ] && break; sleep 0.5
  done
  if [ "$st" != "Running" ]; then
    say "WARN tailscale BackendState=${st:-unknown} (NeedsLogin => Jeffrey must re-approve oid-rose-box; not running 'tailscale up' here)"
    rc=3
  fi
  local code
  for _ in 1 2 3 4 5; do  # fresh tailscaled needs a few seconds to reach the peer
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 -x http://localhost:1056 "http://$MINI_IP:8787/v1/health" 2>/dev/null)"
    [ "$code" = "200" ] && break; sleep 2
  done
  if [ "$code" != "200" ]; then say "WARN mini /v1/health http=$code (poller will fall back to rh-quotes)"; [ $rc -eq 0 ] && rc=4; fi
  # Opt out (mini marks cutover, scripts/oid-cutover.sh flip marks): touch cache/mini-poller.disabled
  if [ ! -f "$OID/cache/mini-poller.disabled" ] && ! "$OID/scripts/mini-poller.sh" status >/dev/null 2>&1; then
    say "mini-poller down -> starting"; "$OID/scripts/mini-poller.sh" start
  fi
  # Extended-hours (PRE/AH/OVERNIGHT) blotter publisher rides with the poller. Opt out: touch cache/extended-publisher.disabled
  if [ ! -f "$OID/cache/extended-publisher.disabled" ] && ! "$OID/scripts/extended-publisher.sh" status >/dev/null 2>&1; then
    say "extended-publisher down -> starting"; "$OID/scripts/extended-publisher.sh" start
  fi
  # 5s spot-vs-wall focus watch (Jeffrey 2026-10-09) rides with the poller. Opt out: touch cache/focus-watch.disabled
  if [ -x "$OID/scripts/focus-watch.sh" ] && [ ! -f "$OID/cache/focus-watch.disabled" ] && ! "$OID/scripts/focus-watch.sh" status >/dev/null 2>&1; then
    say "focus-watch down -> starting"; "$OID/scripts/focus-watch.sh" start
  fi
  # Unusual Whales box refresher (Jeffrey 2026-10-10) rides with the poller. Needs UW_API_KEY in the watchdog's env.
  # Opt out: touch cache/uw-refresh.disabled
  if [ -x "$OID/scripts/uw-refresh.sh" ] && [ ! -f "$OID/cache/uw-refresh.disabled" ] && ! "$OID/scripts/uw-refresh.sh" status >/dev/null 2>&1; then
    say "uw-refresh down -> starting"; "$OID/scripts/uw-refresh.sh" start
  fi
  # 5m/15m bars + RVOL poller (2026-10-10; was unguarded). Opt out: touch cache/bars-poller.disabled
  if [ -x "$OID/scripts/bars-poller.sh" ] && [ ! -f "$OID/cache/bars-poller.disabled" ] && ! "$OID/scripts/bars-poller.sh" status >/dev/null 2>&1; then
    say "bars-poller down -> starting"; "$OID/scripts/bars-poller.sh" start
  fi
  # UW whale-flow collector (chart-bot/whale-flow, 60 s RTH; was unguarded). Needs UW_API_KEY in the watchdog's env.
  # Opt out: touch cache/whale-flow.disabled
  if [ -x "$OID/chart-bot/whale-flow/run.sh" ] && [ ! -f "$OID/cache/whale-flow.disabled" ] && \
     ! "$OID/chart-bot/whale-flow/run.sh" status 2>/dev/null | head -1 | grep -q '^running'; then
    say "whale-flow down -> starting"; "$OID/chart-bot/whale-flow/run.sh" ensure
  fi
  # Mac mini mirror (MINI-MIGRATION-PLAN). OPT-IN: only when cache/mirror-poller.enabled exists.
  if [ -x "$OID/scripts/mirror-poller.sh" ] && [ -f "$OID/cache/mirror-poller.enabled" ] && ! "$OID/scripts/mirror-poller.sh" status >/dev/null 2>&1; then
    say "mirror-poller down -> starting"; "$OID/scripts/mirror-poller.sh" start
  fi
  # Data Sources status + front-page alarm (Jeffrey 2026-10-10). Self-throttled (5 min RTH / hourly otherwise) and
  # flock'd inside source_status.py; republishes the blotter only when the alarm changes or the RTH snapshot is
  # >15 min old (routines stalled). Backgrounded so a publish never delays this loop. Opt out: touch cache/source-status.disabled
  if [ -f "$OID/dashboard/source_status.py" ] && [ ! -f "$OID/cache/source-status.disabled" ]; then
    ( nohup timeout 600 python3 "$OID/dashboard/source_status.py" --if-due --publish-on-change >/dev/null 2>&1 < /dev/null & )
  fi
  return $rc
}

case "${1:-}" in
  --watch)
    echo $$ > "$WPID"
    trap 'rm -f "$WPID"; exit 0' TERM INT
    while true; do ensure_once >>"$WLOG" 2>&1; sleep "${OID_MINI_WATCH_S:-60}" & wait $!; done
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
  "")
    ensure_once; rc=$?
    tailscaled_running && echo "tailscaled: running" || echo "tailscaled: DOWN"
    "$OID/scripts/mini-poller.sh" status | head -3
    "$OID/scripts/extended-publisher.sh" status | head -2
    [ -x "$OID/scripts/focus-watch.sh" ] && "$OID/scripts/focus-watch.sh" status | head -1
    [ -x "$OID/scripts/uw-refresh.sh" ] && "$OID/scripts/uw-refresh.sh" status | head -1
    exit $rc
    ;;
  *) echo "usage: $0 [--watch|--watch-start|--watch-stop|--watch-status]"; exit 2 ;;
esac
