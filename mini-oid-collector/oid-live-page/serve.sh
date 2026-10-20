#!/bin/bash
# Expose the live page to the tailnet only (HTTPS via tailscale serve). Never Funnel.
#   ./serve.sh on | off | status
TS(){ /opt/homebrew/bin/tailscale --socket="$HOME/oid-quote/tailscale/tailscaled.sock" "$@"; }
case "${1:-status}" in
  on)  TS serve --bg --https=443 http://127.0.0.1:8791 ;;
  off) TS serve --https=443 off ;;
  *)   TS serve status; echo; TS funnel status 2>/dev/null | head -3 ;;
esac
