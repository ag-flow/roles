# Sprint 4 — Corpus Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** À partir d'un transcript pivot dans MinIO (issu Sprint 3), produire des chunks 500 tokens overlap 50 avec timestamps préservés, embeddés via Mistral (1024 dim), stockés dans `corpus_chunks` (pgvector). Exposer une recherche sémantique via API + onglet Corpus dans l'UI.

**Architecture:**
- **Abstraction `agflow_client.py`** : `invoke_embeddings(texts) → list[list[float]]` et `invoke_chat(messages, model) → ChatResult`. Implémentation MVP appelle directement `api.mistral.ai`. Quand l'OpenAPI ag.flow sera connu, swap interne sans toucher aux callers.
- **`chunking_worker`** : asyncio task interne au backend (pas de container séparé MVP, l'opération est CPU-bound léger). Poll `chunking_jobs` en FIFO `FOR UPDATE SKIP LOCKED`, télécharge transcript MinIO, chunk, embed batch 32, insert pgvector.
- **Câblage Sprint 3** : le worker transcription insère un `chunking_job` après `mark_job_done` (cf. spec 05 § Boucle principale + spec 04 § process_job).
- **Routes API corpus** : `/api/role-projects/{id}/corpus/search` (sémantique), `/api/.../chunks`, `/api/.../items/{item_id}/transcript`, `/api/.../items/{item_id}/audio-url` (presigned MinIO).
- **Frontend** : onglet Corpus dans `app/projects/[id]/corpus/` avec barre de recherche sémantique + résultats avec timestamps cliquables + browsing par source.

**Tech Stack:**
- Backend : `httpx` (Mistral API), `asyncpg` + extension pgvector (`<=>` cosine distance), pas de nouvelle dépendance Python.
- Frontend : SWR (déjà installé Sprint 2), pas de nouvelle dépendance npm.
- Tests : `respx` ou stub pattern Sprint 1/2/3 pour mocker httpx Mistral.

**Décisions actées** :
- Modèle embed : `mistral-embed` (1024 dim).
- Modèle LLM Sprint 5 : `mistral-large-latest` (Settings préparées Phase A).
- Stratégie chunking : 500 tokens cible, 50 overlap, frontières de phrases respectées.
- Approximation tokens : `chars // 4` (français ~20% près, suffisant MVP).
- Index pgvector : `ivfflat` avec `vector_cosine_ops` (déjà créé migration 0004), `lists=100`.
- Dimension provisoire : 1024 (à reconfirmer si Mistral change).
- Worker chunking dans le backend (asyncio task, pas un container séparé).

**Critères de fin** (cf. spec 05 § Critères de fin de sprint) :
- Worker chunking pull les `chunking_jobs` et produit des `corpus_chunks` avec embeddings.
- Une vidéo passe end-to-end : audio → transcript → chunks indexés.
- Recherche sémantique retourne des résultats pertinents.
- Index pgvector créé et utilisé (vérifier `EXPLAIN ANALYZE`).
- UI Corpus affiche les chunks et permet la recherche.
- WebSocket push : un item passe à `indexed` est visible immédiatement dans l'UI (déjà câblé Sprint 2 via PG NOTIFY `source_items_changes`).
- Présigned URLs fonctionnent : audio écoutable depuis le navigateur sans login MinIO.
- Tests verts : backend + worker + frontend.

---

## File Structure

```
agflow.roles/
├── backend/
│   ├── pyproject.toml                                           # inchangé
│   └── src/role_builder/
│       ├── config.py                                            # Phase A2 modify (MISTRAL_*)
│       ├── main.py                                              # Phase C3 modify (chunking_worker lifespan)
│       ├── services/
│       │   ├── agflow_client.py                                 # Phase A1 NEW
│       │   ├── chunker.py                                       # Phase B NEW
│       │   ├── embedder.py                                      # Phase C1 NEW
│       │   ├── chunking_worker.py                               # Phase C2 NEW
│       │   ├── corpus_search.py                                 # Phase D5 NEW (RAG helper)
│       │   └── event_handlers.py                                # NOT MODIFIED Sprint 4 (le worker insère)
│       ├── db_helpers/
│       │   ├── chunking_jobs.py                                 # Phase C5 NEW (claim, mark_done, mark_failed)
│       │   └── corpus_chunks.py                                 # Phase C5 NEW (insert_bulk, semantic_search, list_by_item)
│       ├── schemas/
│       │   └── corpus.py                                        # Phase D1 NEW (DTOs Pydantic)
│       └── routes/
│           └── corpus.py                                        # Phase D NEW (4 endpoints)
│
├── docker/transcription-worker/                                 # Phase C4 modify : insert chunking_job after mark_done
│   └── worker/
│       ├── db.py                                                # Phase C4 modify (+insert_chunking_job)
│       └── main.py                                              # Phase C4 modify (call insert_chunking_job after mark_done)
│
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   ├── api/
│   │   │   │   └── corpus.ts                                    # Phase E1 NEW
│   │   │   └── types.ts                                         # Phase E1 modify (Chunk, SearchResult types)
│   │   ├── app/projects/[id]/corpus/
│   │   │   ├── page.tsx                                         # Phase E2 NEW (overview + search bar)
│   │   │   ├── SearchBar.tsx                                    # Phase E3 NEW
│   │   │   ├── SearchResults.tsx                                # Phase E3 NEW
│   │   │   ├── ChunkCard.tsx                                    # Phase E4 NEW
│   │   │   ├── SourcesList.tsx                                  # Phase E5 NEW
│   │   │   └── TranscriptViewer.tsx                             # Phase E5 NEW
│   │   └── __tests__/
│   │       └── corpus-api.test.ts                               # Phase E6 NEW
│
└── docs/specs/12-open-decisions.md                              # Phase F update
```

---

# Phase A — Abstraction agflow_client + Settings

## Task A1 : `services/agflow_client.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/services/agflow_client.py`
- Create: `backend/tests/test_agflow_client.py`

**Architecture** : interface stable qui encapsule "comment appeler Mistral". MVP = appel direct `api.mistral.ai`. Phase 2 = swap vers ag.flow OpenAPI.

- [ ] **Step 1: Test rouge**

`backend/tests/test_agflow_client.py` :
```python
"""Tests for the AgflowClient (Mistral API abstraction)."""
from __future__ import annotations

from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int, json_body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = json_body

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from httpx import HTTPStatusError, Request, Response
            raise HTTPStatusError(
                "fake", request=Request("POST", "http://x"),
                response=Response(status_code=self.status_code),
            )


class _StubAsyncClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_response: _StubResponse | None = None

    async def post(self, path: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"path": path, **kwargs})
        return self.next_response or _StubResponse(200, {})

    async def aclose(self) -> None: ...


@pytest.mark.asyncio
async def test_invoke_embeddings_calls_mistral_embed(stubbed_env: None) -> None:
    """invoke_embeddings POST sur /v1/embeddings avec model + input."""
    from role_builder.services.agflow_client import AgflowClient

    client = AgflowClient(api_key="sk-test", embed_model="mistral-embed")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(200, {
        "data": [
            {"embedding": [0.1, 0.2, 0.3], "index": 0},
            {"embedding": [0.4, 0.5, 0.6], "index": 1},
        ],
    })
    client._http = stub  # type: ignore[assignment]

    vectors = await client.invoke_embeddings(["text 1", "text 2"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert stub.calls[0]["path"] == "/v1/embeddings"
    assert stub.calls[0]["json"] == {"model": "mistral-embed", "input": ["text 1", "text 2"]}


@pytest.mark.asyncio
async def test_invoke_chat_returns_content_and_usage(stubbed_env: None) -> None:
    """invoke_chat POST sur /v1/chat/completions et retourne ChatResult."""
    from role_builder.services.agflow_client import AgflowClient

    client = AgflowClient(api_key="sk-test", chat_model="mistral-large-latest")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(200, {
        "choices": [{"message": {"content": "Bonjour"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "model": "mistral-large-latest",
    })
    client._http = stub  # type: ignore[assignment]

    result = await client.invoke_chat([{"role": "user", "content": "Salut"}])

    assert result.content == "Bonjour"
    assert result.tokens_input == 10
    assert result.tokens_output == 5
    assert result.model == "mistral-large-latest"
    assert stub.calls[0]["path"] == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_invoke_embeddings_batches_above_32(stubbed_env: None) -> None:
    """Si input > 32, plusieurs appels sont faits (batching)."""
    from role_builder.services.agflow_client import AgflowClient

    client = AgflowClient(api_key="sk-test", embed_model="mistral-embed")
    stub = _StubAsyncClient()
    # Toujours retourner 2 vecteurs (peu importe la taille demandée — le test vérifie le nombre d'appels)
    stub.next_response = _StubResponse(200, {
        "data": [{"embedding": [0.1] * 1024, "index": 0}],
    })
    client._http = stub  # type: ignore[assignment]

    texts = ["t"] * 50  # 50 inputs → 2 batches (32 + 18)
    await client.invoke_embeddings(texts)

    assert len(stub.calls) == 2
    assert len(stub.calls[0]["json"]["input"]) == 32
    assert len(stub.calls[1]["json"]["input"]) == 18
```

Run : `cd backend && uv run pytest tests/test_agflow_client.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 2: Implémentation**

`backend/src/role_builder/services/agflow_client.py` :
```python
"""Abstraction LLM/embeddings.

MVP : appel direct api.mistral.ai. Phase 2 : swap interne vers ag.flow
quand son OpenAPI sera figé, sans changer l'interface des callers.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from role_builder.config import settings


@dataclass
class ChatResult:
    content: str
    tokens_input: int
    tokens_output: int
    cost_usd: float | None
    model: str


class AgflowClient:
    """Client unifié pour les LLM/embeddings."""

    EMBED_BATCH_SIZE = 32

    def __init__(
        self,
        *,
        api_key: str | None = None,
        embed_model: str | None = None,
        chat_model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.mistral_api_key
        self._embed_model = embed_model or settings.mistral_embed_model
        self._chat_model = chat_model or settings.mistral_chat_model
        self._base_url = base_url or settings.mistral_base_url
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=120.0,
        )

    async def invoke_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed une liste de textes. Auto-batches si > EMBED_BATCH_SIZE."""
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.EMBED_BATCH_SIZE):
            batch = texts[i : i + self.EMBED_BATCH_SIZE]
            resp = await self._http.post(
                "/v1/embeddings",
                json={"model": self._embed_model, "input": batch},
            )
            resp.raise_for_status()
            body = resp.json()
            all_vectors.extend(item["embedding"] for item in body["data"])
        return all_vectors

    async def invoke_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        """Appel chat completion. Le response_format peut forcer du JSON strict."""
        payload: dict = {
            "model": model or self._chat_model,
            "messages": messages,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if temperature is not None:
            payload["temperature"] = temperature

        resp = await self._http.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        body = resp.json()
        usage = body.get("usage", {})
        return ChatResult(
            content=body["choices"][0]["message"]["content"],
            tokens_input=int(usage.get("prompt_tokens", 0)),
            tokens_output=int(usage.get("completion_tokens", 0)),
            cost_usd=None,  # Mistral n'expose pas de cost direct, à calculer post-hoc si besoin
            model=body.get("model", payload["model"]),
        )

    async def aclose(self) -> None:
        await self._http.aclose()


_singleton: AgflowClient | None = None


def get_agflow_client() -> AgflowClient:
    """Singleton FastAPI dependency-style. Lazy init pour respect du settings."""
    global _singleton
    if _singleton is None:
        _singleton = AgflowClient()
    return _singleton
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add backend/src/role_builder/services/agflow_client.py backend/tests/test_agflow_client.py
git commit -m "$(cat <<'EOF'
feat(backend): agflow_client (abstraction Mistral embeddings + chat, batching auto)

Wrapper httpx async pour api.mistral.ai. Implémentation MVP — quand
l'OpenAPI ag.flow sera figé, swap interne sans toucher aux callers
(décision ouverte n°1 du projet).

Méthodes :
- invoke_embeddings(texts) -> list[list[float]] : auto-batch en
  blocs de 32, retourne les vecteurs aplatis dans l'ordre d'origine.
- invoke_chat(messages, model, response_format, temperature) ->
  ChatResult (content + tokens_input/output + model).

Singleton get_agflow_client() pour DI FastAPI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A2 : Settings Mistral

**Files:**
- Modify: `backend/src/role_builder/config.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Étendre Settings**

Ajouter dans `Settings` :
```python
mistral_api_key: str = ""
mistral_base_url: str = "https://api.mistral.ai"
mistral_embed_model: str = "mistral-embed"
mistral_chat_model: str = "mistral-large-latest"
chunking_enabled: bool = True  # disable_chunking_worker pattern Sprint 1/2/3
disable_chunking_worker: bool = False
```

- [ ] **Step 2: Étendre `test_config.py`**

Ajouter au test existant les 6 nouvelles defaults :
```python
assert s.mistral_api_key == ""
assert s.mistral_base_url == "https://api.mistral.ai"
assert s.mistral_embed_model == "mistral-embed"
assert s.mistral_chat_model == "mistral-large-latest"
assert s.disable_chunking_worker is False
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/role_builder/config.py backend/tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(backend): config Mistral (api_key + base_url + embed/chat models + disable_chunking_worker)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Task A3 : `.env.example` + docker-compose.yml

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: `.env.example`** ajout d'une section :
```env
# === Mistral (LLM + embeddings) ===
# MVP : appel direct api.mistral.ai. À swap vers ag.flow quand l'OpenAPI sera figé.
MISTRAL_API_KEY=
MISTRAL_BASE_URL=https://api.mistral.ai
MISTRAL_EMBED_MODEL=mistral-embed
MISTRAL_CHAT_MODEL=mistral-large-latest

# Worker chunking (asyncio task interne au backend)
DISABLE_CHUNKING_WORKER=false
```

- [ ] **Step 2: `docker-compose.yml`** propager dans le service `backend` :
```yaml
      MISTRAL_API_KEY: ${MISTRAL_API_KEY:-}
      MISTRAL_BASE_URL: ${MISTRAL_BASE_URL:-https://api.mistral.ai}
      MISTRAL_EMBED_MODEL: ${MISTRAL_EMBED_MODEL:-mistral-embed}
      MISTRAL_CHAT_MODEL: ${MISTRAL_CHAT_MODEL:-mistral-large-latest}
      DISABLE_CHUNKING_WORKER: ${DISABLE_CHUNKING_WORKER:-false}
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docker-compose.yml
git commit -m "$(cat <<'EOF'
feat(infra): env vars Mistral + DISABLE_CHUNKING_WORKER (Sprint 4)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase B — Module chunker

## Task B1 : `services/chunker.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/services/chunker.py`
- Create: `backend/tests/test_chunker.py`

**Algorithme** :
1. Iterate sentence by sentence (segments du transcript pivot).
2. Accumulate sentences jusqu'à atteindre `target_tokens`.
3. Emit chunk (avec start_s = premier segment, end_s = dernier segment).
4. Backtrack `overlap_tokens` pour le chunk suivant.

- [ ] **Step 1: Test rouge**

`backend/tests/test_chunker.py` :
```python
"""Tests for the transcript chunker."""
from __future__ import annotations

import pytest


def _make_segment(start: float, end: float, text: str) -> dict:
    return {"id": 0, "start": start, "end": end, "text": text}


def test_chunk_short_transcript_returns_one_chunk() -> None:
    """Un transcript court (< target_tokens) tient dans 1 chunk."""
    from role_builder.services.chunker import chunk_transcript

    transcript = {
        "segments": [
            _make_segment(0.0, 2.0, "Bonjour à tous."),
            _make_segment(2.0, 5.0, "Bienvenue dans cette vidéo."),
        ],
    }
    chunks = chunk_transcript(transcript, target_tokens=500, overlap_tokens=50)
    assert len(chunks) == 1
    assert chunks[0].start_s == 0.0
    assert chunks[0].end_s == 5.0
    assert "Bonjour" in chunks[0].text
    assert "Bienvenue" in chunks[0].text


def test_chunk_preserves_timestamps() -> None:
    """Les start_s / end_s des chunks correspondent aux segments inclus."""
    from role_builder.services.chunker import chunk_transcript

    transcript = {
        "segments": [
            _make_segment(0.0, 10.0, "x" * 200),  # ~50 tokens
            _make_segment(10.0, 20.0, "y" * 200),  # ~50 tokens
            _make_segment(20.0, 30.0, "z" * 200),  # ~50 tokens
        ],
    }
    chunks = chunk_transcript(transcript, target_tokens=100, overlap_tokens=0)
    # Avec target=100 et 50 tokens/segment, on a 2 segments par chunk.
    # Premier chunk : seg 1+2 → 0.0-20.0
    # Deuxième chunk : seg 3 → 20.0-30.0
    assert chunks[0].start_s == 0.0
    assert chunks[0].end_s == 20.0
    assert chunks[-1].end_s == 30.0


def test_chunk_overlap_creates_repetition() -> None:
    """Avec overlap > 0, les chunks consécutifs partagent du contenu."""
    from role_builder.services.chunker import chunk_transcript

    # 4 segments de 80 chars (~20 tokens chacun) → ~80 tokens total
    transcript = {
        "segments": [_make_segment(i * 5.0, (i + 1) * 5.0, "x" * 80) for i in range(4)],
    }
    chunks = chunk_transcript(transcript, target_tokens=40, overlap_tokens=20)
    # Premier chunk : 2 segments = 40 tokens. Backtrack 1 segment (20 tokens) pour le 2e chunk.
    # 2e chunk démarre au segment 2 (index 1).
    assert len(chunks) >= 2
    # Le 2e chunk commence dans le temps du 1er
    assert chunks[1].start_s < chunks[0].end_s


def test_chunk_empty_transcript_returns_empty() -> None:
    """Pas de segments → pas de chunks."""
    from role_builder.services.chunker import chunk_transcript

    chunks = chunk_transcript({"segments": []}, target_tokens=500, overlap_tokens=50)
    assert chunks == []
```

Run : FAIL.

- [ ] **Step 2: Implémentation**

`backend/src/role_builder/services/chunker.py` :
```python
"""Chunking d'un transcript pivot en fenêtres avec overlap, timestamps préservés.

Stratégie MVP : taille fixe par tokens approximés (1 token ≈ 4 caractères),
frontières de phrases (segments) respectées, overlap configurable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranscriptChunk:
    text: str
    start_s: float
    end_s: float
    word_count: int  # approximation tokens


def _approx_tokens(text: str) -> int:
    """Approximation : 1 token ≈ 4 caractères en français. Précis ~20%."""
    return max(1, len(text) // 4)


def chunk_transcript(
    transcript: dict,
    *,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[TranscriptChunk]:
    """Découpe un PivotTranscript en chunks avec overlap.

    Spec : docs/specs/05-corpus-indexing.md § Stratégie de chunking.

    Args:
        transcript: dict pivot avec key "segments" (chaque segment a start/end/text).
        target_tokens: taille cible par chunk (~500 tokens).
        overlap_tokens: backtrack en tokens entre chunks consécutifs.

    Returns:
        Liste de TranscriptChunk, chacun avec text concaténé + start_s/end_s.
    """
    segments_raw = transcript.get("segments", [])
    if not segments_raw:
        return []

    sentences = [
        {
            "text": str(seg["text"]).strip(),
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "tokens": _approx_tokens(str(seg["text"])),
        }
        for seg in segments_raw
        if str(seg.get("text", "")).strip()
    ]
    if not sentences:
        return []

    chunks: list[TranscriptChunk] = []
    i = 0
    n = len(sentences)
    while i < n:
        # Accumuler des phrases jusqu'à atteindre target_tokens.
        buf_text: list[str] = []
        buf_tokens = 0
        start_s = sentences[i]["start"]
        end_s = sentences[i]["end"]
        j = i
        while j < n and buf_tokens < target_tokens:
            buf_text.append(sentences[j]["text"])
            buf_tokens += sentences[j]["tokens"]
            end_s = sentences[j]["end"]
            j += 1

        chunks.append(TranscriptChunk(
            text=" ".join(buf_text),
            start_s=start_s,
            end_s=end_s,
            word_count=buf_tokens,
        ))

        if j >= n:
            break

        # Backtrack pour overlap : reculer i de manière à inclure ~overlap_tokens.
        if overlap_tokens <= 0:
            i = j
        else:
            backtrack = 0
            k = j
            while k > i + 1 and backtrack < overlap_tokens:
                k -= 1
                backtrack += sentences[k]["tokens"]
            i = max(k, i + 1)

    return chunks
```

Run : tests verts.

- [ ] **Step 3: Commit**

```bash
git add backend/src/role_builder/services/chunker.py backend/tests/test_chunker.py
git commit -m "$(cat <<'EOF'
feat(backend): chunker (transcripts pivot → chunks 500 tokens overlap 50, timestamps préservés)

Approximation tokens = chars // 4. Frontières de phrases respectées
(jamais coupé en milieu de segment). Overlap backtrack en tokens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase C — Embedder + chunking_worker + câblage Sprint 3

## Task C1 : `services/embedder.py` (TDD léger)

**Files:**
- Create: `backend/src/role_builder/services/embedder.py`
- Create: `backend/tests/test_embedder.py`

Wrapper mince autour de `agflow_client.invoke_embeddings`. Le batching est déjà dans `AgflowClient` ; ce module sert juste de point d'extension futur (ex: cache local, normalisation).

- [ ] **Step 1: Tests + impl**

```python
# backend/tests/test_embedder.py
import pytest


@pytest.mark.asyncio
async def test_embed_texts_delegates_to_agflow_client(stubbed_env, monkeypatch) -> None:
    from role_builder.services import embedder, agflow_client

    captured_texts: list[list[str]] = []

    class _StubClient:
        async def invoke_embeddings(self, texts):
            captured_texts.append(texts)
            return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(agflow_client, "get_agflow_client", lambda: _StubClient())

    vectors = await embedder.embed_texts(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 1024 for v in vectors)
    assert captured_texts == [["a", "b", "c"]]
```

```python
# backend/src/role_builder/services/embedder.py
"""Wrapper minimaliste autour de AgflowClient pour les embeddings de chunks."""
from __future__ import annotations

from role_builder.services.agflow_client import get_agflow_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed une liste de textes. Délègue au singleton AgflowClient."""
    if not texts:
        return []
    client = get_agflow_client()
    return await client.invoke_embeddings(texts)
```

Commit : `feat(backend): embedder (wrapper agflow_client.invoke_embeddings)`

## Task C2 : `db_helpers/chunking_jobs.py` + `corpus_chunks.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/chunking_jobs.py`
- Create: `backend/src/role_builder/db_helpers/corpus_chunks.py`
- Create: `backend/tests/test_db_helpers_chunking_jobs.py`
- Create: `backend/tests/test_db_helpers_corpus_chunks.py`

### `chunking_jobs.py`

Signatures :
```python
async def insert_job(
    *, source_item_id, role_project_id, tenant_id, transcript_s3_key,
    pool,
) -> UUID: ...

async def claim_next_pending_job(worker_id: str, *, pool) -> dict | None:
    """SELECT FOR UPDATE SKIP LOCKED + UPDATE status='claimed' atomic."""

async def mark_processing(job_id, *, pool) -> None: ...
async def mark_done(job_id, *, chunks_produced: int, pool) -> None: ...
async def mark_failed(job_id, error: str, *, pool) -> None: ...
async def list_jobs(*, status=None, limit=50, pool) -> list[dict]: ...
```

Tests : 4-5 tests TDD asyncpg stub pattern Sprint 1/2/3.

### `corpus_chunks.py`

Signatures :
```python
async def insert_chunks_bulk(
    chunks: list[dict],  # chaque chunk = {chunk_index, start_s, end_s, text, embedding}
    *,
    source_item_id, role_project_id, tenant_id,
    pool,
) -> int: ...

async def semantic_search(
    role_project_id: UUID, query_embedding: list[float],
    *, limit: int = 20, min_similarity: float = 0.0,
    pool,
) -> list[dict]:
    """SELECT ... ORDER BY embedding <=> $1 LIMIT $n. Retourne chunk_id, source_item_id,
    text, start_s, end_s, similarity (= 1 - cosine_distance)."""

async def list_by_item(source_item_id, *, limit=50, offset=0, pool) -> list[dict]: ...

async def count_by_project(role_project_id, *, pool) -> int: ...
```

Tests : 4-5 tests. Pour `semantic_search`, le mock retourne des rows avec `distance` calculé manuellement, vérifie que le SQL contient `<=>` et que le tri est respecté.

Commit : `feat(backend): db_helpers chunking_jobs + corpus_chunks (insert_bulk + semantic_search pgvector <=>)`

## Task C3 : `services/chunking_worker.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/services/chunking_worker.py`
- Create: `backend/tests/test_chunking_worker.py`

Signature :
```python
class ChunkingWorker:
    def __init__(self, *, pool, worker_id: str = "chunking-worker-1") -> None: ...

    async def process_one_job(self, job: dict) -> None:
        """Download transcript MinIO, chunk, embed, insert pgvector, update statuses."""

    async def run_loop(self, stop_event: asyncio.Event, *, poll_interval_s: float = 2.0) -> None:
        """Boucle pull/process avec timeout entre pulls vides."""
```

`process_one_job` orchestre :
1. `mark_processing(job["id"], pool=...)`
2. Download transcript JSON depuis MinIO via `MinioWrapper.download_bytes("corpus-transcripts", job["transcript_s3_key"])`
3. Parse JSON → call `chunker.chunk_transcript(...)`
4. Si chunks vides : `mark_done(chunks_produced=0)` et `update_source_item_status(... status="indexed")` (déjà fait Sprint 2 helper).
5. Sinon : `embedder.embed_texts(...)` → liste de vecteurs.
6. Build chunks dict avec embedding aplati.
7. `db_helpers.corpus_chunks.insert_chunks_bulk(...)`
8. `mark_done(chunks_produced=N)` + update `source_items.status='indexed'`.
9. En cas d'exception : `mark_failed(error=str(exc))`.

Tests (~4) : monkeypatch `MinioWrapper.download_bytes`, `chunker.chunk_transcript`, `embedder.embed_texts`, db_helpers. Vérifier l'enchaînement et la gestion d'erreur.

Commit : `feat(backend): chunking_worker (poll → download transcript → chunk → embed → insert pgvector)`

## Task C4 : Câblage Sprint 3 (transcription-worker insère chunking_job)

**Files:**
- Modify: `docker/transcription-worker/worker/db.py` (+ `insert_chunking_job` helper)
- Modify: `docker/transcription-worker/worker/main.py` (call après `mark_job_done`)
- Modify: `docker/transcription-worker/tests/test_db.py` (+ test)
- Modify: `docker/transcription-worker/tests/test_main_loop.py` (+ test)

### Ajouter à `worker/db.py`

```python
async def insert_chunking_job(
    *,
    source_item_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    transcript_s3_key: str,
    pool: asyncpg.Pool,
) -> UUID:
    """Crée un chunking_job après que la transcription est uploadée."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO chunking_jobs
                (source_item_id, role_project_id, tenant_id, transcript_s3_key, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id
            """,
            source_item_id, role_project_id, tenant_id, transcript_s3_key,
        )
```

### Modifier `worker/main.py` `process_job`

Après `mark_job_done` et avant le cleanup, ajouter :
```python
# Récupérer le role_project_id depuis source_item → source → role_project
async with pool.acquire() as conn:
    row = await conn.fetchrow(
        """
        SELECT s.role_project_id, si.tenant_id
        FROM source_items si
        JOIN sources s ON s.id = si.source_id
        WHERE si.id = $1
        """,
        job["source_item_id"],
    )
if row is not None:
    await db.insert_chunking_job(
        source_item_id=job["source_item_id"],
        role_project_id=row["role_project_id"],
        tenant_id=row["tenant_id"],
        transcript_s3_key=transcript_s3_key,
        pool=pool,
    )
```

Tests : 1 test pour `insert_chunking_job` (asyncpg stub), 1 test pour `process_job` qui vérifie l'enchaînement.

Commit : `feat(workers): transcription-worker crée un chunking_job après mark_done`

## Task C5 : Intégration lifespan FastAPI

**Files:**
- Modify: `backend/src/role_builder/main.py`
- Modify: `backend/tests/conftest.py` (`disable_chunking_worker=True`)

Pattern strictement identique à `disable_orchestrator` Sprint 2 et `disable_worker_manager` Sprint 3 :
```python
chunking_task = None
if not settings.disable_chunking_worker:
    chunking_worker = ChunkingWorker(pool=db_pool.pool)
    chunking_task = asyncio.create_task(chunking_worker.run_loop(stop_event))
# yield
# at shutdown : stop_event.set() + await chunking_task
```

Conftest : `monkeypatch.setattr(_settings, "disable_chunking_worker", True, raising=False)` dans la fixture `client`.

Run : `cd backend && uv run pytest -v` → tous tests verts (~95+).

Commit : `feat(backend): chunking_worker démarré dans lifespan (gardé par DISABLE_CHUNKING_WORKER)`

---

# Phase D — Routes API corpus

## Task D1 : Schemas Pydantic

**Files:**
- Create: `backend/src/role_builder/schemas/corpus.py`

```python
"""DTOs Pydantic pour les routes corpus."""
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class ChunkOut(BaseModel):
    chunk_id: UUID
    source_item_id: UUID
    source_title: str | None = None
    text: str
    start_s: float | None = None
    end_s: float | None = None


class SearchResultOut(ChunkOut):
    similarity: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]


class TranscriptResponse(BaseModel):
    item_id: UUID
    s3_key: str
    pivot: dict  # transcript pivot brut


class AudioUrlResponse(BaseModel):
    item_id: UUID
    url: str
    expires_in_s: int
```

Commit : `feat(backend): schemas corpus (ChunkOut, SearchResponse, TranscriptResponse, AudioUrlResponse)`

## Task D2 : `routes/corpus.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/routes/corpus.py`
- Create: `backend/tests/test_corpus_route.py`

4 endpoints (tous protégés par `Depends(get_current_user)`) :

```python
@router.get("/role-projects/{project_id}/corpus/search")
async def search_corpus(
    project_id: UUID,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(le=100)] = 20,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SearchResponse:
    """Recherche sémantique : embed la query → ANN search pgvector."""

@router.get("/role-projects/{project_id}/corpus/chunks")
async def list_chunks(
    project_id: UUID,
    source_item_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[ChunkOut]: ...

@router.get("/role-projects/{project_id}/corpus/items/{item_id}/transcript")
async def get_transcript(
    project_id: UUID, item_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TranscriptResponse: ...

@router.get("/role-projects/{project_id}/corpus/items/{item_id}/audio-url")
async def get_audio_url(
    project_id: UUID, item_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AudioUrlResponse: ...
```

Implémentations :
- `search_corpus` : `embedder.embed_texts([q])` → `corpus_chunks.semantic_search(...)` → mapping vers `SearchResultOut`.
- `list_chunks` : `corpus_chunks.list_by_item(...)` ou liste tous via une fonction séparée.
- `get_transcript` : `db_helpers.source_items.get(item_id)` pour récupérer `transcript_s3_key`, puis `MinioWrapper.download_bytes("corpus-transcripts", key)` → parse JSON.
- `get_audio_url` : `db_helpers.source_items.get(item_id)` pour `audio_s3_key`, puis `MinioWrapper.presigned_get_url("corpus-audio", key, expires_seconds=900)`.

Tests TDD (~5-6 tests) : monkeypatch embedder + db_helpers + MinioWrapper. Vérifier les 4 endpoints + les filtres + l'auth (avec `disable_auth=True` du conftest).

Commit : `feat(backend): routes/corpus (search + chunks + transcript + audio-url, 4 endpoints protégés)`

## Task D3 : Câbler dans main.py + RAG helper `corpus_search.py`

**Files:**
- Modify: `backend/src/role_builder/main.py` (`include_router(corpus.router, prefix="/api")`)
- Create: `backend/src/role_builder/services/corpus_search.py` (helper réutilisable Sprint 5)

`corpus_search.py` :
```python
"""High-level corpus search helpers, réutilisable par le pipeline de synthèse Sprint 5."""
from __future__ import annotations
from uuid import UUID

from role_builder.services import embedder
from role_builder.db_helpers import corpus_chunks


async def find_relevant_chunks(
    project_id: UUID, query: str,
    *, top_k: int = 10, min_similarity: float = 0.5, pool,
) -> list[dict]:
    """Find top-k chunks pertinents pour une query. Utilisé par le RAG du document_writer (Sprint 5)."""
    if not query.strip():
        return []
    [query_emb] = await embedder.embed_texts([query])
    return await corpus_chunks.semantic_search(
        role_project_id=project_id,
        query_embedding=query_emb,
        limit=top_k,
        min_similarity=min_similarity,
        pool=pool,
    )
```

Test : 1 test rapide `test_corpus_search.py` qui mock embedder + corpus_chunks.

Commit : `feat(backend): corpus_search helper find_relevant_chunks (RAG réutilisable Sprint 5) + cablage routes/corpus dans main`

---

# Phase E — Frontend onglet Corpus

## Task E1 : Types + client API typé (1 commit)

**Files:**
- Modify: `frontend/src/lib/types.ts` (+ `Chunk`, `SearchResult`, `Transcript`)
- Create: `frontend/src/lib/api/corpus.ts`
- Create: `frontend/src/__tests__/corpus-api.test.ts`

`types.ts` ajouts :
```typescript
export interface Chunk {
  chunk_id: string;
  source_item_id: string;
  source_title: string | null;
  text: string;
  start_s: number | null;
  end_s: number | null;
}

export interface SearchResult extends Chunk {
  similarity: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface AudioUrlResponse {
  item_id: string;
  url: string;
  expires_in_s: number;
}
```

`corpus.ts` :
```typescript
import { api } from './client';
import type { Chunk, SearchResponse, AudioUrlResponse } from '../types';

export async function searchCorpus(projectId: string, q: string, limit = 20): Promise<SearchResponse> {
  return api(`/api/role-projects/${projectId}/corpus/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export async function listChunks(projectId: string, opts: { source_item_id?: string; limit?: number; offset?: number } = {}): Promise<Chunk[]> {
  const qs = new URLSearchParams();
  if (opts.source_item_id) qs.set('source_item_id', opts.source_item_id);
  if (opts.limit !== undefined) qs.set('limit', String(opts.limit));
  if (opts.offset !== undefined) qs.set('offset', String(opts.offset));
  return api(`/api/role-projects/${projectId}/corpus/chunks${qs.toString() ? '?' + qs : ''}`);
}

export async function getAudioUrl(projectId: string, itemId: string): Promise<AudioUrlResponse> {
  return api(`/api/role-projects/${projectId}/corpus/items/${itemId}/audio-url`);
}
```

Tests Vitest (~3) : mocks `globalThis.fetch`, vérifie URLs construites + body parsing.

Commit : `feat(frontend): clients API corpus (search + listChunks + getAudioUrl) + types`

## Task E2 : Page Corpus + SearchBar + SearchResults (1 commit)

**Files:**
- Create: `frontend/src/app/projects/[id]/corpus/page.tsx`
- Create: `frontend/src/app/projects/[id]/corpus/SearchBar.tsx`
- Create: `frontend/src/app/projects/[id]/corpus/SearchResults.tsx`

Pattern Server Component pour la page principale + Client Components pour le formulaire de recherche.

`page.tsx` minimal (Server Component) qui rend un Client wrapper pour la recherche interactive :
```tsx
import { CorpusSearchClient } from './CorpusSearchClient';

export default function CorpusPage({ params }: { params: { id: string } }) {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Corpus</h1>
      <p style={{ color: '#666' }}>Recherche sémantique dans le corpus indexé.</p>
      <CorpusSearchClient projectId={params.id} />
    </main>
  );
}
```

`CorpusSearchClient.tsx` (Client Component) :
- `useState` pour la query
- Appel `searchCorpus(...)` au submit
- Affiche `<SearchResults results={...} />`
- `<SearchBar onSearch={(q) => setQuery(q)} />`

`SearchBar.tsx` : input + bouton, debounce optionnel.
`SearchResults.tsx` : map sur les results, render `<ChunkCard>` pour chaque.

Commit : `feat(frontend): page Corpus avec SearchBar + SearchResults (recherche sémantique)`

## Task E3 : ChunkCard (1 commit)

**Files:**
- Create: `frontend/src/app/projects/[id]/corpus/ChunkCard.tsx`

Composant qui affiche un chunk :
- Titre : `source_title` (ou fallback)
- Timestamp : format `mm:ss - mm:ss`
- Texte avec mise en valeur
- Bouton "Lire l'audio" (si présent) → fetch `/audio-url` → `<audio>` lecture

```tsx
'use client';

import { useState } from 'react';
import { getAudioUrl } from '@/lib/api/corpus';
import type { Chunk } from '@/lib/types';

interface Props {
  projectId: string;
  chunk: Chunk;
  similarity?: number;
}

function formatTimestamp(s: number | null): string {
  if (s == null) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function ChunkCard({ projectId, chunk, similarity }: Props) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  async function handlePlay() {
    const resp = await getAudioUrl(projectId, chunk.source_item_id);
    setAudioUrl(resp.url);
  }

  return (
    <article style={{ border: '1px solid #eaeaea', borderRadius: 8, padding: '1rem', marginBottom: '1rem' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.5rem' }}>
        <strong>{chunk.source_title ?? 'Sans titre'}</strong>
        <span style={{ color: '#888', fontSize: '0.85rem' }}>
          {formatTimestamp(chunk.start_s)} → {formatTimestamp(chunk.end_s)}
          {similarity !== undefined && ` · ${Math.round(similarity * 100)}%`}
        </span>
      </header>
      <p style={{ marginBottom: '0.5rem' }}>{chunk.text}</p>
      {audioUrl ? (
        <audio controls src={audioUrl} style={{ width: '100%' }} />
      ) : (
        <button onClick={handlePlay} style={{ fontSize: '0.85rem' }}>
          Lire l'audio
        </button>
      )}
    </article>
  );
}
```

Commit : `feat(frontend): ChunkCard (timestamps + lecture audio via presigned URL)`

## Task E4 : SourcesList + TranscriptViewer (1 commit, optionnel MVP)

**Files:**
- Create: `frontend/src/app/projects/[id]/corpus/SourcesList.tsx`
- Create: `frontend/src/app/projects/[id]/corpus/TranscriptViewer.tsx`

`SourcesList.tsx` : liste les `source_items` indexed du projet, click → ouvre `TranscriptViewer`.

`TranscriptViewer.tsx` : récupère via `/items/{id}/transcript`, affiche les segments avec leurs timestamps, chaque timestamp est un lien qui appelle `/audio-url` et `seek` sur l'audio joué.

Commit : `feat(frontend): SourcesList + TranscriptViewer (browse par source + transcript complet)`

## Task E5 : Vérif vitest + typecheck + lint (pas de commit sauf fix)

Run : `cd frontend && npm test && npm run typecheck && npm run lint` → tout vert.

Si fix nécessaire : commit `chore(frontend): ajustements lint Sprint 4`.

---

# Phase F — Tag + open-decisions

## Task F1 : MAJ `12-open-decisions.md`

Acter dans `Sprint 4` :
- Mistral via `agflow_client` direct (décision #1 toujours ouverte mais déférée).
- `mistral-embed` 1024 dim retenu.
- Worker chunking interne backend (asyncio task, pas un container).
- Worker transcription Sprint 3 modifié pour insérer chunking_job (Sprint 3 G2 bullet point clos).
- Index pgvector ivfflat lists=100 retenu (HNSW si volume > 100k chunks Phase 2).

Reportés :
- Re-chunking d'un transcript existant (endpoint admin "rebuild corpus") → Phase 2.
- Déduplication de chunks similaires entre vidéos → Phase 2.
- Streaming d'indexation (progression chunk par chunk côté UI) → Phase 2.

Commit : `docs(specs): décisions Sprint 4 actées`

## Task F2 : Vérification globale + tag

Run :
- `cd backend && uv run pytest -v` → ~95+ verts, ruff clean
- `cd docker/transcription-worker && uv run pytest -v` → 35+ verts (33 + 2 nouveaux)
- `cd docker/scrapers/youtube && uv run pytest -v` → 10 verts (inchangé)
- `cd frontend && npm test && npm run typecheck && npm run lint` → tout vert (15+ verts + nouveaux corpus tests)

```bash
git tag -a v0.4.0-sprint-4 -m "Sprint 4 — Corpus indexing terminé

Pipeline complet : transcript pivot → chunks 500 tokens overlap 50 →
embeddings Mistral 1024 dim → corpus_chunks pgvector. Recherche
sémantique exposée via /api/role-projects/{id}/corpus/search avec
ANN cosine ivfflat. Onglet Corpus avec SearchBar + SearchResults
+ ChunkCard (lecture audio via presigned URL MinIO).

Câblage Sprint 3 → 4 : transcription-worker insère chunking_job
après mark_done (le trou noté en open-decisions Sprint 3 est comblé).

Décisions actées :
- Abstraction agflow_client (Mistral direct MVP, swap ag.flow Phase 2)
- mistral-embed 1024 dim
- Worker chunking interne backend (asyncio task)
- ivfflat lists=100 (HNSW Phase 2 si volume > 100k)
"
```

---

## Récapitulatif estimé

~24 commits :
- A : 3 (agflow_client, settings, env)
- B : 1 (chunker)
- C : 5 (embedder, db_helpers, chunking_worker, câblage Sprint 3, lifespan)
- D : 3 (schemas, routes, corpus_search helper)
- E : 4 (types/api, page+search, ChunkCard, SourcesList/TranscriptViewer)
- F : 2 (open-decisions, tag)
+ ~6 commits potentiels de tests bug fixes selon retours subagent.

Tag final : `v0.4.0-sprint-4`.
