#!/bin/bash
# OID private live page: install / uninstall the launchd job (loopback 127.0.0.1:8791 only).
#   ./install.sh            install + start      ./install.sh --uninstall   stop + remove job (tailscale serve untouched)
set -euo pipefail
D="$HOME/oid-live-page"; P="$HOME/Library/LaunchAgents/com.oid.desk.livepage.plist"; U="gui/$(id -u)"
if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$U" "$P" 2>/dev/null || true; rm -f "$P"; echo "livepage job removed"; exit 0
fi
mkdir -p "$D/logs"
SRC="$(cd "$(dirname "$0")" && pwd)"
if [ "$SRC" != "$D" ]; then cp "$SRC/livepage.py" "$SRC/index.html" "$SRC/install.sh" "$SRC/serve.sh" "$SRC/com.oid.desk.livepage.plist" "$SRC/README.md" "$D/"; fi
sed "s#__HOME__#$HOME#g" "$D/com.oid.desk.livepage.plist" > "$P"
launchctl bootout "$U" "$P" 2>/dev/null || true
launchctl bootstrap "$U" "$P"
echo "livepage job installed: http://127.0.0.1:8791/"
