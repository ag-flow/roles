# CI / CD — Build et publication des images Docker (toutes sur GHCR)

## Vue d'ensemble

Quatre workflows GitHub Actions :

- **`test.yml`** — déclenché sur push/PR. 4 jobs en parallèle : backend (pytest + ruff), scraper YouTube (pytest + ruff), worker transcription (pytest + ruff), frontend (vitest + typecheck + lint). ~3-5 min.
- **`build-app.yml`** — déclenché sur push `main` et tags `v*`. Build & push matriciel de 2 images applicatives sur GHCR : `agflow-backend` et `agflow-frontend`. ~3-5 min.
- **`build-scrapers.yml`** — déclenché sur push `main` et tags `v*`. Build & push 4 images sur GHCR : `agflow-scraper-{base,youtube,instagram,tiktok}`. ~5-8 min.
- **`build-workers.yml`** — déclenché sur push `main` et tags `v*`. Build & push matriciel de 2 images worker transcription sur GHCR : `agflow-transcription-worker` (CPU, base `python:3.12-slim`) et `agflow-transcription-worker-cuda` (GPU, base `nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04`). ~6-10 min (CUDA plus long).

**Directive** : toutes les images Docker sont buildées sur GitHub Actions, jamais en local. Aucun build sur la machine de dev Windows. Le `docker-compose.yml` pull depuis GHCR par défaut. Pour builder localement (sur LXC pve1 par exemple), copier `docker-compose.override.yml.example` vers `docker-compose.override.yml`.

## Images cumulées (8 au total)

| Image | Workflow | Base | Notes |
| --- | --- | --- | --- |
| `agflow-backend` | `build-app.yml` | `python:3.12-slim` | FastAPI + asyncpg, healthcheck `/health/` |
| `agflow-frontend` | `build-app.yml` | `node:20-alpine` | Next.js 14, multi-stage prod (`next start`) |
| `agflow-scraper-base` | `build-scrapers.yml` | `python:3.12-slim` | yt-dlp + ffmpeg, image socle pour les 3 plateformes |
| `agflow-scraper-youtube` | `build-scrapers.yml` | `agflow-scraper-base` | Découverte + download YouTube |
| `agflow-scraper-instagram` | `build-scrapers.yml` | `agflow-scraper-base` | Découverte + download Instagram |
| `agflow-scraper-tiktok` | `build-scrapers.yml` | `agflow-scraper-base` | Découverte + download TikTok |
| `agflow-transcription-worker` | `build-workers.yml` | `python:3.12-slim` | CPU (OpenAI Whisper, Deepgram, AssemblyAI, Speechmatics) |
| `agflow-transcription-worker-cuda` | `build-workers.yml` | `nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04` | GPU (faster-whisper sur RTX 4090 pve2) |

## Registry : GHCR (GitHub Container Registry)

Images publiées sous `ghcr.io/<owner>/<image>:<tag>`. Tags :

- `:sha-<short>` — un par commit
- `:latest` — dernier push `main`
- `:vX.Y.Z` — quand un tag `v*` est poussé

Auth : chaque workflow utilise `${{ secrets.GITHUB_TOKEN }}` avec `permissions: packages: write`. Aucun PAT manuel requis pour la publication CI.

## Bootstrap GHCR (à faire une fois)

1. Vérifier que GHCR est activé sur le repo (Settings → Packages).
2. Au premier push sur `main`, les workflows `build-*` publient automatiquement les images.
3. Après la première publication, vérifier que les packages apparaissent dans la section "Packages" du repo GitHub. Par défaut, chaque package est privé.
4. Pour rendre un package public : Repo → Packages → cliquer sur l'image → "Package settings" → "Change visibility" → Public. Refaire pour chaque image qu'on souhaite consommer publiquement.

## Pull des images depuis docker-compose

Configurer `.env` à partir de `.env.example` :

```bash
GHCR_OWNER=<github-username-lowercase>
IMAGE_TAG=latest                 # ou sha-XXX, vX.Y.Z
```

`IMAGE_TAG` est commun à toutes les images Role Builder (backend, frontend, scrapers, workers). Le compose interne propage cette variable au backend (qui en dérive `SCRAPER_IMAGE_TAG` et `WORKER_IMAGE_TAG` pour ses orchestrateurs).

Si l'image est privée :

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <github-username> --password-stdin
```

`GHCR_PAT` = Personal Access Token (classic) avec scope `read:packages`. Pour les images publiques, le login est facultatif.

Puis :

```bash
docker compose pull
docker compose up -d
```

## Forcer un rebuild / retag

Chaque workflow déclare `workflow_dispatch: {}`, ce qui permet un déclenchement manuel depuis l'onglet Actions du repo (bouton "Run workflow"). Utile pour repush un tag identique après une correction d'infra (par exemple repackager `:latest` à partir d'un commit non encore poussé sur `main`).

## Build local (override optionnel)

Cas d'usage : LXC pve1 sans accès GHCR, ou dev qui veut un cycle build-test rapide.

1. `cp docker-compose.override.yml.example docker-compose.override.yml`
2. Ajuster les volumes / chemins si nécessaire.
3. `docker compose up -d --build` — Compose merge l'override avec le compose principal et build au lieu de pull.

Le tag local de l'image suit le nom GHCR (`ghcr.io/...`) mais n'est pas pushé.

## Logs et debugging

- Voir l'onglet "Actions" du repo GitHub.
- Logs persistés 90 jours par défaut.
- Si un build échoue, regarder le step "Build & push" pour le contexte Docker (chemin du Dockerfile, dépendance manquante, etc.).
- Tous les workflows utilisent `docker/setup-buildx-action@v3` + `docker/build-push-action@v6` (cache layer, multi-arch possible).

## Images workers transcription

Le worker transcription est packagé en deux variantes :

- **`agflow-transcription-worker`** — base `python:3.12-slim`. Utilisé par les workers user (provider OpenAI Whisper en MVP) et le pool shared CPU. Pas de support GPU. Petite taille (~300 MB).
- **`agflow-transcription-worker-cuda`** — base `nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04`. Embarque les libs CUDA + cuDNN nécessaires à `faster-whisper` sur GPU NVIDIA. Réservé au pool shared sur pve2 (RTX 4090). Image volumineuse (~2-3 GB).

Les deux images partagent le même code (`worker/`) et sont buildées en parallèle par le workflow `build-workers.yml` (matrix sur `variant`). Tags identiques (`:sha-<short>`, `:latest`, `:vX.Y.Z`).

## Déploiement du pool shared faster-whisper sur pve2

Le pool shared faster-whisper tourne dans un container GPU sur pve2 (host Proxmox équipé d'une RTX 4090). Il consomme les jobs de transcription des users sans clé SaaS active (ou en fallback quand la clé du user est exhausted).

Le fichier `docker-compose.pve2.yml` (à la racine du repo, créé en Phase G) définit le service `transcription-worker-shared` :

- image `ghcr.io/<owner>/agflow-transcription-worker-cuda:latest`
- runtime `nvidia` (devices : `all`)
- env : `TRANSCRIPTION_PROVIDER=faster_whisper`, `WORKER_POOL_ID=shared`, accès Postgres + MinIO + (optionnel) Redis
- restart policy `unless-stopped`

### Étapes de déploiement initial

1. **Provisionner le LXC ou container GPU sur pve2**
   - LXC privilégié OU container Docker hôte avec accès device GPU NVIDIA (`nvidia-container-toolkit` installé sur l'hôte pve2).
   - Vérifier `nvidia-smi` à l'intérieur du container avant d'aller plus loin.
   - Installer Docker + Compose v2 si pas déjà présent (cf. `scripts/infra/01-install-docker.sh`).

2. **Authentification GHCR**
   ```bash
   echo "$GHCR_PAT" | docker login ghcr.io -u <github-username> --password-stdin
   ```
   `GHCR_PAT` = Personal Access Token (classic) avec scope `read:packages`. Si l'image est publique, le login est facultatif.

3. **Récupérer les fichiers de déploiement**
   ```bash
   git clone https://github.com/<owner>/agflow.roles.git /opt/agflow
   cd /opt/agflow
   cp .env.example .env   # éditer avec les credentials Postgres / MinIO / etc.
   ```

4. **Pull de l'image worker-cuda**
   ```bash
   docker pull ghcr.io/<owner>/agflow-transcription-worker-cuda:latest
   ```

5. **Démarrage du pool shared**
   ```bash
   docker compose -f docker-compose.pve2.yml up -d
   ```

6. **Vérification**
   ```bash
   docker compose -f docker-compose.pve2.yml ps
   docker compose -f docker-compose.pve2.yml logs -f transcription-worker-shared
   ```
   Logs attendus : `worker started` (structlog JSON), puis polling régulier de la file `transcription_jobs` filtrée sur `worker_pool_id = shared`. Le premier job déclenchera le téléchargement du modèle `faster-whisper` (~few GB) — tolérer une latence sur le démarrage à froid.

### Mise à jour du pool shared

À chaque release stable (tag `vX.Y.Z`), repull l'image et relancer :

```bash
docker pull ghcr.io/<owner>/agflow-transcription-worker-cuda:vX.Y.Z
docker compose -f docker-compose.pve2.yml pull
docker compose -f docker-compose.pve2.yml up -d
```

Le `:latest` reste pointé sur le dernier push `main` (potentiellement instable). Préférer pinner sur un tag versionné en production.

### Surveillance

- **Logs** : récoltés par Grafana Alloy (déployé sur pve2) → Loki (LXC 116) → Grafana (`https://log.yoops.org`). Filtrer sur `service="transcription-worker-shared"`.
- **GPU** : `nvidia-smi` sur l'hôte pve2 ou dans le container. Métriques Prometheus à brancher en Phase 2.
- **Backlog jobs** : monitorer la table `transcription_jobs` en `status='queued'` avec `worker_pool_id='shared'`. Au-delà d'un seuil, prévoir un second worker GPU ou augmenter la concurrence.
