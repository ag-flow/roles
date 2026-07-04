> ⚠️ **OBSOLÈTE — Refonte V2 (2026-07-04).** Chunking/embeddings/pgvector supprimés — la recherche corpus est le métier d'agflow-rag sur docflow.
> Voir `docs/specs/OBSOLETE.md` et `docs/specs/v2/00-fondations-v2.md`. Conservé pour référence historique uniquement — ne plus implémenter.

# 05 — Corpus indexing : chunking, embeddings, pgvector

> Sprint 4 : indexation. À l'issue de ce sprint, les transcripts sont
> découpés en chunks sémantiques, embeddés, et stockés dans pgvector. La
> recherche sémantique fonctionne dans l'onglet "Corpus".

## Objectif du sprint

- Worker de chunking qui pull `chunking_jobs`
- Découpage des transcripts en chunks taille fixe + overlap
- Génération des embeddings via Mistral (par défaut) ou OpenAI
- Stockage dans `corpus_chunks` avec embedding
- Recherche sémantique exposée via API
- Onglet "Corpus" dans l'UI : exploration, recherche, lecture

## Modèle conceptuel

### Pourquoi chunker ?

Le pipeline de synthèse (sprint 5) envoie des chunks au LLM, pas des
transcripts entiers. Un transcript d'1h peut faire 10000-20000 mots, ce qui
sature le contexte. On découpe donc en unités plus petites.

### Stratégie de chunking

**Décision pour le MVP :** chunking par taille fixe avec overlap.

- Taille cible : ~500 tokens par chunk (~3000-3500 caractères en français)
- Overlap : ~50 tokens (~300 caractères)
- Découpage respectant les frontières de phrases (ne jamais couper en
  milieu de phrase)

**Raison du choix :** simple, prévisible, suffisant pour démarrer. On
pourra ajouter du chunking sémantique (par sujet) en Phase 2 si la qualité
le justifie.

### Préservation des timestamps

Chaque chunk garde `start_s` et `end_s` (premier et dernier timestamps des
mots/segments inclus). C'est essentiel pour :

- La traçabilité ("cette idée vient de la vidéo X à 12:34")
- Le rejouage audio dans l'UI
- La citation des sources dans les documents générés

## Architecture

### Worker de chunking

Service backend (pas un container séparé pour le MVP — l'opération est
légère). Tourne dans le même processus FastAPI ou comme worker asyncio
détaché.

```
backend/src/role_builder/services/
├── chunking_worker.py         # boucle de pull
├── chunker.py                 # logique de découpage
├── embedder.py                # appels d'embedding
└── corpus_search.py           # recherche sémantique
```

### Boucle principale

```python
# backend/src/role_builder/services/chunking_worker.py
"""Chunking worker that polls chunking_jobs queue."""
import asyncio
from datetime import datetime, timezone

from role_builder.db import db_pool
from role_builder.services import minio_client, chunker, embedder


WORKER_ID = "chunking-worker-1"
POLL_INTERVAL_S = 2.0


async def run_loop() -> None:
    """Pull chunking_jobs and process them."""
    while True:
        job = await claim_next_chunking_job(WORKER_ID)
        if job is None:
            await asyncio.sleep(POLL_INTERVAL_S)
            continue

        try:
            await process_job(job)
        except Exception as exc:
            await mark_job_failed(job, exc)


async def process_job(job) -> None:
    # 1. Download transcript depuis MinIO
    transcript = await minio_client.download_json("corpus-transcripts", job.transcript_s3_key)

    # 2. Chunk
    chunks = chunker.chunk_transcript(
        transcript,
        target_tokens=500,
        overlap_tokens=50,
    )

    # 3. Embed (batch)
    texts = [c.text for c in chunks]
    embeddings = await embedder.embed_batch(texts)

    # 4. Insert in DB
    async with db_pool.pool.acquire() as conn:
        async with conn.transaction():
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                await conn.execute(
                    """
                    INSERT INTO corpus_chunks
                    (source_item_id, role_project_id, tenant_id, chunk_index,
                     start_s, end_s, text, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    job.source_item_id, job.role_project_id, job.tenant_id,
                    i, chunk.start_s, chunk.end_s, chunk.text, emb,
                )

    # 5. Update source_items status
    await db.update_source_item_status(
        source_item_id=job.source_item_id,
        status="indexed",
    )

    # 6. Mark job done
    await db.update_chunking_job(job.id, status="done", chunks_produced=len(chunks))
```

## Module chunker

### Logique de découpage

```python
# backend/src/role_builder/services/chunker.py
"""Chunk a pivot transcript into overlapping windows."""
from dataclasses import dataclass


@dataclass
class TranscriptChunk:
    text: str
    start_s: float
    end_s: float
    word_count: int


def chunk_transcript(
    transcript: dict,
    *,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[TranscriptChunk]:
    """Chunk a pivot transcript into overlapping windows.

    Strategy:
      - Iterate sentence by sentence (split via segments boundary)
      - Accumulate sentences until reaching target_tokens
      - Emit chunk
      - Backtrack overlap_tokens for next chunk
    """
    # Concaténer les segments en respectant les frontières
    sentences = []
    for seg in transcript["segments"]:
        sentences.append({
            "text": seg["text"].strip(),
            "start": seg["start"],
            "end": seg["end"],
            # approximation token count (1 token ≈ 4 caractères en français)
            "tokens": max(1, len(seg["text"]) // 4),
        })

    chunks = []
    i = 0
    while i < len(sentences):
        # Accumuler des phrases jusqu'à target_tokens
        current_text = []
        current_tokens = 0
        current_start = sentences[i]["start"]
        current_end = sentences[i]["end"]
        j = i

        while j < len(sentences) and current_tokens < target_tokens:
            current_text.append(sentences[j]["text"])
            current_tokens += sentences[j]["tokens"]
            current_end = sentences[j]["end"]
            j += 1

        chunks.append(TranscriptChunk(
            text=" ".join(current_text),
            start_s=current_start,
            end_s=current_end,
            word_count=current_tokens,
        ))

        # Backtrack pour overlap
        if j >= len(sentences):
            break

        # Reculer i de manière à inclure ~overlap_tokens dans le chunk suivant
        backtrack_tokens = 0
        k = j
        while k > i and backtrack_tokens < overlap_tokens:
            k -= 1
            backtrack_tokens += sentences[k]["tokens"]
        i = max(k, i + 1)  # éviter boucle infinie

    return chunks
```

### Estimation de tokens

Pour le MVP, approximation simpliste : `tokens ≈ caractères / 4`. Précis à
~20% près pour le français. Si on a besoin de plus de précision plus tard,
utiliser `tiktoken` ou le tokenizer Mistral.

## Module embedder

### Choix du modèle d'embedding

**Décision pour le MVP :** utiliser **Mistral Embed** via les ressources LLM
ag.flow (cohérent avec le choix Mistral pour la synthèse).

**Caractéristiques de Mistral Embed :**
- Dimension : 1024 (à confirmer en implémentation)
- Multilingue
- Cohérent avec le LLM de synthèse

**Alternative possible :** OpenAI text-embedding-3-small (dim 1536) si
disponible côté ag.flow.

> **Important :** la dimension du vecteur côté `corpus_chunks.embedding`
> doit matcher celle du modèle utilisé. Si Mistral Embed renvoie 1024, le
> schéma SQL doit être `vector(1024)`. À ajuster dans la migration `0004`.

### Service d'embedding

```python
# backend/src/role_builder/services/embedder.py
"""Embed text chunks via ag.flow LLM resources."""
import httpx
from typing import Sequence

from role_builder.config import settings


class Embedder:
    """Embed texts using ag.flow's LLM resources (Mistral)."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.agflow_base_url,
            timeout=60.0,
        )

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per text."""
        # Le mécanisme d'invocation exact ag.flow pour les embeddings
        # est à finaliser (cf. § 12-open-decisions.md).
        # Schéma probable :
        resp = await self._http.post(
            "/api/admin/llm/embeddings",  # à confirmer
            json={
                "model": "mistral-embed",
                "inputs": list(texts),
                "secret_ref": settings.mistral_secret_ref,
            },
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


embedder = Embedder()
```

### Batch et pagination

Pour des transcripts longs, on peut avoir 50-200 chunks. Embedder en batch
de 32 max (limite typique des API) :

```python
async def embed_all(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed a list of texts in batches."""
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embs = await embedder.embed_batch(batch)
        embeddings.extend(batch_embs)
    return embeddings
```

## Recherche sémantique

### Endpoint API

```python
# backend/src/role_builder/routes/corpus.py
"""Corpus exploration endpoints."""
from fastapi import APIRouter, Query
from uuid import UUID

router = APIRouter(prefix="/role-projects/{project_id}/corpus", tags=["corpus"])


@router.get("/search")
async def search_corpus(
    project_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
) -> dict:
    """Semantic search over the project's corpus."""
    # 1. Embed la query
    query_emb = (await embedder.embed_batch([q]))[0]

    # 2. ANN search via pgvector
    async with db_pool.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cc.id,
                cc.source_item_id,
                cc.text,
                cc.start_s,
                cc.end_s,
                si.title,
                cc.embedding <=> $1 AS distance
            FROM corpus_chunks cc
            JOIN source_items si ON si.id = cc.source_item_id
            WHERE cc.role_project_id = $2
            ORDER BY cc.embedding <=> $1
            LIMIT $3
            """,
            query_emb, project_id, limit,
        )

    return {
        "query": q,
        "results": [
            {
                "chunk_id": str(r["id"]),
                "source_item_id": str(r["source_item_id"]),
                "source_title": r["title"],
                "text": r["text"],
                "start_s": r["start_s"],
                "end_s": r["end_s"],
                "similarity": 1 - r["distance"],
            }
            for r in rows
        ],
    }


@router.get("/chunks")
async def list_chunks(
    project_id: UUID,
    source_item_id: UUID | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    """Browse chunks (no semantic search)."""
    ...


@router.get("/items/{item_id}/transcript")
async def get_transcript(project_id: UUID, item_id: UUID) -> dict:
    """Get the full pivot transcript for browsing."""
    # Récupère le transcript depuis MinIO et le retourne
    ...
```

### Index pgvector

Référence : voir `01-data-model.md` pour le DDL. L'index ivfflat avec
`vector_cosine_ops` doit être créé après avoir inséré au moins quelques
chunks (sinon il est inefficace) :

```sql
-- À recréer périodiquement quand le volume grossit
REINDEX INDEX corpus_chunks_embedding_idx;

-- Si volume très grand, considérer HNSW (plus rapide, plus de RAM) :
CREATE INDEX corpus_chunks_embedding_hnsw_idx
    ON corpus_chunks USING hnsw (embedding vector_cosine_ops);
```

## RAG helper pour la synthèse

Le pipeline de synthèse (§ 06) aura besoin de récupérer les chunks
pertinents pour un brief de document. Exposer un helper réutilisable :

```python
# backend/src/role_builder/services/corpus_search.py
"""High-level corpus search helpers."""

async def find_relevant_chunks(
    project_id: UUID,
    query: str,
    *,
    top_k: int = 10,
    min_similarity: float = 0.5,
) -> list[dict]:
    """Find the top-k chunks most relevant to a query.

    Used by document_writer to build context for each document.
    """
    query_emb = (await embedder.embed_batch([query]))[0]

    async with db_pool.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.id, cc.text, cc.start_s, cc.end_s, cc.source_item_id,
                   1 - (cc.embedding <=> $1) AS similarity
            FROM corpus_chunks cc
            WHERE cc.role_project_id = $2
              AND 1 - (cc.embedding <=> $1) >= $3
            ORDER BY cc.embedding <=> $1
            LIMIT $4
            """,
            query_emb, project_id, min_similarity, top_k,
        )

    return [dict(r) for r in rows]
```

## UI : onglet "Corpus"

### Fonctionnalités

1. **Vue d'ensemble** : nombre de chunks, sources couvertes, durée totale
   de l'audio indexé
2. **Recherche sémantique** : barre de recherche, résultats avec extraits
   et lien vers la vidéo source au timestamp précis
3. **Browsing par source** : sélectionner une vidéo, voir tous ses chunks
   en lecture (avec timestamps cliquables)
4. **Lecture du transcript** : afficher le transcript complet d'une vidéo
   (download depuis MinIO via présigned URL)

### Composants React

```
frontend/src/app/projects/[id]/corpus/
├── page.tsx                    # vue d'ensemble + barre de recherche
├── SearchBar.tsx
├── SearchResults.tsx
├── ChunkCard.tsx
├── SourcesList.tsx
└── TranscriptViewer.tsx        # affichage chunks + timestamps cliquables
```

### Présigned URLs MinIO

Pour permettre au frontend d'accéder directement aux audios/transcripts
sans proxy backend :

```python
# backend/src/role_builder/routes/corpus.py
@router.get("/items/{item_id}/audio-url")
async def get_audio_url(project_id: UUID, item_id: UUID) -> dict:
    """Generate a presigned URL for the audio file."""
    item = await db.get_source_item(item_id)
    url = minio_client.presigned_get_url(
        bucket="corpus-audio",
        key=item.audio_s3_key,
        expires_in=900,  # 15 min
    )
    return {"url": url}
```

## Critères de fin de sprint

- [ ] Worker de chunking pull les `chunking_jobs` et produit des
      `corpus_chunks` avec embeddings
- [ ] Une vidéo passe end-to-end : audio → transcript → chunks indexés
- [ ] Recherche sémantique retourne des résultats pertinents (test manuel
      avec une query qui matche un thème connu du corpus)
- [ ] Index pgvector créé et utilisé (vérifier avec `EXPLAIN ANALYZE`)
- [ ] UI Corpus affiche les chunks et permet la recherche
- [ ] WebSocket push : un item passe à `indexed` est visible immédiatement
      dans l'UI
- [ ] Présigned URLs fonctionnent : on peut écouter l'audio depuis le
      navigateur sans login MinIO

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Confirmer la dimension exacte des embeddings Mistral et adapter le
      schéma SQL en conséquence
- [ ] Mécanisme d'invocation exact des embeddings côté ag.flow (endpoint,
      format de requête) — dépend du § 12-open-decisions.md
- [ ] Index pgvector : ivfflat ou HNSW ? Décider en fonction du volume
      attendu (HNSW plus rapide mais plus gourmand en RAM)
- [ ] Re-chunker un transcript existant si on change la stratégie : prévoir
      un endpoint admin "rebuild corpus" qui re-process tous les
      transcripts d'un projet
- [ ] Stratégie pour les chunks dupliqués entre vidéos très similaires :
      détection ? déduplication ?
- [ ] Streaming de l'indexation : pour un gros corpus (200 vidéos), on
      peut vouloir afficher la progression chunk par chunk

---

**Document précédent :** `04-transcription.md`
**Document suivant :** `06-synthesis.md`
