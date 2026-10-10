"""APScheduler wrapper pour les jobs périodiques de Role Builder."""

from __future__ import annotations

import datetime as dt

import asyncpg
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from role_builder.config import settings
from role_builder.db_helpers import transcription_jobs as transcription_jobs_helper
from role_builder.db_helpers import transcription_keys as keys_helper
from role_builder.services.audio_sweeper import sweep_orphan_audio
from role_builder.services.credit_monitor import poll_all_balances

log = structlog.get_logger(__name__)

_BALANCE_POLL_INTERVAL_HOURS = 1
_RESET_SPEND_DAY = 1
_CLEANUP_HOUR = 3
_TRANSCRIPTION_RECONCILE_INTERVAL_MIN = 2


class RoleBuilderScheduler:
    """Wrapper léger autour d'AsyncIOScheduler : jobs Sprint 6 (poll balance, reset, cleanup)."""

    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._scheduler = AsyncIOScheduler()
        self._started = False

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.add_job(
            self._poll_balances,
            IntervalTrigger(hours=_BALANCE_POLL_INTERVAL_HOURS),
            id="poll_credit_balances",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._reset_monthly_spend,
            CronTrigger(day=_RESET_SPEND_DAY, hour=0, minute=0),
            id="reset_monthly_spend",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._cleanup_revoked_secrets,
            CronTrigger(hour=_CLEANUP_HOUR, minute=0),
            id="cleanup_revoked_secrets",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._reconcile_dead_transcriptions,
            IntervalTrigger(minutes=_TRANSCRIPTION_RECONCILE_INTERVAL_MIN),
            id="reconcile_dead_transcriptions",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._sweep_orphan_audio,
            IntervalTrigger(minutes=settings.audio_sweep_interval_min),
            id="sweep_orphan_audio",
            replace_existing=True,
        )
        self._scheduler.start()
        self._started = True
        log.info("scheduler.started", jobs=[j.id for j in self._scheduler.get_jobs()])

    async def shutdown(self) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        log.info("scheduler.shutdown")

    async def _poll_balances(self) -> None:
        try:
            await poll_all_balances(pool=self._pool)
        except Exception:
            log.exception("scheduler.poll_balances_failed")

    async def _reset_monthly_spend(self) -> None:
        try:
            count = await keys_helper.reset_monthly_spend_all(pool=self._pool)
            log.info("scheduler.reset_monthly_spend_completed", reset_count=count)
        except Exception:
            log.exception("scheduler.reset_monthly_spend_failed")

    async def _reconcile_dead_transcriptions(self) -> None:
        """Bascule `failed` les items dont le job de transcription a échoué
        sans les faire progresser (le container ne touche que le job, §BUG-19)."""
        try:
            failed = await transcription_jobs_helper.fail_items_with_dead_transcription_jobs(
                pool=self._pool
            )
            if failed:
                log.info("scheduler.transcriptions_reconciled", failed=failed)
        except Exception:
            log.exception("scheduler.reconcile_transcriptions_failed")

    async def _sweep_orphan_audio(self) -> None:
        """Balaie les fichiers audio orphelins du volume local (tâche 6).

        `now` est injecté ici plutôt que lu dans `sweep_orphan_audio` lui-même
        — l'horloge appartient à l'appelant, pas à la logique de balayage."""
        try:
            deleted = await sweep_orphan_audio(pool=self._pool, now=dt.datetime.now(dt.UTC))
            if deleted:
                log.info("scheduler.audio_orphans_swept", deleted=deleted)
        except Exception:
            log.exception("scheduler.sweep_orphan_audio_failed")

    async def _cleanup_revoked_secrets(self) -> None:
        """Best-effort : nettoyage des secrets vault liés à des credentials
        révoqués depuis > 7 jours. MVP : logs uniquement, le delete est déjà
        fait dans le DELETE endpoint. Reporté Phase 2 pour scan exhaustif."""
        log.info(
            "scheduler.cleanup_revoked_secrets_skipped",
            reason="MVP: cleanup déjà géré par DELETE endpoints",
        )
