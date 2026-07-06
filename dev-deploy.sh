#!/usr/bin/env bash
# Déploiement dev de roles — build local + docker compose + smoke test.
# Geste opérateur harmonisé avec le modèle devpod : sudo ./dev-deploy.sh [BRANCH]
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERREUR : ce script doit être exécuté en root (sudo ./dev-deploy.sh)." >&2
    exit 1
fi

REPO_URL="git@github.com:ag-flow/roles.git"

# --- 1) Positionnement dans le repo (mode "dans le repo" ou "bootstrap clone") ---
# git fetch + reset --hard (plutôt que pull --ff-only) : robuste quand ce
# script se met à jour lui-même via le commit qu'on est en train de fetcher.
# Branche = argument $1, sinon branche courante détectée.
if [ -d ".git" ]; then
  BRANCH="${1:-$(git branch --show-current)}"
  [ -z "$BRANCH" ] && BRANCH="main"
  echo "Repo détecté dans le répertoire courant: $(pwd)"
  echo "Mise à jour (fetch + reset --hard) sur ${BRANCH}..."
  git fetch origin "$BRANCH"
  DIRTY="$(git status --porcelain)"
  if [ -n "$DIRTY" ]; then
    echo "ATTENTION : modifications locales non commitées, elles vont être écrasées :" >&2
    echo "$DIRTY" >&2
  fi
  git reset --hard "origin/${BRANCH}"
else
  APP_DIR="roles"
  if [ -d "$APP_DIR/.git" ]; then
    BRANCH="${1:-$(git -C "$APP_DIR" branch --show-current)}"
    [ -z "$BRANCH" ] && BRANCH="main"
    echo "Repo déjà cloné dans ./${APP_DIR}"
    echo "Mise à jour (fetch + reset --hard) sur ${BRANCH}..."
    git -C "$APP_DIR" fetch origin "$BRANCH"
    DIRTY="$(git -C "$APP_DIR" status --porcelain)"
    if [ -n "$DIRTY" ]; then
      echo "ATTENTION : modifications locales non commitées, elles vont être écrasées :" >&2
      echo "$DIRTY" >&2
    fi
    git -C "$APP_DIR" reset --hard "origin/${BRANCH}"
  else
    echo "Clone du repo dans ./${APP_DIR}..."
    git clone "$REPO_URL" "$APP_DIR"
    if [ -n "${1:-}" ]; then
      git -C "$APP_DIR" checkout "$1"
    fi
  fi
  cd "$APP_DIR"
fi

ENV_FILE=".env"

# --- 2) .env ---
if [ ! -f "$ENV_FILE" ] && [ -f ".env.example" ]; then
  echo ".env absent -> création depuis .env.example"
  cp .env.example "$ENV_FILE"
fi

# --- 3) Complétion des secrets manquants ou vides ---
# Chaque secret est vérifié individuellement : le .env peut exister mais
# avoir des valeurs vides, ou porter le placeholder générique
# "changeme_in_real_env" copié tel quel depuis .env.example.

_env_get() { grep -m1 "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true; }
_env_set() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
}
_env_needs_generation() {
    local val
    val="$(_env_get "$1")"
    # Les indirections '${vault://...}' des anciens .env ne sont plus résolues
    # depuis la refonte self-service : un tel litéral doit être régénéré,
    # sinon il deviendrait la valeur effective du secret.
    [[ -z "$val" || "$val" == "changeme_in_real_env" || "$val" == *'${vault://'* ]]
}

if _env_needs_generation POSTGRES_USER || _env_needs_generation POSTGRES_PASSWORD; then
    PG_USER="rb_$(openssl rand -hex 4)"
    PG_PASS="$(openssl rand -hex 24)"
    PG_PORT="$(_env_get POSTGRES_PORT)"; PG_PORT="${PG_PORT:-5432}"
    PG_DB="$(_env_get POSTGRES_DB)"; PG_DB="${PG_DB:-role_builder}"
    DB_URL="postgresql://${PG_USER}:${PG_PASS}@localhost:${PG_PORT}/${PG_DB}"
    _env_set POSTGRES_USER     "$PG_USER"
    _env_set POSTGRES_PASSWORD "$PG_PASS"
    _env_set DATABASE_URL      "$DB_URL"
    echo "==> POSTGRES_USER/PASSWORD générés (${PG_USER})"
fi

if _env_needs_generation MINIO_ROOT_USER || _env_needs_generation MINIO_ROOT_PASSWORD; then
    MINIO_USER="minioadmin_$(openssl rand -hex 4)"
    MINIO_PASS="$(openssl rand -hex 24)"
    _env_set MINIO_ROOT_USER     "$MINIO_USER"
    _env_set MINIO_ROOT_PASSWORD "$MINIO_PASS"
    echo "==> MINIO_ROOT_USER/PASSWORD générés (${MINIO_USER})"
fi

if _env_needs_generation LOCAL_ADMIN_SECRET; then
    _env_set LOCAL_ADMIN_SECRET "$(openssl rand -hex 32)"
    echo "==> LOCAL_ADMIN_SECRET généré"
fi

if _env_needs_generation LOCAL_ADMIN_PASSWORD; then
    _env_set LOCAL_ADMIN_PASSWORD "$(openssl rand -hex 12)"
    echo "==> LOCAL_ADMIN_PASSWORD généré"
fi

if _env_needs_generation NEXTAUTH_SECRET; then
    _env_set NEXTAUTH_SECRET "$(openssl rand -hex 32)"
    echo "==> NEXTAUTH_SECRET généré"
fi

# KEYCLOAK_CLIENT_SECRET est un prérequis externe (jamais généré ici) : si
# l'ancien .env porte encore une indirection vault, on la vide + warning.
if [[ "$(_env_get KEYCLOAK_CLIENT_SECRET)" == *'${vault://'* ]]; then
    _env_set KEYCLOAK_CLIENT_SECRET ""
    echo "ATTENTION : KEYCLOAK_CLIENT_SECRET portait une indirection vault" >&2
    echo "obsolète — vidé. Renseigner la vraie valeur si l'auth Keycloak est utilisée." >&2
fi

# Clé Fernet (32 octets base64 url-safe) : chiffre les secrets utilisateur
# stockés en base (tokens de wallets Harpocrate + secrets "local").
if _env_needs_generation SECRET_ENCRYPTION_KEY; then
    _env_set SECRET_ENCRYPTION_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
    echo "==> SECRET_ENCRYPTION_KEY générée"
fi

unset -f _env_needs_generation

# --- 4) Build images locales ---
# build.sh ne lit que l'env du shell, pas .env : on lui passe l'IMAGE_TAG de
# .env pour qu'il tague les images comme le compose les attend au `up`, sinon
# `up --pull never` échoue « image not found » (BUG-59).
IMAGE_TAG="$(_env_get IMAGE_TAG)"; export IMAGE_TAG="${IMAGE_TAG:-latest}"
chmod +x build.sh
./build.sh

# --- 5) Nettoyage containers orphelins / anciennes runs du projet ---
# down supprime les containers du projet + réseaux, et --remove-orphans enlève ceux qui traînent
echo "Arrêt/cleanup du projet docker compose (incl. orphelins)..."
docker compose -f docker-compose-dev.yml down --remove-orphans || true

# --- 6) Relance ---
# --remove-orphans : supprime les orphelins détectés
# --pull never : utilise les images locales buildées à l'étape 4
echo "Démarrage docker compose..."
docker compose -f docker-compose-dev.yml up -d --remove-orphans --pull never

# --- 7) Smoke test /health (timeout 90s) + tail des logs ---
BACKEND_PORT="$(_env_get BACKEND_PORT)"; BACKEND_PORT="${BACKEND_PORT:-8000}"
HEALTH_URL="http://localhost:${BACKEND_PORT}/health/"

echo "Smoke test : ${HEALTH_URL} (timeout 90s)..."
START="$SECONDS"
until curl -sf "$HEALTH_URL" >/dev/null 2>&1; do
    if [ "$((SECONDS - START))" -ge 90 ]; then
        echo "ÉCHEC : ${HEALTH_URL} ne répond pas après 90s." >&2
        docker compose -f docker-compose-dev.yml logs --tail=100
        exit 1
    fi
    sleep 2
done
echo "OK : backend healthy (${SECONDS}s)."
docker compose -f docker-compose-dev.yml logs --tail=50
