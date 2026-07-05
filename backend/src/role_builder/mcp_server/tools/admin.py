"""Adaptateurs MCP — `roles__cancel_request` / `roles__retry_failed` (spec §2.5)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from role_builder.db import db_pool
from role_builder.services.acquisition.admin import cancel_request as _cancel_request
from role_builder.services.acquisition.admin import retry_failed as _retry_failed
from role_builder.services.acquisition.errors import AcquisitionError


async def cancel_request(request_key: str, note: str | None = None) -> dict[str, Any]:
    """Annule les jobs pending/claimed ; les items déjà déposés restent dans docflow."""
    try:
        return await _cancel_request(request_key, note, pool=db_pool.pool)
    except AcquisitionError as exc:
        return exc.to_dict()


async def retry_failed(
    request_key: str, item_ids: list[str] | None = None
) -> dict[str, Any]:
    """Re-queue les items `failed` (tous, ou une sélection explicite)."""
    try:
        resolved_ids = [UUID(item_id) for item_id in item_ids] if item_ids is not None else None
        return await _retry_failed(request_key, resolved_ids, pool=db_pool.pool)
    except AcquisitionError as exc:
        return exc.to_dict()
