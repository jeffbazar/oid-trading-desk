#!/usr/bin/env bash
# Thin wrapper: scripts/oid-cutover.sh status | shadow <g|all> | flip <g> | rollback <g> | off <g>
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/oid_cutover.py" "$@"
