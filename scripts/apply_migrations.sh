#!/usr/bin/env bash
# Applique les migrations SQL du dossier migrations/ dans l'ordre numérique, en
# suivant la table `schema_migrations` — MÊME contrat que le runner intégré au
# backend (backend/src/role_builder/migrations.py). Les migrations déjà
# appliquées sont sautées, ce qui rend le script idempotent et compatible avec
# une base déjà migrée par le backend (BUG-57 : sinon psql échouait sur 0001
# « relation already exists », ou le backend crash-loopait sur une base migrée
# hors suivi).
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
MIGRATIONS_DIR="$(dirname "$0")/../migrations"

if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "Migrations directory not found: $MIGRATIONS_DIR" >&2
    exit 1
fi

# Table de suivi (identique au runner).
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -c \
    "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"

echo "Applying migrations from $MIGRATIONS_DIR"
for file in "$MIGRATIONS_DIR"/*.sql; do
    version="$(basename "$file")"
    already="$(psql "$DB_URL" -tA -c \
        "SELECT 1 FROM schema_migrations WHERE version = '${version}'")"
    if [ "$already" = "1" ]; then
        echo ">> $version (déjà appliquée, sautée)"
        continue
    fi
    echo ">> $version"
    # Migration + enregistrement dans une même transaction (--single-transaction).
    psql "$DB_URL" -v ON_ERROR_STOP=1 --single-transaction \
        -f "$file" \
        -c "INSERT INTO schema_migrations (version) VALUES ('${version}')"
done

echo "All migrations applied."
