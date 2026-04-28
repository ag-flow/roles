"""DTOs Pydantic pour les routes corpus (Sprint 4)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ChunkOut(BaseModel):
    """Représentation publique d'un chunk indexé."""

    chunk_id: UUID
    source_item_id: UUID
    source_title: str | None = None
    text: str
    start_s: float | None = None
    end_s: float | None = None


class SearchResultOut(ChunkOut):
    """Chunk + score de similarité retourné par la recherche sémantique."""

    similarity: float


class SearchResponse(BaseModel):
    """Réponse de ``GET /corpus/search``."""

    query: str
    results: list[SearchResultOut]


class TranscriptResponse(BaseModel):
    """Réponse de ``GET /corpus/items/{item_id}/transcript``.

    ``pivot`` est le JSON pivot brut tel que stocké dans MinIO.
    """

    item_id: UUID
    s3_key: str
    pivot: dict[str, Any]


class AudioUrlResponse(BaseModel):
    """Réponse de ``GET /corpus/items/{item_id}/audio-url`` (URL signée MinIO)."""

    item_id: UUID
    url: str
    expires_in_s: int
