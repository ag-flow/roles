"""roles__get_corpus — récupération incrémentale du corpus (spec §2.4).

Retourne les **références** docflow des items déposés, jamais le contenu :
la lecture du texte passe par `docflow__get_document` (§1 point 3). Le mode
`only_new` s'appuie sur un curseur serveur par `(request_key, caller)`
(table `corpus_pull_cursors`) ; `cursor` explicite (ISO 8601) est
l'alternative stateless et ne touche pas le curseur stocké.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import corpus_pull_cursors as cursors_helper
from role_builder.db_helpers import deposit_queue
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.status_shape import derive_display_status, fold_counts

_TERMINAL_DISPLAY_STATUSES = {"completed", "partially_failed", "cancelled"}


async def get_corpus(
    request_key: str,
    *,
    caller: str,
    only_new: bool = False,
    cursor: str | None = None,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None:
        raise AcquisitionError("UNKNOWN_REQUEST", f"no acquisition request {request_key!r}")

    stateless = cursor is not None
    since: datetime | None = None
    if stateless:
        since = _parse_cursor(cursor)
    elif only_new:
        since = await cursors_helper.get_last_pulled_at(request["id"], caller, pool=pool)

    source_id = request["source_id"]
    source = await sources_helper.get_source(source_id, pool=pool) if source_id else None
    rows = (
        await deposit_queue.list_deposited_for_source(source_id, since=since, pool=pool)
        if source_id
        else []
    )
    failed_rows = (
        await source_items_helper.list_items_by_source(
            source_id, status="failed", limit=10_000, offset=0, pool=pool
        )
        if source_id
        else []
    )
    counts = fold_counts(
        await source_items_helper.count_by_status(source_id, pool=pool) if source_id else []
    )
    display_status = derive_display_status(
        request["status"], counts, selected_total=counts["selected"]
    )

    # « Depuis le dernier get_corpus de cet appelant » : tout pull non
    # stateless avance le curseur au dépôt le plus récent servi.
    latest = rows[-1]["deposited_at"] if rows else None
    if not stateless and latest is not None:
        await cursors_helper.upsert_cursor(request["id"], caller, latest, pool=pool)

    return {
        "request_key": request_key,
        "complete": display_status in _TERMINAL_DISPLAY_STATUSES,
        "documents": [_shape_document(row, source) for row in rows],
        "failed_items": [
            {"item_id": row["id"], "title": row.get("title"), "error": row.get("error")}
            for row in failed_rows
        ],
        "next_cursor": latest.isoformat() if latest else cursor,
    }


def _parse_cursor(cursor: str) -> datetime:
    try:
        return datetime.fromisoformat(cursor)
    except ValueError as exc:
        raise AcquisitionError(
            "INVALID_CURSOR",
            f"cursor {cursor!r} is not an ISO 8601 timestamp",
        ) from exc


def _shape_document(row: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
    """Réfs + métadonnées d'un item déposé — aucun texte de transcript.

    `source_url` = URL de la source d'origine (l'URL par item n'est pas
    conservée par les scrapers actuels, cf. DepositWorker._build_metadata).
    """
    published_at = row.get("published_at")
    return {
        "item_id": row["id"],
        "docflow": {
            "doc_id": row["docflow_doc_id"],
            "slug": row["docflow_slug"],
            "title": row.get("title"),
        },
        "metadata": {
            "platform": source["platform"] if source else None,
            "source_url": source["url"] if source else None,
            "duration_s": row.get("duration_s"),
            "published_at": published_at.isoformat() if published_at else None,
            "provider": row.get("provider_used"),
        },
    }
