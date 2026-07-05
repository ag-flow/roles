"""roles__request_status / roles__list_requests — suivi (spec §2.3).

`completed`/`partially_failed` sont toujours **calculés** à la lecture
(cf. status_shape.derive_display_status), jamais stockés : leur détection
dépend de l'état courant des items (dépôt docflow inclus), qui évolue en
dehors de cette façade. Limite assumée pour ce lot : le filtre `status` de
`list_requests` ne porte que sur les stades stockés (discovering/
discovered/acquiring/cancelled) — filtrer par "completed" nécessitera le
dépôt docflow (lot suivant).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.db_helpers import transcription_jobs as transcription_jobs_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.status_shape import derive_display_status, fold_counts


async def request_status(request_key: str, *, pool: asyncpg.Pool) -> dict[str, Any]:
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None:
        raise AcquisitionError("UNKNOWN_REQUEST", f"no acquisition request {request_key!r}")

    source_id = request["source_id"]
    counts = fold_counts(
        await source_items_helper.count_by_status(source_id, pool=pool) if source_id else []
    )
    items_rows = (
        await source_items_helper.list_items_by_source(source_id, limit=50, offset=0, pool=pool)
        if source_id
        else []
    )
    cost = (
        await transcription_jobs_helper.sum_cost_for_source(source_id, pool=pool)
        if source_id
        else 0.0
    )
    queue_position = await compute_queue_position(source_id, pool=pool) if source_id else None

    result: dict[str, Any] = {
        "request_key": request["request_key"],
        "kind": request["kind"],
        "status": derive_display_status(
            request["status"], counts, selected_total=counts["selected"]
        ),
        "submitted_by": request["submitted_by"],
        "submitted_at": request["created_at"].isoformat(),
        "counts": counts,
        "items": [_shape_item_summary(row) for row in items_rows],
        "cost": {"transcription_usd": cost},
    }
    if queue_position is not None:
        result["queue_position"] = queue_position
    return result


async def list_requests(
    *,
    status: str | None = None,
    submitted_by: str | None = None,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    rows = await ar.list_requests(status=status, submitted_by=submitted_by, pool=pool)
    result = []
    for row in rows:
        source_id = row["source_id"]
        source = await sources_helper.get_source(source_id, pool=pool) if source_id else None
        counts = fold_counts(
            await source_items_helper.count_by_status(source_id, pool=pool) if source_id else []
        )
        result.append(
            {
                "request_key": row["request_key"],
                "kind": row["kind"],
                "status": derive_display_status(
                    row["status"], counts, selected_total=counts["selected"]
                ),
                "url": source["url"] if source else None,
                "counts_summary": counts,
                "submitted_by": row["submitted_by"],
                "submitted_at": row["created_at"].isoformat(),
            }
        )
    return result


async def compute_queue_position(source_id: UUID, *, pool: asyncpg.Pool) -> int | None:
    """Position dans la queue partagée scraping_jobs (discover/download).

    Ne couvre que scraping_jobs : la queue transcription a son propre
    modèle de pools (shared_default / user_X, cf. spec 04), pas une FIFO
    globale comparable. None si aucun job pending pour cette source.
    """
    async with pool.acquire() as conn:
        head = await conn.fetchrow(
            "SELECT priority, created_at FROM scraping_jobs "
            "WHERE source_id = $1 AND status = 'pending' "
            "ORDER BY priority DESC, created_at ASC LIMIT 1",
            source_id,
        )
        if head is None:
            return None
        ahead = await conn.fetchval(
            "SELECT count(*) FROM scraping_jobs WHERE status = 'pending' "
            "AND (priority > $1 OR (priority = $1 AND created_at < $2))",
            head["priority"],
            head["created_at"],
        )
    return int(ahead) + 1


def _shape_item_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": row["id"],
        "title": row.get("title"),
        "duration_s": row.get("duration_s"),
        "status": row["status"],
        "error": row.get("error"),
    }
