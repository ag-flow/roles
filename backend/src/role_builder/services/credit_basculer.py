"""Bascule sur épuisement de crédit côté provider de transcription.

Quand le worker détecte un HTTP 402 / quota_exceeded sur sa clé primary :
  1. Il appelle `db_helpers.transcription_keys.mark_exhausted(key_id, ...)`
  2. (Sprint 6 — futur) Un trigger PG NOTIFY 'keys_changes' réveillera le
     backend qui invoquera `handle_key_exhausted` ci-dessous.

Pour Sprint 3, ce module est appelé côté worker (ou côté backend dès qu'un
trigger DB est en place). Il :
  1. Stoppe les workers user liés à cette clé via WorkerManager
  2. Réassigne les transcription_jobs encore pending vers `shared_default`
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.db_helpers import transcription_jobs as tj

log = structlog.get_logger(__name__)


async def handle_key_exhausted(
    *,
    key_id: UUID,
    user_id: UUID,
    pool: asyncpg.Pool,
    manager: Any,
) -> None:
    """Stoppe les workers de la clé et réassigne les jobs pending au pool shared.

    `manager` doit exposer `stop_workers_for_key(key_id)`. On le passe en
    argument plutôt que d'importer WorkerManager pour (1) éviter le cycle
    d'import et (2) faciliter le test.
    """
    log.info(
        "credit_basculer.start",
        key_id=str(key_id),
        user_id=str(user_id),
    )
    stopped = await manager.stop_workers_for_key(key_id)
    log.info("credit_basculer.workers_stopped", count=stopped)

    user_pool_id = f"user_{user_id}"
    reassigned = await tj.reassign_pending_to_shared(user_pool_id, pool=pool)
    log.info(
        "credit_basculer.jobs_reassigned",
        user_pool_id=user_pool_id,
        count=reassigned,
    )
