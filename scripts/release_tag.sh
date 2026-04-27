#!/usr/bin/env bash
# Tag local le HEAD avec une version semver et la pousse pour déclencher le build CI.
set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" || ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.-]+)?$ ]]; then
    echo "Usage: $0 vX.Y.Z[-suffix]" >&2
    echo "Example: $0 v0.2.0" >&2
    exit 1
fi

if ! git diff-index --quiet HEAD --; then
    echo "Working tree not clean. Commit or stash first." >&2
    exit 2
fi

echo "Tagging HEAD as $VERSION"
git tag -a "$VERSION" -m "Release $VERSION"

echo "Push the tag with : git push origin $VERSION"
echo "(Le push déclenchera le workflow build-scrapers et publiera vers GHCR)"
