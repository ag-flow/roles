"""Endpoints REST corpus (Sprint 4 — recherche sémantique + accès artefacts).

Routes :
- GET /api/role-projects/{project_id}/corpus/search?q=...
- GET /api/role-projects/{project_id}/corpus/chunks
- GET /api/role-projects/{project_id}/corpus/items/{item_id}/transcript
- GET /api/role-projects/{project_id}/corpus/items/{item_id}/audio-url

Tous protégés par ``Depends(get_current_user)`` (bypass via
``settings.disable_auth=True`` en tests/dev).
"""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import corpus_chunks as chunks_helper
from role_builder.db_helpers import source_items as items_helper
from role_builder.schemas.corpus import (
    AudioUrlResponse,
    ChunkOut,
    SearchResponse,
    SearchResultOut,
    TranscriptResponse,
)
from role_builder.services import embedder
from role_builder.services import minio_client as minio_module

log = structlog.get_logger(__name__)

router = APIRouter()

_TRANSCRIPT_BUCKET = "corpus-transcripts"
_AUDIO_BUCKET = "corpus-audio"
_AUDIO_URL_TTL_S = 900


@router.get(
    "/role-projects/{project_id}/corpus/search",
    response_model=SearchResponse,
)
async def search_corpus(
    project_id: UUID,
    q: Annotated[str, Query(min_length=1)],
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001 — auth gate
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    min_similarity: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
) -> SearchResponse:
    """Recherche sémantique : embed la query → ANN search pgvector.

    TODO multi-tenant : vérifier que ``project_id`` appartient à
    ``user.user_id`` via ``role_projects.get_user_id_for_project``.
    """
    pool = db_pool.pool
    [query_embedding] = await embedder.embed_texts([q])
    rows = await chunks_helper.semantic_search(
        role_project_id=project_id,
        query_embedding=query_embedding,
        limit=limit,
        min_similarity=min_similarity,
        pool=pool,
    )
    results = [SearchResultOut(**_pick_search_fields(r)) for r in rows]
    return SearchResponse(query=q, results=results)


@router.get(
    "/role-projects/{project_id}/corpus/chunks",
    response_model=list[ChunkOut],
)
async def list_chunks(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001 — auth gate
    source_item_id: UUID | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ChunkOut]:
    """Liste chunks ; filtrée par ``source_item_id`` ou tout le projet sinon."""
    pool = db_pool.pool
    if source_item_id is not None:
        rows = await chunks_helper.list_by_item(
            source_item_id, limit=limit, offset=offset, pool=pool
        )
    else:
        rows = await chunks_helper.list_by_project(
            project_id, limit=limit, offset=offset, pool=pool
        )
    return [ChunkOut(**_pick_chunk_fields(r)) for r in rows]


@router.get(
    "/role-projects/{project_id}/corpus/items/{item_id}/transcript",
    response_model=TranscriptResponse,
)
async def get_transcript(
    project_id: UUID,  # noqa: ARG001 — scoping (TODO multi-tenant)
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001 — auth gate
) -> TranscriptResponse:
    """Récupère le transcript pivot JSON d'un source_item depuis MinIO."""
    pool = db_pool.pool
    item = await items_helper.get_by_id(item_id, pool=pool)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

    transcript_key = item.get("transcript_s3_key")
    if not transcript_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="transcript not available yet for this item",
        )

    payload = minio_module.minio_client.download_bytes(_TRANSCRIPT_BUCKET, transcript_key)
    try:
        pivot = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.error(
            "corpus.transcript_decode_error",
            item_id=str(item_id),
            transcript_key=transcript_key,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="transcript payload is not valid JSON",
        ) from exc

    return TranscriptResponse(item_id=item_id, s3_key=transcript_key, pivot=pivot)


@router.get(
    "/role-projects/{project_id}/corpus/items/{item_id}/audio-url",
    response_model=AudioUrlResponse,
)
async def get_audio_url(
    project_id: UUID,  # noqa: ARG001 — scoping (TODO multi-tenant)
    item_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001 — auth gate
) -> AudioUrlResponse:
    """Génère une presigned URL GET (15 min) pour l'audio d'un source_item."""
    pool = db_pool.pool
    item = await items_helper.get_by_id(item_id, pool=pool)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

    audio_key = item.get("audio_s3_key")
    if not audio_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="audio not available yet for this item",
        )

    url = minio_module.minio_client.presigned_get_url(
        _AUDIO_BUCKET, audio_key, expires_seconds=_AUDIO_URL_TTL_S
    )
    return AudioUrlResponse(item_id=item_id, url=url, expires_in_s=_AUDIO_URL_TTL_S)


def _pick_chunk_fields(row: dict) -> dict:
    """Adapte un row DB → kwargs ChunkOut (chunk_id ← id si besoin)."""
    chunk_id = row.get("chunk_id") or row.get("id")
    return {
        "chunk_id": chunk_id,
        "source_item_id": row.get("source_item_id"),
        "source_title": row.get("source_title"),
        "text": row.get("text", ""),
        "start_s": row.get("start_s"),
        "end_s": row.get("end_s"),
    }


def _pick_search_fields(row: dict) -> dict:
    """Adapte un row semantic_search → kwargs SearchResultOut."""
    base = _pick_chunk_fields(row)
    base["similarity"] = float(row.get("similarity") or 0.0)
    return base
