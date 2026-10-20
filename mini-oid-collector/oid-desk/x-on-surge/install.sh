#!/bin/bash
# Install / enable Phase 3 x_on_surge on the mini. Run on the mini (or via ssh from mars).
set -euo pipefail
HOME_DIR="${HOME}"
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${HOME_DIR}/oid-desk/x-on-surge"
DATA="${HOME_DIR}/oid-data"
LABEL=com.oid.desk.x-on-surge
UID_NUM="$(id -u)"

mkdir -p "$DEST" "$DATA/config" "$DATA/state/x" "$DATA/logs" \
  "$DATA/archive/posts_raw" "$DATA/archive/post_query_hits" \
  "$DATA/archive/item_filter" "$HOME_DIR/oid-desk/logs" \
  "$HOME_DIR/Library/LaunchAgents"

# Copy code
rsync -a --delete --exclude '__pycache__' --exclude 'tests' --exclude '*.pyc' \
  "$SRC/" "$DEST/"

# Live config (hot-reloadable): only overwrite if missing OR FORCE_CONFIG=1
if [[ ! -f "$DATA/config/x-on-surge-config.json" || "${FORCE_CONFIG:-0}" == "1" ]]; then
  cp "$DEST/lib/x-on-surge-config.json" "$DATA/config/x-on-surge-config.json"
  chmod 600 "$DATA/config/x-on-surge-config.json"
  echo "wrote $DATA/config/x-on-surge-config.json"
else
  # Ensure fetch_enabled=true without clobbering other live edits
  /usr/bin/python3 - <<PY
import json
p="$DATA/config/x-on-surge-config.json"
c=json.load(open(p))
c["fetch_enabled"]=True
c["fetch_enabled_note"]="ON 2026-10-19 per Jeffrey go. Caps \$5/day \$100/month. Kill: ~/oid-data/state/x/STOP"
json.dump(c, open(p,"w"), indent=1)
print("enabled fetch_enabled on", p)
PY
fi

# Token check (existence + mode only; never print contents)
TOK="$DATA/secrets/X_BEARER_TOKEN"
if [[ ! -f "$TOK" ]]; then
  echo "ERROR: missing $TOK — run enter-keys.sh --archive X_BEARER_TOKEN first" >&2
  exit 1
fi
chmod 600 "$TOK" 2>/dev/null || true
# Ensure secrets dir is 700
chmod 700 "$DATA/secrets" 2>/dev/null || true

# Clear kill file if present? NO — leave STOP alone; operator deletes deliberately.

# Plist
PLIST_SRC="$DEST/com.oid.desk.x-on-surge.plist"
PLIST_DST="$HOME_DIR/Library/LaunchAgents/${LABEL}.plist"
sed "s|__HOME__|${HOME_DIR}|g" "$PLIST_SRC" > "$PLIST_DST"

# Selftest
/usr/bin/python3 "$DEST/oid_x_on_surge.py" --selftest

# Load / kickstart
launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/${UID_NUM}" "$PLIST_DST"
launchctl enable "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl kickstart -k "gui/${UID_NUM}/${LABEL}"

sleep 2
launchctl list | grep x-on-surge || true
echo "--- status ---"
cat "$DATA/state/x/status.json" 2>/dev/null || echo "(status not yet)"
echo "--- config fetch_enabled ---"
/usr/bin/python3 -c "import json; print(json.load(open('$DATA/config/x-on-surge-config.json'))['fetch_enabled'])"
echo "KILL SWITCH: touch $DATA/state/x/STOP   (or set fetch_enabled=false in config)"
echo "DONE Phase 3 install"
