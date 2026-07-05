"""MinIO client wrapper for object storage operations."""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from typing import Protocol
from urllib.parse import urlparse

from minio import Minio

from role_builder.config import settings


class _MinioLike(Protocol):
    def bucket_exists(self, bucket: str) -> bool: ...
    def make_bucket(self, bucket: str) -> None: ...
    def put_object(
        self,
        bucket: str,
        key: str,
        data: BytesIO,
        length: int,
        content_type: str | None = ...,
    ) -> None: ...
    def get_object(self, bucket: str, key: str) -> object: ...
    def presigned_get_object(self, bucket: str, key: str, expires: timedelta) -> str: ...
    def presigned_put_object(self, bucket: str, key: str, expires: timedelta) -> str: ...
    def stat_object(self, bucket: str, key: str) -> object: ...
    def remove_object(self, bucket: str, key: str) -> None: ...


def _build_minio_client() -> Minio:
    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


class MinioWrapper:
    """Thin wrapper around `minio.Minio` exposing the operations Role Builder needs."""

    def __init__(self, client: _MinioLike | None = None) -> None:
        self._client: _MinioLike = client or _build_minio_client()

    def ensure_bucket(self, bucket: str) -> None:
        """Create the bucket if it doesn't already exist."""
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        payload: bytes,
        content_type: str | None = None,
    ) -> None:
        """Upload a byte payload at `bucket/key`."""
        buf = BytesIO(payload)
        self._client.put_object(bucket, key, buf, len(payload), content_type=content_type)

    def download_bytes(self, bucket: str, key: str) -> bytes:
        """Download an object's bytes."""
        resp = self._client.get_object(bucket, key)
        try:
            return resp.read()  # type: ignore[no-any-return]
        finally:
            close = getattr(resp, "close", None)
            release = getattr(resp, "release_conn", None)
            if callable(close):
                close()
            if callable(release):
                release()

    def presigned_get_url(
        self,
        bucket: str,
        key: str,
        *,
        expires_seconds: int = 900,
    ) -> str:
        """Generate a presigned GET URL valid for `expires_seconds`."""
        return self._client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=expires_seconds)
        )

    def presigned_put_url(
        self,
        bucket: str,
        key: str,
        *,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate a presigned PUT URL valid for `expires_seconds`."""
        return self._client.presigned_put_object(
            bucket, key, expires=timedelta(seconds=expires_seconds)
        )

    def object_exists(self, bucket: str, key: str) -> bool:
        """True si l'objet existe (stat) ; les autres erreurs S3 remontent."""
        from minio.error import S3Error

        try:
            self._client.stat_object(bucket, key)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject"):
                return False
            raise
        return True

    def remove_object(self, bucket: str, key: str) -> None:
        """Delete an object; no-op if it does not exist (sémantique S3)."""
        self._client.remove_object(bucket, key)


minio_client = MinioWrapper()
