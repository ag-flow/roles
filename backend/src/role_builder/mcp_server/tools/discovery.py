"""Adaptateurs MCP — `roles__list_discovered` / `roles__select_items` (spec §2.1)."""

from __future__ import annotations

from typing import Any

from role_builder.db import db_pool
from role_builder.mcp_server.tools.parsing import parse_item_ids
from role_builder.services.acquisition.discovery import list_discovered as _list_discovered
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.selection import select_items as _select_items


async def list_discovered(
    request_key: str,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Liste enrichie des items découverts (titre, extrait, tags, durée) — aucune thématisation."""
    try:
        return await _list_discovered(
            request_key=request_key, cursor=cursor, limit=limit, pool=db_pool.pool
        )
    except AcquisitionError as exc:
        return exc.to_dict()


async def select_items(
    request_key: str,
    item_ids: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sélectionne les items à télécharger/transcrire — idempotent, cumulable."""
    try:
        return await _select_items(
            request_key=request_key, item_ids=parse_item_ids(item_ids),
            filters=filters, pool=db_pool.pool,
        )
    except AcquisitionError as exc:
        return exc.to_dict()
