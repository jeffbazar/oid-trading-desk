#!/bin/bash
# mini-oid-collector/push.sh
# Publishes this repo's committed tree to GitHub: jeffbazar/oid-trading-desk, folder mini-oid-collector/.
# How: keeps a working clone (~/oid-trading-desk-clone, remote git@github-oid:..., i.e. the dedicated deploy key
# ~/.ssh/oid_deploy_ed25519 via the github-oid alias in ~/.ssh/config), mirrors `git archive HEAD` of this repo
# (tracked files only, so .gitignore'd secrets/data/logs/backups never go) into its mini-oid-collector/ folder,
# re-runs the secret scan on that copy, commits (message lists the local commits covered) and pushes.
#   Usage: ~/mini-oid-collector/push.sh          # called at the end of sync.sh; safe to run by hand
#   Env:   OID_PUSH_BRANCH (default mini-sync)  OID_PUSH_CLONE (default ~/oid-trading-desk-clone)
# Exit codes: 0 pushed or nothing new; 10 GitHub unreachable / key not authorized; other = error. sync.sh treats all as soft.
# Never touches the live dirs; never pushes anything but mini-oid-collector/.
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
CLONE="${OID_PUSH_CLONE:-$HOME/oid-trading-desk-clone}"
BRANCH="${OID_PUSH_BRANCH:-mini-sync}"
URL="git@github-oid:jeffbazar/oid-trading-desk.git"
SUB="mini-oid-collector"
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15"
G() { git -C "$CLONE" -c user.name='Rose (OID desk)' -c user.email='jb@jbv.com' "$@"; }
ts() { date '+%Y-%m-%d %H:%M:%S %Z'; }
echo "[$(ts)] push.sh start (branch $BRANCH)"

HEAD_SHA="$(git -C "$REPO" rev-parse HEAD)"
LAST_FILE="$CLONE/.git/mini-last-pushed"

# 1) reach GitHub (fails soft until the deploy key is added with write access)
if ! git ls-remote "$URL" HEAD >/dev/null 2>&1; then
  echo "[$(ts)] GitHub not reachable with the deploy key (not authorized yet?); nothing pushed"; exit 10; fi

# 2) working clone on $BRANCH (from origin/$BRANCH if it exists, else origin/main), with main merged in
if [ ! -d "$CLONE/.git" ]; then git clone -q "$URL" "$CLONE"; fi
G remote set-url origin "$URL"
G fetch -q --prune origin
G reset -q --hard; G clean -qfd
if G rev-parse -q --verify "origin/$BRANCH" >/dev/null; then G checkout -q -B "$BRANCH" "origin/$BRANCH"
else G checkout -q -B "$BRANCH" origin/main; fi
G merge -q --no-edit -X ours origin/main >/dev/null 2>&1 || { G merge --abort 2>/dev/null || true; echo "[$(ts)] note: could not merge origin/main into $BRANCH; continuing on $BRANCH"; }

# 3) mirror the committed tree into mini-oid-collector/
T="$(mktemp -d /tmp/mini-push.XXXXXX)"; trap 'rm -rf "$T"' EXIT
git -C "$REPO" archive --format=tar HEAD | tar -x -C "$T"
/usr/bin/python3 "$REPO/tools/secret_scan.py" --check "$T" >/dev/null || { echo "[$(ts)] secret scan FAILED on the push copy; not pushing"; exit 3; }
mkdir -p "$CLONE/$SUB"
rsync -rpt --delete --checksum "$T/" "$CLONE/$SUB/"
G add -A -- "$SUB"
if G diff --cached --name-only | grep -Ev "^$SUB/oid-desk/app/(oid_desk/tokens|tests/test_read_tokens)\.py$" | grep -Ei '(^|/)(secrets?|logs?|cache|data|venv|tailscale)/|\.(env|jsonl|parquet|sqlite3?|db|log|pid|pem|key)$|\.bak|TOKEN|API_KEY|api-key'; then
  echo "[$(ts)] guard: secret/data-like path staged (listed above); not pushing"; G reset -q; exit 4; fi
if G diff --cached --quiet; then
  echo "[$(ts)] $SUB already matches $(git -C "$REPO" rev-parse --short HEAD); nothing to push"
else
  LAST="$(cat "$LAST_FILE" 2>/dev/null || true)"
  if [ -n "$LAST" ] && git -C "$REPO" cat-file -e "$LAST^{commit}" 2>/dev/null; then RANGE="$LAST..HEAD"; else RANGE="-n 30 HEAD"; fi
  MSG="$T.msg"
  { echo "mini-oid-collector: sync from Mac mini @ $(git -C "$REPO" rev-parse --short HEAD) ($(date '+%Y-%m-%d %H:%M %Z'))"
    echo; echo "Mini commits covered:"; git -C "$REPO" log --format='- %h %s' $RANGE; } > "$MSG"
  G commit -q -F "$MSG"; rm -f "$MSG"
fi
# 4) push (also retries a commit left unpushed by an earlier failed run)
if [ "$(G rev-parse HEAD)" != "$(G rev-parse -q --verify "origin/$BRANCH" 2>/dev/null || echo none)" ]; then
  G push -q origin "HEAD:refs/heads/$BRANCH" || { echo "[$(ts)] push failed (key read-only or not authorized?)"; exit 10; }
  echo "[$(ts)] pushed $(G rev-parse --short HEAD) to $BRANCH"
fi
echo "$HEAD_SHA" > "$LAST_FILE"
echo "[$(ts)] push.sh done"
