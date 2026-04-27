"""Wrappers MinIO pour le worker (download audio + upload transcript JSON).

Buckets (cf. spec 04 § Process d'un job) :
- corpus-audio       : input audio (.mp3, .wav…) téléchargé via fget_object
- corpus-transcripts : output transcript JSON (format pivot) uploadé via put_object
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from minio import Minio

from worker.config import settings

AUDIO_BUCKET = "corpus-audio"
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


def download_audio(s3_key: str, dest_path: Path) -> None:
    """Télécharge l'objet `s3_key` du bucket `corpus-audio` vers `dest_path` local."""
    _get_client().fget_object(AUDIO_BUCKET, s3_key, str(dest_path))


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
