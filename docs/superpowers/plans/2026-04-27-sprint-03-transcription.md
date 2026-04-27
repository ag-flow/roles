# Sprint 3 — Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** À partir d'un `source_items` en état `audio_ready` (issu de Sprint 2), un worker transcrit l'audio MP3 en `PivotTranscript` JSON et l'upload dans `corpus-transcripts/`. Deux providers livrés : OpenAI Whisper API (SaaS) et faster-whisper (local GPU). Le worker pool shared tourne en permanence sur pve2 (faster-whisper). Les pools user sont provisionnés à la demande par le backend.

**Architecture:**
- **1 container générique `agflow-transcription-worker`** paramétré par `TRANSCRIPTION_PROVIDER` env var (`faster-whisper`, `openai-whisper`, ...) — buildé par GitHub Actions vers GHCR, jamais en local.
- **Provider abstrait** (Protocol Python) + adaptateurs concrets vers le format pivot. Provider = encapsule l'API spécifique d'un moteur de transcription.
- **Worker main loop** : poll `transcription_jobs` (FOR UPDATE SKIP LOCKED), download audio MinIO, transcribe via provider, normalize en pivot, upload transcript MinIO, mark job done, update `source_items.status='transcribed'`.
- **Backend `worker_manager`** : à la création/modification d'une clé SaaS user, provisionne N containers worker (slider 1-5). Loop auto-stop des workers idle > 5 min (sauf pool shared).
- **Câblage Sprint 2** : `event_handlers.on_item_done` crée maintenant un `transcription_jobs` avec `worker_pool_id` calculé selon que le user a une clé SaaS active ou pas.

**Tech Stack:**
- Worker container : `python:3.12-slim` + `faster-whisper>=1.0` + `httpx` + `minio` + `asyncpg` + `structlog`
- CUDA pour faster-whisper sur pve2 (image variante `agflow-transcription-worker-cuda`, buildée séparément Phase H+)
- Backend : asyncpg, subprocess Docker, asyncio Task pour la loop auto-stop
- Tests : mocks WhisperModel + httpx.AsyncClient + asyncpg

**Décisions actées en amont** :
- **Providers MVP** : OpenAI Whisper API (priorité 1) + faster-whisper local (priorité 2). Deepgram, AssemblyAI, Speechmatics : différés Phase 2.
- **Clés SaaS** : env vars docker-compose (`OPENAI_API_KEY`, etc.) — pas d'OpenBao, comme cookies Sprint 2.
- **Pool shared faster-whisper** : tourne en permanence sur pve2, lancé via `docker-compose.pve2.yml` (créé en Phase G). Pas de provisioning à la demande.
- **Pools user** : provisionnés à la demande sur pve1 par `worker_manager` backend (subprocess docker run).
- **Auto-stop** : asyncio Task dans le lifespan FastAPI, période 60s, threshold 5 min.
- **Polling crédit Deepgram, diarization, retry exponential backoff** : différés Phase 2 (à recoder quand prioritaire).
- **Image worker** : `agflow-transcription-worker:latest` pour CPU, `agflow-transcription-worker-cuda:latest` pour GPU pve2 (variante avec base CUDA différente, Phase H).

**Critères de fin** (cf. `docs/specs/04-transcription.md` § Critères de fin de sprint, adaptés pour MVP sans runtime Docker local) :
- Worker code complet : poll → download audio → transcribe → upload pivot → mark done. TDD strict sur chaque étape.
- Provider OpenAI Whisper : tests d'API mockés + adaptation au format pivot.
- Provider faster-whisper : tests TDD avec `WhisperModel` mocké (pas d'inférence réelle en dev).
- Backend `worker_manager` : provisioning + auto-stop testés via subprocess mocké + DB mockée.
- Bascule épuisement crédit testée (HTTP 402 → key.status='exhausted' + workers stoppés + jobs réassignés au pool shared).
- `event_handlers.on_item_done` crée un `transcription_jobs` correct.
- Suite tests verte : backend, worker, scrapers, frontend (~80+ tests cumulés).
- CI GitHub étendue pour builder l'image worker.
- Aucun smoke runtime — vérifs au déploiement pve2/pve1 ultérieures.

---

## File Structure

```
agflow.roles/
├── docker/
│   └── transcription-worker/                     # Phase A1
│       ├── Dockerfile                            # Phase A1 (CPU base)
│       ├── Dockerfile.cuda                       # Phase H (GPU base)
│       ├── pyproject.toml                        # Phase A2
│       ├── worker/
│       │   ├── __init__.py                       # Phase A2
│       │   ├── main.py                           # Phase E1 (poll + dispatch)
│       │   ├── config.py                         # Phase A2 (env vars)
│       │   ├── db.py                             # Phase E2 (asyncpg helpers)
│       │   ├── minio_client.py                   # Phase E3 (download/upload S3)
│       │   ├── pivot.py                          # Phase A3 (PivotTranscript + helpers)
│       │   ├── error_classifier.py               # Phase D
│       │   └── providers/
│       │       ├── __init__.py                   # Phase A4
│       │       ├── base.py                       # Phase A4 (Protocol + dataclasses)
│       │       ├── openai_whisper.py             # Phase B
│       │       └── faster_whisper.py             # Phase C
│       └── tests/
│           ├── __init__.py
│           ├── test_pivot.py                     # Phase A3
│           ├── test_providers_base.py            # Phase A4
│           ├── test_openai_whisper.py            # Phase B
│           ├── test_faster_whisper.py            # Phase C
│           ├── test_error_classifier.py          # Phase D
│           ├── test_main_loop.py                 # Phase E1
│           ├── test_db.py                        # Phase E2
│           └── test_minio_client.py              # Phase E3
│
├── backend/
│   └── src/role_builder/
│       ├── config.py                             # Phase F (modify : add OPENAI_API_KEY etc + worker config)
│       ├── main.py                               # Phase F (modify : start worker_manager loop)
│       ├── db_helpers/
│       │   ├── transcription_jobs.py             # Phase G2 (NEW)
│       │   └── transcription_keys.py             # Phase F (NEW : list_active_keys, mark_exhausted)
│       ├── services/
│       │   ├── worker_manager.py                 # Phase F1 (provisioning + auto-stop)
│       │   ├── credit_basculer.py                # Phase F3 (bascule shared sur exhausted)
│       │   └── event_handlers.py                 # Phase G1 (modify : on_item_done crée transcription_jobs)
│       └── (tests dans backend/tests/)
│
├── docker-compose.yml                            # inchangé
├── docker-compose.pve2.yml                       # Phase G (NEW : worker shared faster-whisper toujours up)
│
└── .github/workflows/
    ├── build-scrapers.yml                        # inchangé
    └── build-workers.yml                         # Phase H (NEW : build & push agflow-transcription-worker[-cuda])
```

**Total** : ~30 nouveaux fichiers + ~5 modifications de fichiers existants. Estimation ~25 commits.

---

# Phase A — Image worker base + framework provider abstrait

Objectif : squelette du container `agflow-transcription-worker` (CPU pour MVP), framework de providers (Protocol + dataclasses), modèle pivot. Ne pas builder localement — la CI s'en chargera Phase H.

## Task A1 : Image Docker base CPU

**Files:**
- Create: `docker/transcription-worker/Dockerfile`

- [ ] **Step 1: Créer le Dockerfile**

```dockerfile
# CPU base. Une variante CUDA (Dockerfile.cuda) sera ajoutée Phase H pour pve2 GPU.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg utilisé par faster-whisper pour les audios non WAV
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache .

COPY worker/ /app/worker/

ENV PYTHONPATH=/app

CMD ["python", "-m", "worker.main"]
```

- [ ] **Step 2: Commit**

```bash
git add docker/transcription-worker/Dockerfile
git commit -m "$(cat <<'EOF'
chore(workers): Dockerfile transcription-worker CPU (python 3.12-slim + ffmpeg)

Variante CUDA (Dockerfile.cuda) ajoutée Phase H pour le pool shared
faster-whisper sur pve2 GPU. Build via CI GitHub Actions, jamais en local.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A2 : pyproject.toml + squelette package + config

**Files:**
- Create: `docker/transcription-worker/pyproject.toml`
- Create: `docker/transcription-worker/worker/__init__.py`
- Create: `docker/transcription-worker/worker/config.py`
- Create: `docker/transcription-worker/tests/__init__.py`

- [ ] **Step 1: pyproject.toml**

```toml
[project]
name = "agflow-transcription-worker"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "asyncpg>=0.29",
    "minio>=7.2",
    "httpx>=0.26",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "structlog>=24.1",
    "faster-whisper>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["worker"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "ASYNC"]
ignore = ["E501"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: __init__.py**

`docker/transcription-worker/worker/__init__.py` :
```python
"""Transcription worker package. Container générique paramétré par TRANSCRIPTION_PROVIDER."""
```

`docker/transcription-worker/tests/__init__.py` : (vide)

- [ ] **Step 3: config.py**

```python
"""Worker config via Pydantic Settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration du worker, alimentée par env vars passées au container."""

    model_config = SettingsConfigDict(extra="ignore")

    # Identifiant logique du pool ('shared_default' ou 'user_<uuid>')
    worker_pool_id: str
    # Identifiant unique du worker (container_name typiquement)
    worker_id: str
    # Provider à instancier
    transcription_provider: str  # 'faster-whisper' | 'openai-whisper' | ...

    # Connexion DB partagée avec le backend
    database_url: str

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str

    # Cadence du polling (s)
    poll_interval_s: float = 2.0

    # Provider-spécifique
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    assemblyai_api_key: str = ""
    speechmatics_api_key: str = ""

    # faster-whisper
    faster_whisper_model: str = "large-v3"
    faster_whisper_device: str = "auto"  # auto|cpu|cuda
    faster_whisper_compute_type: str = "float16"  # float16 sur GPU, int8 sur CPU


settings = Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Initialiser uv**

Run : `cd docker/transcription-worker && uv sync --extra dev`

Expected : pas d'erreur. Si faster-whisper télécharge des wheels ML lourds, c'est attendu (~100-200 MB). Si timeout, retry une fois.

- [ ] **Step 5: Commit**

```bash
git add docker/transcription-worker/pyproject.toml \
        docker/transcription-worker/worker/__init__.py \
        docker/transcription-worker/worker/config.py \
        docker/transcription-worker/tests/__init__.py \
        docker/transcription-worker/uv.lock
git commit -m "$(cat <<'EOF'
chore(workers): pyproject + config Settings (env vars provider/pool/db/MinIO/clés API)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A3 : Module `pivot.py` (PivotTranscript dataclass)

**Files:**
- Create: `docker/transcription-worker/worker/pivot.py`
- Create: `docker/transcription-worker/tests/test_pivot.py`

- [ ] **Step 1: Test rouge**

`tests/test_pivot.py` :
```python
"""Tests pour le format pivot des transcripts."""
from __future__ import annotations

import json

import pytest


def test_pivot_transcript_to_dict_round_trip() -> None:
    """PivotTranscript.to_dict produit un JSON conforme spec 04 § Format pivot."""
    from worker.pivot import PivotTranscript, Segment, Word

    pivot = PivotTranscript(
        provider="openai-whisper",
        model="whisper-1",
        language="fr",
        language_confidence=None,
        duration_s=812.3,
        segments=[
            Segment(
                id=0, start=0.0, end=4.32,
                text="Bonjour à tous",
                avg_logprob=-0.21,
                words=[Word(word="Bonjour", start=0.0, end=0.42, probability=0.98)],
            ),
        ],
        metadata={"transcribed_at": "2026-04-27T08:00:00Z", "cost_estimate_usd": 0.0043},
    )
    data = pivot.to_dict()
    assert data["schema_version"] == "1.0"
    assert data["provider"] == "openai-whisper"
    assert data["segments"][0]["words"][0]["word"] == "Bonjour"
    # Round-trip JSON ne casse rien
    assert json.loads(json.dumps(data))["language"] == "fr"


def test_pivot_transcript_handles_no_words() -> None:
    """Provider sans word-timestamps : Segment.words=[]."""
    from worker.pivot import PivotTranscript, Segment

    pivot = PivotTranscript(
        provider="x", model="y", language="fr", language_confidence=None,
        duration_s=10.0,
        segments=[Segment(id=0, start=0.0, end=10.0, text="hello", avg_logprob=None, words=[])],
        metadata={},
    )
    data = pivot.to_dict()
    assert data["segments"][0]["words"] == []
```

Run : `cd docker/transcription-worker && uv run pytest tests/test_pivot.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Implémentation**

`worker/pivot.py` :
```python
"""Format pivot du transcript (cf. spec 04 § Format pivot)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Word:
    word: str
    start: float
    end: float
    probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "start": self.start,
            "end": self.end,
            "probability": self.probability,
        }


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "avg_logprob": self.avg_logprob,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class PivotTranscript:
    """Format pivot indépendant du provider. Cf. spec 04 § Format pivot."""
    provider: str
    model: str
    language: str
    language_confidence: float | None
    duration_s: float
    segments: list[Segment]
    metadata: dict[str, Any]

    SCHEMA_VERSION = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "duration_s": self.duration_s,
            "segments": [s.to_dict() for s in self.segments],
            "metadata": self.metadata,
        }
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add docker/transcription-worker/worker/pivot.py docker/transcription-worker/tests/test_pivot.py
git commit -m "$(cat <<'EOF'
feat(workers): pivot.py (PivotTranscript + Segment + Word, schema 1.0 conforme spec 04)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A4 : `providers/base.py` (Protocol + dataclasses partagées)

**Files:**
- Create: `docker/transcription-worker/worker/providers/__init__.py`
- Create: `docker/transcription-worker/worker/providers/base.py`
- Create: `docker/transcription-worker/tests/test_providers_base.py`

- [ ] **Step 1: Test rouge**

`tests/test_providers_base.py` :
```python
"""Tests pour le framework provider abstrait."""
from __future__ import annotations

import pytest

from worker.pivot import PivotTranscript


@pytest.mark.asyncio
async def test_provider_protocol_runtime_check() -> None:
    """Une classe minimaliste implémentant le Protocol passe runtime_checkable."""
    from worker.providers.base import (
        TranscriptionProvider,
        CreditInfo,
    )

    class _Impl:
        name = "stub"
        supports_language_detection = False
        supports_diarization = False
        supports_word_timestamps = False
        cost_per_minute_usd = 0.01

        async def transcribe(self, audio_path, *, language=None, options=None):
            return PivotTranscript(
                provider="stub", model="m", language="fr",
                language_confidence=None, duration_s=1.0,
                segments=[], metadata={},
            )

        def estimate_cost(self, duration_s):
            return duration_s / 60 * self.cost_per_minute_usd

        async def get_remaining_credit(self):
            return CreditInfo(balance_usd=42.0, last_check_at="2026-04-27T08:00:00Z", raw={})

    p: TranscriptionProvider = _Impl()
    assert isinstance(p, TranscriptionProvider)
    assert p.estimate_cost(60.0) == 0.01


def test_credit_info_dataclass() -> None:
    """CreditInfo accepte balance None pour les providers sans API balance."""
    from worker.providers.base import CreditInfo

    info = CreditInfo(balance_usd=None, last_check_at="2026-04-27T08:00:00Z", raw={})
    assert info.balance_usd is None
```

Run : FAIL.

- [ ] **Step 2: Implémentation**

`worker/providers/__init__.py` :
```python
"""Provider abstractions et implémentations concrètes."""
```

`worker/providers/base.py` :
```python
"""Provider abstrait commun à tous les moteurs de transcription."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from worker.pivot import PivotTranscript


@dataclass
class CreditInfo:
    """Information sur le crédit restant (None si non exposé par le provider)."""
    balance_usd: float | None
    last_check_at: str
    raw: dict[str, Any]


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Interface unifiée pour tous les providers de transcription.

    Chaque provider concret normalise sa sortie au format PivotTranscript.
    """

    name: str
    supports_language_detection: bool
    supports_diarization: bool
    supports_word_timestamps: bool
    cost_per_minute_usd: float | None  # None pour les providers locaux (gratuits modulo électricité)

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        ...

    def estimate_cost(self, duration_s: float) -> float:
        ...

    async def get_remaining_credit(self) -> CreditInfo | None:
        """Retourne le crédit restant si l'API du provider l'expose, None sinon."""
        ...
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add docker/transcription-worker/worker/providers/__init__.py \
        docker/transcription-worker/worker/providers/base.py \
        docker/transcription-worker/tests/test_providers_base.py
git commit -m "$(cat <<'EOF'
feat(workers): providers/base (Protocol TranscriptionProvider + CreditInfo)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase B — Provider OpenAI Whisper (priorité MVP)

Objectif : provider concret OpenAI Whisper API qui transcrit un fichier audio et retourne un `PivotTranscript`. Tests TDD avec `httpx.AsyncClient` mocké.

## Task B1 : `providers/openai_whisper.py` (TDD)

**Files:**
- Create: `docker/transcription-worker/worker/providers/openai_whisper.py`
- Create: `docker/transcription-worker/tests/test_openai_whisper.py`

- [ ] **Step 1: Test rouge**

`tests/test_openai_whisper.py` :
```python
"""Tests pour le provider OpenAI Whisper API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from httpx import HTTPStatusError, Request, Response
            raise HTTPStatusError(
                "fake", request=Request("POST", "http://x"),
                response=Response(status_code=self.status_code, json=self._body),
            )


class _StubAsyncClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_response: _StubResponse | None = None

    async def post(self, path: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"path": path, **kwargs})
        return self.next_response or _StubResponse(200, {})

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def openai_response_verbose() -> dict[str, Any]:
    """Sortie typique de OpenAI Whisper API en verbose_json + word timestamps."""
    return {
        "task": "transcribe",
        "language": "french",
        "duration": 12.34,
        "text": "Bonjour à tous, bienvenue.",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.32,
                "text": "Bonjour à tous,",
                "avg_logprob": -0.21,
                "words": [
                    {"word": "Bonjour", "start": 0.0, "end": 0.42},
                    {"word": "à", "start": 0.42, "end": 0.55},
                    {"word": "tous", "start": 0.55, "end": 1.10},
                ],
            },
            {
                "id": 1,
                "start": 4.32,
                "end": 6.50,
                "text": "bienvenue.",
                "avg_logprob": -0.18,
                "words": [{"word": "bienvenue", "start": 4.32, "end": 6.50}],
            },
        ],
    }


@pytest.mark.asyncio
async def test_transcribe_calls_audio_endpoint_with_verbose_json_and_word(
    tmp_path: Path, openai_response_verbose: dict[str, Any],
) -> None:
    audio = tmp_path / "v1.mp3"
    audio.write_bytes(b"fake audio")

    from worker.providers.openai_whisper import OpenAIWhisperProvider

    p = OpenAIWhisperProvider(api_key="sk-test")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(200, openai_response_verbose)
    p._http = stub  # type: ignore[assignment]

    pivot = await p.transcribe(str(audio), language="fr")

    # 1 appel à /audio/transcriptions
    call = stub.calls[0]
    assert call["path"] == "/audio/transcriptions"
    # response_format + timestamp_granularities + langue dans le multipart
    data = call["data"]
    assert data["model"] == "whisper-1"
    assert data["response_format"] == "verbose_json"
    assert data["timestamp_granularities[]"] == "word"
    assert data["language"] == "fr"

    # Adaptation pivot
    assert pivot.provider == "openai-whisper"
    assert pivot.language == "french"
    assert pivot.duration_s == 12.34
    assert len(pivot.segments) == 2
    assert pivot.segments[0].words[0].word == "Bonjour"


def test_estimate_cost_at_006_per_minute() -> None:
    from worker.providers.openai_whisper import OpenAIWhisperProvider

    p = OpenAIWhisperProvider(api_key="sk-test")
    assert p.estimate_cost(60.0) == pytest.approx(0.006)
    assert p.estimate_cost(600.0) == pytest.approx(0.06)


@pytest.mark.asyncio
async def test_get_remaining_credit_returns_none() -> None:
    """OpenAI n'expose pas de balance API publique."""
    from worker.providers.openai_whisper import OpenAIWhisperProvider

    p = OpenAIWhisperProvider(api_key="sk-test")
    assert await p.get_remaining_credit() is None
```

Run : `cd docker/transcription-worker && uv run pytest tests/test_openai_whisper.py -v` → FAIL.

- [ ] **Step 2: Implémentation**

`worker/providers/openai_whisper.py` :
```python
"""Provider OpenAI Whisper API."""
from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

import httpx

from worker.pivot import PivotTranscript, Segment, Word
from worker.providers.base import CreditInfo


class OpenAIWhisperProvider:
    """Implémentation TranscriptionProvider via OpenAI /v1/audio/transcriptions."""

    name = "openai-whisper"
    supports_language_detection = True
    supports_diarization = False
    supports_word_timestamps = True
    cost_per_minute_usd = 0.006

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300.0,
        )

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.rsplit("/", 1)[-1], f.read(), "audio/mpeg")}
        data: dict[str, Any] = {
            "model": "whisper-1",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        if language:
            data["language"] = language

        resp = await self._http.post("/audio/transcriptions", data=data, files=files)
        resp.raise_for_status()
        body = resp.json()
        return self._adapt(body)

    @staticmethod
    def _adapt(body: dict[str, Any]) -> PivotTranscript:
        segments_in = body.get("segments") or []
        segments_out: list[Segment] = []
        for seg in segments_in:
            words_out = [
                Word(
                    word=w["word"],
                    start=w["start"],
                    end=w["end"],
                    probability=None,  # OpenAI ne renvoie pas de prob par mot
                )
                for w in seg.get("words", [])
            ]
            segments_out.append(Segment(
                id=seg["id"],
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
                avg_logprob=seg.get("avg_logprob"),
                words=words_out,
            ))

        return PivotTranscript(
            provider="openai-whisper",
            model="whisper-1",
            language=body.get("language", ""),
            language_confidence=None,
            duration_s=float(body.get("duration", 0.0)),
            segments=segments_out,
            metadata={
                "transcribed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def estimate_cost(self, duration_s: float) -> float:
        return (duration_s / 60.0) * self.cost_per_minute_usd

    async def get_remaining_credit(self) -> CreditInfo | None:
        # OpenAI n'expose pas de balance API publique. La détection à l'usage
        # (HTTP 402 / insufficient_quota) est gérée par error_classifier.
        return None

    async def aclose(self) -> None:
        await self._http.aclose()
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add docker/transcription-worker/worker/providers/openai_whisper.py \
        docker/transcription-worker/tests/test_openai_whisper.py
git commit -m "$(cat <<'EOF'
feat(workers): provider OpenAI Whisper API (verbose_json + word timestamps + adaptation pivot)

Cost : 0.006 USD/min. Pas de balance API exposée — détection à l'usage
(HTTP 402) via error_classifier (Phase D).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase C — Provider faster-whisper (TDD avec mock)

Objectif : provider local faster-whisper. Tests TDD en mockant `WhisperModel` (pas d'inférence réelle en dev). En CI/pve2, l'image CUDA tournera réellement.

## Task C1 : `providers/faster_whisper.py` (TDD)

**Files:**
- Create: `docker/transcription-worker/worker/providers/faster_whisper.py`
- Create: `docker/transcription-worker/tests/test_faster_whisper.py`

- [ ] **Step 1: Test rouge**

`tests/test_faster_whisper.py` :
```python
"""Tests pour le provider faster-whisper local."""
from __future__ import annotations

from typing import Any

import pytest


class _StubSegment:
    """Mimique un Segment de faster-whisper."""
    def __init__(self, id, start, end, text, avg_logprob, words=None):
        self.id, self.start, self.end, self.text, self.avg_logprob = id, start, end, text, avg_logprob
        self.words = words or []


class _StubWord:
    def __init__(self, word, start, end, probability):
        self.word, self.start, self.end, self.probability = word, start, end, probability


class _StubInfo:
    def __init__(self, language, language_probability, duration):
        self.language = language
        self.language_probability = language_probability
        self.duration = duration


class _StubModel:
    """Simule WhisperModel.transcribe()."""
    def __init__(self, segments, info):
        self.segments = segments
        self.info = info
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, audio_path, **kwargs):
        self.calls.append({"audio_path": audio_path, **kwargs})
        return iter(self.segments), self.info


@pytest.fixture()
def stub_model_with_one_segment() -> _StubModel:
    return _StubModel(
        segments=[
            _StubSegment(
                id=0, start=0.0, end=4.32, text="Bonjour", avg_logprob=-0.21,
                words=[_StubWord("Bonjour", 0.0, 0.42, 0.98)],
            )
        ],
        info=_StubInfo(language="fr", language_probability=0.99, duration=812.0),
    )


@pytest.mark.asyncio
async def test_transcribe_calls_model_and_adapts_to_pivot(stub_model_with_one_segment) -> None:
    from worker.providers.faster_whisper import FasterWhisperProvider

    p = FasterWhisperProvider(model_size="large-v3", device="cpu", compute_type="int8")
    p._model = stub_model_with_one_segment  # bypass __init__ heavy load

    pivot = await p.transcribe("/tmp/v1.mp3", language="fr")

    assert pivot.provider == "faster-whisper"
    assert pivot.model == "large-v3"
    assert pivot.language == "fr"
    assert pivot.language_confidence == pytest.approx(0.99)
    assert pivot.duration_s == 812.0
    assert pivot.segments[0].words[0].probability == pytest.approx(0.98)


def test_estimate_cost_returns_zero_for_local_provider() -> None:
    from worker.providers.faster_whisper import FasterWhisperProvider

    p = FasterWhisperProvider.__new__(FasterWhisperProvider)
    p._model_name = "large-v3"
    assert p.estimate_cost(3600.0) == 0.0


@pytest.mark.asyncio
async def test_get_remaining_credit_is_none_for_local() -> None:
    from worker.providers.faster_whisper import FasterWhisperProvider

    p = FasterWhisperProvider.__new__(FasterWhisperProvider)
    assert await p.get_remaining_credit() is None
```

Run : FAIL.

- [ ] **Step 2: Implémentation**

`worker/providers/faster_whisper.py` :
```python
"""Provider faster-whisper local (CPU ou CUDA)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worker.pivot import PivotTranscript, Segment, Word
from worker.providers.base import CreditInfo


class FasterWhisperProvider:
    """Provider local. Charge le modèle en mémoire à l'init.

    Sur CPU : compute_type='int8' recommandé.
    Sur CUDA : compute_type='float16' recommandé (RTX 4090 sur pve2).
    """

    name = "faster-whisper"
    supports_language_detection = True
    supports_diarization = False
    supports_word_timestamps = True
    cost_per_minute_usd = None  # local : pas de coût marginal

    def __init__(
        self,
        *,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "float16",
    ) -> None:
        # Import lazy : faster-whisper est lourd à importer.
        from faster_whisper import WhisperModel

        self._model_name = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        opts = options or {}
        beam_size = int(opts.get("beam_size", 5))

        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            beam_size=beam_size,
        )

        segments_out: list[Segment] = []
        for seg in segments_iter:
            words_out = [
                Word(word=w.word, start=w.start, end=w.end, probability=w.probability)
                for w in (seg.words or [])
            ]
            segments_out.append(Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=seg.text,
                avg_logprob=seg.avg_logprob,
                words=words_out,
            ))

        return PivotTranscript(
            provider="faster-whisper",
            model=self._model_name,
            language=info.language,
            language_confidence=info.language_probability,
            duration_s=info.duration,
            segments=segments_out,
            metadata={
                "transcribed_at": datetime.now(timezone.utc).isoformat(),
                "device": self._device,
                "compute_type": self._compute_type,
            },
        )

    def estimate_cost(self, duration_s: float) -> float:
        return 0.0

    async def get_remaining_credit(self) -> CreditInfo | None:
        return None
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add docker/transcription-worker/worker/providers/faster_whisper.py \
        docker/transcription-worker/tests/test_faster_whisper.py
git commit -m "$(cat <<'EOF'
feat(workers): provider faster-whisper (CPU int8 / CUDA float16 + adaptation pivot)

Test TDD avec WhisperModel mocké. Inference réelle uniquement en CI ou
sur pve2 (image variante CUDA Phase H).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase D — Error classifier

Objectif : module commun qui mappe une erreur HTTP / exception provider vers une `ClassifiedError` (5 catégories : `invalid_key`, `exhausted`, `rate_limit`, `transient`, `unknown`). Utilisé par le main loop pour décider du retry et de la bascule shared.

## Task D1 : `error_classifier.py` (TDD)

**Files:**
- Create: `docker/transcription-worker/worker/error_classifier.py`
- Create: `docker/transcription-worker/tests/test_error_classifier.py`

- [ ] **Step 1: Test rouge**

```python
"""Tests pour le classifier d'erreurs de transcription."""
from __future__ import annotations

import pytest


def test_classify_401_invalid_key() -> None:
    from worker.error_classifier import classify_error, ErrorCategory

    err = classify_error(provider_name="openai-whisper", status_code=401,
                         body={"error": {"code": "invalid_api_key", "message": "Invalid API key"}})
    assert err.category == ErrorCategory.INVALID_KEY
    assert err.should_disable_key is True
    assert err.should_retry is False


def test_classify_402_exhausted() -> None:
    from worker.error_classifier import classify_error, ErrorCategory

    err = classify_error(provider_name="openai-whisper", status_code=402,
                         body={"error": {"code": "insufficient_quota"}})
    assert err.category == ErrorCategory.EXHAUSTED
    assert err.should_disable_key is True


def test_classify_429_rate_limit_not_quota() -> None:
    from worker.error_classifier import classify_error, ErrorCategory

    err = classify_error(provider_name="openai-whisper", status_code=429,
                         body={"error": {"code": "rate_limit_exceeded"}})
    assert err.category == ErrorCategory.RATE_LIMIT
    assert err.should_retry is True
    assert err.should_disable_key is False


def test_classify_429_quota_is_exhausted() -> None:
    from worker.error_classifier import classify_error, ErrorCategory

    err = classify_error(provider_name="openai-whisper", status_code=429,
                         body={"error": {"code": "monthly_quota_exceeded"}})
    assert err.category == ErrorCategory.EXHAUSTED
    assert err.should_disable_key is True


def test_classify_5xx_transient() -> None:
    from worker.error_classifier import classify_error, ErrorCategory

    err = classify_error(provider_name="openai-whisper", status_code=502, body={})
    assert err.category == ErrorCategory.TRANSIENT
    assert err.should_retry is True


def test_classify_unknown_defaults_to_transient() -> None:
    """Si on ne sait pas, on retry — moins risqué que de désactiver une clé valide."""
    from worker.error_classifier import classify_error, ErrorCategory

    err = classify_error(provider_name="unknown-provider", status_code=418, body={})
    assert err.category == ErrorCategory.TRANSIENT
    assert err.should_disable_key is False
    assert err.should_retry is True
```

Run : FAIL.

- [ ] **Step 2: Implémentation**

`worker/error_classifier.py` :
```python
"""Classification des erreurs renvoyées par les providers de transcription.

Spec : docs/specs/04-transcription.md § Classification des erreurs et bascule.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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


_QUOTA_HINT_KEYWORDS = ("quota", "insufficient", "billing", "exceeded")


def _looks_like_quota(body: dict[str, Any]) -> bool:
    err = body.get("error", {}) if isinstance(body, dict) else {}
    code = (err.get("code") or "").lower()
    msg = (err.get("message") or "").lower()
    blob = code + " " + msg
    return any(k in blob for k in _QUOTA_HINT_KEYWORDS) and "rate_limit" not in blob


def classify_error(
    *,
    provider_name: str,
    status_code: int,
    body: dict[str, Any],
) -> ClassifiedError:
    """Map une erreur HTTP du provider vers une ClassifiedError."""
    err_obj = body.get("error", {}) if isinstance(body, dict) else {}
    code = (err_obj.get("code") or "").lower()
    message = err_obj.get("message") or f"HTTP {status_code}"

    if status_code == 401 or "invalid_api_key" in code:
        return ClassifiedError(
            category=ErrorCategory.INVALID_KEY, message=message,
            should_retry=False, should_disable_key=True,
        )

    if status_code == 402:
        return ClassifiedError(
            category=ErrorCategory.EXHAUSTED, message=message,
            should_retry=False, should_disable_key=True,
        )

    if status_code == 429:
        if _looks_like_quota(body):
            return ClassifiedError(
                category=ErrorCategory.EXHAUSTED, message=message,
                should_retry=False, should_disable_key=True,
            )
        return ClassifiedError(
            category=ErrorCategory.RATE_LIMIT, message=message,
            should_retry=True, should_disable_key=False,
        )

    if status_code >= 500:
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT, message=message,
            should_retry=True, should_disable_key=False,
        )

    # Default conservateur : transient (retry max_attempts gère la cap)
    return ClassifiedError(
        category=ErrorCategory.TRANSIENT, message=message,
        should_retry=True, should_disable_key=False,
    )
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add docker/transcription-worker/worker/error_classifier.py \
        docker/transcription-worker/tests/test_error_classifier.py
git commit -m "$(cat <<'EOF'
feat(workers): error_classifier (5 catégories : invalid_key/exhausted/rate_limit/transient/unknown)

Cf. spec 04 § Classification des erreurs. Distingue 429 rate_limit vs quota
via inspection du body (mots-clés). Default conservateur = transient.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase E — Worker main loop + DB + MinIO client

Objectif : code complet du worker qui poll la queue, claim un job, télécharge l'audio, transcrit via le provider, upload le pivot, marque le job done. TDD avec asyncpg + MinIO mockés.

## Task E1 : `worker/db.py` (asyncpg helpers)

**Files:**
- Create: `docker/transcription-worker/worker/db.py`
- Create: `docker/transcription-worker/tests/test_db.py`

Signatures cibles (TDD avec stub asyncpg pool comme en Sprint 1/2 backend) :
```python
async def claim_next_job(
    worker_pool_id: str, worker_id: str,
    *, pool: asyncpg.Pool,
) -> dict | None:
    """SELECT FOR UPDATE SKIP LOCKED + UPDATE status='claimed' atomic."""

async def mark_job_done(
    job_id: UUID, *, provider_used: str, cost_estimate_usd: float,
    cost_actual_usd: float | None, result_s3_key: str,
    pool: asyncpg.Pool,
) -> None: ...

async def mark_job_failed(
    job_id: UUID, *, error: str, error_history_entry: dict,
    pool: asyncpg.Pool,
) -> None:
    """Append à error_history jsonb, set status='failed', incremente attempts."""

async def update_source_item_to_transcribed(
    source_item_id: UUID, transcript_s3_key: str,
    *, pool: asyncpg.Pool,
) -> None: ...

async def reassign_pending_to_shared(
    user_pool_id: str, *, pool: asyncpg.Pool,
) -> int:
    """UPDATE transcription_jobs SET worker_pool_id='shared_default'
    WHERE worker_pool_id=$1 AND status='pending'. Retourne le count."""

async def register_worker(
    worker_id: str, worker_pool_id: str, provider: str,
    *, status: str, host: str | None,
    pool: asyncpg.Pool,
) -> None: ...

async def update_worker_status(
    worker_id: str, status: str,
    *, last_activity_at: datetime | None = None,
    stopped_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> None: ...
```

Tests TDD : 6-8 tests vérifiant la SQL et les retours via stub `_StubPool` / `_StubConn` (réutiliser le pattern Sprint 1 backend).

Commit : `feat(workers): db.py (asyncpg helpers job lifecycle + workers + reassign)`

## Task E2 : `worker/minio_client.py`

**Files:**
- Create: `docker/transcription-worker/worker/minio_client.py`
- Create: `docker/transcription-worker/tests/test_minio_client.py`

Signatures :
```python
def download_audio(s3_key: str, dest_path: Path) -> None: ...
def upload_transcript(s3_key: str, payload: dict) -> None: ...
```

Implémentation basée sur `minio.Minio` avec `fget_object` / `put_object` (BytesIO du JSON).

Tests TDD : 2-3 tests avec stub minio (cf. pattern Sprint 1 `MinioWrapper`).

Commit : `feat(workers): minio_client (download_audio + upload_transcript JSON)`

## Task E3 : `worker/main.py` (boucle principale)

**Files:**
- Create: `docker/transcription-worker/worker/main.py`
- Create: `docker/transcription-worker/tests/test_main_loop.py`

Pseudocode :
```python
async def main() -> None:
    settings = Settings()
    configure_logging(...)
    provider = build_provider(settings.transcription_provider, settings)
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    await register_worker(settings.worker_id, settings.worker_pool_id, provider.name, status="idle", pool=pool)

    shutdown = asyncio.Event()
    install_signal_handlers(shutdown)

    try:
        while not shutdown.is_set():
            job = await claim_next_job(settings.worker_pool_id, settings.worker_id, pool=pool)
            if job is None:
                await wait_or_shutdown(shutdown, settings.poll_interval_s)
                continue

            await update_worker_status(settings.worker_id, "busy", pool=pool)
            try:
                await process_job(job, provider, pool, settings)
            except Exception as exc:
                await handle_error(job, provider, exc, pool)
            finally:
                await update_worker_status(settings.worker_id, "idle",
                                           last_activity_at=datetime.now(timezone.utc), pool=pool)
    finally:
        await update_worker_status(settings.worker_id, "stopped",
                                   stopped_at=datetime.now(timezone.utc), pool=pool)
        await pool.close()


async def process_job(job, provider, pool, settings) -> None:
    audio_path = Path(tempfile.gettempdir()) / f"{job['id']}.audio"
    download_audio(job["audio_s3_key"], audio_path)
    pivot = await provider.transcribe(str(audio_path), language=job.get("language"))
    pivot.metadata["cost_estimate_usd"] = provider.estimate_cost(pivot.duration_s)
    transcript_key = job["audio_s3_key"].replace("corpus-audio/", "corpus-transcripts/").rsplit(".", 1)[0] + ".json"
    upload_transcript(transcript_key, pivot.to_dict())
    await mark_job_done(job["id"], provider_used=provider.name,
                        cost_estimate_usd=pivot.metadata["cost_estimate_usd"],
                        cost_actual_usd=None, result_s3_key=transcript_key, pool=pool)
    await update_source_item_to_transcribed(job["source_item_id"], transcript_key, pool=pool)
    audio_path.unlink(missing_ok=True)


async def handle_error(job, provider, exc, pool) -> None:
    # Si exc est httpx.HTTPStatusError, classify + persist error_history
    # + si should_disable_key → mark key exhausted (DB), reassign jobs to shared
    # Sinon : mark_job_failed
    ...


def build_provider(name: str, settings: Settings) -> TranscriptionProvider:
    if name == "openai-whisper":
        return OpenAIWhisperProvider(api_key=settings.openai_api_key)
    if name == "faster-whisper":
        return FasterWhisperProvider(
            model_size=settings.faster_whisper_model,
            device=settings.faster_whisper_device,
            compute_type=settings.faster_whisper_compute_type,
        )
    raise ValueError(f"Unknown provider: {name}")
```

Tests TDD (`test_main_loop.py`, ~5-6 tests) — mocker provider + db + minio :
1. `process_job` enchaîne download → transcribe → upload → mark_done.
2. `process_job` upload le bon transcript_s3_key (replace corpus-audio→corpus-transcripts + .mp3→.json).
3. `handle_error` avec HTTPStatusError 402 → mark key exhausted + reassign pending to shared.
4. `handle_error` avec exception générique → mark_job_failed avec error_history_entry.
5. `build_provider` instancie le bon provider selon name.
6. `build_provider` raise ValueError sur name inconnu.

Commit : `feat(workers): main loop (poll + process + handle_error + build_provider)`

## Task E4 : Re-vérif suite tests worker complète

Run : `cd docker/transcription-worker && uv run pytest -v && uv run ruff check worker/ tests/`

Expected : tous tests verts (~25 tests cumulés A-E), ruff clean.

Pas de commit (sauf petits ajustements lint si nécessaire).

---

# Phase F — Backend worker_manager (provisioning + auto-stop)

Objectif : côté backend, gérer le cycle de vie des workers user (provisioning subprocess docker + auto-stop loop). Bascule sur épuisement.

## Task F1 : `db_helpers/transcription_keys.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/transcription_keys.py`
- Create: `backend/tests/test_db_helpers_transcription_keys.py`

Signatures :
```python
async def list_active_keys(*, pool) -> list[dict]: ...
async def list_active_keys_for_user(user_id, *, pool) -> list[dict]: ...
async def get_primary_key(user_id, *, pool) -> dict | None: ...
async def mark_exhausted(key_id, *, pool) -> None: ...
async def mark_invalid(key_id, *, pool) -> None: ...
```

Tests TDD identiques au pattern Sprint 2 db_helpers (4-5 tests).

Commit : `feat(backend): db_helpers/transcription_keys (list_active + mark_exhausted/invalid)`

## Task F2 : `services/worker_manager.py` (provisioning Docker + auto-stop)

**Files:**
- Create: `backend/src/role_builder/services/worker_manager.py`
- Create: `backend/tests/test_worker_manager.py`

Signatures :
```python
class WorkerManager:
    def __init__(self, *, pool, image_tag: str = "latest") -> None: ...

    async def ensure_user_workers_running(self, user_id: UUID) -> int:
        """Provisionne les workers manquants pour la primary key du user.
        Retourne le nombre de workers spawned."""

    async def spawn_worker(self, *, user_id, key, instance_index: int) -> str:
        """docker run -d --name rb-worker-... -e ... — retourne container_id."""

    async def stop_workers_for_key(self, key_id: UUID) -> int:
        """docker stop des workers liés à cette clé. Retourne count."""

    async def auto_stop_idle(self, *, threshold_seconds: int = 300) -> int:
        """Stoppe workers user idle depuis > threshold. Pas le shared. Retourne count."""

    async def run_auto_stop_loop(self, stop_event: asyncio.Event,
                                 period_seconds: int = 60) -> None:
        """Boucle qui appelle auto_stop_idle toutes les period_seconds."""
```

Implémentation : subprocess docker (pattern Sprint 2 docker_runner). Image name : `agflow-transcription-worker:{image_tag}` (CPU image générique pour les workers SaaS sur pve1 ; faster-whisper variante CUDA déployée séparément sur pve2).

Tests TDD (~6-8 tests) :
1. `ensure_user_workers_running` spawne le delta entre `key.workers_count` et workers actifs.
2. `spawn_worker` construit la bonne commande `docker run -d -e ...`.
3. `stop_workers_for_key` appelle `docker stop` pour chaque container.
4. `auto_stop_idle` exclut `shared_default` du candidate set.
5. `auto_stop_idle` ne stoppe que les workers `idle` avec `last_activity_at < now - threshold`.
6. `run_auto_stop_loop` exit quand `stop_event` est set.

Commit : `feat(backend): worker_manager (provisioning subprocess docker + auto_stop loop)`

## Task F3 : `services/credit_basculer.py` (bascule sur exhausted)

**Files:**
- Create: `backend/src/role_builder/services/credit_basculer.py`
- Create: `backend/tests/test_credit_basculer.py`

Quand un worker reporte une clé exhausted (via `db_helpers.transcription_keys.mark_exhausted`), un trigger PG NOTIFY `keys_changes` peut être consommé par le backend pour :
1. Stopper les workers liés à cette clé via `worker_manager.stop_workers_for_key`
2. Réassigner les jobs en attente du user vers `shared_default` via `db_helpers.transcription_jobs.reassign_pending_to_shared`
3. (Sprint 6) Notifier l'user via UI/email

Pour Sprint 3 : exposer un module `credit_basculer.handle_key_exhausted(key_id, user_id, pool, manager)` qui fait les 2 actions ci-dessus. Le wiring PG NOTIFY → trigger réel sera fait Sprint 6 (Ma stack), pour l'instant le worker appelle directement `handle_key_exhausted` à la détection.

Tests TDD : 2 tests (workers stoppés + jobs réassignés).

Commit : `feat(backend): credit_basculer (stop workers + reassign jobs to shared sur exhausted)`

## Task F4 : Intégration lifespan FastAPI

**Files:**
- Modify: `backend/src/role_builder/config.py` (ajouter `disable_worker_manager: bool = False`)
- Modify: `backend/src/role_builder/main.py` (instancier WorkerManager + démarrer auto_stop_loop)
- Modify: `backend/tests/conftest.py` (`disable_worker_manager = True` dans fixture client)

Pattern identique à `disable_orchestrator` / `disable_ws_relay` Sprint 2.

Run pytest backend complet : `cd backend && uv run pytest -v` → ~70+ tests verts.

Commit : `feat(backend): worker_manager démarré dans lifespan (gardé par DISABLE_WORKER_MANAGER)`

---

# Phase G — Câblage Sprint 2 → Sprint 3

Objectif : combler le trou noté en Sprint 2 — `event_handlers.on_item_done` doit créer un `transcription_jobs`. Ajouter aussi le helper DB côté backend.

## Task G1 : `db_helpers/transcription_jobs.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/transcription_jobs.py`
- Create: `backend/tests/test_db_helpers_transcription_jobs.py`

Signatures :
```python
async def insert_job(
    *, source_item_id, tenant_id, audio_s3_key, language=None,
    worker_pool_id, priority=0, pool,
) -> UUID: ...

async def reassign_pending_to_shared(
    user_pool_id, *, pool,
) -> int: ...

async def list_jobs(
    *, status=None, worker_pool_id=None, limit=50, pool,
) -> list[dict]: ...
```

Tests TDD (~3 tests).

Commit : `feat(backend): db_helpers/transcription_jobs (insert + reassign + list)`

## Task G2 : Modifier `event_handlers.on_item_done`

**Files:**
- Modify: `backend/src/role_builder/services/event_handlers.py`
- Modify: `backend/tests/test_event_handlers.py`

Logique :
- Sur `item_done`, calculer `worker_pool_id` :
  - Si user a une primary key active (`db_helpers.transcription_keys.get_primary_key`), `worker_pool_id = f"user_{user_id}"`
  - Sinon `worker_pool_id = "shared_default"`
- Insérer un `transcription_jobs` via `db_helpers.transcription_jobs.insert_job`.
- Update `source_items.status='queued_transcription'` (utiliser le helper Sprint 2 `update_source_item_status`).

Test : ajouter 2 tests vérifiant le nouveau path (user avec key → `user_<id>`, sans key → `shared_default`).

Commit : `feat(backend): event_handlers crée transcription_jobs sur item_done`

## Task G3 : `docker-compose.pve2.yml` (référence pour le pool shared)

**Files:**
- Create: `docker-compose.pve2.yml`

```yaml
# Stack à déployer sur pve2 (GPU RTX 4090).
# Lance le worker faster-whisper en pool shared, toujours up.
# Pas exécuté localement — provisionné sur pve2 via scripts d'infra.

services:
  shared-whisper-worker:
    image: ghcr.io/${GHCR_OWNER:-yoops}/agflow-transcription-worker-cuda:${WORKER_IMAGE_TAG:-latest}
    restart: unless-stopped
    runtime: nvidia
    environment:
      WORKER_POOL_ID: shared_default
      WORKER_ID: shared-whisper-pve2
      TRANSCRIPTION_PROVIDER: faster-whisper
      DATABASE_URL: ${DATABASE_URL}
      MINIO_ENDPOINT: ${MINIO_ENDPOINT}
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
      FASTER_WHISPER_MODEL: large-v3
      FASTER_WHISPER_DEVICE: cuda
      FASTER_WHISPER_COMPUTE_TYPE: float16
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Note : ce fichier est documentaire et opérationnel pour pve2. L'orchestration backend (worker_manager) ne le manipule PAS — il sert au sysadmin pour provisionner manuellement le pool shared.

Commit : `chore(infra): docker-compose.pve2.yml (worker shared faster-whisper toujours up)`

## Task G4 : Mise à jour `.env.example` et `Settings` backend

**Files:**
- Modify: `.env.example`
- Modify: `backend/src/role_builder/config.py`

Ajouter :
```bash
# Clés API SaaS de transcription (vides = pas de provisioning auto, fallback shared)
OPENAI_API_KEY=
DEEPGRAM_API_KEY=
ASSEMBLYAI_API_KEY=
SPEECHMATICS_API_KEY=

# Auto-stop des workers user idle
WORKER_AUTO_STOP_THRESHOLD_S=300
WORKER_AUTO_STOP_PERIOD_S=60

# Tag d'image du worker
WORKER_IMAGE_TAG=latest

# Owner GHCR (pour les pulls de production)
GHCR_OWNER=
```

Étendre Settings backend :
```python
openai_api_key: str = ""
deepgram_api_key: str = ""
assemblyai_api_key: str = ""
speechmatics_api_key: str = ""
worker_auto_stop_threshold_s: int = 300
worker_auto_stop_period_s: int = 60
worker_image_tag: str = "latest"
ghcr_owner: str = ""
```

Étendre 1 test config existant pour vérifier les nouvelles defaults.

Commit : `feat(backend): config Settings ajoute clés SaaS + worker auto-stop + GHCR owner`

---

# Phase H — CI étendue + image CUDA

Objectif : la CI build l'image worker (CPU) et la variante CUDA pour pve2.

## Task H1 : `Dockerfile.cuda` (variante GPU)

**Files:**
- Create: `docker/transcription-worker/Dockerfile.cuda`

```dockerfile
# Variante CUDA pour le pool shared sur pve2 (RTX 4090).
FROM nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip \
        ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3.12 /usr/bin/python && \
    pip install --no-cache-dir --break-system-packages uv

WORKDIR /app

COPY pyproject.toml /app/
RUN uv pip install --system --no-cache .

COPY worker/ /app/worker/

ENV PYTHONPATH=/app

CMD ["python", "-m", "worker.main"]
```

Commit : `chore(workers): Dockerfile.cuda (base nvidia/cuda 12.4 cudnn pour pve2 GPU)`

## Task H2 : `.github/workflows/build-workers.yml`

**Files:**
- Create: `.github/workflows/build-workers.yml`

Pattern similaire à `build-scrapers.yml` Sprint 2. Build matriciel :
- `agflow-transcription-worker` (CPU, depuis `Dockerfile`)
- `agflow-transcription-worker-cuda` (GPU, depuis `Dockerfile.cuda`)

Tags `:sha-<short>`, `:latest` (sur push main), `:vX.Y.Z` (sur tag).

```yaml
name: build-workers

on:
  push:
    branches: [main]
    tags: ["v*"]
  workflow_dispatch: {}

env:
  REGISTRY: ghcr.io
  IMAGE_OWNER: ${{ github.repository_owner }}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        variant:
          - { name: "agflow-transcription-worker", dockerfile: "Dockerfile" }
          - { name: "agflow-transcription-worker-cuda", dockerfile: "Dockerfile.cuda" }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: tags
        run: |
          OWNER_LC="${IMAGE_OWNER,,}"
          IMAGE="${REGISTRY}/${OWNER_LC}/${{ matrix.variant.name }}"
          TAGS="${IMAGE}:sha-${GITHUB_SHA:0:7}"
          if [[ "${GITHUB_REF}" == "refs/heads/main" ]]; then TAGS="${TAGS},${IMAGE}:latest"; fi
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then TAGS="${TAGS},${IMAGE}:${GITHUB_REF_NAME}"; fi
          echo "tags=${TAGS}" >> "$GITHUB_OUTPUT"
      - uses: docker/build-push-action@v6
        with:
          context: docker/transcription-worker
          file: docker/transcription-worker/${{ matrix.variant.dockerfile }}
          push: true
          tags: ${{ steps.tags.outputs.tags }}
```

Commit : `ci: workflow build-workers (matrix CPU + CUDA vers GHCR)`

## Task H3 : Étendre `tests.yml` — job worker tests

**Files:**
- Modify: `.github/workflows/test.yml`

Ajouter un 4ème job en parallèle :
```yaml
  worker-tests:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: docker/transcription-worker
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { version: "0.10.9" }
      - run: uv python install 3.12
      - run: uv sync --extra dev
      - run: uv run ruff check worker/ tests/
      - run: uv run pytest -v
```

Commit : `ci: workflow tests ajoute job worker-tests (pytest + ruff)`

## Task H4 : Étendre la doc opérations

**Files:**
- Modify: `docs/operations/ci.md`

Ajouter une section sur les images workers, `docker-compose.pve2.yml`, et le déploiement du pool shared faster-whisper sur pve2 (étapes : créer LXC ou container avec accès GPU, `docker pull`, `docker compose -f docker-compose.pve2.yml up -d`).

Commit : `docs(operations): ajout section workers + déploiement pool shared pve2`

---

# Phase I — Tests + tag + open-decisions

## Task I1 : Vérification globale

Run :
- `cd backend && uv run pytest -v` (~75+ tests)
- `cd backend && uv run ruff check src/ tests/`
- `cd docker/scrapers/youtube && uv run pytest -v` (10 tests inchangés)
- `cd docker/transcription-worker && uv run pytest -v` (~25 tests)
- `cd docker/transcription-worker && uv run ruff check worker/ tests/`
- `cd frontend && npm test && npm run typecheck && npm run lint`

Tout doit être vert.

## Task I2 : Mise à jour `12-open-decisions.md`

Cocher les décisions tranchées et ajouter une section "Sprint 3 — Décisions actées et observations". Notamment :
- Providers MVP : OpenAI Whisper + faster-whisper (autres reportés Phase 2)
- Auto-stop : asyncio task interne backend (pas APScheduler)
- Polling crédit Deepgram : reporté
- Diarization : reportée
- Retry exponential backoff : reporté (max_attempts gère la cap)
- Audios > 25 MB OpenAI Whisper : reporté (à splitter côté worker Phase 2)
- Image variante CUDA pour pve2

Commit : `docs(specs): décisions Sprint 3 actées dans 12-open-decisions.md`

## Task I3 : Tag

```bash
git tag -a v0.3.0-sprint-3 -m "Sprint 3 — Transcription terminé

Worker générique paramétré par TRANSCRIPTION_PROVIDER. 2 providers MVP :
OpenAI Whisper API et faster-whisper local. Backend worker_manager
provisionne les workers user à la demande via subprocess Docker, et stoppe
les workers idle > 5 min via une asyncio task. Bascule sur épuisement
de crédit (HTTP 402 → mark exhausted + reassign jobs to shared).

Câblage Sprint 2 : event_handlers.on_item_done crée maintenant un
transcription_jobs avec worker_pool_id selon que le user a une primary
key SaaS active.

Tests : ~25 tests worker + ~75+ tests backend + 10 scrapers + 12 frontend.
CI : workflow build-workers (CPU + CUDA vers GHCR), workflow tests étendu
au 4ème job worker-tests.

Limites :
- Pas de smoke runtime local (Docker mis de côté)
- Polling crédit Deepgram reporté
- Diarization reportée
- Retry exponential backoff reporté
- Audios > 25 MB OpenAI : reporté"
```

Pas de commit (tag = pointeur git).

---

## Récapitulatif estimé des commits

~25 commits :
- Phase A : 4 (Dockerfile, pyproject+config+init, pivot, providers/base)
- Phase B : 1 (openai_whisper)
- Phase C : 1 (faster_whisper)
- Phase D : 1 (error_classifier)
- Phase E : 4 (db, minio_client, main, ajustements)
- Phase F : 4 (transcription_keys, worker_manager, credit_basculer, lifespan)
- Phase G : 4 (db_helpers/transcription_jobs, event_handlers modify, pve2.yml, .env+config)
- Phase H : 4 (Dockerfile.cuda, build-workers, tests.yml extend, doc ops)
- Phase I : 1 (open-decisions) + 1 tag

Tag final : `v0.3.0-sprint-3`.
