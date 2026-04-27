#!/bin/bash
###############################################################################
# Script 03 : Déploiement de la stack Role Builder dans un LXC Docker-ready
#
# A executer DANS le container LXC (en tant que root ou user agflow avec sudo).
# Pre-requis : 00-create-lxc.sh + 01-install-docker.sh exécutés (Docker + Compose).
#
# Etapes :
#   1. Clone (ou pull) le repo agflow.roles dans /opt/agflow.roles
#   2. Login GHCR avec le PAT fourni
#   3. Cree .env depuis .env.example (genere les passwords aleatoires)
#   4. docker compose pull (toutes les images depuis GHCR)
#   5. docker compose up -d (postgres + minio + openbao + backend + frontend)
#   6. Wait healthy (postgres + minio + openbao)
#   7. Apply migrations SQL via docker compose exec postgres
#   8. Init MinIO (3 buckets) via docker compose exec minio mc
#   9. Init OpenBao (KV v2) via docker compose exec openbao bao
#  10. Healthcheck final : curl /health/
#
# Variables d'environnement requises :
#   GHCR_OWNER          - owner GHCR (lowercase), ex: ag-flow
#   GHCR_USER           - user GitHub pour le login
#   GHCR_TOKEN          - PAT GitHub avec permissions read:packages
#
# Variables optionnelles (si non définies, valeurs par défaut/aléatoires) :
#   IMAGE_TAG           - tag d'image à pull (défaut: latest)
#   REPO_URL            - URL git du repo (défaut: https://github.com/ag-flow/roles.git)
#   REPO_BRANCH         - branche à checkout (défaut: main)
#   INSTALL_DIR         - répertoire d'installation (défaut: /opt/agflow.roles)
#
# Usage typique depuis l'hote Proxmox :
#   pct exec <CTID> -- env GHCR_OWNER=ag-flow GHCR_USER=mygithubuser \
#       GHCR_TOKEN=ghp_xxx bash /root/03-deploy-rolebuilder.sh
###############################################################################
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# ── Variables ────────────────────────────────────────────────────────────────
GHCR_OWNER="${GHCR_OWNER:-}"
GHCR_USER="${GHCR_USER:-}"
GHCR_TOKEN="${GHCR_TOKEN:-}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REPO_URL="${REPO_URL:-https://github.com/ag-flow/roles.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/agflow.roles}"

if [ -z "${GHCR_OWNER}" ] || [ -z "${GHCR_USER}" ] || [ -z "${GHCR_TOKEN}" ]; then
    echo "ERREUR : GHCR_OWNER, GHCR_USER et GHCR_TOKEN sont requis." >&2
    echo "Exemple : env GHCR_OWNER=ag-flow GHCR_USER=mygithubuser GHCR_TOKEN=ghp_xxx $0" >&2
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo "ERREUR : Docker n'est pas installe. Lancez 01-install-docker.sh d'abord." >&2
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo "ERREUR : Docker Compose plugin manquant." >&2
    exit 1
fi

# ── Outils nécessaires ───────────────────────────────────────────────────────
echo "==========================================="
echo "  Deploiement Role Builder"
echo "==========================================="
echo "  GHCR_OWNER  : ${GHCR_OWNER}"
echo "  IMAGE_TAG   : ${IMAGE_TAG}"
echo "  REPO_URL    : ${REPO_URL}"
echo "  REPO_BRANCH : ${REPO_BRANCH}"
echo "  INSTALL_DIR : ${INSTALL_DIR}"
echo ""

# Installer git + curl si absents (LXC minimaux)
for tool in git curl; do
    if ! command -v "${tool}" &>/dev/null; then
        echo "[deps] Installation ${tool}..."
        apt-get update -qq
        apt-get install -y -qq "${tool}"
    fi
done

# ── 1. Clone ou pull le repo ─────────────────────────────────────────────────
echo "[1/10] Clone / pull du repo..."
if [ ! -d "${INSTALL_DIR}" ]; then
    git clone --branch "${REPO_BRANCH}" --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
    echo "  -> Cloné dans ${INSTALL_DIR}"
else
    cd "${INSTALL_DIR}"
    git fetch --depth 1 origin "${REPO_BRANCH}"
    git reset --hard "origin/${REPO_BRANCH}"
    echo "  -> Mis à jour à origin/${REPO_BRANCH}"
fi
cd "${INSTALL_DIR}"

# ── 2. Login GHCR ────────────────────────────────────────────────────────────
echo "[2/10] Login GHCR..."
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
echo "  -> Logged in to ghcr.io as ${GHCR_USER}"

# ── 3. Generer .env si absent ────────────────────────────────────────────────
echo "[3/10] Génération .env..."
if [ -f "${INSTALL_DIR}/.env" ]; then
    echo "  -> .env existe déjà — non écrasé"
else
    cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"

    # Helper : génère un secret aléatoire URL-safe de 32 char
    rand() { tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 32; }

    POSTGRES_PASS=$(rand)
    MINIO_PASS=$(rand)
    OPENBAO_TOKEN=$(rand)

    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASS}|" "${INSTALL_DIR}/.env"
    sed -i "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=${MINIO_PASS}|" "${INSTALL_DIR}/.env"
    sed -i "s|^OPENBAO_DEV_TOKEN=.*|OPENBAO_DEV_TOKEN=${OPENBAO_TOKEN}|" "${INSTALL_DIR}/.env"
    sed -i "s|^GHCR_OWNER=.*|GHCR_OWNER=${GHCR_OWNER}|" "${INSTALL_DIR}/.env"
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${IMAGE_TAG}|" "${INSTALL_DIR}/.env"

    # Cohérence DATABASE_URL avec POSTGRES_PASSWORD
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://rb:${POSTGRES_PASS}@postgres:5432/role_builder|" "${INSTALL_DIR}/.env"

    echo "  -> .env généré avec passwords aléatoires"
    echo "     POSTGRES_PASSWORD : ${POSTGRES_PASS}"
    echo "     MINIO_ROOT_PASSWORD : ${MINIO_PASS}"
    echo "     OPENBAO_DEV_TOKEN : ${OPENBAO_TOKEN}"
fi

# ── 4. Pull images depuis GHCR ───────────────────────────────────────────────
echo "[4/10] Pull des images depuis GHCR..."
cd "${INSTALL_DIR}"
docker compose pull
echo "  -> Images pull OK"

# ── 5. Up de la stack ────────────────────────────────────────────────────────
echo "[5/10] Démarrage de la stack..."
docker compose up -d
echo "  -> Stack démarrée en background"

# ── 6. Wait healthy ──────────────────────────────────────────────────────────
echo "[6/10] Attente que les services soient healthy..."
TIMEOUT=120
for service in postgres minio openbao; do
    elapsed=0
    while [ ${elapsed} -lt ${TIMEOUT} ]; do
        STATUS=$(docker compose ps --format json "${service}" 2>/dev/null | \
            grep -oE '"Health":"[^"]*"' | head -1 | cut -d':' -f2 | tr -d '"' || echo "")
        if [ "${STATUS}" = "healthy" ]; then
            echo "  -> ${service} healthy"
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        echo "  -> ${service} pas encore healthy (${elapsed}s)"
    done
    if [ ${elapsed} -ge ${TIMEOUT} ]; then
        echo "  [!] ${service} pas healthy après ${TIMEOUT}s — vérifier 'docker compose logs ${service}'"
    fi
done

# ── 7. Apply migrations SQL ──────────────────────────────────────────────────
echo "[7/10] Application des migrations SQL..."
for migration in "${INSTALL_DIR}"/migrations/*.sql; do
    name=$(basename "${migration}")
    echo "  >> ${name}"
    docker compose exec -T postgres psql -U rb -d role_builder -v ON_ERROR_STOP=1 < "${migration}" >/dev/null
done
echo "  -> Toutes les migrations appliquées"

# ── 8. Init MinIO (3 buckets) ────────────────────────────────────────────────
echo "[8/10] Création des buckets MinIO..."
. "${INSTALL_DIR}/.env"
docker compose exec -T minio sh -c "
mc alias set rb-local http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} >/dev/null 2>&1
for bucket in corpus-audio corpus-transcripts corpus-thumbnails; do
    if ! mc ls rb-local/\$bucket >/dev/null 2>&1; then
        mc mb rb-local/\$bucket
        echo '  -> Created: '\$bucket
    else
        echo '  -> Exists: '\$bucket
    fi
done
"

# ── 9. Init OpenBao (KV v2) ──────────────────────────────────────────────────
echo "[9/10] Activation OpenBao KV v2..."
docker compose exec -T openbao sh -c "
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=${OPENBAO_DEV_TOKEN}
if bao secrets list 2>/dev/null | grep -q '^secret/'; then
    echo '  -> KV v2 déjà activé'
else
    bao secrets enable -path=secret -version=2 kv
    echo '  -> KV v2 activé au path secret/'
fi
"

# ── 10. Healthcheck final ────────────────────────────────────────────────────
echo "[10/10] Healthcheck backend..."
sleep 5
HEALTH=$(curl -fsS http://localhost:8000/health/ 2>/dev/null || echo "FAILED")
if echo "${HEALTH}" | grep -q '"status":"ok"'; then
    echo "  -> Backend OK : ${HEALTH}"
else
    echo "  [!] Backend health echec : ${HEALTH}"
    echo "       docker compose logs backend --tail 30"
    docker compose logs backend --tail 30 || true
fi

# ── Résumé ───────────────────────────────────────────────────────────────────
CT_IP=$(ip -4 addr show eth0 2>/dev/null | grep inet | awk '{print $2}' | cut -d/ -f1 | head -1 || echo "?")

echo ""
echo "==========================================="
echo "  Role Builder déployé"
echo "==========================================="
echo ""
echo "  Stack : $(docker compose ps --format '{{.Service}}' | tr '\n' ' ')"
echo ""
echo "  URLs :"
echo "    Backend  : http://${CT_IP}:8000/health/"
echo "    Frontend : http://${CT_IP}:3000"
echo "    MinIO console : http://${CT_IP}:9001"
echo "    OpenBao  : http://${CT_IP}:8200"
echo ""
echo "  Secrets (sauvegardés dans ${INSTALL_DIR}/.env) :"
echo "    POSTGRES_PASSWORD"
echo "    MINIO_ROOT_PASSWORD"
echo "    OPENBAO_DEV_TOKEN"
echo ""
echo "  Commandes utiles :"
echo "    cd ${INSTALL_DIR}"
echo "    docker compose ps"
echo "    docker compose logs -f backend"
echo "    docker compose pull && docker compose up -d   # mise à jour"
echo ""
echo "==========================================="

# Sortie JSON (convention pipeline agflow)
echo "{\"status\":\"ok\",\"install_dir\":\"${INSTALL_DIR}\",\"ip\":\"${CT_IP}\",\"image_tag\":\"${IMAGE_TAG}\"}"
