> ℹ️ **Conservée avec adaptations V2 (2026-07-04).** Conservée ; l'étape post-transcription devient le dépôt docflow (statuts depositing/deposited), plus de chunking.
> Voir `docs/specs/v2/00-fondations-v2.md` et `docs/specs/v2/01-protocole-mcp.md`.

# 04 — Transcription : workers, pools et providers

> Sprint 3 : pipeline de transcription. À l'issue de ce sprint, les audios
> uploadés sur MinIO sont transcrits par un worker (local ou SaaS) et le
> résultat est stocké en format pivot dans MinIO.

## Objectif du sprint

- Image `agflow-transcription-worker` configurable par provider
- Provider local `faster-whisper` opérationnel sur GPU pve2
- Provider SaaS au choix : commencer par **OpenAI Whisper API** (le plus
  simple) puis **Deepgram** et **AssemblyAI**
- Pool shared (faster-whisper) en permanence sur pve2
- Pools utilisateurs provisionnés dynamiquement (1 à 5 workers par user)
- Auto-stop des workers user après 5 minutes d'inactivité
- Bascule automatique sur épuisement de crédit

## Modèle conceptuel

### Le worker = un consommateur abstrait

Le container de transcription **n'est pas spécifique à un moteur**. C'est un
**consommateur abstrait** qui encapsule un *provider* de transcription. Le
moteur réel est choisi par configuration (variable d'environnement
`TRANSCRIPTION_PROVIDER`).

Ce que fait le worker :

- Poll la queue `transcription_jobs` en boucle
- Pour chaque job, instancie le provider configuré
- Délègue la transcription au provider via une interface unifiée
- Normalise la sortie au format pivot (cf. § Format pivot)
- Upload le résultat sur MinIO
- Met à jour la base de données

### Pool shared vs pools utilisateurs

**Pool shared** :
- 1 instance unique du worker
- Tourne en permanence sur pve2
- Provider : `faster-whisper` local sur GPU RTX 4090
- Reçoit les jobs des users **qui n'ont pas configuré de clé SaaS**
- Pull : `worker_pool_id = "shared_default"`

**Pools utilisateurs** :
- Provisionnés à la demande quand l'user a configuré une clé SaaS active
- 1 à 5 instances par user (slider dans "Ma stack")
- Provider : la clé SaaS de l'user (Deepgram, AssemblyAI, etc.)
- Pull : `worker_pool_id = "user_{user_id}"`
- Auto-stop après 5 min sans tâche

### Pourquoi pas de SaaS dans le pool shared ?

Décision économique : si un utilisateur veut du SaaS rapide, il fournit ses
propres clés et obtient ses propres workers. L'application n'a pas de clé
SaaS de transcription côté admin. Pas de clés user = pas de coût pour
l'admin.

### Calcul du `worker_pool_id` à la création d'un job

```
SI le user a au moins une clé SaaS active dans user_transcription_keys:
    worker_pool_id = f"user_{user_id}"
SINON:
    worker_pool_id = "shared_default"
```

## Format pivot du transcript

Pour permettre l'interchangeabilité des providers, l'application définit un
**format pivot** qui sert d'interface entre les providers et le reste du
système. Tous les providers sont adaptés vers ce format à la sortie.

Le format pivot est calqué sur la sortie native de faster-whisper avec
`word_timestamps=True` :

```json
{
  "schema_version": "1.0",
  "provider": "faster-whisper",
  "model": "large-v3",
  "language": "fr",
  "language_confidence": 0.97,
  "duration_s": 812,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 4.32,
      "text": "Bonjour à tous et bienvenue...",
      "avg_logprob": -0.21,
      "words": [
        {"word": "Bonjour", "start": 0.0, "end": 0.42, "probability": 0.98}
      ]
    }
  ],
  "metadata": {
    "transcribed_at": "2026-04-25T14:32:00Z",
    "cost_estimate_usd": 0.0043,
    "processing_time_s": 27.3
  }
}
```

**Adaptation par provider :** chaque provider produit sa sortie native, un
adaptateur la transforme en format pivot. Quand un provider ne fournit pas
une donnée (ex: `avg_logprob` n'existe que pour Whisper), le champ est
laissé à `null`.

## Interface du provider

```python
# worker/src/providers/base.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass
class CreditInfo:
    """Information about remaining credit on a SaaS provider."""
    balance_usd: float | None
    last_check_at: str
    raw: dict  # réponse brute du provider


@dataclass
class PivotTranscript:
    """Format pivot d'un transcript."""
    schema_version: str = "1.0"
    provider: str = ""
    model: str = ""
    language: str = ""
    language_confidence: float | None = None
    duration_s: float = 0.0
    segments: list[dict] = None
    metadata: dict = None


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Common interface for all transcription providers."""

    name: str
    supports_language_detection: bool
    supports_diarization: bool
    supports_word_timestamps: bool
    cost_per_minute_usd: float | None

    async def transcribe(
        self,
        audio_path_or_url: str,
        *,
        language: str | None = None,
        options: dict | None = None,
    ) -> PivotTranscript:
        ...

    def estimate_cost(self, duration_s: float) -> float:
        ...

    async def get_remaining_credit(self) -> CreditInfo | None:
        """Returns remaining credit if the provider exposes it, None otherwise."""
        ...
```

## Providers à implémenter

### Provider local : faster-whisper

**Caractéristiques :**
- Modèle large-v3 sur RTX 4090 (pve2)
- Coût : 0$ (juste l'électricité du GPU)
- Latence : ~15-30% de la durée audio (1h audio → ~10-20 min)
- Langues : 99+ via Whisper
- Word timestamps : oui
- Diarization : non native

**Implémentation :**

```python
# worker/src/providers/faster_whisper_provider.py
from faster_whisper import WhisperModel


class FasterWhisperProvider:
    name = "faster-whisper"
    supports_language_detection = True
    supports_diarization = False
    supports_word_timestamps = True
    cost_per_minute_usd = None  # 0, mais on met None pour signaler "local"

    def __init__(self, model_size: str = "large-v3", device: str = "cuda"):
        self._model = WhisperModel(model_size, device=device, compute_type="float16")
        self._model_name = model_size

    async def transcribe(self, audio_path, *, language=None, options=None) -> PivotTranscript:
        segments, info = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            beam_size=5,
        )
        # Transformer en PivotTranscript
        ...

    def estimate_cost(self, duration_s: float) -> float:
        return 0.0

    async def get_remaining_credit(self) -> CreditInfo | None:
        return None  # pas applicable en local
```

### Provider SaaS : OpenAI Whisper API

**Caractéristiques :**
- Coût : ~0.006$/minute (~0.36$/heure)
- Langues : 99+
- Word timestamps : oui (avec `timestamp_granularities=["word"]`)
- Pas de balance API exposée

```python
# worker/src/providers/openai_whisper_provider.py
import httpx


class OpenAIWhisperProvider:
    name = "openai-whisper"
    supports_language_detection = True
    supports_diarization = False
    supports_word_timestamps = True
    cost_per_minute_usd = 0.006

    def __init__(self, api_key: str):
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300.0,
        )

    async def transcribe(self, audio_path, *, language=None, options=None) -> PivotTranscript:
        with open(audio_path, "rb") as f:
            resp = await self._client.post(
                "/audio/transcriptions",
                files={"file": f},
                data={
                    "model": "whisper-1",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                    **({"language": language} if language else {}),
                },
            )
        resp.raise_for_status()
        return self._adapt(resp.json())

    def estimate_cost(self, duration_s: float) -> float:
        return (duration_s / 60) * self.cost_per_minute_usd

    async def get_remaining_credit(self) -> CreditInfo | None:
        # OpenAI n'expose pas de balance API
        return None
```

### Provider SaaS : Deepgram Nova-3

**Caractéristiques :**
- Coût batch : ~0.0043$/min mono (~0.26$/heure)
- API balance disponible : `GET /v1/projects/{project_id}/balance`
- $200 crédit gratuit à l'inscription

### Provider SaaS : AssemblyAI Universal

**Caractéristiques :**
- Coût batch : ~0.0025$/min (~0.15$/heure)
- Word timestamps : oui
- Diarization : incluse
- Pas de balance API publique

### Provider SaaS : Speechmatics

**Caractéristiques :**
- Coût : ~0.004$/min + 480 min gratuites/mois
- Word-level confidence

### Tableau récap

| Provider | Coût batch /h | Latence | Langues | Diariz. | Balance API |
|----------|---------------|---------|---------|---------|-------------|
| faster-whisper local | 0$ (élec.) | 10-20 min | 99+ | non | N/A |
| OpenAI Whisper API | ~0.36$ | 30s/5min | 99+ | non | non |
| Deepgram Nova-3 | ~0.26$ | rapide | 50+ | $$ | oui |
| AssemblyAI Universal | ~0.15$ | rapide | 50+ | inclus | non |
| Speechmatics | ~0.24$ | rapide | 50+ | inclus | non |

> Prix vérifiés en avril 2026.

### Priorité d'implémentation pour le MVP

1. **Sprint 3a** : faster-whisper local (indispensable pour le pool shared)
2. **Sprint 3b** : OpenAI Whisper API (le plus simple à intégrer)
3. **Sprint 3c** : Deepgram (pour avoir un cas avec balance API)
4. **Plus tard** : AssemblyAI, Speechmatics

## Architecture du worker

### Structure du repo

```
docker/transcription-worker/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py                 # boucle principale
    ├── config.py
    ├── db.py                   # asyncpg pull/update jobs
    ├── minio_client.py
    ├── pivot.py                # adaptation vers PivotTranscript
    ├── error_classifier.py     # classification des erreurs
    └── providers/
        ├── __init__.py
        ├── base.py
        ├── faster_whisper_provider.py
        ├── openai_whisper_provider.py
        ├── deepgram_provider.py
        └── assemblyai_provider.py
```

### `worker/src/main.py`

```python
"""Transcription worker main loop."""
import asyncio
import os
import signal
from datetime import datetime, timezone

from worker import config, db
from worker.providers import build_provider
from worker.error_classifier import classify_error


WORKER_POOL_ID = os.environ["WORKER_POOL_ID"]
PROVIDER_NAME = os.environ["TRANSCRIPTION_PROVIDER"]
WORKER_ID = os.environ.get("WORKER_ID", f"worker-{os.getpid()}")
POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", "2"))

shutdown = False


def handle_signal(signum, frame):
    global shutdown
    shutdown = True


async def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    await db.connect()
    provider = build_provider(PROVIDER_NAME)

    await db.register_worker(WORKER_ID, WORKER_POOL_ID, PROVIDER_NAME, status="idle")

    try:
        while not shutdown:
            job = await db.claim_next_job(WORKER_POOL_ID, WORKER_ID)
            if job is None:
                await asyncio.sleep(POLL_INTERVAL_S)
                continue

            await db.update_worker_status(WORKER_ID, "busy")
            try:
                await process_job(job, provider)
            except Exception as exc:
                await handle_error(job, provider, exc)
            finally:
                await db.update_worker_status(WORKER_ID, "idle", last_activity_at=datetime.now(timezone.utc))
    finally:
        await db.update_worker_status(WORKER_ID, "stopped")
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

### Process d'un job

```python
async def process_job(job, provider):
    # 1. Download audio depuis MinIO
    audio_path = await minio.download(job.audio_s3_key)

    # 2. Transcribe
    transcript = await provider.transcribe(audio_path, language=job.language)

    # 3. Adapter au format pivot (déjà fait par le provider en théorie)
    pivot = pivot.normalize(transcript)
    pivot["metadata"]["transcribed_at"] = datetime.now(timezone.utc).isoformat()
    pivot["metadata"]["cost_estimate_usd"] = provider.estimate_cost(transcript.duration_s)

    # 4. Upload vers MinIO
    transcript_s3_key = job.audio_s3_key.replace("corpus-audio/", "corpus-transcripts/").replace(".mp3", ".json")
    await minio.upload_json("corpus-transcripts", transcript_s3_key, pivot)

    # 5. Update DB
    await db.mark_job_done(
        job_id=job.id,
        provider_used=provider.name,
        cost_estimate_usd=pivot["metadata"]["cost_estimate_usd"],
        result_s3_key=transcript_s3_key,
    )
    await db.update_source_item(
        source_item_id=job.source_item_id,
        status="transcribed",
        transcript_s3_key=transcript_s3_key,
    )

    # 6. Créer un chunking_job (cf. § 05)
    await db.insert_chunking_job(...)

    # 7. Cleanup local
    os.unlink(audio_path)
```

## Classification des erreurs et bascule

### Codes d'erreur à classifier

| Code | Signification | Action |
|------|---------------|--------|
| 401 + invalid_key | Clé invalide/révoquée | status=invalid, stop workers |
| 402 / insufficient | Crédit épuisé | status=exhausted, bascule shared |
| 429 + rate_limit | Throttling | retry avec backoff exponentiel |
| 429 + quota | Quota mensuel atteint | status=exhausted, bascule shared |
| 5xx | Erreur transitoire | retry avec backoff |

**Important :** ne jamais désactiver une clé sur un simple `429 rate limit`.
La distinction rate-limit / crédit épuisé doit être faite finement par
inspection du body de la réponse.

### Module `error_classifier.py`

```python
"""Classify errors from transcription providers."""
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    INVALID_KEY = "invalid_key"
    EXHAUSTED = "exhausted"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    category: ErrorCategory
    message: str
    should_retry: bool
    should_disable_key: bool


def classify_error(provider_name: str, status_code: int, body: dict) -> ClassifiedError:
    """Map a provider error to a ClassifiedError."""
    # Logic per provider, with sensible defaults
    ...
```

### Bascule sur épuisement

Quand un crédit est détecté épuisé :

1. Clé marquée `exhausted` en base (`UPDATE user_transcription_keys SET status='exhausted'`)
2. Workers user de ce provider stoppés (containers)
3. Jobs en attente du user pour ce provider basculent vers le pool shared
   (`UPDATE transcription_jobs SET worker_pool_id='shared_default' WHERE worker_pool_id=$1 AND status='pending'`)
4. Notification immédiate (UI + email)
5. PG NOTIFY sur `keys_changes` pour rafraîchir l'UI "Ma stack"

## Worker manager côté backend

Le backend FastAPI a un service `worker_manager.py` qui s'occupe de :

- Provisionner les workers user à la demande
- Stopper les workers idle après 5 minutes
- Stopper les workers d'une clé épuisée

### Provisioning à la demande

Au moment d'insérer un `transcription_job` avec `worker_pool_id = "user_X"` :

```python
async def ensure_user_workers_running(user_id: UUID) -> None:
    """Ensure the user's workers are running for their primary key."""
    # 1. Get user's active primary key
    key = await db.get_user_primary_key(user_id)
    if key is None or key.status != "active":
        return  # rien à faire

    # 2. Count current running workers for this user/provider
    pool_id = f"user_{user_id}"
    running = await db.count_workers(pool_id, statuses=["starting", "idle", "busy"])

    # 3. Spawn missing workers
    needed = key.workers_count - running
    for i in range(needed):
        await spawn_worker(user_id, key, instance_index=running + i)


async def spawn_worker(user_id: UUID, key: UserTranscriptionKey, instance_index: int) -> None:
    """Spawn a Docker container for a transcription worker."""
    # 1. Get API key from OpenBao
    api_key = await openbao.get(key.openbao_path)

    # 2. docker run
    container_name = f"rb-worker-user-{user_id}-{key.provider}-{instance_index}"
    process = await asyncio.create_subprocess_exec(
        "docker", "run", "-d",
        "--name", container_name,
        "-e", f"WORKER_POOL_ID=user_{user_id}",
        "-e", f"TRANSCRIPTION_PROVIDER={key.provider}",
        "-e", f"WORKER_ID={container_name}",
        "-e", f"{key.provider.upper().replace('-', '_')}_API_KEY={api_key}",
        "-e", f"DATABASE_URL={settings.database_url}",
        "-e", f"MINIO_ENDPOINT={settings.minio_endpoint}",
        "-e", f"MINIO_ACCESS_KEY={settings.minio_access_key}",
        "-e", f"MINIO_SECRET_KEY={settings.minio_secret_key}",
        "agflow-transcription-worker:stable",
        capture_output=True,
    )
    container_id = (await process.stdout.read()).decode().strip()

    # 3. Register in DB
    await db.insert_worker(
        worker_pool_id=f"user_{user_id}",
        container_id=container_id,
        container_name=container_name,
        provider=key.provider,
        status="starting",
        host="pve1",
    )
```

### Auto-stop des workers idle

Cron toutes les minutes :

```python
async def stop_idle_workers() -> None:
    """Stop workers idle for more than 5 minutes."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    idle_workers = await db.get_idle_workers_older_than(threshold)

    for worker in idle_workers:
        # Ne pas auto-stop le pool shared
        if worker.worker_pool_id == "shared_default":
            continue

        await db.update_worker_status(worker.id, "stopping")
        await asyncio.create_subprocess_exec("docker", "stop", worker.container_id)
        await db.update_worker_status(worker.id, "stopped", stopped_at=datetime.now(timezone.utc))
```

## Cas particuliers

### User retire toutes ses clés

Si un utilisateur désactive toutes ses clés SaaS :

1. Workers user stoppés
2. Futurs jobs créés avec `worker_pool_id = "shared_default"`
3. Jobs en attente dans `user_{user_id}` réassignés au pool shared
   (UPDATE de `worker_pool_id`)

### Pool shared : 1 seul worker

Le worker `faster-whisper` tourne en permanence sur pve2. Il est lancé via
docker-compose et redémarré automatiquement (`restart: unless-stopped`).
Cap : 1 seul worker (1 GPU disponible).

### Cap à 5 par user

Limite arbitraire pour protéger l'infra. À configurer comme variable
d'environnement `MAX_WORKERS_PER_USER` (default 5).

## Critères de fin de sprint

- [ ] Image `agflow-transcription-worker` build sans erreur
- [ ] Worker faster-whisper tourne sur pve2 et traite les jobs
      `worker_pool_id="shared_default"`
- [ ] Worker OpenAI Whisper traite les jobs `worker_pool_id="user_X"` avec
      la clé du user
- [ ] Worker manager backend provisionne les workers à la demande
- [ ] Auto-stop fonctionne (vérifié par mise en pause + observation après 6 min)
- [ ] Format pivot validé : on peut lire un transcript et tous les champs
      sont cohérents quel que soit le provider
- [ ] Bascule sur épuisement testée : on simule une 402, on vérifie que la
      clé est marquée exhausted et que le job bascule en shared
- [ ] WebSocket pousse les events `transcription_done` au front
- [ ] Une vidéo passe end-to-end : upload audio → transcription → fichier
      dans `corpus-transcripts/`

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Détection automatique de la langue : on garde l'auto-detect par
      faster-whisper ou on utilise le `language_override` du projet ?
- [ ] Word-level confidence vs segment-level pour la sélection RAG : à
      affiner pendant le sprint 5 (synthèse).
- [ ] Stratégie de retry sur erreur transitoire : exponential backoff,
      combien de tentatives ?
- [ ] Gestion des audios longs (> 1h) : OpenAI Whisper a une limite de
      25MB par fichier, à découper côté worker ?
- [ ] Diarization : nécessaire pour le use case (interviews à plusieurs) ?
      Si oui, ajouter pyannote-audio en post-process pour faster-whisper.

---

**Document précédent :** `03-scrapers.md`
**Document suivant :** `05-corpus-indexing.md`
