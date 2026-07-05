"""Worker de dépôt docflow — étape `transcribed → depositing → deposited`.

Boucle longue durée dans le process backend (même modèle que
ScraperOrchestrator) : claim FIFO sur `source_items` (FOR UPDATE SKIP
LOCKED), lecture du pivot JSON dans MinIO `corpus-transcripts`, dépôt via
`CorpusDepositor` avec retry/backoff exponentiel in-process. Échec après
épuisement des tentatives : item `failed` avec
`error.code=DOCFLOW_DEPOSIT_FAILED`, transcript conservé dans MinIO
(spec v2/01 §3 et §5.2).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg
import structlog

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import deposit_queue
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.deposit.base import CorpusDepositor
from role_builder.services.minio_client import MinioWrapper, minio_client

log = structlog.get_logger(__name__)

TRANSCRIPT_BUCKET = "corpus-transcripts"


def extract_transcript_text(pivot: dict[str, Any]) -> str:
    """Texte consommable à partir du format pivot (segments concaténés)."""
    lines = (str(segment.get("text", "")).strip() for segment in pivot.get("segments", []))
    return "\n".join(line for line in lines if line)


class DepositWorker:
    """Un seul worker de dépôt par déploiement (cf. requeue_stale_depositing)."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        depositor: CorpusDepositor,
        minio: MinioWrapper | None = None,
        max_attempts: int = 3,
        backoff_base_s: float = 1.0,
        poll_interval_s: float = 2.0,
    ) -> None:
        self._pool = pool
        self._depositor = depositor
        self._minio = minio or minio_client
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._poll_interval_s = poll_interval_s

    async def recover(self) -> int:
        """Remet en queue les items `depositing` orphelins (reprise crash)."""
        requeued = await deposit_queue.requeue_stale_depositing(pool=self._pool)
        if requeued:
            log.warning("deposit.recovered_stale_items", count=requeued)
        return requeued

    async def tick(self) -> bool:
        """Claim et traite un item ; False si la queue est vide."""
        item = await deposit_queue.claim_next_for_deposit(pool=self._pool)
        if item is None:
            return False
        await self.process_item(item)
        return True

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """Boucle longue durée : recover puis claim/process jusqu'à stop."""
        log.info("deposit.loop_start")
        await self.recover()
        while not stop_event.is_set():
            try:
                processed = await self.tick()
            except Exception:  # noqa: BLE001 — la boucle doit survivre
                log.exception("deposit.tick_error")
                processed = False
            if processed:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_s)
            except TimeoutError:
                continue
            else:
                break
        log.info("deposit.loop_stop")

    async def process_item(self, item: dict[str, Any]) -> None:
        """Dépose un item claimé, avec retry/backoff ; marque l'issue en DB."""
        item_id = item["id"]
        last_error: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                result = await self._attempt_deposit(item)
            except Exception as exc:  # noqa: BLE001 — classifié en échec de dépôt
                last_error = exc
                log.warning(
                    "deposit.attempt_failed",
                    item_id=str(item_id),
                    attempt=attempt,
                    max_attempts=self._max_attempts,
                    error=str(exc),
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_base_s * 2 ** (attempt - 1))
            else:
                await deposit_queue.mark_deposited(
                    item_id, doc_id=result.doc_id, slug=result.slug, pool=self._pool
                )
                log.info(
                    "deposit.item_deposited",
                    item_id=str(item_id),
                    doc_id=result.doc_id,
                    slug=result.slug,
                )
                return

        message = str(last_error) or last_error.__class__.__name__
        await deposit_queue.mark_deposit_failed(item_id, message=message, pool=self._pool)
        log.error("deposit.item_failed", item_id=str(item_id), error=message)

    async def _attempt_deposit(self, item: dict[str, Any]) -> Any:
        """Une tentative complète : lecture pivot MinIO + dépôt."""
        transcript_key = item.get("transcript_s3_key")
        if not transcript_key:
            raise ValueError(f"item {item['id']} sans transcript_s3_key")
        raw = await asyncio.to_thread(
            self._minio.download_bytes, TRANSCRIPT_BUCKET, transcript_key
        )
        pivot = json.loads(raw)
        metadata = await self._build_metadata(item, pivot)
        return await self._depositor.deposit(
            item=item,
            transcript_text=extract_transcript_text(pivot),
            metadata=metadata,
        )

    async def _build_metadata(
        self, item: dict[str, Any], pivot: dict[str, Any]
    ) -> dict[str, Any]:
        """Métadonnées du document docflow (spec v2/01 §2.4 + fondations §7).

        `source_url` = URL de la source d'origine (chaîne/playlist/compte) —
        l'URL par item n'est pas conservée par les scrapers actuels.
        """
        source = await sources_helper.get_source(item["source_id"], pool=self._pool)
        request = (
            await ar.get_by_source_id(item["source_id"], pool=self._pool) if source else None
        )
        published_at = item.get("published_at")
        return {
            "platform": source["platform"] if source else None,
            "source_url": source["url"] if source else None,
            "title": item.get("title"),
            "duration_s": item.get("duration_s"),
            "published_at": published_at.isoformat() if published_at else None,
            "request_key": request["request_key"] if request else None,
            "provider": pivot.get("provider"),
        }
