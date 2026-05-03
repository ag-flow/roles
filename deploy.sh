#!/usr/bin/env bash
set -euo pipefail

REPO_URL="git@github.com:ag-flow/roles.git"

# Si on est déjà dans le repo (présence de .git), on update ici.
if [ -d ".git" ]; then
  echo "Repo détecté dans le répertoire courant: $(pwd)"
  echo "Mise à jour..."
  git pull --ff-only

# Sinon, on clone dans ./roles (comportement bootstrap)
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

# .env
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo ".env absent -> création depuis .env.example"
  cp .env.example .env
fi

# build
chmod +x build.sh
./build.sh

# run
docker compose up -d