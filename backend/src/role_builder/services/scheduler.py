"""APScheduler wrapper pour les jobs périodiques de Role Builder."""

from __future__ import annotations

import asyncpg
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from role_builder.db_helpers import transcription_keys as keys_helper
from role_builder.services.credit_monitor import poll_all_balances

log = structlog.get_logger(__name__)

_BALANCE_POLL_INTERVAL_HOURS = 1
_RESET_SPEND_DAY = 1
_CLEANUP_HOUR = 3


class RoleBuilderScheduler:
    """Wrapper léger autour d'AsyncIOScheduler avec 3 jobs Sprint 6."""

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

    async def _cleanup_revoked_secrets(self) -> None:
        """Best-effort : supprime de OpenBao les secrets liés à des credentials
        révoqués depuis > 7 jours. MVP : logs uniquement, le delete est déjà
        fait dans le DELETE endpoint. Reporté Phase 2 pour scan exhaustif."""
        log.info(
            "scheduler.cleanup_revoked_secrets_skipped",
            reason="MVP: cleanup déjà géré par DELETE endpoints",
        )
