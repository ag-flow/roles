"""WorkerManager : provisioning + auto-stop des containers transcription user.

Lance les workers user à la demande via subprocess `docker run -d` et les
arrête après `WORKER_AUTO_STOP_THRESHOLD_S` d'inactivité (status='idle').
Le pool `shared_default` (faster-whisper sur pve2) tourne en permanence et
n'est jamais touché par l'auto-stop.

Un worker est uniquement identifié par :
- son container_id (stdout de `docker run -d`)
- son worker_pool_id (ex: `user_<uuid>`) qui sert au consumer-group côté worker

La table `transcription_workers` (migration 0007) stocke le mapping et l'état.
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.config import settings
from role_builder.db_helpers import transcription_keys as tk

log = structlog.get_logger(__name__)


# Mapping provider name (kebab-case côté DB) -> attribut Settings (snake_case).
_PROVIDER_TO_SETTINGS_ATTR: dict[str, str] = {
    "openai-whisper": "openai_api_key",
    "deepgram": "deepgram_api_key",
    "assemblyai": "assemblyai_api_key",
    "speechmatics": "speechmatics_api_key",
    # faster-whisper local : pas d'API key requise (modèle embarqué).
    "faster-whisper": "",
}


def _provider_env_key(provider: str) -> str:
    """Env var attendue par le worker côté container pour un provider donné."""
    # `openai-whisper` → `OPENAI_API_KEY`
    base = provider.split("-", 1)[0].upper()
    return f"{base}_API_KEY"


class WorkerManager:
    """Orchestre le cycle de vie des workers transcription user.

    Une instance par process backend. Détenteur de la boucle auto-stop.
    """

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        image_tag: str = "latest",
        host: str = "pve1",
    ) -> None:
        self._pool = pool
        self._image_tag = image_tag
        self._host = host

    # --- Public API -----------------------------------------------------

    async def ensure_user_workers_running(self, user_id: UUID) -> int:
        """Provisionne les workers manquants pour la primary key du user.

        Retourne le nombre de workers spawned (peut être 0).
        """
        primary = await tk.get_primary_key(user_id, pool=self._pool)
        if primary is None:
            log.info("worker_manager.no_primary_key", user_id=str(user_id))
            return 0

        target = int(primary.get("workers_count") or 1)
        active = await self._count_active_workers(user_id, primary["provider"])
        delta = max(target - active, 0)

        log.info(
            "worker_manager.ensure",
            user_id=str(user_id),
            provider=primary["provider"],
            target=target,
            active=active,
            delta=delta,
        )

        spawned = 0
        for idx in range(active, active + delta):
            await self.spawn_worker(user_id=user_id, key=primary, instance_index=idx)
            spawned += 1
        return spawned

    async def spawn_worker(
        self,
        *,
        user_id: UUID,
        key: dict[str, Any],
        instance_index: int,
    ) -> str:
        """`docker run -d` un worker user, l'enregistre en DB. Retourne container_id."""
        provider = str(key["provider"])
        worker_pool_id = f"user_{user_id}"
        worker_id = f"rb-worker-{user_id}-{provider}-{instance_index}"

        env: dict[str, str] = {
            "WORKER_POOL_ID": worker_pool_id,
            "WORKER_ID": worker_id,
            "TRANSCRIPTION_PROVIDER": provider,
            "DATABASE_URL": settings.database_url,
            "MINIO_ENDPOINT": settings.minio_endpoint,
            "MINIO_ACCESS_KEY": settings.minio_access_key,
            "MINIO_SECRET_KEY": settings.minio_secret_key,
            "LOG_LEVEL": settings.log_level,
        }
        api_attr = _PROVIDER_TO_SETTINGS_ATTR.get(provider, "")
        if api_attr:
            api_key = getattr(settings, api_attr, "") or ""
            if api_key:
                env[_provider_env_key(provider)] = api_key

        env_args: list[str] = []
        for k, v in env.items():
            env_args.extend(["-e", f"{k}={v}"])

        image = f"agflow-transcription-worker:{self._image_tag}"
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            worker_id,
            *env_args,
            image,
        ]

        log.info(
            "worker_manager.spawn",
            user_id=str(user_id),
            provider=provider,
            instance_index=instance_index,
            image=image,
        )

        stdout, _stderr = await self._run_subprocess(cmd)
        container_id = stdout.decode("utf-8", errors="replace").strip()
        # Si docker run échoue, container_id sera vide → on lève.
        if not container_id:
            raise RuntimeError(
                f"docker run produced empty container_id for {worker_id}"
            )

        await self._insert_worker_row(
            worker_pool_id=worker_pool_id,
            container_id=container_id,
            container_name=worker_id,
            provider=provider,
        )
        return container_id

    async def stop_workers_for_key(self, key_id: UUID) -> int:
        """Stoppe tous les workers d'un user pour un provider donné par key_id."""
        # Résoudre user_id + provider depuis la clé
        async with self._pool.acquire() as conn:
            key_row = await conn.fetchrow(
                "SELECT user_id, provider FROM user_transcription_keys WHERE id = $1",
                key_id,
            )
        if key_row is None:
            log.warning("worker_manager.key_not_found", key_id=str(key_id))
            return 0
        user_id = key_row["user_id"]
        provider = key_row["provider"]

        async with self._pool.acquire() as conn:
            workers = await conn.fetch(
                "SELECT id, container_id, container_name "
                "FROM transcription_workers "
                "WHERE worker_pool_id = $1 AND provider = $2 "
                "AND status NOT IN ('stopped', 'failed')",
                f"user_{user_id}",
                provider,
            )

        return await self._stop_and_mark(workers)

    async def auto_stop_idle(self, *, threshold_seconds: int = 300) -> int:
        """Stoppe les workers user idle depuis > threshold (jamais shared_default)."""
        query = (
            "SELECT id, container_id, container_name "
            "FROM transcription_workers "
            "WHERE status = 'idle' "
            "AND worker_pool_id <> 'shared_default' "
            "AND last_activity_at IS NOT NULL "
            "AND last_activity_at < now() - ($1::int * interval '1 second')"
        )
        async with self._pool.acquire() as conn:
            workers = await conn.fetch(query, threshold_seconds)
        if not workers:
            return 0
        return await self._stop_and_mark(workers)

    async def run_auto_stop_loop(
        self, stop_event: asyncio.Event, period_seconds: int = 60
    ) -> None:
        """Boucle tournant tant que stop_event n'est pas set.

        Pattern strictement identique à scraper_orchestrator.run_loop : on
        attend stop_event avec timeout=period_seconds entre 2 itérations.
        """
        log.info("worker_manager.loop_start", period_seconds=period_seconds)
        threshold = settings.worker_auto_stop_threshold_s
        while not stop_event.is_set():
            try:
                await self.auto_stop_idle(threshold_seconds=threshold)
            except Exception:  # noqa: BLE001 — keep the loop alive
                log.exception("worker_manager.auto_stop_error")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=period_seconds)
            except TimeoutError:
                continue
            else:
                break
        log.info("worker_manager.loop_stop")

    # --- Internals ------------------------------------------------------

    async def _count_active_workers(self, user_id: UUID, provider: str) -> int:
        async with self._pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    "SELECT count(*) FROM transcription_workers "
                    "WHERE worker_pool_id = $1 AND provider = $2 "
                    "AND status NOT IN ('stopped', 'failed')",
                    f"user_{user_id}",
                    provider,
                )
                or 0
            )

    async def _insert_worker_row(
        self,
        *,
        worker_pool_id: str,
        container_id: str,
        container_name: str,
        provider: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transcription_workers "
                "(worker_pool_id, container_id, container_name, provider, "
                " status, host, last_activity_at) "
                "VALUES ($1, $2, $3, $4, 'starting', $5, now())",
                worker_pool_id,
                container_id,
                container_name,
                provider,
                self._host,
            )

    async def _stop_and_mark(self, workers: list[dict[str, Any]] | list[Any]) -> int:
        """`docker stop` chaque worker + UPDATE status='stopped'."""
        count = 0
        for w in workers:
            row = dict(w) if not isinstance(w, dict) else w
            container_id = row.get("container_id")
            if container_id:
                try:
                    await self._run_subprocess(["docker", "stop", str(container_id)])
                except Exception:  # noqa: BLE001
                    log.exception(
                        "worker_manager.docker_stop_failed",
                        container_id=container_id,
                    )
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE transcription_workers "
                    "SET status = 'stopped', stopped_at = now() "
                    "WHERE id = $1",
                    row["id"],
                )
            count += 1
        return count

    async def _run_subprocess(self, cmd: list[str]) -> tuple[bytes, bytes]:
        """Wrapper subprocess testable (monkeypatch asyncio.create_subprocess_exec)."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.warning(
                "worker_manager.subprocess_nonzero",
                cmd=cmd[:3],
                returncode=proc.returncode,
                stderr=stderr.decode("utf-8", errors="replace")[:500],
            )
        return stdout, stderr
