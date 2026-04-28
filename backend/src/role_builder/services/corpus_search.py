"""High-level corpus search helpers, réutilisable par le pipeline de synthèse Sprint 5.

``find_relevant_chunks`` est l'entrée principale du RAG : elle prend une
query texte, l'embed via :mod:`embedder`, puis interroge ``corpus_chunks``
en recherche sémantique (pgvector). Le helper est volontairement mince
pour que le ``document_writer`` Sprint 5 puisse l'appeler sans logique
métier supplémentaire.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from role_builder.db_helpers import corpus_chunks
from role_builder.services import embedder


async def find_relevant_chunks(
    project_id: UUID,
    query: str,
    *,
    top_k: int = 10,
    min_similarity: float = 0.5,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """Find top-k chunks pertinents pour une ``query``.

    - Query vide / blanche → ``[]`` sans appel réseau ni SQL.
    - Sinon : embed unique → ``corpus_chunks.semantic_search`` filtré
      par ``min_similarity`` (cosine, similarity = 1 - distance).

    Réutilisé par le pipeline RAG du ``document_writer`` Sprint 5.
    """
    if not query.strip():
        return []
    [query_embedding] = await embedder.embed_texts([query])
    return await corpus_chunks.semantic_search(
        role_project_id=project_id,
        query_embedding=query_embedding,
        limit=top_k,
        min_similarity=min_similarity,
        pool=pool,
    )
