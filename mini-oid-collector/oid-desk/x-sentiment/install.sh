#!/bin/bash
# Install the SHADOW X sentiment feed on the mini. Idempotent. Config is only seeded if missing (never overwritten).
set -euo pipefail
H="$HOME"; D="$H/oid-desk/x-sentiment"
mkdir -p "$H/oid-data/sentiment/x" "$H/oid-data/state/x" "$H/oid-desk/logs"
[ -f "$H/oid-data/config/x-sentiment-config.json" ] || cp "$D/x-sentiment-config.json" "$H/oid-data/config/x-sentiment-config.json"
for J in x-sentiment x-sentiment-scorecard x-sentiment-corr; do
  sed "s#__HOME__#$H#g" "$D/com.oid.desk.$J.plist" > "$H/Library/LaunchAgents/com.oid.desk.$J.plist"
  launchctl bootout "gui/$(id -u)/com.oid.desk.$J" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$H/Library/LaunchAgents/com.oid.desk.$J.plist"
done
echo "installed; pull job no-ops while fetch_enabled=false in ~/oid-data/config/x-sentiment-config.json"
