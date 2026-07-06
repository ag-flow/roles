"""roles__select_items — sélection des items à télécharger/transcrire (spec §2.1).

Idempotent (un item déjà sélectionné + déjà en download ne recrée pas de
job) et cumulable (jamais de désélection automatique) — cf. §2.1.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.filters import resolve_item_filters


async def select_items(
    *,
    request_key: str,
    item_ids: list[UUID] | None,
    filters: dict[str, Any] | None,
    pool: asyncpg.Pool,
) -> dict[str, int]:
    """Résout la requête, puis les item_ids (explicites ou via filters), puis applique."""
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None:
        raise AcquisitionError("UNKNOWN_REQUEST", f"no acquisition request {request_key!r}")
    if request["status"] == "cancelled":
        raise AcquisitionError(
            "ALREADY_CANCELLED", f"request {request_key!r} is cancelled — no new selection"
        )

    source_id = request["source_id"]
    source = await sources_helper.get_source(source_id, pool=pool)

    resolved_ids = (
        item_ids
        if item_ids is not None
        else await resolve_item_ids_from_filters(source_id, filters, pool=pool)
    )

    result = await apply_selection(
        source_id=source_id,
        tenant_id=request["tenant_id"],
        item_ids=resolved_ids,
        credentials_id=source.get("credentials_id") if source else None,
        pool=pool,
    )

    # Cycle deux temps (§3) : select_items fait franchir discovering/discovered
    # -> acquiring. N'avance jamais une requête déjà acquiring/cancelled.
    if request["status"] in ("discovering", "discovered"):
        await ar.update_status(request_key, "acquiring", pool=pool)

    return result


async def resolve_item_ids_from_filters(
    source_id: UUID, filters: dict[str, Any] | None, *, pool: asyncpg.Pool
) -> list[UUID]:
    """Traduit les filtres déclaratifs en liste d'item_ids matchant (§2.1)."""
    kwargs = resolve_item_filters(filters)
    limit = kwargs.pop("limit", 10_000)
    rows = await source_items_helper.list_items_by_source(
        source_id, limit=limit, offset=0, pool=pool, **kwargs
    )
    return [row["id"] for row in rows]


async def apply_selection(
    *,
    source_id: UUID,
    tenant_id: UUID,
    item_ids: list[UUID],
    credentials_id: UUID | None,
    pool: asyncpg.Pool,
) -> dict[str, int]:
    """Marque `selected` puis enqueue un download job par item pas déjà en vol."""
    selected_count = await source_items_helper.select_items(
        source_id, item_ids, deselect_others=False, pool=pool
    )

    queued_count = 0
    for item_id in item_ids:
        if await scraping_jobs_helper.get_active_job_for_item(item_id, "download", pool=pool):
            continue
        item = await source_items_helper.get_by_id(item_id, pool=pool)
        # Vérifie l'appartenance à la source : un item d'une autre requête ne
        # doit pas obtenir un download job sous ce source_id/tenant (BUG-13).
        if item is None or item["source_id"] != source_id:
            continue
        if item["status"] != "pending_download":
            continue
        await scraping_jobs_helper.insert_job(
            source_id=source_id,
            source_item_id=item_id,
            tenant_id=tenant_id,
            command="download",
            credentials_id=credentials_id,
            priority=0,
            pool=pool,
        )
        queued_count += 1

    return {"selected_count": selected_count, "queued_count": queued_count}
