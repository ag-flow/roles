"""Test d'intégration de l'extraction audio ffmpeg (vidéo uploadée → mp3).

Skip si ffmpeg n'est pas installé sur l'hôte de test (il l'est dans l'image
backend, cf. backend/Dockerfile). Le fichier vidéo de test est synthétisé
par ffmpeg lui-même (mire + sinusoïde d'une seconde).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from role_builder.services.acquisition.upload.audio_extraction import (
    AudioExtractionError,
    extract_audio_to_mp3,
)
from tests.services.acquisition.upload_helpers import FakeObjectStore

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg non installé"),
]

BUCKET = "corpus-audio"


def _make_test_video(tmp_path) -> bytes:
    """Vidéo mp4 d'une seconde (mire 64x64 + sinusoïde 440 Hz)."""
    path = tmp_path / "in.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


async def test_extract_audio_from_real_video(tmp_path) -> None:
    store = FakeObjectStore()
    store.objects[(BUCKET, "upload/rk/item.mp4")] = _make_test_video(tmp_path)

    await extract_audio_to_mp3(
        store, bucket=BUCKET, source_key="upload/rk/item.mp4", target_key="upload/rk/item.mp3"
    )

    audio = store.objects[(BUCKET, "upload/rk/item.mp3")]
    assert len(audio) > 0
    # mp3 : trame MPEG (0xFFEx) ou en-tête ID3.
    assert audio[:3] == b"ID3" or audio[0] == 0xFF


async def test_extract_raises_on_invalid_input() -> None:
    store = FakeObjectStore()
    store.objects[(BUCKET, "upload/rk/item.mp4")] = b"pas-une-video"

    with pytest.raises(AudioExtractionError):
        await extract_audio_to_mp3(
            store, bucket=BUCKET, source_key="upload/rk/item.mp4", target_key="upload/rk/item.mp3"
        )
