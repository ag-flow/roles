"""Sélection automatique post-découverte pour `mode=auto` (spec §2.1, §3).

Appelé par `event_handlers.handle_scraper_event` sur l'event `discovered`,
quand la source est rattachée à une acquisition_request — c'est le seul
point où la couche requête se branche sur le pipeline scraper existant
sans le réécrire (cf. CLAUDE.md §Points d'attention).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.selection import (
    apply_selection,
    resolve_item_ids_from_filters,
)


async def on_discovery_complete(
    request: dict[str, Any],
    *,
    source_id: UUID,
    tenant_id: UUID,
    pool: asyncpg.Pool,
) -> None:
    """`mode=auto` : applique les filtres et enqueue le download automatiquement.
    `mode=discover_only` : marque simplement la requête `discovered`, le pilote
    appellera `list_discovered` puis `select_items` lui-même.
    """
    if request["mode"] != "auto":
        await ar.update_status(request["request_key"], "discovered", pool=pool)
        return

    filters = json.loads(request["filters"]) if request["filters"] else None
    item_ids = await resolve_item_ids_from_filters(source_id, filters, pool=pool)

    source = await sources_helper.get_source(source_id, pool=pool)
    await apply_selection(
        source_id=source_id,
        tenant_id=tenant_id,
        item_ids=item_ids,
        credentials_id=source.get("credentials_id") if source else None,
        pool=pool,
    )
    await ar.update_status(request["request_key"], "acquiring", pool=pool)
