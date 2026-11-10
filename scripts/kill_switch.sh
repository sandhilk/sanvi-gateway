#!/usr/bin/env bash
# SanVi kill switch. Usage: kill_switch.sh block <alias> | unblock <alias> | block-all | unblock-all | status
set -euo pipefail
GW=${SANVI_GATEWAY:-http://localhost:4000}; : "${SANVI_ADMIN_KEY:?Set SANVI_ADMIN_KEY}"
api() { curl -sf -H "Authorization: Bearer $SANVI_ADMIN_KEY" -H "Content-Type: application/json" "$@"; }
tokens() {  # print "token alias blocked" for each key (optionally filtered by alias)
  api "$GW/key/list?return_full_object=true&size=100" | python3 -c '
import sys, json
f = sys.argv[1] if len(sys.argv) > 1 else ""
for k in json.load(sys.stdin).get("keys", []):
    if isinstance(k, dict) and (not f or k.get("key_alias") == f):
        print(k["token"], k.get("key_alias") or "unnamed", k.get("blocked"))' "${1:-}"; }
act() { api -X POST "$GW/key/$1" -d "{\"key\": \"$2\"}" >/dev/null && echo "$1ed: $3"; }
case "${1:-status}" in
  block|unblock) [ -n "${2:-}" ] || { echo "need an alias"; exit 1; }
                 found=0; while read -r t a b; do act "$1" "$t" "$a"; found=1; done < <(tokens "$2")
                 [ $found = 1 ] || { echo "no key with alias $2"; exit 1; } ;;
  block-all|unblock-all) op=${1%-all}; while read -r t a b; do act "$op" "$t" "$a"; done < <(tokens) ;;
  status) tokens | awk '{printf "  %-20s blocked=%s\n", $2, $3}' ;;
  *) echo "usage: $0 block <alias> | unblock <alias> | block-all | unblock-all | status"; exit 1 ;;
esac
