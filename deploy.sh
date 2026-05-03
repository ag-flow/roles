#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/ag-flow/roles.git"
APP_DIR="roles"

if [ -d "$APP_DIR/.git" ]; then
  echo "Mise à jour du repo existant..."
  git -C "$APP_DIR" pull --ff-only
else
  echo "Clone du repo..."
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# Gestion du .env
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "Fichier .env absent → création depuis .env.example"
    mv .env.example .env
  else
    echo "⚠️ Aucun .env ni .env.example trouvé"
  fi
else
  echo ".env déjà présent"
fi

echo "Build des images..."
chmod +x ./build.sh
./build.sh

echo "Démarrage des services..."
docker compose up -d