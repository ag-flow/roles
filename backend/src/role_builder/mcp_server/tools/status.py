"""Adaptateurs MCP — `roles__request_status` / `roles__list_requests` (spec §2.3)."""

from __future__ import annotations

from typing import Any

from role_builder.db import db_pool
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.status import list_requests as _list_requests
from role_builder.services.acquisition.status import request_status as _request_status


async def request_status(request_key: str) -> dict[str, Any]:
    """Statut détaillé d'une requête : counts, items résumés, coût, queue_position."""
    try:
        return await _request_status(request_key, pool=db_pool.pool)
    except AcquisitionError as exc:
        return exc.to_dict()


async def list_requests(
    status: str | None = None,
    submitted_by: str | None = None,
) -> list[dict[str, Any]]:
    """Reprise conversationnelle et vue multi-acteurs des requêtes."""
    return await _list_requests(status=status, submitted_by=submitted_by, pool=db_pool.pool)
