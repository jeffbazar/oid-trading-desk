#!/bin/bash
# Jeffrey runs this ON THE MINI himself (Terminal or Screen Sharing), never via chat or a pasted command with values.
#   ~/oid-desk/bin/enter-keys.sh                    prompts for every desk key (Enter = keep existing)
#   ~/oid-desk/bin/enter-keys.sh UW_API_KEY ...     prompts only for the named keys
#   ~/oid-desk/bin/enter-keys.sh --archive [NAME ...]
#        2026-10-18: research-archive keys -> ~/oid-data/secrets (dir 700, files 600):
#        GRADER_API_KEY, OID_ARCHIVE_READ_TOKEN, X_BEARER_TOKEN
#   ~/oid-desk/bin/enter-keys.sh --archive --generate-read-token
#        creates a random OID_ARCHIVE_READ_TOKEN on the mini (never printed; replaces an existing one only if you confirm)
# Input is hidden (read -s), not in shell history, written 600. Prints only present/missing. No key value ever leaves
# the mini through this script, and agents never type or copy key values.
set -u
ARCHIVE=0; GEN=0; ARGS=""
for a in "$@"; do
  case "$a" in --archive) ARCHIVE=1;; --generate-read-token) GEN=1;; *) ARGS="$ARGS $a";; esac
done
umask 077
if [ "$ARCHIVE" = 1 ]; then
  DATA="${OID_DATA_ROOT:-$HOME/oid-data}"; SECRETS="$DATA/secrets"
  ALL="GRADER_API_KEY OID_ARCHIVE_READ_TOKEN X_BEARER_TOKEN"; KNOWN=" $ALL "
  mkdir -p "$SECRETS"; chmod 700 "$DATA" "$SECRETS"
  if [ "$GEN" = 1 ]; then
    f="$SECRETS/OID_ARCHIVE_READ_TOKEN"
    if [ -s "$f" ]; then printf 'OID_ARCHIVE_READ_TOKEN is present. Replace it? [y/N] '; read -r yn; [ "$yn" = y ] || [ "$yn" = Y ] || { echo "kept"; GEN=2; }; fi
    if [ "$GEN" = 1 ]; then
      /usr/bin/python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(32)+"\n")' > "$f.tmp" && chmod 600 "$f.tmp" && mv "$f.tmp" "$f" && echo "  generated OID_ARCHIVE_READ_TOKEN (not shown)"
    fi
    NAMES=""
  else
    NAMES="${ARGS:-$ALL}"
  fi
else
  SECRETS="${OID_SECRETS_DIR:-$HOME/oid-quote/secrets}"
  ALL="FLASHALPHA_API_KEY UW_API_KEY HERENOW_API_KEY EIA_API_KEY"
  KNOWN=" FLASHALPHA_API_KEY UW_API_KEY HERENOW_API_KEY EIA_API_KEY BENZINGA_API_TOKEN APCA_API_KEY_ID APCA_API_SECRET_KEY "
  NAMES="${ARGS:-$ALL}"
  mkdir -p "$SECRETS"; chmod 700 "$SECRETS"
fi
for n in $NAMES; do
  case "$KNOWN" in *" $n "*) ;; *) echo "skip unknown name $n"; continue;; esac
  have="missing"; [ -s "$SECRETS/$n" ] && have="present"
  printf '%s (%s; Enter keeps it): ' "$n" "$have"
  IFS= read -rs V; echo
  if [ -n "$V" ]; then printf '%s\n' "$V" > "$SECRETS/$n"; chmod 600 "$SECRETS/$n"; echo "  saved $n"; fi
  unset V
done
echo; echo "Key files in $SECRETS (presence only):"
if [ "$ARCHIVE" = 1 ]; then LIST="$ALL"; else LIST="APCA_API_KEY_ID APCA_API_SECRET_KEY OID_QUOTE_TOKEN OID_DESK_WRITE_TOKEN $ALL"; fi
for n in $LIST; do
  if [ -s "$SECRETS/$n" ]; then echo "  present  $n"; else echo "  missing  $n"; fi
done
