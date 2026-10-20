#!/bin/bash
# Install / reload / uninstall the score jobs (research/log only - never orders).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; LA="$HOME/Library/LaunchAgents"; U="gui/$(id -u)"
for J in com.oid.desk.score com.oid.desk.score-wide com.oid.desk.score-widefull com.oid.desk.score-grade com.oid.desk.score-scorecard; do
  launchctl bootout "$U/$J" 2>/dev/null || true
  if [ "${1:-}" = "--uninstall" ]; then rm -f "$LA/$J.plist"; echo "removed $J"; continue; fi
  cp "$HERE/launchd/$J.plist" "$LA/$J.plist"; launchctl bootstrap "$U" "$LA/$J.plist"; echo "loaded $J"
done
