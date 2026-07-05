"""roles__list_discovered — liste enrichie des items découverts (spec §2.1).

Aucune thématisation ici : titre + extrait + tags suffisent au pilote, qui
fait le travail de jugement lui-même (§1 point 5).
"""

from __future__ import annotations

from typing import Any

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.errors import AcquisitionError


async def list_discovered(
    *,
    request_key: str,
    cursor: str | None,
    limit: int,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None:
        raise AcquisitionError("UNKNOWN_REQUEST", f"no acquisition request {request_key!r}")

    source_id = request["source_id"]
    source = await sources_helper.get_source(source_id, pool=pool) if source_id else None

    offset = int(cursor) if cursor else 0
    rows = (
        await source_items_helper.list_items_by_source(
            source_id, limit=limit + 1, offset=offset, pool=pool
        )
        if source_id
        else []
    )
    has_more = len(rows) > limit
    page = rows[:limit]

    return {
        "request_key": request_key,
        "discovery_complete": source is not None and source["status"] != "pending_discovery",
        "items": [_shape_item(row) for row in page],
        "next_cursor": str(offset + limit) if has_more else None,
    }


def _shape_item(row: dict[str, Any]) -> dict[str, Any]:
    published_at = row.get("published_at")
    return {
        "item_id": row["id"],
        "title": row.get("title"),
        "description_excerpt": row.get("description_excerpt"),
        "tags": row.get("tags") or [],
        "duration_s": row.get("duration_s"),
        "published_at": published_at.isoformat() if published_at else None,
        "thumbnail_url": row.get("thumbnail_url"),
        "already_selected": bool(row.get("selected", False)),
    }
