#!/bin/bash
# Disable + remove every OID mini desk launchd job. Keeps ~/oid-desk data and ~/oid-quote untouched.
# Full removal afterwards (optional): rm -rf ~/oid-desk
set -u
ROOT="${OID_DESK_ROOT:-$HOME/oid-desk}"
[ -x "$ROOT/bin/oidctl" ] && "$ROOT/bin/oidctl" all-off
for p in "$HOME"/Library/LaunchAgents/com.oid.desk.*.plist; do
  [ -e "$p" ] || continue
  launchctl bootout "gui/$(id -u)/$(basename "$p" .plist)" 2>/dev/null || true; rm -f "$p"
done
echo "OID mini desk jobs removed (data kept in $ROOT; quote collector untouched)"
