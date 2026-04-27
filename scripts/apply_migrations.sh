#!/usr/bin/env bash
# Applique toutes les migrations SQL du dossier migrations/ dans l'ordre numérique.
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
MIGRATIONS_DIR="$(dirname "$0")/../migrations"

if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "Migrations directory not found: $MIGRATIONS_DIR" >&2
    exit 1
fi

echo "Applying migrations from $MIGRATIONS_DIR"
for file in "$MIGRATIONS_DIR"/*.sql; do
    echo ">> $(basename "$file")"
    psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$file"
done

echo "All migrations applied."
