#!/bin/bash
# OID mini desk installer. Run ON THE MAC MINI as jake from the unpacked folder:
#   tar xzf oid-mini-desk.tar.gz && cd oid-mini-desk && ./app/install.sh
# Idempotent. Installs to ~/oid-desk (OID_DESK_ROOT). EVERY JOB STAYS DISABLED (flags/*.disabled); nothing is
# bootstrapped into launchd. Enable later with ~/oid-desk/bin/oidctl enable <job>.
# Never touches ~/oid-quote (the quote collector) except: creates secrets/OID_DESK_WRITE_TOKEN if missing.
# Desk tree: first install copies desk/ in full; upgrades replace CODE only (*.py, *.sh, config/mirror-feeds.json,
# config/mini-desk.json defaults if absent) and keep data/ledger/config the box pushes.
# Env: OID_DESK_ROOT, OID_SECRETS_DIR (default ~/oid-quote/secrets), PYTHON (default /opt/homebrew/bin/python3.12),
#      OID_DESK_SKIP_LAUNCHD=1 (tests; also skips nothing else since install never bootstraps).
set -euo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${OID_DESK_ROOT:-$HOME/oid-desk}"
SECRETS="${OID_SECRETS_DIR:-$HOME/oid-quote/secrets}"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
say() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -x "$PY" ] || PY="$(command -v python3.12 || command -v python3 || true)"
[ -n "$PY" ] && "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || die "need python >= 3.10"
[ -d "$PKG/app/oid_desk" ] && [ -d "$PKG/desk" ] || die "run from the unpacked oid-mini-desk folder"
say "install root $ROOT  (python $("$PY" -V 2>&1))"

umask 022
mkdir -p "$ROOT"/{app,desk,flags,logs,launchd,state,overrides,env,bin}
# ---- venv (stdlib only; isolates from system python)
[ -x "$ROOT/venv/bin/python" ] || "$PY" -m venv "$ROOT/venv"
# ---- app code (replaced every install)
rm -rf "$ROOT/app/oid_desk" "$ROOT/app/tests" "$ROOT/app/vendor"
cp -R "$PKG/app/oid_desk" "$PKG/app/tests" "$PKG/app/vendor" "$ROOT/app/"
cp "$PKG/app/jobs.json" "$PKG/app/README.md" "$PKG/app/install.sh" "$PKG/app/uninstall.sh" "$ROOT/app/"
cp "$PKG"/app/bin/* "$ROOT/bin/"; chmod 755 "$ROOT"/bin/* "$ROOT/app/vendor/"*.sh
# ---- shadow overrides + env switches (only if absent: a flip deletes them on purpose)
FIRST=0; [ -f "$ROOT/state/installed.json" ] || FIRST=1
if [ $FIRST -eq 1 ]; then
  for f in "$PKG"/app/config/*.json; do [ -e "$f" ] && cp -n "$f" "$ROOT/overrides/" || true; done
  for f in "$PKG"/app/env/*.env; do [ -e "$f" ] && cp -n "$f" "$ROOT/env/" || true; done
fi
# ---- desk tree
if [ $FIRST -eq 1 ] || [ ! -f "$ROOT/desk/dashboard/live_refresh.py" ]; then
  say "first install: copying desk snapshot"
  cp -R "$PKG/desk/." "$ROOT/desk/"
else
  say "upgrade: refreshing desk code only (*.py, *.sh, catalog)"
  ( cd "$PKG/desk" && find . -type f \( -name '*.py' -o -name '*.sh' \) -print0 ) | while IFS= read -r -d '' f; do
    mkdir -p "$ROOT/desk/$(dirname "$f")"; cp "$PKG/desk/$f" "$ROOT/desk/$f"; done
  cp "$PKG/desk/config/mirror-feeds.json" "$ROOT/desk/config/mirror-feeds.json"
  [ -f "$ROOT/desk/config/mini-desk.json" ] || cp "$PKG/desk/config/mini-desk.json" "$ROOT/desk/config/"
fi
# apply shadow overrides to the seeded desk configs (box pushes re-apply them via /v1/desk-state)
"$ROOT/venv/bin/python" - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "app"))
from oid_desk.api import deep_merge, strip_doc
for ov in (root / "overrides").glob("*.json"):
    tgt = root / "desk" / "config" / ov.name
    if tgt.exists():
        tgt.write_text(json.dumps(deep_merge(json.loads(tgt.read_text()), strip_doc(json.loads(ov.read_text()))), indent=1) + "\n")
        print(f"==> override applied: config/{ov.name}")
PY
mkdir -p "$ROOT/desk/cache" "$ROOT/desk/tmp" "$ROOT/desk/market-data/latest" "$ROOT/desk/secrets"
chmod 700 "$ROOT/desk/secrets"
# FlashAlpha key path the desk code expects -> the mini secrets file (value never copied)
ln -sfn "$SECRETS/FLASHALPHA_API_KEY" "$ROOT/desk/secrets/flashalpha-api-key"
# ---- write token for POST /v1/desk-state (never printed; handed to the box by `oidctl token-handoff`)
mkdir -p "$SECRETS"; chmod 700 "$SECRETS"
if [ ! -s "$SECRETS/OID_DESK_WRITE_TOKEN" ]; then
  ( umask 077; "$ROOT/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))' > "$SECRETS/OID_DESK_WRITE_TOKEN" )
  say "generated OID_DESK_WRITE_TOKEN (not printed)"
fi
# ---- every job disabled by default
"$ROOT/venv/bin/python" - "$ROOT" <<'PY'
import json, sys, time
from pathlib import Path
root = Path(sys.argv[1])
reg = json.loads((root / "app" / "jobs.json").read_text())
for job in reg["jobs"]:
    plist = Path.home() / "Library" / "LaunchAgents" / f"{reg['label_prefix']}{job}.plist"
    f = root / "flags" / f"{job}.disabled"
    if not plist.exists() and not f.exists():
        f.write_text("installed disabled\n")
(root / "state" / "installed.json").write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S %Z")}) + "\n")
PY
# ---- tests + selfcheck (no network)
( cd "$ROOT/app" && OID_DESK_ROOT="$ROOT" PYTHONPATH="$ROOT/app" "$ROOT/venv/bin/python" -m unittest discover -s tests -t . -q ) || die "unit tests failed"
"$ROOT/bin/oidctl" selfcheck || true
"$ROOT/bin/oidctl" list
command -v jq >/dev/null || printf 'WARN: jq not found (needed only by the publish job): brew install jq\n' >&2
say "done. All jobs disabled. Next: ~/oid-desk/bin/enter-keys.sh, then oidctl enable <job> per the runbook."
