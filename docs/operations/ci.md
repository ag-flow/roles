# CI / CD — Build et publication des images scrapers

## Vue d'ensemble

Deux workflows GitHub Actions :

- **`test.yml`** — déclenché sur push/PR. 3 jobs en parallèle : backend (pytest + ruff), scraper YouTube (pytest + ruff), frontend (vitest + typecheck + lint). ~3-5 min.
- **`build-scrapers.yml`** — déclenché sur push `main` et tags `v*`. Build & push 4 images sur GHCR : `agflow-scraper-{base,youtube,instagram,tiktok}`. ~5-8 min.

## Registry : GHCR (GitHub Container Registry)

Images publiées sous `ghcr.io/<owner>/agflow-scraper-<platform>`. Tags :

- `:sha-<short>` — un par commit
- `:latest` — dernier push `main`
- `:vX.Y.Z` — quand un tag `v*` est poussé

## Bootstrap GHCR (à faire une fois)

1. Vérifier que GHCR est activé sur le repo (Settings → Packages).
2. Le workflow utilise `${{ secrets.GITHUB_TOKEN }}` avec permissions `packages: write` (déclarées dans le job). Aucune action manuelle pour la première publication.
3. Après la première publication, vérifier que les packages apparaissent dans la section "Packages" du repo GitHub. Marquer en visibilité publique si besoin (par défaut privé).

## Pull des images depuis docker-compose

Pour utiliser ces images en local (LXC pve1, dev avec Docker Desktop), définir dans `.env` :

```bash
GHCR_OWNER=<github-username-lowercase>
SCRAPER_IMAGE_TAG=latest
```

Puis ajouter au `docker-compose.yml` (Sprint suivant — pas dans Sprint 2) une section pour pull automatique des images scrapers, ou laisser l'orchestrator backend les pull à la demande via `docker run`.

## Logs et debugging

- Voir l'onglet "Actions" du repo GitHub.
- Logs persistés 90 jours par défaut.
- Si un build échoue, regarder le step "Build & push" pour le contexte Docker (chemin du Dockerfile, dépendance manquante, etc.).
