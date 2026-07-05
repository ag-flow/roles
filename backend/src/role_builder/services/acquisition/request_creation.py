"""Insertion d'une acquisition_request avec unicité du request_key garantie.

Partagé entre la soumission scrape (§2.1) et l'ouverture d'une requête
upload (§2.2) : `acquisition_requests.insert_request` propage
`asyncpg.UniqueViolationError` sur collision, ici levée par retry avec un
suffixe aléatoire (cf. `request_key.with_random_suffix`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.services.acquisition.request_key import with_random_suffix

_MAX_KEY_ATTEMPTS = 5


async def insert_request_with_retry(
    base_key: str,
    *,
    tenant_id: UUID,
    submitted_by: str,
    kind: str,
    source_id: UUID,
    mode: str | None,
    filters: dict[str, Any] | None,
    docflow_target: dict[str, Any] | None,
    note: str | None,
    status: str,
    pool: asyncpg.Pool,
) -> str:
    """Insère l'acquisition_request, retente avec un suffixe aléatoire sur collision."""
    candidate = base_key
    for _ in range(_MAX_KEY_ATTEMPTS):
        try:
            await ar.insert_request(
                request_key=candidate,
                tenant_id=tenant_id,
                submitted_by=submitted_by,
                kind=kind,
                source_id=source_id,
                mode=mode,
                filters=filters,
                docflow_target=docflow_target,
                note=note,
                status=status,
                pool=pool,
            )
        except asyncpg.UniqueViolationError:
            candidate = with_random_suffix(base_key)
            continue
        return candidate
    raise RuntimeError(f"could not generate a unique request_key from base {base_key!r}")
