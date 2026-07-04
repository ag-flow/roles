> ℹ️ **Conservée avec adaptations V2 (2026-07-04).** Conservée intégralement — les contrats stdin/NDJSON figés remplissent leur office.
> Voir `docs/specs/v2/00-fondations-v2.md` et `docs/specs/v2/01-protocole-mcp.md`.

# 03 — Scrapers : containers + contrat d'invocation

> Sprint 2 : pipeline d'acquisition. À l'issue de ce sprint, l'application
> peut découvrir une chaîne YouTube, lister ses vidéos, et télécharger
> l'audio de vidéos sélectionnées vers MinIO.

## Objectif du sprint

- Construire 3 containers de scraping (YouTube, Instagram, TikTok)
- Implémenter le contrat stdin (tâche JSON) / stdout (events NDJSON)
- Backend orchestrateur qui pull `scraping_jobs` et lance les containers
- API REST pour créer une source, lancer un discover, sélectionner des items
- WebSocket qui pousse les events au front
- UI minimale pour l'onglet "Sources"

## Modèle conceptuel

### Pourquoi un container par plateforme

- Chaque plateforme a ses propres dépendances et cadence de cassure
  (YouTube via yt-dlp casse souvent, Instagram encore plus)
- Credentials par plateforme isolés (pas de fuite croisée)
- Possibilité de désactiver une plateforme indépendamment
- Updates indépendants

### Pattern : containers one-shot

Chaque container :
- Reçoit une tâche JSON sur stdin
- Émet des events NDJSON sur stdout au fur et à mesure de l'exécution
- Se termine en fin de tâche avec `exit 0` (succès) ou code > 0 (erreur)
- N'est jamais réutilisé pour deux tâches différentes

### Pourquoi les credentials utilisateur ?

Décision structurante : chaque utilisateur fournit ses propres credentials.

**Raisons :**
- Responsabilité légale : l'utilisateur est responsable de l'usage de son
  propre compte vis-à-vis des ToS des plateformes
- Pas de ban centralisé : un ban d'un user ne casse pas le service
- Accès aux contenus restreints : un user peut accéder à des vidéos
  privées qu'il a le droit de voir
- Rate limits distribués : N users = N quotas séparés

## Contrat des containers

### Format de tâche stdin

JSON unique passé sur stdin au démarrage du container :

```json
{
  "task_id": "uuid",
  "command": "discover" | "download",
  "url": "https://...",
  "options": {
    "max_items": 50,
    "since_date": "2023-01-01",
    "audio_format": "mp3",
    "audio_quality": 9,
    "audio_args": "-ac 1 -ar 16000 -b:a 32k",
    "sleep_interval_min": 3,
    "sleep_interval_max": 10
  },
  "output": {
    "type": "minio",
    "endpoint": "https://...",
    "bucket": "corpus-audio",
    "prefix": "{tenant_id}/{role_id}/{source_id}/",
    "access_key": "...",
    "secret_key": "..."
  }
}
```

### Format des events NDJSON sur stdout

Un event = une ligne JSON. À émettre dans cet ordre :

```json
{"type": "started", "task_id": "..."}
{"type": "discovered", "total": 42, "items": [{"id": "...", "title": "...", "duration_s": 812, "published_at": "...", "thumbnail_url": "..."}]}
{"type": "progress", "item_id": "...", "phase": "downloading", "percent": 34}
{"type": "item_done", "item_id": "...", "audio_s3_key": "...", "metadata": {"size_bytes": 14523412, "format": "mp3"}}
{"type": "item_failed", "item_id": "...", "error": "geo-restricted"}
{"type": "complete", "downloaded": 40, "failed": 2}
```

### Variables d'environnement attendues

```bash
# Credentials (cookies en base64)
YOUTUBE_COOKIES_B64=...
INSTAGRAM_COOKIES_B64=...
TIKTOK_COOKIES_B64=...

# MinIO
MINIO_ENDPOINT=http://...
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...

# Configuration
LOG_LEVEL=info
```

### Codes de sortie

- `0` : succès complet
- `1` : erreur de configuration (tâche invalide, credentials manquants)
- `2` : erreur d'exécution (toutes les requêtes ont échoué)
- `3` : erreur partielle (au moins un item échoué, mais pas tous)

## Implémentation des containers

### Image Docker générique (`docker/scrapers/base.Dockerfile`)

Une image de base partagée pour réduire la duplication :

```dockerfile
FROM python:3.12-slim

# ffmpeg requis par yt-dlp pour l'extraction audio
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY base/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code spécifique à chaque plateforme est ajouté par les Dockerfiles enfants
```

### `docker/scrapers/base/requirements.txt`

```
yt-dlp>=2025.1.0
minio>=7.2
pydantic>=2.5
structlog>=24.1
```

### Structure de chaque scraper

```
docker/scrapers/youtube/
├── Dockerfile
├── entrypoint.py          # point d'entrée, parse stdin et dispatch
├── discover.py            # logique de discover (channel/playlist)
├── download.py            # logique de download (audio extraction)
├── minio_uploader.py      # upload vers MinIO
└── events.py              # helpers pour émettre les events NDJSON
```

### `docker/scrapers/youtube/Dockerfile`

```dockerfile
FROM agflow-scraper-base:latest

COPY youtube/ /app/youtube/

ENTRYPOINT ["python", "-m", "youtube.entrypoint"]
```

### `docker/scrapers/youtube/entrypoint.py`

Squelette du point d'entrée :

```python
"""YouTube scraper entrypoint.

Reads a task from stdin (JSON), dispatches to discover or download,
emits NDJSON events on stdout.
"""
import asyncio
import json
import sys
from pathlib import Path

from youtube import discover, download
from youtube.events import emit


async def main() -> int:
    """Read task from stdin and execute."""
    task_json = sys.stdin.read()
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError as exc:
        emit("error", error=f"invalid JSON: {exc}")
        return 1

    emit("started", task_id=task["task_id"])

    command = task.get("command")
    if command == "discover":
        return await discover.run(task)
    elif command == "download":
        return await download.run(task)
    else:
        emit("error", error=f"unknown command: {command}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

### Récupération de l'audio (yt-dlp)

yt-dlp peut directement extraire l'audio sans télécharger la vidéo complète :

```bash
yt-dlp -x --audio-format mp3 --audio-quality 9 \
       --postprocessor-args "ffmpeg:-ac 1 -ar 16000 -b:a 32k" \
       -o "/tmp/{video_id}.%(ext)s" \
       https://youtube.com/watch?v=...
```

**Format optimisé pour Whisper :**
- **Mono** (`-ac 1`) — Whisper ré-échantillonne en mono de toute façon
- **16 kHz** (`-ar 16000`) — taux natif de Whisper
- **32 kbps** (`-b:a 32k`) — largement suffisant pour la voix

Résultat : ~14 MB pour 1h d'audio.

### Sous-titres YouTube

**Décision : on les ignore.** Whisper produit du texte mieux ponctué, mieux
segmenté, avec timestamps fins. Les subs auto YouTube ne sont pas
exploitables pour de l'analyse LLM. On re-transcrit toujours.

### Anti-ban

Indépendamment des credentials, les scrapers doivent ralentir leurs requêtes :

- yt-dlp `--sleep-interval 3 --max-sleep-interval 10` pour YouTube
- Délais plus agressifs (30-60s) pour Instagram
- Configurable via les `options` de la tâche

## Backend orchestrateur

### Service `scraping_orchestrator.py`

Responsable de :
- Pull les jobs `scraping_jobs` en FIFO avec `FOR UPDATE SKIP LOCKED`
- Récupérer les credentials depuis OpenBao
- Lancer le container Docker correspondant
- Streamer le NDJSON et mettre à jour la base au fil de l'eau
- Émettre des PG NOTIFY pour le WebSocket

### Pattern de pull

Cf. `01-data-model.md` § 9. Pour le scraping :

```sql
SELECT * FROM scraping_jobs
WHERE status = 'pending'
ORDER BY priority DESC, created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Cap à **5 containers de scraping simultanés** sur pve1 (configurable). Au-delà,
les jobs attendent dans la queue.

### Lancement du container

Pseudocode :

```python
async def execute_scraping_job(job: ScrapingJob) -> None:
    # 1. Récupérer credentials depuis OpenBao
    creds = await openbao.get(f"scraping-credentials/{job.tenant_id}/{platform}/{job.credentials_id}")
    cookies_b64 = base64.b64encode(creds["cookies"]).decode()

    # 2. Construire la tâche
    task = {
        "task_id": str(job.id),
        "command": job.command,
        "url": job.source.url,
        "options": {...},
        "output": {
            "type": "minio",
            "endpoint": settings.minio_endpoint,
            "bucket": "corpus-audio",
            "prefix": f"{job.tenant_id}/{job.source.role_project_id}/{job.source.id}/",
            "access_key": settings.minio_access_key,
            "secret_key": settings.minio_secret_key,
        },
    }

    # 3. Lancer le container
    image = f"agflow-scraper-{platform}:stable"
    process = await asyncio.create_subprocess_exec(
        "docker", "run", "--rm", "-i",
        "-e", f"YOUTUBE_COOKIES_B64={cookies_b64}",
        image,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 4. Envoyer la tâche
    process.stdin.write(json.dumps(task).encode())
    process.stdin.close()

    # 5. Streamer les events NDJSON
    async for line in process.stdout:
        try:
            event = json.loads(line)
            await handle_scraper_event(job, event)
        except json.JSONDecodeError:
            log.warning("invalid_event_line", line=line)

    # 6. Vérifier l'exit code
    return_code = await process.wait()
    if return_code != 0:
        await mark_job_failed(job, return_code)
```

### Handler des events

Pour chaque event reçu, mettre à jour la base et notifier :

```python
async def handle_scraper_event(job: ScrapingJob, event: dict) -> None:
    event_type = event["type"]

    if event_type == "discovered":
        # Insérer les items découverts
        for item in event["items"]:
            await db.insert_source_item(
                source_id=job.source_id,
                tenant_id=job.tenant_id,
                platform_item_id=item["id"],
                title=item["title"],
                duration_s=item.get("duration_s"),
                published_at=item.get("published_at"),
                thumbnail_url=item.get("thumbnail_url"),
                status="pending_download",
            )
        await db.update_source_status(
            source_id=job.source_id,
            status="discovered",
            discovered_count=event["total"],
        )

    elif event_type == "item_done":
        await db.update_source_item(
            source_id=job.source_id,
            platform_item_id=event["item_id"],
            status="audio_ready",
            audio_s3_key=event["audio_s3_key"],
        )
        # Créer un transcription_job (cf. § 04)
        await db.insert_transcription_job(...)

    elif event_type == "item_failed":
        await db.update_source_item(
            source_id=job.source_id,
            platform_item_id=event["item_id"],
            status="failed",
            error=event["error"],
        )

    elif event_type == "complete":
        await db.update_scraping_job(
            job_id=job.id,
            status="done",
            completed_at=now(),
        )
```

## API REST

### Endpoints à exposer

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/role-projects` | Créer un projet de rôle |
| `POST` | `/api/role-projects/{id}/sources` | Ajouter une source à un projet |
| `POST` | `/api/sources/{id}/discover` | Lancer la découverte |
| `GET` | `/api/sources/{id}/items` | Lister les items découverts (avec filtres) |
| `POST` | `/api/sources/{id}/items/select` | Sélectionner les items à ingérer |
| `GET` | `/api/scraping-jobs` | Lister les jobs (suivi pour l'UI) |

### Schemas Pydantic

```python
# backend/src/role_builder/schemas/sources.py
from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from datetime import datetime
from typing import Literal


class CreateSourceRequest(BaseModel):
    url: HttpUrl
    platform: Literal["youtube", "instagram", "tiktok"]
    source_type: Literal["single", "channel", "playlist", "account"]
    credentials_id: UUID


class SourceItem(BaseModel):
    id: UUID
    platform_item_id: str
    title: str | None
    duration_s: int | None
    published_at: datetime | None
    thumbnail_url: str | None
    status: str
    selected: bool


class SelectItemsRequest(BaseModel):
    item_ids: list[UUID]
    deselect_others: bool = False
```

### Filtres pour `/items`

Query params :
- `min_duration_s` : durée minimale en secondes
- `since_date` : date ISO 8601, items publiés après cette date
- `status` : filtrer par statut
- `selected` : true / false / null
- `limit`, `offset` : pagination

## WebSocket pour temps réel

Le frontend ouvre un WebSocket `/ws` après authentification. Le backend
relaie les PG NOTIFY pertinents au tenant connecté.

### Pattern

```python
# backend/src/role_builder/services/ws_relay.py
import asyncpg
import asyncio
from typing import AsyncIterator


async def listen_pg_notify(channels: list[str]) -> AsyncIterator[dict]:
    """Listen to PG NOTIFY on multiple channels and yield events."""
    conn = await asyncpg.connect(settings.database_url)
    queue: asyncio.Queue = asyncio.Queue()

    def handle(connection, pid, channel, payload):
        queue.put_nowait({"channel": channel, "payload": payload})

    for channel in channels:
        await conn.add_listener(channel, handle)

    try:
        while True:
            event = await queue.get()
            yield event
    finally:
        await conn.close()
```

Le WS filtre par `tenant_id` côté backend avant de pousser au client.

## UI : onglet "Sources" (front)

### Fonctionnalités à implémenter

1. **Création d'une source** : modal avec champ URL + sélecteur de plateforme
   + dropdown des credentials disponibles (filtrés par plateforme)
2. **Bouton "Découvrir"** : lance le discover, affiche un loader
3. **Liste des items découverts** :
   - Tableau avec : thumbnail, titre, durée, date publication, statut
   - Filtres : durée min, date min, statut, sélection
   - Bouton "Tout sélectionner" / "Inverser sélection"
   - Checkbox par ligne
4. **Bouton "Lancer l'ingestion"** : pousse les items sélectionnés en queue
5. **Live updates** via WebSocket : statuts qui changent en temps réel

### Composants React clés

```
frontend/src/app/projects/[id]/sources/
├── page.tsx                    # liste des sources du projet
├── [sourceId]/
│   ├── page.tsx               # vue d'une source avec ses items
│   ├── DiscoverButton.tsx
│   ├── ItemsTable.tsx
│   ├── ItemsFilters.tsx
│   └── SelectionActions.tsx
```

## Critères de fin de sprint

- [ ] Image `agflow-scraper-base` build sans erreur
- [ ] Image `agflow-scraper-youtube` build et fonctionne en standalone
      (test manuel avec une vidéo publique)
- [ ] L'app peut créer une source, lancer un discover, lister les items
- [ ] Sélection d'items et lancement d'ingestion produisent des
      `scraping_jobs` puis des fichiers audio dans MinIO
- [ ] WebSocket pousse les events au front en temps réel
- [ ] Test avec une chaîne YouTube de 10+ vidéos : tout est ingéré sans
      crash
- [ ] Anti-ban actif (sleep_interval respecté, vérifié dans les logs)
- [ ] Container Instagram et TikTok au moins squelettés (peuvent être
      simplifiés en MVP, mais le contrat NDJSON doit être respecté)

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Stratégie pour Instagram : yt-dlp seul ou gallery-dl en complément ?
      Tester sur des reels publics réels.
- [ ] Format de stockage des thumbnails : récupérer + uploader vers MinIO
      ou juste stocker l'URL d'origine ?
- [ ] Stratégie de retry : un item qui échoue, on retry combien de fois ?
      `max_attempts` est dans le schéma mais la logique reste à coder.
- [ ] Détection d'expiration des cookies : pour l'instant, on traite l'erreur
      comme un échec normal. À affiner pour distinguer "expired" vs
      "geo-restricted" vs "private video".
- [ ] Cap à 5 containers simultanés : configurable où ? (env var ou
      paramètre du tenant ?)

---

**Document précédent :** `02-foundations.md`
**Document suivant :** `04-transcription.md`
