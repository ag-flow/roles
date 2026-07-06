"""Worker d'extraction audio des uploads vidéo (spec §2.2, §1.1).

Boucle longue durée dans le process backend, même modèle que le
DepositWorker : claim FIFO sur `source_items` (FOR UPDATE SKIP LOCKED),
extraction ffmpeg de l'objet vidéo brut vers un mp3, puis entrée en queue de
transcription. Sortir le ffmpeg de l'appel `roles__finalize_upload` garantit
qu'aucun tool MCP ne bloque (spec §1.1) et libère l'event loop.

Cycle de l'item : `pending_extraction` (posé par finalize) → `extracting_audio`
(claim) → `audio_ready`/`queued_transcription` (succès) ou `failed`
(épuisement des tentatives, `error.code=AUDIO_EXTRACTION_FAILED`).

Reprise crash : `recover()` remet les `extracting_audio` orphelins en
`pending_extraction` ; la ré-extraction est idempotente (l'objet vidéo brut
n'est supprimé qu'après l'entrée effective en transcription, et le job n'est
inséré qu'une fois — cf. enter_transcription_pipeline).
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import structlog

from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import source_items_upload as siu
from role_builder.services.acquisition.upload.audio_extraction import (
    AudioExtractionError,
    extract_audio_to_mp3,
)
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from role_builder.services.acquisition.upload.transcription_entry import (
    enter_transcription_pipeline,
)
from role_builder.services.minio_client import MinioWrapper, minio_client

log = structlog.get_logger(__name__)


class AudioExtractionWorker:
    """Un seul worker d'extraction par déploiement (cf. requeue_stale_extracting)."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        minio: MinioWrapper | None = None,
        max_attempts: int = 3,
        backoff_base_s: float = 1.0,
        poll_interval_s: float = 2.0,
    ) -> None:
        self._pool = pool
        self._minio = minio or minio_client
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._poll_interval_s = poll_interval_s

    async def recover(self) -> int:
        """Remet en queue les items `extracting_audio` orphelins (reprise crash)."""
        requeued = await siu.requeue_stale_extracting(pool=self._pool)
        if requeued:
            log.warning("extraction.recovered_stale_items", count=requeued)
        return requeued

    async def tick(self) -> bool:
        """Claim et traite un item ; False si la queue est vide."""
        item = await siu.claim_next_for_extraction(pool=self._pool)
        if item is None:
            return False
        await self.process_item(item)
        return True

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """Boucle longue durée : recover puis claim/process jusqu'à stop."""
        log.info("extraction.loop_start")
        await self.recover()
        while not stop_event.is_set():
            try:
                processed = await self.tick()
            except Exception:  # noqa: BLE001 — la boucle doit survivre
                log.exception("extraction.tick_error")
                processed = False
            if processed:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_s)
            except TimeoutError:
                continue
            else:
                break
        log.info("extraction.loop_stop")

    async def process_item(self, item: dict[str, Any]) -> None:
        """Extrait l'audio d'un item claimé, avec retry/backoff ; marque l'issue."""
        item_id = item["id"]
        upload_key = item["upload_s3_key"]
        audio_key = upload_key.rsplit(".", 1)[0] + ".mp3"
        last_error: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                await extract_audio_to_mp3(
                    self._minio, bucket=AUDIO_BUCKET,
                    source_key=upload_key, target_key=audio_key,
                )
            except AudioExtractionError as exc:
                last_error = exc
                log.warning(
                    "extraction.attempt_failed",
                    item_id=str(item_id),
                    attempt=attempt,
                    max_attempts=self._max_attempts,
                    error=str(exc),
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_base_s * 2 ** (attempt - 1))
            else:
                await enter_transcription_pipeline(
                    item, audio_key=audio_key, pool=self._pool,
                    minio=self._minio, remove_raw_key=upload_key,
                )
                log.info("extraction.item_ready", item_id=str(item_id), audio_s3_key=audio_key)
                return

        message = str(last_error) or "AudioExtractionError"
        await source_items_helper.update_source_item_status(
            item["source_id"], item["platform_item_id"], "failed",
            error=f"AUDIO_EXTRACTION_FAILED: {message}", pool=self._pool,
        )
        log.error("extraction.item_failed", item_id=str(item_id), error=message)
