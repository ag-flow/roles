#!/usr/bin/env bash
# Crée les 3 buckets MinIO requis par Role Builder.
set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changeme_in_real_env}"

if ! command -v mc >/dev/null 2>&1; then
    echo "MinIO client 'mc' not found. Install from https://min.io/docs/minio/linux/reference/minio-mc.html" >&2
    exit 1
fi

mc alias set rb-local "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

for bucket in corpus-audio corpus-transcripts corpus-thumbnails; do
    if ! mc ls "rb-local/$bucket" >/dev/null 2>&1; then
        mc mb "rb-local/$bucket"
        echo "Created bucket: $bucket"
    else
        echo "Bucket exists: $bucket"
    fi
done

echo "MinIO initialization complete."
