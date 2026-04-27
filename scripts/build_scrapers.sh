#!/usr/bin/env bash
# Build local des images scrapers.
# Usage : ./scripts/build_scrapers.sh [base|youtube|instagram|tiktok|all]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-all}"

build_base() {
    echo ">> build agflow-scraper-base"
    docker build -t agflow-scraper-base:latest -f "$ROOT/docker/scrapers/base/Dockerfile" "$ROOT/docker/scrapers"
}

build_platform() {
    local platform="$1"
    echo ">> build agflow-scraper-$platform"
    docker build -t "agflow-scraper-$platform:latest" -f "$ROOT/docker/scrapers/$platform/Dockerfile" "$ROOT/docker/scrapers/$platform"
}

case "$TARGET" in
    base) build_base ;;
    youtube|instagram|tiktok)
        build_base
        build_platform "$TARGET"
        ;;
    all)
        build_base
        for p in youtube instagram tiktok; do
            build_platform "$p"
        done
        ;;
    *)
        echo "Unknown target: $TARGET" >&2
        echo "Usage: $0 [base|youtube|instagram|tiktok|all]" >&2
        exit 1
        ;;
esac

echo "Build complete."
