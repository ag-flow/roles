"""Tests for the MinIO client wrapper."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest


class _StubMinio:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.last_presigned: tuple[str, str, int] | None = None

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(
        self,
        bucket: str,
        key: str,
        data: BytesIO,
        length: int,
        content_type: str | None = None,
    ) -> None:
        self.objects[(bucket, key)] = data.read()

    def get_object(self, bucket: str, key: str) -> Any:
        class _Resp:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def close(self) -> None: ...
            def release_conn(self) -> None: ...

        return _Resp(self.objects[(bucket, key)])

    def presigned_get_object(self, bucket: str, key: str, expires: Any) -> str:
        self.last_presigned = (bucket, key, int(expires.total_seconds()))
        return f"http://stub/{bucket}/{key}?signed"


@pytest.fixture()
def stub_minio(stubbed_env: None) -> _StubMinio:
    return _StubMinio()


def test_ensure_bucket_creates_when_missing(stub_minio: _StubMinio) -> None:
    """ensure_bucket creates the bucket if it doesn't exist."""
    from role_builder.services.minio_client import MinioWrapper

    wrapper = MinioWrapper(client=stub_minio)
    wrapper.ensure_bucket("corpus-audio")
    assert "corpus-audio" in stub_minio.buckets


def test_ensure_bucket_noop_when_exists(stub_minio: _StubMinio) -> None:
    """ensure_bucket does nothing if the bucket already exists."""
    from role_builder.services.minio_client import MinioWrapper

    stub_minio.buckets.add("corpus-audio")
    wrapper = MinioWrapper(client=stub_minio)
    wrapper.ensure_bucket("corpus-audio")
    assert stub_minio.buckets == {"corpus-audio"}


def test_upload_bytes_round_trip(stub_minio: _StubMinio) -> None:
    """Upload then download returns the same bytes."""
    from role_builder.services.minio_client import MinioWrapper

    wrapper = MinioWrapper(client=stub_minio)
    stub_minio.buckets.add("corpus-audio")
    wrapper.upload_bytes("corpus-audio", "k.mp3", b"hello", "audio/mpeg")
    assert wrapper.download_bytes("corpus-audio", "k.mp3") == b"hello"


def test_presigned_get_url_uses_seconds(stub_minio: _StubMinio) -> None:
    """presigned_get_url passes expires as a timedelta."""
    from role_builder.services.minio_client import MinioWrapper

    wrapper = MinioWrapper(client=stub_minio)
    url = wrapper.presigned_get_url("corpus-audio", "k.mp3", expires_seconds=900)
    assert url == "http://stub/corpus-audio/k.mp3?signed"
    assert stub_minio.last_presigned == ("corpus-audio", "k.mp3", 900)
