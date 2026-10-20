#!/bin/bash
# Stops and removes the launchd agent. Leaves ~/oid-quote (secrets, logs, cache, venv) in place.
set -euo pipefail
LABEL="com.oid.quote-collector"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UIDN="$(id -u)"
for DOMAIN in "gui/$UIDN" "user/$UIDN"; do
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
done
rm -f "$PLIST"
echo "==> removed launchd agent $LABEL"
echo "    data left in ${OID_QUOTE_ROOT:-$HOME/oid-quote} (delete it manually only if you are sure; it holds your secrets)"
