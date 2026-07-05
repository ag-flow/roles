"""Helpers pour les tests du cycle upload : object store fake (corpus-audio +
corpus-transcripts) et extracteur audio fake, injectables dans les services.

Séparé du conftest pour ne pas masquer la fixture `pool` (cf. LESSONS.md).
"""

from __future__ import annotations

import json
from typing import Any


class FakeObjectStore:
    """Double de MinioWrapper couvrant les besoins upload + dépôt.

    Objets stockés par clé ``(bucket, key)``. Le "PUT client" d'un test se
    simule en écrivant directement dans ``objects``.
    """

    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = objects or {}
        self.presigned_puts: list[tuple[str, str, int]] = []
        self.removed: list[tuple[str, str]] = []

    def put_json(self, bucket: str, key: str, payload: dict[str, Any]) -> None:
        self.objects[(bucket, key)] = json.dumps(payload).encode("utf-8")

    def presigned_put_url(self, bucket: str, key: str, *, expires_seconds: int = 3600) -> str:
        self.presigned_puts.append((bucket, key, expires_seconds))
        return f"https://minio.test/{bucket}/{key}?X-Amz-Signature=fake"

    def object_exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self.objects

    def remove_object(self, bucket: str, key: str) -> None:
        self.removed.append((bucket, key))
        self.objects.pop((bucket, key), None)

    def download_bytes(self, bucket: str, key: str) -> bytes:
        if (bucket, key) not in self.objects:
            raise FileNotFoundError(f"{bucket}/{key}")
        return self.objects[(bucket, key)]

    def upload_bytes(
        self, bucket: str, key: str, payload: bytes, content_type: str | None = None
    ) -> None:
        self.objects[(bucket, key)] = payload


def make_fake_extractor(store: FakeObjectStore, *, fail: bool = False):
    """Extracteur audio fake : copie l'objet source vers la clé cible.

    Même signature que ``audio_extraction.extract_audio_to_mp3`` ; ``fail=True``
    simule un échec ffmpeg.
    """
    from role_builder.services.acquisition.upload.audio_extraction import AudioExtractionError

    calls: list[tuple[str, str, str]] = []

    async def _extract(minio: Any, *, bucket: str, source_key: str, target_key: str) -> None:
        calls.append((bucket, source_key, target_key))
        if fail:
            raise AudioExtractionError("ffmpeg exited with code 1")
        store.objects[(bucket, target_key)] = b"fake-extracted-audio"

    _extract.calls = calls  # type: ignore[attr-defined]
    return _extract
