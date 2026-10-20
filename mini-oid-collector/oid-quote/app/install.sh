#!/bin/bash
# OID quote collector installer — run ON THE MAC MINI as the logged-in user (jake), from the unpacked folder:
#   tar xzf oid-quote-collector.tar.gz && cd oid-quote-collector && ./install.sh
# Idempotent: re-run to upgrade. Never touches secrets other than creating OID_QUOTE_TOKEN if missing.
# Env overrides: OID_QUOTE_ROOT (default ~/oid-quote), PYTHON (default /opt/homebrew/bin/python3.12),
#                OID_QUOTE_SKIP_LAUNCHD=1 (dev/test: skip the launchd agent).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${OID_QUOTE_ROOT:-$HOME/oid-quote}"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
LABEL="com.oid.quote-collector"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST="$AGENT_DIR/$LABEL.plist"

say() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- python
if [ ! -x "$PY" ]; then
  PY="$(command -v python3.12 || true)"
fi
[ -n "$PY" ] && [ -x "$PY" ] || die "python3.12 not found. Install with: brew install python@3.12  (or PYTHON=/path/to/python3.12 ./install.sh)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || die "need Python >= 3.12 (got: $("$PY" -V 2>&1))"
say "python: $PY ($("$PY" -V 2>&1))"
say "install root: $ROOT"

# ---------------------------------------------------------------- layout
umask 022
mkdir -p "$ROOT/secrets" "$ROOT/app" "$ROOT/logs" "$ROOT/cache"
chmod 700 "$ROOT/secrets"

# ---------------------------------------------------------------- venv + deps
if [ ! -x "$ROOT/venv/bin/python" ]; then
  say "creating venv at $ROOT/venv"
  "$PY" -m venv "$ROOT/venv"
fi
VPY="$ROOT/venv/bin/python"
say "installing requirements"
"$VPY" -m pip install --quiet --disable-pip-version-check --upgrade pip
"$VPY" -m pip install --quiet --disable-pip-version-check -r "$SRC/requirements.txt"

# ---------------------------------------------------------------- app files
say "copying app files to $ROOT/app"
rm -rf "$ROOT/app/oid_quote" "$ROOT/app/tests"
cp -R "$SRC/oid_quote" "$ROOT/app/"
cp -R "$SRC/tests" "$ROOT/app/"
for f in stream-quote-allowlist.json requirements.txt README.md config.example.json com.oid.quote-collector.plist install.sh uninstall.sh; do
  cp "$SRC/$f" "$ROOT/app/"
done
find "$ROOT/app" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
[ -f "$ROOT/config.json" ] || { cp "$SRC/config.example.json" "$ROOT/config.json"; say "created $ROOT/config.json"; }
[ -f "$ROOT/options-subs.json" ] || { echo '[]' > "$ROOT/options-subs.json"; say "created empty $ROOT/options-subs.json"; }

# ---------------------------------------------------------------- read token (never printed)
TOK="$ROOT/secrets/OID_QUOTE_TOKEN"
if [ ! -s "$TOK" ]; then
  ( umask 077; "$VPY" -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TOK" )
  say "generated API read token at $TOK (not printed)"
else
  say "keeping existing API read token"
fi
chmod 600 "$ROOT"/secrets/* 2>/dev/null || true

if [ -s "$ROOT/secrets/APCA_API_KEY_ID" ] && [ -s "$ROOT/secrets/APCA_API_SECRET_KEY" ]; then
  say "Alpaca keys: present"
else
  warn "Alpaca keys not found in $ROOT/secrets — collector will run in placeholder mode (health status=no_keys). See README 'Save your keys'."
fi

# ---------------------------------------------------------------- byte-compile sanity check
"$VPY" -m compileall -q "$ROOT/app/oid_quote" >/dev/null
( cd "$ROOT/app" && PYTHONPATH="$ROOT/app" "$VPY" -m oid_quote --root "$ROOT" --check >/dev/null ) || die "config check failed: run  cd $ROOT/app && $VPY -m oid_quote --root $ROOT --check"

PORT="$("$VPY" -c 'import json,sys
try: print(int(json.load(open(sys.argv[1])).get("port", 8787)))
except Exception: print(8787)' "$ROOT/config.json")"

# ---------------------------------------------------------------- launchd agent
sed "s#__ROOT__#$ROOT#g" "$SRC/com.oid.quote-collector.plist" > "$ROOT/app/$LABEL.rendered.plist"

if [ "${OID_QUOTE_SKIP_LAUNCHD:-0}" = "1" ] || ! command -v launchctl >/dev/null 2>&1; then
  warn "skipping launchd (OID_QUOTE_SKIP_LAUNCHD=1 or no launchctl). Rendered plist: $ROOT/app/$LABEL.rendered.plist"
  warn "run in foreground with:  cd $ROOT/app && $VPY -m oid_quote --root $ROOT"
  exit 0
fi

UIDN="$(id -u)"
DOMAIN="gui/$UIDN"
launchctl print "$DOMAIN" >/dev/null 2>&1 || DOMAIN="user/$UIDN"

# stop any previous copy before checking the port
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
for _ in 1 2 3 4 5 6 7 8 9 10; do
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || break
  sleep 0.5
done

if command -v lsof >/dev/null 2>&1; then
  HOLDER="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1" (pid "$2")"}' | sort -u | tr '\n' ' ' || true)"
  if [ -n "$HOLDER" ]; then
    warn "port $PORT is already in use by: $HOLDER"
    warn "stop that process (e.g. the Phase 0 placeholder) or change \"port\" in $ROOT/config.json, then re-run ./install.sh"
  fi
fi

mkdir -p "$AGENT_DIR"
cp "$ROOT/app/$LABEL.rendered.plist" "$PLIST"
chmod 644 "$PLIST"
if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$PLIST" >/dev/null || die "plist failed lint: $PLIST"
fi

say "loading launchd agent $LABEL into $DOMAIN"
if ! launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null; then
  warn "launchctl bootstrap failed; trying legacy 'launchctl load -w'"
  launchctl load -w "$PLIST" || die "could not load $PLIST"
fi
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null || true

# ---------------------------------------------------------------- health check
say "waiting for http://127.0.0.1:$PORT/v1/health"
OUT=""
for _ in $(seq 1 30); do
  if OUT="$(curl -fsS --max-time 2 "http://127.0.0.1:$PORT/v1/health" 2>/dev/null)"; then
    break
  fi
  OUT=""
  sleep 1
done

if [ -z "$OUT" ]; then
  warn "collector did not answer on port $PORT within 30s"
  warn "check: tail -n 50 $ROOT/logs/collector.log $ROOT/logs/launchd.err.log ; launchctl print $DOMAIN/$LABEL | head -40"
  exit 1
fi

printf '%s' "$OUT" | "$VPY" -c '
import json, sys
h = json.load(sys.stdin)
s, o = h.get("stocks") or {}, h.get("options") or {}
print("health:", h["status"])
print("  keys present:", all(h["keys_present"].values()), "| token configured:", h["token_configured"])
print("  stocks : connected=%s feed=%s desired=%s subscribed=%s" % (s.get("connected"), s.get("feed"), s.get("desired_count"), s.get("subscribed_count")))
print("  options: connected=%s feed=%s desired=%s subscribed=%s" % (o.get("connected"), o.get("feed"), o.get("desired_count"), o.get("subscribed_count")))
'
say "installed. Logs: $ROOT/logs/collector.log   Cache: $ROOT/cache/quotes.json"
say "restart: launchctl kickstart -k $DOMAIN/$LABEL    stop: launchctl bootout $DOMAIN/$LABEL"
