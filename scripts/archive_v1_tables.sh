#!/usr/bin/env bash
# Dump les tables de synthèse/publication V1 avant leur suppression (refonte
# V2). Référence : docs/specs/v2/01-protocole-mcp.md § 4 "Supprimées".
#
# Prérequis à exécuter AVANT la migration 0006_drop_synthesis_tables.sql.
# Rejouable : si l'archive du jour existe déjà et est valide, ne refait rien
# (utiliser --force pour regénérer). Refuse de continuer si le dump produit
# est vide ou incomplet.
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
ARCHIVE_DIR="$(dirname "$0")/../archive"
DATE_TAG="$(date +%Y%m%d)"
OUT_FILE="$ARCHIVE_DIR/v1-synthesis-${DATE_TAG}.sql.gz"
FORCE="${1:-}"

# Tables listées dans docs/specs/v2/01-protocole-mcp.md § 4 "Supprimées".
TABLES=(
    corpus_chunks
    chunking_jobs
    prompts
    prompt_versions
    runs
    signals
    clusters
    document_plans
    role_documents
    role_publication_config
    role_publications
    github_integrations
    oauth_states
)

mkdir -p "$ARCHIVE_DIR"

if [ -f "$OUT_FILE" ] && [ "$FORCE" != "--force" ]; then
    echo "Archive déjà présente : $OUT_FILE (utiliser --force pour regénérer)."
    echo "Vérification de l'archive existante..."
else
    echo "Dump de ${#TABLES[@]} tables vers $OUT_FILE ..."
    table_args=()
    for t in "${TABLES[@]}"; do
        table_args+=(--table="$t")
    done
    pg_dump "$DB_URL" \
        --no-owner --no-privileges \
        "${table_args[@]}" \
        | gzip > "$OUT_FILE"
fi

echo "Vérification d'intégrité gzip..."
gzip -t "$OUT_FILE"

echo "Vérification du contenu du dump..."
CONTENT="$(zcat "$OUT_FILE")"

BYTE_SIZE="$(printf '%s' "$CONTENT" | wc -c)"
if [ "$BYTE_SIZE" -lt 200 ]; then
    echo "REFUS : dump anormalement petit (${BYTE_SIZE} octets) — $OUT_FILE" >&2
    exit 1
fi

MISSING=()
for t in "${TABLES[@]}"; do
    if ! grep -q "CREATE TABLE.*\"\?${t}\"\?" <<<"$CONTENT"; then
        MISSING+=("$t")
    fi
done

if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "REFUS : tables absentes du dump (déjà supprimées ? mauvaise DB ?) :" >&2
    printf '  - %s\n' "${MISSING[@]}" >&2
    exit 1
fi

echo "OK : archive valide, ${#TABLES[@]} tables présentes, ${BYTE_SIZE} octets décompressés."
echo "$OUT_FILE"
