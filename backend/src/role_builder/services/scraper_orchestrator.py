"""Orchestrator scrapers Sprint 2.

Pull les `scraping_jobs` pending en FIFO (FOR UPDATE SKIP LOCKED), lance
le container scraper correspondant via `docker_runner.run_container`, et
dispatche les events NDJSON vers `event_handlers.handle_scraper_event`.
Marque le job done|failed selon le returncode.

Cap simultané : `settings.max_concurrent_scrapers` via `asyncio.Semaphore`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import structlog

from role_builder.config import settings
from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import scraping_jobs as sj
from role_builder.db_helpers import sources as sm
from role_builder.db_helpers.credentials import get_cookies_b64, get_credential_by_id
from role_builder.services.audio_sweeper import check_disk_guard
from role_builder.services.docker_runner import run_container
from role_builder.services.event_handlers import handle_scraper_event
from role_builder.services.secret_store import (
    get_secret_store as _get_secret_store,
)

log = structlog.get_logger(__name__)

# Defaults applied to the stdin payload when not overridden at the job level.
_DEFAULT_OPTIONS = {
    "audio_format": "mp3",
    "audio_quality": 9,
    "audio_args": "-ac 1 -ar 16000 -b:a 32k",
    "sleep_interval_min": 3,
    "sleep_interval_max": 10,
}


class ScraperOrchestrator:
    """One instance per backend process. Use `run_loop` for the long-lived task."""

    def __init__(self, *, pool: asyncpg.Pool, worker_id: str = "orchestrator-1") -> None:
        self._pool = pool
        self._worker_id = worker_id
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scrapers)

    async def process_one_job(self, job: dict[str, Any]) -> None:
        """Run a single scraping job: build payload, stream events, mark lifecycle."""
        job_id = job["id"]
        source_id = job["source_id"]

        await sj.mark_job_processing(job_id, pool=self._pool)

        # Fail closed, bruyamment : sans audio_volume_host_dir, le `-v` n'a
        # rien à monter côté host — l'audio écrit disparaîtrait avec le
        # conteneur éphémère, en succès silencieux (BUG-01). Ne pas traiter
        # un host_dir vide comme un no-op.
        if not settings.audio_volume_host_dir:
            await self._fail_job(
                job,
                job_id,
                "audio_volume_host_dir non configuré : refus de lancer le scraper, "
                "l'audio écrit serait perdu avec le conteneur éphémère (BUG-01)",
                "orchestrator.audio_volume_host_dir_missing",
            )
            return

        # Garde disque (tâche 6) : déléguée à audio_sweeper.py, qui porte déjà
        # les préoccupations disque de ce volume (balayage d'orphelins) —
        # pas une responsabilité de cet orchestrateur.
        guard = await check_disk_guard()
        if guard is not None:
            err, log_fields = guard
            await self._fail_job(job, job_id, err, "orchestrator.disk_guard_refused", **log_fields)
            return

        source = await sm.get_source(source_id, pool=self._pool)
        if source is None:
            await self._fail_job(
                job,
                job_id,
                f"source {source_id} not found",
                "orchestrator.source_missing",
                source_id=str(source_id),
            )
            return

        platform = source["platform"]
        env = await self._build_env(platform, source)
        payload = self._build_payload(job, source)
        image = f"agflow-scraper-{platform}:{settings.scraper_image_tag}"
        # -v doit précéder l'image dans la commande docker (cf. docker_runner.
        # run_container, paramètre docker_args) : --network n'est PAS ajouté
        # ici — le scraper n'appelle plus aucun service interne (ni MinIO ni
        # autre) depuis le retrait des credentials MinIO de _build_env, le
        # bridge par défaut lui suffit pour Internet.
        docker_args = ["-v", f"{settings.audio_volume_host_dir}:{settings.audio_volume_dir}"]

        log.info(
            "orchestrator.process_start",
            job_id=str(job_id),
            platform=platform,
            command=job["command"],
            image=image,
        )

        returncode: int | None = None
        try:
            async for event in run_container(image, env, payload, docker_args=docker_args):
                if event.get("type") == "_exit":
                    returncode = int(event.get("returncode", -1))
                    continue
                await handle_scraper_event(event, job, pool=self._pool)
        except Exception as exc:  # noqa: BLE001 — orchestrator must keep running
            await self._fail_job(
                job,
                job_id,
                f"orchestrator error: {exc}",
                "orchestrator.process_error",
                exc_info=True,
            )
            return

        if returncode == 0:
            await sj.mark_job_done(job_id, pool=self._pool)
        else:
            await self._fail_job(
                job,
                job_id,
                f"scraper exited with returncode {returncode}",
                "orchestrator.returncode_nonzero",
            )

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """Long-lived worker loop. Pulls pending jobs and dispatches them.

        Jusqu'à `max_concurrent_scrapers` jobs tournent réellement en
        parallèle : le sémaphore est acquis *avant* le claim (pour ne jamais
        claimer plus que la capacité), et chaque job est traité dans sa
        propre task. Un job long ne bloque plus les autres tenants/requêtes.
        """
        log.info("orchestrator.loop_start", worker_id=self._worker_id)
        try:
            requeued = await sj.requeue_stale_jobs(pool=self._pool)
            if requeued:
                log.warning("orchestrator.recovered_stale_jobs", count=requeued)
        except Exception:  # noqa: BLE001 — la reprise ne doit pas empêcher le démarrage
            log.exception("orchestrator.recover_error")
        in_flight: set[asyncio.Task[None]] = set()
        while not stop_event.is_set():
            await self._semaphore.acquire()
            if stop_event.is_set():
                self._semaphore.release()
                break
            try:
                job = await sj.claim_next_pending_job(self._worker_id, pool=self._pool)
            except Exception:  # noqa: BLE001 — la boucle doit survivre à une erreur DB
                log.exception("orchestrator.claim_error", worker_id=self._worker_id)
                self._semaphore.release()
                job = None
            if job is None:
                self._semaphore.release()
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=2.0)
                except TimeoutError:
                    continue
                else:
                    break
            task = asyncio.create_task(self._process_and_release(job))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
        log.info("orchestrator.loop_stop", worker_id=self._worker_id)

    async def _process_and_release(self, job: dict[str, Any]) -> None:
        """Traite un job puis libère le sémaphore, quoi qu'il arrive.

        Toute exception est loguée ici (pas propagée) : une erreur DB
        transitoire sur un job ne doit tuer ni la task ni la boucle (BUG-09).
        """
        try:
            await self.process_one_job(job)
        except Exception:  # noqa: BLE001 — la boucle doit survivre
            log.exception("orchestrator.job_error", job_id=str(job.get("id")))
        finally:
            self._semaphore.release()

    # --- internals -------------------------------------------------------

    async def _fail_job(
        self,
        job: dict[str, Any],
        job_id: Any,
        err: str,
        event: str,
        *,
        exc_info: bool = False,
        **log_fields: Any,
    ) -> None:
        """Factorise log + mark_job_failed + propagation, répétés à chaque
        sortie en échec de `process_one_job`. L'appelant garde le `return`.
        `exc_info=True` (le seul site avec une exception inattendue) bascule
        sur `log.exception` pour capturer la trace ; les autres refus sont
        des décisions attendues (`log.error` suffit).
        """
        if exc_info:
            log.exception(event, job_id=str(job_id), **log_fields)
        else:
            log.error(event, job_id=str(job_id), **log_fields)
        await sj.mark_job_failed(job_id, err, pool=self._pool)
        await self._propagate_discover_failure(job, err)

    async def _propagate_discover_failure(self, job: dict[str, Any], reason: str) -> None:
        """Un job `discover` échoué doit sortir la requête de `discovering`.

        Sinon `request_status` répond `discovering` à jamais (le ticket
        asynchrone devient un trou noir). Sans effet pour les jobs `download`
        (échec géré par item) ni pour les sources V1 sans requête.
        """
        if job.get("command") != "discover":
            return
        source_id = job["source_id"]
        try:
            await sm.update_source_status(source_id, "discovery_failed", pool=self._pool)
            request = await ar.get_by_source_id(source_id, pool=self._pool)
            if request is not None and request["status"] in ("discovering", "discovered"):
                await ar.update_status(request["request_key"], "failed", pool=self._pool)
                log.warning(
                    "orchestrator.discovery_failed",
                    request_key=request["request_key"],
                    reason=reason,
                )
        except Exception:  # noqa: BLE001 — best-effort, ne doit pas masquer l'échec initial
            log.exception("orchestrator.propagate_failure_error", source_id=str(source_id))

    async def _build_env(self, platform: str, source: dict[str, Any]) -> dict[str, str]:
        # Plus de credentials MinIO ici : le scraper écrit l'audio sur le
        # volume monté (output.dir), il n'uploade plus rien (tâche 1 a retiré
        # minio_uploader). Les envoyer encore exposerait des secrets sans
        # usage côté conteneur.
        env: dict[str, str] = {
            "LOG_LEVEL": settings.log_level,
        }
        cookies = await self._resolve_cookies(platform, source)
        if cookies:
            env[f"{platform.upper()}_COOKIES_B64"] = cookies
        return env

    async def _resolve_cookies(self, platform: str, source: dict[str, Any]) -> str:
        """Cookies du credential lié à la source (via son secret), sinon .env."""
        cred_id = source.get("credentials_id")
        if cred_id is not None:
            cred = await get_credential_by_id(cred_id, pool=self._pool)
            if cred is not None and cred.get("secret_id") is not None:
                value = await _get_secret_store().read_secret_by_id(
                    secret_id=cred["secret_id"],
                    user_id=cred["user_id"],
                    pool=self._pool,
                )
                if value:
                    return value
                log.warning(
                    "orchestrator.credential_secret_unresolvable",
                    credentials_id=str(cred_id),
                    platform=platform,
                )
        return get_cookies_b64(platform)

    def _build_payload(self, job: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        # Préfixe scopé au tenant/source (le concept role_project est retiré,
        # migration 0011) ; "v2" garde la structure de chemin stable. Ce n'est
        # plus un préfixe de clé S3 : c'est un sous-répertoire du volume local.
        prefix = f"{job['tenant_id']}/v2/{source['id']}/"
        return {
            "task_id": str(job["id"]),
            "command": job["command"],
            "url": source["url"],
            "options": dict(_DEFAULT_OPTIONS),
            # output = {dir, prefix} seulement : plus de "type" (discriminant à
            # valeur unique), plus de "format" (dérivé de options.audio_format,
            # seule source de vérité), plus d'identifiants MinIO (l'audio
            # n'est plus uploadé — il est écrit directement sur le volume
            # monté). Cf. docs/specs/03-scrapers.md.
            "output": {
                "dir": settings.audio_volume_dir,
                "prefix": prefix,
            },
        }
