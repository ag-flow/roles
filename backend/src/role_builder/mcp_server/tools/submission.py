"""Adaptateur MCP — `roles__submit_acquisition` (spec v2/01-protocole-mcp.md §2.1).

Couche fine : résout `tenant_id`/`today`/`pool`, délègue au service, et
convertit `AcquisitionError` en enveloppe `{"error": {...}}` — le format
d'erreur uniforme (§5.6) fait partie du contrat du tool, pas du protocole
MCP, donc on ne laisse pas l'exception remonter comme erreur de transport.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from role_builder.config import TENANT_ID_DEFAULT
from role_builder.db import db_pool
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.submission import submit_acquisition as _submit_acquisition


async def submit_acquisition(
    url: str,
    *,
    submitted_by: str,
    platform: Literal["youtube", "instagram", "tiktok"] | None = None,
    mode: Literal["discover_only", "auto"] = "discover_only",
    filters: dict[str, Any] | None = None,
    docflow_target: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Soumet une acquisition (chaîne, playlist, compte ou vidéo unique).

    `mode="discover_only"` (défaut) découvre toute la source et s'arrête ;
    `mode="auto"` sélectionne automatiquement selon `filters` puis lance le
    téléchargement. Retourne `{request_key, status, platform, url}`, ou
    `{"error": {code, message, details}}` sur échec.
    """
    try:
        return await _submit_acquisition(
            url=url,
            submitted_by=submitted_by,
            tenant_id=TENANT_ID_DEFAULT,
            platform=platform,
            mode=mode,
            filters=filters,
            docflow_target=docflow_target,
            note=note,
            today=datetime.now(UTC).date(),
            pool=db_pool.pool,
        )
    except AcquisitionError as exc:
        return exc.to_dict()
