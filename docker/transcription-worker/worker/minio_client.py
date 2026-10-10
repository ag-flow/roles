"""Wrapper MinIO pour le worker (upload du transcript JSON uniquement).

Bucket (cf. spec 04 § Process d'un job) :
- corpus-transcripts : output transcript JSON (format pivot) uploadé via put_object

L'audio d'entrée ne transite plus par MinIO (cf. migration 0012 / lot "relais
audio volume local") : le scraper l'écrit directement sur un volume local
partagé, et `worker.main.process_job` le lit sur disque via `job["audio_path"]`.
Le bucket `corpus-audio` et le téléchargement associé n'ont donc plus d'objet.
"""
from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

from minio import Minio

from worker.config import settings

TRANSCRIPT_BUCKET = "corpus-transcripts"

_client: Minio | None = None


def _build_minio_client() -> Minio:
    """Construit un client minio à partir des settings (endpoint http(s)://host:port)."""
    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = _build_minio_client()
    return _client


def upload_transcript(s3_key: str, payload: dict[str, Any]) -> None:
    """Upload le pivot JSON dans `corpus-transcripts` à la clef `s3_key`."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    buf = BytesIO(body)
    _get_client().put_object(
        TRANSCRIPT_BUCKET,
        s3_key,
        buf,
        len(body),
        content_type="application/json",
    )
