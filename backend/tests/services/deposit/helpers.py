"""Helpers de peuplement pour les tests du lot dépôt : requête + source +
item au statut voulu, pivot JSON minimal, MinIO fake (corpus-transcripts).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.deposit.worker import TRANSCRIPT_BUCKET
from tests.services.acquisition.conftest import TENANT_ID


def make_pivot(*segments: str, provider: str = "faster-whisper") -> dict[str, Any]:
    """Pivot JSON minimal valide (format spec 04) pour un FakeMinio."""
    return {
        "schema_version": "1.0",
        "provider": provider,
        "model": "large-v3",
        "language": "fr",
        "language_confidence": 0.98,
        "duration_s": 913.0,
        "segments": [
            {"id": i, "start": float(i), "end": float(i + 1), "text": text}
            for i, text in enumerate(segments)
        ],
        "metadata": {},
    }


class FakeMinio:
    """Sert les pivots JSON comme le ferait le bucket corpus-transcripts."""

    def __init__(self, objects: dict[str, dict[str, Any]] | None = None) -> None:
        self.objects = objects or {}
        self.requested: list[tuple[str, str]] = []

    def download_bytes(self, bucket: str, key: str) -> bytes:
        self.requested.append((bucket, key))
        if bucket != TRANSCRIPT_BUCKET or key not in self.objects:
            raise FileNotFoundError(f"{bucket}/{key}")
        return json.dumps(self.objects[key]).encode("utf-8")


async def seed_request_with_item(
    pool: asyncpg.Pool,
    *,
    request_key: str = "yt-clea-ux-2026-07-05-t3st",
    submitted_by: str = "claude-web",
    item_status: str = "transcribed",
    title: str = "Interview UX : observer avant de questionner",
    platform_item_id: str | None = None,
    selected: bool = True,
    transcript_s3_key: str | None = "t/v2/src/vid-1.json",
) -> dict[str, Any]:
    """Crée requête + source + item ; retourne les ids utiles au test."""
    source_id = await sources_helper.insert_source(
        tenant_id=TENANT_ID,
        platform="youtube",
        source_type="channel",
        url="https://youtube.com/@clea-ux",
        pool=pool,
    )
    request_id = await ar.insert_request(
        request_key=request_key,
        tenant_id=TENANT_ID,
        submitted_by=submitted_by,
        kind="scrape",
        source_id=source_id,
        mode="auto",
        filters=None,
        docflow_target=None,
        note=None,
        status="acquiring",
        pool=pool,
    )
    item_id = await insert_item(
        pool,
        source_id=source_id,
        status=item_status,
        title=title,
        platform_item_id=platform_item_id or f"vid-{uuid4().hex[:8]}",
        selected=selected,
        transcript_s3_key=transcript_s3_key,
    )
    return {
        "request_id": request_id,
        "request_key": request_key,
        "source_id": source_id,
        "item_id": item_id,
    }


async def insert_item(
    pool: asyncpg.Pool,
    *,
    source_id: UUID,
    status: str,
    title: str = "Interview UX",
    platform_item_id: str | None = None,
    selected: bool = True,
    transcript_s3_key: str | None = "t/v2/src/vid-n.json",
) -> UUID:
    """Insère un source_item directement au statut demandé."""
    async with pool.acquire() as conn:
        item_id = await conn.fetchval(
            """
            INSERT INTO source_items
                (source_id, tenant_id, platform_item_id, title, duration_s,
                 published_at, status, selected, audio_s3_key, transcript_s3_key)
            VALUES ($1, $2, $3, $4, 913,
                    '2025-11-02T00:00:00+00:00', $5, $6, 'a/vid.mp3', $7)
            RETURNING id
            """,
            source_id,
            TENANT_ID,
            platform_item_id or f"vid-{uuid4().hex[:8]}",
            title,
            status,
            selected,
            transcript_s3_key,
        )
    return item_id
