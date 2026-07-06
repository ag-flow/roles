"""Wrapper subprocess pour `docker run -i` avec stream NDJSON.

L'orchestrator Phase C utilise ce module pour lancer les containers
scrapers one-shot, leur envoyer une tâche JSON sur stdin, et streamer
les events NDJSON sur stdout. Un event terminal `_exit` est yieldé
avec le returncode pour permettre à l'appelant de marquer le job
done/failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@contextmanager
def env_file(env: dict[str, str]) -> Iterator[str]:
    """Écrit `env` dans un fichier temporaire 0600 pour `docker run --env-file`.

    Passer les secrets (clés SaaS, DATABASE_URL, MINIO_SECRET_KEY, cookies) en
    `-e K=V` les exposerait sur la ligne de commande du CLI docker, lisible par
    tout process du host (`ps`, `/proc/<pid>/cmdline`). Un env-file 0600, lu par
    docker au démarrage puis supprimé, retire cette exposition. (`docker inspect`
    reste un point d'exposition inhérent aux env Docker.)
    """
    fd, path = tempfile.mkstemp(prefix="rb-env-")  # mkstemp crée en 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key, value in env.items():
                handle.write(f"{key}={value}\n")
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


async def run_container(
    image: str,
    env: dict[str, str],
    stdin_payload: dict[str, Any],
    *,
    extra_args: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run `docker run --rm -i image`, write JSON payload to stdin, stream NDJSON events.

    Yields each parsed event dict, then a terminal `{"type": "_exit",
    "returncode": int}`. Invalid JSON lines are yielded as
    `{"type": "_invalid_line", "raw": str}`.
    """
    extras = extra_args or []

    log.info("docker_runner.start", image=image, env_keys=list(env.keys()))

    # env-file plutôt que -e K=V : les secrets ne transitent pas par l'argv.
    with env_file(env) as env_path:
        cmd = ["docker", "run", "--rm", "-i", "--env-file", env_path, image, *extras]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # stderr doit être drainé en continu : sinon un scraper verbeux remplit
        # le buffer pipe et se bloque en écriture → readline() n'atteint jamais
        # EOF, l'orchestrator gèle (BUG-06). Le try/finally garantit que le
        # process est tué si le consommateur abandonne le générateur (BUG-07).
        stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, image))
        try:
            payload = json.dumps(stdin_payload).encode("utf-8")
            proc.stdin.write(payload)  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]

            while True:
                raw = await proc.stdout.readline()  # type: ignore[union-attr]
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not text:
                    continue
                try:
                    yield json.loads(text)
                except json.JSONDecodeError:
                    log.warning("docker_runner.invalid_line", line=text)
                    yield {"type": "_invalid_line", "raw": text}

            returncode = await proc.wait()
        finally:
            if proc.returncode is None:  # consommateur parti / exception : on tue
                proc.kill()
                await proc.wait()
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await stderr_task
    log.info("docker_runner.exit", image=image, returncode=returncode)
    yield {"type": "_exit", "returncode": returncode}


async def _drain_stderr(stream: asyncio.StreamReader | None, image: str) -> None:
    """Lit stderr en continu et le logge, pour éviter le blocage du pipe (BUG-06)."""
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if text:
            log.debug("docker_runner.stderr", image=image, line=text)
