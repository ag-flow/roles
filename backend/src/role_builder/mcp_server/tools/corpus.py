"""Adaptateur MCP — `roles__get_corpus` (spec v2/01-protocole-mcp.md §2.4).

`caller` est l'identité déclarée de l'appelant (même modèle que
`submitted_by` à la soumission, §5.3) : elle porte le curseur `only_new`.
Le tool ne retourne que des références docflow — jamais le contenu.
"""

from __future__ import annotations

from typing import Any

from role_builder.db import db_pool
from role_builder.services.acquisition.corpus import get_corpus as _get_corpus
from role_builder.services.acquisition.errors import AcquisitionError


async def get_corpus(
    request_key: str,
    *,
    caller: str | None = None,
    only_new: bool = False,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Références docflow des transcripts déjà déposés, à tout moment.

    `only_new=true` : uniquement les items déposés depuis le dernier
    `get_corpus` de cet appelant (curseur serveur par (request_key, caller)).
    `caller` est optionnel (défaut partagé) — conforme à la signature spec
    `get_corpus(request_key, only_new?, cursor?)` ; le passer isole le curseur
    only_new par appelant. `cursor` (ISO 8601) : alternative stateless,
    prioritaire sur le curseur serveur et sans effet sur lui. La lecture du
    texte : `docflow__get_document`.
    """
    try:
        return await _get_corpus(
            request_key,
            caller=caller,
            only_new=only_new,
            cursor=cursor,
            pool=db_pool.pool,
        )
    except AcquisitionError as exc:
        return exc.to_dict()
