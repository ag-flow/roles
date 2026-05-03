#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-latest}"

BACKEND_IMAGE="backend-roles:${IMAGE_TAG}"
FRONTEND_IMAGE="frontend-roles:${IMAGE_TAG}"

echo "Build backend: ${BACKEND_IMAGE}"
docker build \
  -f backend/Dockerfile \
  -t "${BACKEND_IMAGE}" \
  .

echo "Build frontend: ${FRONTEND_IMAGE}"
docker build \
  -f frontend/Dockerfile \
  -t "${FRONTEND_IMAGE}" \
  frontend

echo "Nettoyage des anciennes images backend-roles..."
docker images "backend-roles" --format "{{.Repository}}:{{.Tag}} {{.ID}}" \
  | grep -v "${BACKEND_IMAGE}" \
  | awk '{print $2}' \
  | xargs -r docker rmi || true

echo "Nettoyage des anciennes images frontend-roles..."
docker images "frontend-roles" --format "{{.Repository}}:{{.Tag}} {{.ID}}" \
  | grep -v "${FRONTEND_IMAGE}" \
  | awk '{print $2}' \
  | xargs -r docker rmi || true

echo "Prune des layers Docker inutilisés..."
docker image prune -f

echo "Images restantes :"
docker images | grep -E "backend-roles|frontend-roles"