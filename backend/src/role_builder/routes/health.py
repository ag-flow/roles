"""Health-check endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from role_builder.db import db_pool

log = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, object]:
    """Return ok with db=true|false. Never 5xx — DB outage shouldn't crash the probe."""
    try:
        async with db_pool.pool.acquire() as conn:
            db_ok = await conn.fetchval("SELECT 1") == 1
    except Exception:
        # Repli VOLONTAIRE : la sonde doit répondre 200 même base morte, sinon
        # l'orchestrateur tue un conteneur qui n'a qu'une base indisponible.
        # Mais la cause est journalisée : avaler l'exception sans trace rendait
        # un « db: false » indiagnosticable depuis les journaux centralisés.
        log.exception("health.db_probe_failed")
        db_ok = False
    return {"status": "ok", "db": db_ok}
