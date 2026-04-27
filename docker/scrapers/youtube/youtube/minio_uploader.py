"""MinIO upload helper for the YouTube scraper container."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from minio import Minio


def _build_client(cfg: dict[str, Any]) -> Minio:
    """Construct a Minio client from the task's output config."""
    parsed = urlparse(cfg["endpoint"])
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=secure,
    )


def upload_audio(local_path: Path, cfg: dict[str, Any], item_id: str) -> str:
    """Upload an MP3 audio to MinIO and return its s3_key.

    Key layout : {prefix}{item_id}.mp3 (slash inserted between prefix and item_id if missing).
    """
    client = _build_client(cfg)
    prefix = cfg["prefix"]
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    key = f"{prefix}{item_id}.mp3"

    client.fput_object(
        cfg["bucket"],
        key,
        str(local_path),
        content_type="audio/mpeg",
    )
    return key
