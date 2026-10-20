#!/bin/bash
# 2026-10-20 Jeffrey runs this ON THE MINI to arm Hal's exit watcher webhook (hidden input, files 600, values never shown):
#   ~/oid-desk/bin/hal-exit-keys.sh
# Paste the URL and the key of Hal's "Hal live exit wake" webhook routine when asked. The watcher
# (com.oid.desk.hal-exit-watch) re-reads the files every check and switches from dry-run to live by itself.
set -u
"$HOME/oid-desk/bin/enter-keys.sh" HAL_EXIT_WEBHOOK_URL HAL_EXIT_WEBHOOK_KEY
S="${OID_SECRETS_DIR:-$HOME/oid-quote/secrets}"
if [ -s "$S/HAL_EXIT_WEBHOOK_URL" ] && [ -s "$S/HAL_EXIT_WEBHOOK_KEY" ]; then
  echo "hal-exit-watch: LIVE within 3 s (both files present). Undo: rm $S/HAL_EXIT_WEBHOOK_URL $S/HAL_EXIT_WEBHOOK_KEY"
else
  echo "hal-exit-watch: still DRY-RUN (needs both HAL_EXIT_WEBHOOK_URL and HAL_EXIT_WEBHOOK_KEY)"
fi
