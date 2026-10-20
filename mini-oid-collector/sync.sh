#!/bin/bash
# mini-oid-collector/sync.sh
# Copies the LIVE OID code/config/docs on this Mac mini into this repo (read-only on
# the live dirs), scrubs/scans for secrets, and commits if anything changed.
#   Usage:  ~/mini-oid-collector/sync.sh            # sync + scan + commit
#           ~/mini-oid-collector/sync.sh --dry-run  # sync + scan, no commit
#           ~/mini-oid-collector/sync.sh --tar OUT  # also write OUT.tgz (top folder mini-oid-collector/)
# It never restarts, edits or stops anything in the live dirs.
set -euo pipefail
H="$HOME"
REPO="$(cd "$(dirname "$0")" && pwd)"
DRY=0; TAR=""
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --tar) TAR="$2"; shift;; *) echo "unknown arg $1"; exit 64;; esac; shift; done

STAGE="$(mktemp -d /tmp/mini-oid-collector.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
EXC="$STAGE/.excludes"
cat > "$EXC" <<'XEOF'
.git
.DS_Store
__pycache__
*.pyc
venv
venv-*
.venv
node_modules
secrets
logs
cache
data
stage
tmp
tailscale
*.bak
*.bak-*
*.bak.*
bak-*
backup-*
app-backup-*
docs.bak*
app.bak*
*.prev
*.v0*
*.held-*
*.jsonl
*.parquet
*.sqlite
*.sqlite3
*.db
*.log
*.pid
*.lock
.*.lock
*.env
.env
.env.*
*.pem
*.p12
*.key
*TOKEN*
*_token
*-token
*api-key*
*API_KEY*
*.tgz
*.tar.gz
*.zip
XEOF

R() { # rsync a whole directory (common excludes) into the stage
  local src="$1" dst="$2"; [ -d "$src" ] || { echo "skip (missing) $src"; return 0; }
  mkdir -p "$STAGE/$dst"
  rsync -rpt --exclude-from="$EXC" "$src/" "$STAGE/$dst/"
}
F() { # rsync selected files (globs) into a stage folder
  local dst="$1"; shift; mkdir -p "$STAGE/$dst"
  local f; for f in "$@"; do [ -f "$f" ] || continue
    case "$(basename "$f")" in *.bak*|*.prev|*.v0*) continue;; esac
    rsync -pt "$f" "$STAGE/$dst/"; done
}

# --- oid-desk: job runner app, CLI, trigger engine, x-on-surge, overrides, launchd templates
R "$H/oid-desk/app"        oid-desk/app
R "$H/oid-desk/bin"        oid-desk/bin
R "$H/oid-desk/triggers"   oid-desk/triggers
R "$H/oid-desk/x-on-surge" oid-desk/x-on-surge
R "$H/oid-desk/momentum"   oid-desk/momentum
R "$H/oid-desk/news"       oid-desk/news
R "$H/oid-desk/launchd"    oid-desk/launchd
R "$H/oid-desk/overrides"  oid-desk/overrides
R "$H/oid-desk/flags"      oid-desk/flags
# --- oid-desk/desk: dashboard + quote pollers + scripts (code/config only, no market data)
D="$H/oid-desk/desk"
F oid-desk/desk                       "$D/Makefile"
F oid-desk/desk/dashboard             "$D"/dashboard/*.py "$D"/dashboard/*.md "$D"/dashboard/*.sh "$D"/dashboard/*.html
R "$D/quotes"    oid-desk/desk/quotes
R "$D/scripts"   oid-desk/desk/scripts
R "$D/config"    oid-desk/desk/config
R "$D/public"    oid-desk/desk/public
R "$D/dist-prod" oid-desk/desk/dist-prod
F oid-desk/desk/market-data           "$D"/market-data/*.py "$D"/market-data/*.md
R "$D/market-data/schema" oid-desk/desk/market-data/schema
F oid-desk/desk/paper-trades          "$D"/paper-trades/*.py
F oid-desk/desk/chart-bot/whale-flow  "$D"/chart-bot/whale-flow/*.py "$D"/chart-bot/whale-flow/*.sh
# --- live volume page + Field Guide
L="$H/oid-live-page"
F oid-live-page "$L"/*.py "$L"/*.sh "$L"/*.html "$L"/*.md "$L"/sectors.json "$L"/wide-sectors.json "$L"/*.plist
F oid-live-page/guide "$L"/guide/index.html
R "$L/guide/docs"   oid-live-page/guide/docs
R "$L/guide/vendor" oid-live-page/guide/vendor
# --- option flow (C/P chips, momentum)
O="$H/oid-optflow"
F oid-optflow "$O"/*.py "$O"/*.plist
# --- direction score (daemon, grader, report, docs; data lives in ~/oid-data/score and is NOT synced)
R "$H/oid-score" oid-score
# --- quote/volume collector (Alpaca SIP/OPRA stream, :8787)
R "$H/oid-quote/app" oid-quote/app
F oid-quote "$H/oid-quote/config.json" "$H/oid-quote/wide-allowlist.json"
# --- archive / x-on-surge runtime config
F oid-data/config "$H"/oid-data/config/*.json
# --- installed launchd agents (actual ~/Library/LaunchAgents copies)
F launchd "$H"/Library/LaunchAgents/com.oid.*.plist

# scrub known secret values -> ${NAME} placeholders, then regex scan (fails on findings)
/usr/bin/python3 "$REPO/tools/secret_scan.py" --scrub "$STAGE" --report "$STAGE/.scan-report.txt" || { echo "secret scan FAILED (see $STAGE/.scan-report.txt); not syncing"; trap - EXIT; exit 2; }

# mirror the stage into the repo (repo-owned files are protected)
rsync -rpt --delete --checksum \
  --exclude=.git --exclude=/README.md --exclude=/.gitignore --exclude=/sync.sh --exclude=/tools \
  --exclude=/push.sh --exclude=/SCAN-REPORT.txt --exclude=.excludes --exclude=.scan-report.txt \
  "$STAGE/" "$REPO/"
cp "$STAGE/.scan-report.txt" "$REPO/SCAN-REPORT.txt"
/usr/bin/python3 "$REPO/tools/secret_scan.py" --check "$REPO" >/dev/null || { echo "repo-level scan FAILED; not committing"; exit 3; }

cd "$REPO"
[ -d .git ] || { git init -q -b main; }
git add -A
# hard guard: nothing secret/data-like may be staged
if { git diff --cached --name-only | grep -Ei '(^|/)(secrets?|logs?|cache|data|venv|tailscale)/|\.(env|jsonl|parquet|sqlite3?|db|log|pid|pem|key)$|\.bak'; git diff --cached --name-only | grep -E 'TOKEN|API_KEY|api-key'; } ; then
  echo "guard: secret/data-like path staged (listed above); aborting"; git reset -q; exit 4; fi
if git diff --cached --quiet; then echo "sync: no changes"; else
  if [ "$DRY" = 1 ]; then git diff --cached --stat | tail -1; git reset -q; echo "dry run: not committed"
  else git -c user.name='Rose (OID desk)' -c user.email='jb@jbv.com' commit -q \
         -m "sync mini live code $(date '+%Y-%m-%d %H:%M %Z')" && git log -1 --format='committed %h %s'; fi
fi
if [ -n "$TAR" ]; then
  T="$(mktemp -d)"; git archive --format=tar --prefix=mini-oid-collector/ HEAD | tar -x -C "$T"
  tar -czf "$TAR" -C "$T" mini-oid-collector; rm -rf "$T"; ls -l "$TAR"; fi

# publish to GitHub (jeffbazar/oid-trading-desk, folder mini-oid-collector/) after every sync - FAILS SOFT:
# until the deploy key is authorized push.sh exits non-zero, which is logged and never breaks sync.
if [ "$DRY" = 0 ] && [ -x "$REPO/push.sh" ]; then
  mkdir -p "$HOME/oid-data/logs"
  if "$REPO/push.sh" >>"$HOME/oid-data/logs/mini-push.log" 2>&1; then echo "push: ok (see ~/oid-data/logs/mini-push.log)"
  else echo "push: skipped/failed rc=$? (soft; see ~/oid-data/logs/mini-push.log)"; fi
fi
