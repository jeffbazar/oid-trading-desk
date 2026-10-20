#!/bin/bash
# launchd entrypoint: run-job.sh <job> <command...>
# 1) exits 0 (stays down: KeepAlive SuccessfulExit=false) when <root>/flags/<job>.disabled exists
# 2) exports the job's secrets (jobs.json "secrets") from $OID_SECRETS_DIR as env vars; a missing
#    required secret -> log + exit 0 (status shows the job down; no restart storm)
# 3) exec the command. Values are never echoed.
set -u
JOB="$1"; shift
ROOT="${OID_DESK_ROOT:?OID_DESK_ROOT not set}"
SECRETS="${OID_SECRETS_DIR:-$HOME/oid-quote/secrets}"
LOG="$ROOT/logs/$JOB.log"
mkdir -p "$ROOT/logs"
ts() { date '+%Y-%m-%d %I:%M:%S %p %Z'; }
if [ -f "$ROOT/flags/$JOB.disabled" ] && [ "${OID_DESK_IGNORE_FLAG:-0}" != "1" ]; then
  echo "$(ts) [$JOB] disabled by flag; not starting" >>"$LOG"; exit 0
fi
PY="${OID_DESK_PY:-$ROOT/venv/bin/python}"
NAMES="$("$PY" -c 'import json,sys; s=json.load(open(sys.argv[1]))["jobs"][sys.argv[2]]; o=set(s.get("optional_secrets") or []); print(" ".join(("?" if n in o else "")+n for n in s.get("secrets") or []))' "$ROOT/app/jobs.json" "$JOB")" || { echo "$(ts) [$JOB] jobs.json unreadable" >>"$LOG"; exit 0; }
for n in $NAMES; do
  opt=0; case "$n" in \?*) opt=1; n="${n#\?}";; esac
  f="$SECRETS/$n"
  if [ -s "$f" ]; then
    export "$n=$(tr -d '\r\n' < "$f")"
  elif [ $opt -eq 0 ]; then
    echo "$(ts) [$JOB] required secret $n missing in $SECRETS; not starting (run enter-keys.sh)" >>"$LOG"; exit 0
  fi
done
# Non-secret per-job env overrides (e.g. shadow switches): <root>/env/<job>.env, KEY=VALUE lines
if [ -f "$ROOT/env/$JOB.env" ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue;; esac
    case "$k" in *[!A-Za-z0-9_]*) continue;; esac
    export "$k=$v"
  done < "$ROOT/env/$JOB.env"
fi
echo "$(ts) [$JOB] starting" >>"$LOG"
exec "$@"
