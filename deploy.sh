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

# --- 4) Nettoyage containers orphelins / anciennes runs du projet ---
# down supprime les containers du projet + réseaux, et --remove-orphans enlève ceux qui traînent
echo "Arrêt/cleanup du projet docker compose (incl. orphelins)..."
docker compose -f docker-compose-dev.yml down --remove-orphans || true

# --- 5) Relance ---
# --remove-orphans : supprime les orphelins détectés
# --pull never : utilise les images locales buildées à l'étape 3
echo "Démarrage docker compose..."
docker compose -f docker-compose-dev.yml up -d --remove-orphans --pull never

echo "OK. Services actifs:"
docker compose -f docker-compose-dev.yml ps