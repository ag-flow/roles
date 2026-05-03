#!/usr/bin/env bash
set -euo pipefail

REPO_URL="git@github.com:ag-flow/roles.git"

# --- 1) Positionnement dans le repo (mode "dans le repo" ou "bootstrap clone") ---
if [ -d ".git" ]; then
  echo "Repo détecté dans le répertoire courant: $(pwd)"
  echo "Mise à jour..."
  git pull --ff-only
else
  APP_DIR="roles"
  if [ -d "$APP_DIR/.git" ]; then
    echo "Repo déjà cloné dans ./${APP_DIR}"
    echo "Mise à jour..."
    git -C "$APP_DIR" pull --ff-only
  else
    echo "Clone du repo dans ./${APP_DIR}..."
    git clone "$REPO_URL" "$APP_DIR"
  fi
  cd "$APP_DIR"
fi

# --- 2) .env ---
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo ".env absent -> création depuis .env.example"
  cp .env.example .env
fi

# --- 3) Build images locales ---
chmod +x build.sh
./build.sh

# --- 4) Re-tag des images locales avec les noms attendus par docker-compose ---
# build.sh crée backend-roles:latest / frontend-roles:latest (sans préfixe registre).
# docker-compose.yml référence ghcr.io/${GHCR_OWNER}/...:latest.
# On lit GHCR_OWNER depuis .env (set -a exporte toutes les vars, set +a stoppe).
set -a; source .env; set +a
_OWNER="${GHCR_OWNER:-yoops}"
_TAG="${IMAGE_TAG:-latest}"
echo "Re-tag des images locales → ghcr.io/${_OWNER}/*:${_TAG}"
docker tag "backend-roles:${_TAG}"  "ghcr.io/${_OWNER}/backend-roles:${_TAG}"
docker tag "frontend-roles:${_TAG}" "ghcr.io/${_OWNER}/frontend-roles:${_TAG}"

# --- 5) Nettoyage containers orphelins / anciennes runs du projet ---
# down supprime les containers du projet + réseaux, et --remove-orphans enlève ceux qui traînent
echo "Arrêt/cleanup du projet docker compose (incl. orphelins)..."
docker compose down --remove-orphans || true

# --- 6) Relance ---
# --remove-orphans : supprime les orphelins détectés
# --pull never : n'essaie pas de pull des images distantes (on vient de re-tag localement)
echo "Démarrage docker compose..."
docker compose up -d --remove-orphans --pull never

echo "OK. Services actifs:"
docker compose ps