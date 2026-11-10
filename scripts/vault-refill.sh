#!/usr/bin/env bash
# Refill dev-mode Vault from the last good copy in the Kubernetes Secret.
# Values are piped through stdin, never printed or passed as arguments.
set -euo pipefail
NS=sanvi; SECRET=llm-keys; VPOD=vault-0; VNS=vault

get() { kubectl -n "$NS" get secret "$SECRET" -o jsonpath="{.data.$1}" | base64 -d; }

for pair in "LLM_API_KEY:sanvi/llm:api_key" "LITELLM_MASTER_KEY:sanvi/gateway:master_key"; do
  IFS=: read -r k path prop <<<"$pair"
  len=$(get "$k" | wc -c)
  [ "$len" -gt 20 ] || { echo "ERROR: $k looks empty ($len chars) - stopping"; exit 1; }
  get "$k" | kubectl -n "$VNS" exec -i "$VPOD" -- vault kv put "secret/$path" "$prop=-" >/dev/null
  echo "OK  secret/$path ($prop, $len chars)"
done

kubectl -n "$NS" annotate externalsecret "$SECRET" force-sync="$(date +%s)" --overwrite >/dev/null
echo "OK  ExternalSecret force-synced"
