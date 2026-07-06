"""Extraction audio ffmpeg pour les vidéos uploadées (spec §2.2).

Les items scrapés arrivent avec l'audio déjà extrait par le container
yt-dlp+ffmpeg ; pour un upload vidéo, l'extraction se fait côté stack, au
finalize : download de l'objet brut, `ffmpeg -vn` vers mp3, upload de
l'audio. ffmpeg est présent dans l'image backend (cf. backend/Dockerfile).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from role_builder.services.minio_client import MinioWrapper

_FFMPEG_TIMEOUT_S = 1800  # garde-fou : 30 min, au-delà l'extraction est tuée
_STDERR_TAIL_CHARS = 500


class AudioExtractionError(Exception):
    """ffmpeg indisponible, timeout, ou sortie en erreur."""


async def extract_audio_to_mp3(
    minio: MinioWrapper,
    *,
    bucket: str,
    source_key: str,
    target_key: str,
) -> None:
    """Extrait la piste audio de `bucket/source_key` vers `bucket/target_key` (mp3).

    Raises:
        AudioExtractionError
    """
    video_bytes = await asyncio.to_thread(minio.download_bytes, bucket, source_key)

    with tempfile.TemporaryDirectory(prefix="rb-upload-extract-") as tmp_dir:
        source_path = Path(tmp_dir) / ("in" + Path(source_key).suffix)
        target_path = Path(tmp_dir) / "out.mp3"
        # I/O fichier hors de l'event loop : un write/read de plusieurs
        # centaines de Mo bloquerait sinon toute la boucle asyncio.
        await asyncio.to_thread(source_path.write_bytes, video_bytes)

        await _run_ffmpeg(source_path, target_path)

        audio_bytes = await asyncio.to_thread(target_path.read_bytes)

    await asyncio.to_thread(
        minio.upload_bytes, bucket, target_key, audio_bytes, content_type="audio/mpeg"
    )


async def _run_ffmpeg(source_path: Path, target_path: Path) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-i", str(source_path),
            "-vn",
            "-c:a", "libmp3lame",
            "-q:a", "2",
            str(target_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise AudioExtractionError("ffmpeg introuvable dans l'environnement backend") from exc

    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=_FFMPEG_TIMEOUT_S)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise AudioExtractionError(f"ffmpeg timeout après {_FFMPEG_TIMEOUT_S}s") from exc

    if process.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace")[-_STDERR_TAIL_CHARS:].strip()
        raise AudioExtractionError(f"ffmpeg exited with code {process.returncode}: {tail}")
