"""Wrapper subprocess pour `docker run -i` avec stream NDJSON.

L'orchestrator Phase C utilise ce module pour lancer les containers
scrapers one-shot, leur envoyer une tâche JSON sur stdin, et streamer
les events NDJSON sur stdout. Un event terminal `_exit` est yieldé
avec le returncode pour permettre à l'appelant de marquer le job
done/failed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

log = structlog.get_logger(__name__)


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
    env_args: list[str] = []
    for key, value in env.items():
        env_args.extend(["-e", f"{key}={value}"])

    extras = extra_args or []
    cmd = ["docker", "run", "--rm", "-i", *env_args, image, *extras]

    log.info("docker_runner.start", image=image, env_keys=list(env.keys()))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Write payload + close stdin so the container can exit normally.
    payload = json.dumps(stdin_payload).encode("utf-8")
    proc.stdin.write(payload)  # type: ignore[union-attr]
    proc.stdin.close()  # type: ignore[union-attr]

    # Stream stdout line-by-line.
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
    log.info("docker_runner.exit", image=image, returncode=returncode)
    yield {"type": "_exit", "returncode": returncode}
