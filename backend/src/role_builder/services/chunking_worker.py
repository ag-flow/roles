"""ChunkingWorker — asyncio task interne au backend.

Cycle (cf. spec 05 § Boucle principale) :
1. claim_next_pending_job (FOR UPDATE SKIP LOCKED + UPDATE status='claimed')
2. mark_processing
3. download transcript JSON depuis MinIO (bucket ``corpus-transcripts``)
4. chunk_transcript → list[TranscriptChunk]
5. embedder.embed_texts → list[list[float]]
6. corpus_chunks.insert_chunks_bulk
7. mark_done(chunks_produced=N) + source_items.status='indexed'

En cas d'exception : mark_failed(error=str(exc)).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.db_helpers import chunking_jobs, corpus_chunks, source_items
from role_builder.services import chunker, embedder
from role_builder.services.minio_client import MinioWrapper

log = structlog.get_logger(__name__)


class ChunkingWorker:
    """Une instance par process backend. ``run_loop`` est la task long-lived."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        worker_id: str = "chunking-worker-1",
        minio: MinioWrapper | None = None,
    ) -> None:
        self._pool = pool
        self._worker_id = worker_id
        self._minio = minio or MinioWrapper()

    async def process_one_job(self, job: dict[str, Any]) -> None:
        """Traite un chunking_job claimé : download → chunk → embed → insert."""
        job_id: UUID = job["id"]
        item_id: UUID = job["source_item_id"]
        project_id: UUID = job["role_project_id"]
        tenant_id: UUID = job["tenant_id"]
        transcript_key: str = job["transcript_s3_key"]

        await chunking_jobs.mark_processing(job_id, pool=self._pool)
        log.info(
            "chunking_worker.process_start",
            job_id=str(job_id),
            transcript_key=transcript_key,
        )

        try:
            payload = self._minio.download_bytes("corpus-transcripts", transcript_key)
            transcript = json.loads(payload.decode("utf-8"))

            built_chunks = chunker.chunk_transcript(
                transcript, target_tokens=500, overlap_tokens=50
            )

            if not built_chunks:
                log.info(
                    "chunking_worker.no_chunks",
                    job_id=str(job_id),
                    transcript_key=transcript_key,
                )
                await chunking_jobs.mark_done(
                    job_id, chunks_produced=0, pool=self._pool
                )
                await source_items.update_source_item_status_by_id(
                    item_id, "indexed", pool=self._pool
                )
                return

            texts = [c.text for c in built_chunks]
            vectors = await embedder.embed_texts(texts)
            chunk_rows: list[dict[str, Any]] = [
                {
                    "chunk_index": idx,
                    "start_s": c.start_s,
                    "end_s": c.end_s,
                    "text": c.text,
                    "embedding": vec,
                }
                for idx, (c, vec) in enumerate(zip(built_chunks, vectors, strict=True))
            ]

            inserted = await corpus_chunks.insert_chunks_bulk(
                chunk_rows,
                source_item_id=item_id,
                role_project_id=project_id,
                tenant_id=tenant_id,
                pool=self._pool,
            )
            await chunking_jobs.mark_done(
                job_id, chunks_produced=inserted, pool=self._pool
            )
            await source_items.update_source_item_status_by_id(
                item_id, "indexed", pool=self._pool
            )
            log.info(
                "chunking_worker.process_done",
                job_id=str(job_id),
                chunks_produced=inserted,
            )
        except Exception as exc:  # noqa: BLE001 — worker doit rester en vie
            log.exception("chunking_worker.process_error", job_id=str(job_id))
            await chunking_jobs.mark_failed(
                job_id, str(exc) or exc.__class__.__name__, pool=self._pool
            )

    async def run_loop(
        self, stop_event: asyncio.Event, *, poll_interval_s: float = 2.0
    ) -> None:
        """Long-lived loop : pull pending jobs, process, sleep, repeat."""
        log.info("chunking_worker.loop_start", worker_id=self._worker_id)
        while not stop_event.is_set():
            try:
                job = await chunking_jobs.claim_next_pending_job(
                    self._worker_id, pool=self._pool
                )
            except Exception:  # noqa: BLE001 — keep loop alive
                log.exception("chunking_worker.claim_error")
                job = None

            if job is None:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=poll_interval_s
                    )
                except TimeoutError:
                    continue
                else:
                    break
            else:
                await self.process_one_job(job)
        log.info("chunking_worker.loop_stop", worker_id=self._worker_id)
