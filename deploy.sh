#!/usr/bin/env bash
set -euo pipefail

# REPO_URL="https://github.com/ag-flow/roles.git"

# Si vous utilisez SSH pour GitHub, décommentez la ligne suivante et commentez la ligne précédente
REPO_URL="git@github.com:ag-flow/roles.git"
APP_DIR="roles"

if [ -d "$APP_DIR/.git" ]; then
  echo "Mise à jour du repo existant..."
  git -C "$APP_DIR" pull --ff-only
else
  echo "Clone du repo..."
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# .env
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
fi

chmod +x build.sh
./build.sh

docker compose up -d