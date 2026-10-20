#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DESK="$(cd "$ROOT/.." && pwd)"
DIST="${OID_PUBLISH_DIST:-$DESK/dist-prod}"
SLUG="${OID_PUBLISH_SLUG:-swift-dune-cs3e}"
# 2026-10-07: serialize every publish (routines, live_refresh --publish, extended-hours loop, other agents)
# on one lock so two packagers never race on dist-prod/. Callers that already hold it (the extended-hours
# publisher) set OID_PUBLISH_LOCK_HELD=1. Wait up to OID_PUBLISH_LOCK_WAIT_S (default 180s).
LOCK="${OID_PUBLISH_LOCK:-$DESK/cache/publish.lock}"
if [[ "${OID_PUBLISH_LOCK_HELD:-0}" != "1" ]] && command -v flock >/dev/null 2>&1; then
  mkdir -p "$(dirname "$LOCK")"
  exec 9>"$LOCK"
  if ! flock -w "${OID_PUBLISH_LOCK_WAIT_S:-180}" 9; then
    echo "error: another publish holds $LOCK (waited ${OID_PUBLISH_LOCK_WAIT_S:-180}s); skipping" >&2
    exit 75
  fi
fi
SCRIPT="/home/box/agent-data/plugins/cache/cursor-public/here_now/8ec223e927bb2247636aa0653536f63385f05298/skills/here-now/scripts/publish.sh"
# Mac mini: vendored copy (minihost/vendor/herenow-publish.sh) via HERENOW_PUBLISH_SCRIPT. Unset on the box.
if [[ -n "${HERENOW_PUBLISH_SCRIPT:-}" ]]; then
  SCRIPT="$HERENOW_PUBLISH_SCRIPT"
fi
# Prefer newest here.now publish.sh if cache hash moved
if [[ ! -x "$SCRIPT" ]]; then
  SCRIPT="$(find /home/box/agent-data/plugins/cache/cursor-public/here_now -path '*/skills/here-now/scripts/publish.sh' | head -1)"
fi
# 2026-10-07: every publish path (live_refresh.py --publish, rebuild.py -> publish.sh fallbacks,
# routines) must carry the freshly rebuilt dashboard into the SPA snapshot (marks, Key tickers,
# Core 20). Re-run import + package here so a bare publish.sh never ships a stale data/snapshot.json.
# Opt out with OID_PUBLISH_NO_REPACKAGE=1 (e.g. when the caller already ran the full chain).
if [[ "${OID_PUBLISH_NO_REPACKAGE:-0}" != "1" && "$DIST" == "$DESK/dist-prod" ]]; then
  if python3 "$DESK/scripts/import_snapshot.py" --local-dashboard >/dev/null; then
    python3 "$DESK/scripts/package_prod_dist.py" >/dev/null || echo "warn: package_prod_dist.py failed; checking existing dist" >&2
  else
    echo "warn: import_snapshot.py --local-dashboard failed; publishing previously packaged dist" >&2
  fi
fi
if [[ ! -d "$DIST" ]]; then
  echo "error: production dist missing: $DIST" >&2
  echo "hint: python3 $DESK/dashboard/rebuild.py && python3 $DESK/scripts/import_snapshot.py --local-dashboard && python3 $DESK/scripts/package_prod_dist.py" >&2
  exit 1
fi
if [[ ! -f "$DIST/index.html" || ! -f "$DIST/data/snapshot.json" ]]; then
  echo "error: $DIST is not a packaged SPA (need index.html + data/snapshot.json)" >&2
  exit 1
fi
# Publish redesign SPA to production slug. bold-tulip-nejq is frozen — do not update it here.
cd "$DIST"
bash "$SCRIPT" . --slug "$SLUG" --spa --title "OID Trading Desk" --description "OID research/paper production desk"
