#!/usr/bin/env bash
# Drop + recrée la base, puis ré-applique toutes les migrations.
# DEV ONLY. À ne JAMAIS exécuter en prod.
set -euo pipefail

if [ "${ALLOW_RESET:-}" != "yes" ]; then
    echo "Refus : exporter ALLOW_RESET=yes pour confirmer le reset." >&2
    exit 1
fi

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
DB_NAME="$(echo "$DB_URL" | sed -E 's|.*/([^?]+).*|\1|')"
ADMIN_URL="$(echo "$DB_URL" | sed -E "s|/${DB_NAME}|/postgres|")"

echo "Dropping & recreating database '$DB_NAME'…"
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB_NAME\""
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$DB_NAME\""

"$(dirname "$0")/apply_migrations.sh"
