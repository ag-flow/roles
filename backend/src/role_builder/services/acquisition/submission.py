"""roles__submit_acquisition — soumission d'une acquisition (spec §2.1).

Crée la source + l'acquisition_request + le job de découverte, puis rend
la main immédiatement (`status=discovering`) : le pipeline scraper
existant (orchestrator + event_handlers) fait le reste, inchangé — cette
fonction ne fait que le brancher au-dessus d'une requête tracée.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

from role_builder.db_helpers import credentials as credentials_helper
from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.filters import resolve_item_filters
from role_builder.services.acquisition.platform_detection import deduce_platform, infer_source_type
from role_builder.services.acquisition.request_creation import insert_request_with_retry
from role_builder.services.acquisition.request_key import build_request_key_base


async def submit_acquisition(
    *,
    url: str,
    submitted_by: str,
    tenant_id: UUID,
    platform: str | None = None,
    mode: str = "discover_only",
    filters: dict[str, Any] | None = None,
    docflow_target: dict[str, Any] | None = None,
    note: str | None = None,
    today: date,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Soumet une acquisition. Retourne `{request_key, status, platform, url}`.

    Raises:
        AcquisitionError(INVALID_URL | UNSUPPORTED_PLATFORM | NO_CREDENTIALS)
    """
    resolved_platform = deduce_platform(url, platform_hint=platform)

    # Valide les filtres au bord : un mode=auto aux filtres invalides doit
    # échouer ici (INVALID_FILTERS) plutôt que de bloquer la requête en
    # `discovering` à l'event `discovered` (résolution auto), sans signal.
    resolve_item_filters(filters)

    credential = await credentials_helper.get_active_credential_for_platform(
        resolved_platform, pool=pool
    )
    if credential is None:
        raise AcquisitionError(
            "NO_CREDENTIALS", f"no active credential for platform {resolved_platform!r}"
        )

    source_id = await sources_helper.insert_source(
        role_project_id=None,
        tenant_id=tenant_id,
        platform=resolved_platform,
        source_type=infer_source_type(resolved_platform, url),
        url=url,
        credentials_id=credential["id"],
        pool=pool,
    )

    base_key = build_request_key_base(resolved_platform, url, note=note, today=today)
    request_key = await insert_request_with_retry(
        base_key,
        tenant_id=tenant_id,
        submitted_by=submitted_by,
        kind="scrape",
        source_id=source_id,
        mode=mode,
        filters=filters,
        docflow_target=docflow_target,
        note=note,
        status="discovering",
        pool=pool,
    )

    await scraping_jobs_helper.insert_job(
        source_id=source_id,
        source_item_id=None,
        tenant_id=tenant_id,
        command="discover",
        credentials_id=credential["id"],
        priority=0,
        pool=pool,
    )

    return {
        "request_key": request_key,
        "status": "discovering",
        "platform": resolved_platform,
        "url": url,
    }
