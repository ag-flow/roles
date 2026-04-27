#!/usr/bin/env bash
# Active le KV v2 engine au path secret/ dans OpenBao.
set -euo pipefail

OPENBAO_URL="${OPENBAO_URL:-http://localhost:8200}"
OPENBAO_TOKEN="${OPENBAO_TOKEN:-${OPENBAO_DEV_TOKEN:-dev-only-token-change-me}}"

export VAULT_ADDR="$OPENBAO_URL"
export VAULT_TOKEN="$OPENBAO_TOKEN"

if ! command -v bao >/dev/null 2>&1; then
    echo "OpenBao CLI 'bao' not found. Install from https://openbao.org/docs/install/" >&2
    exit 1
fi

if bao secrets list 2>/dev/null | grep -q "^secret/"; then
    echo "KV v2 engine already enabled at secret/"
else
    bao secrets enable -path=secret -version=2 kv
    echo "KV v2 engine enabled at secret/"
fi

echo ""
echo "Expected secret paths (created on demand by the app) :"
echo "  secret/scraping-credentials/{tenant_id}/{platform}/{credential_id}"
echo "  secret/transcription-keys/{tenant_id}/{provider}/{key_id}"
echo "  secret/github-tokens/{tenant_id}/{user_id}"
