"""Résolution des filtres déclaratifs (§2.1) vers les kwargs de
`source_items.list_items_by_source`.

Les filtres viennent du pilote (via la façade MCP) : ils sont validés ici et
toute valeur mal formée lève `AcquisitionError("INVALID_FILTERS")` — jamais
une `ValueError`/`PostgresError` de transport (§5.6). Validés au bord
(submit + select_items) pour qu'un `mode=auto` aux filtres invalides soit
rejeté à la soumission plutôt que de bloquer la requête en `discovering`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from role_builder.services.acquisition.errors import AcquisitionError

_DATE_KEYS = {"since": "since_date", "until": "until_date"}
_INT_KEYS = ("min_duration_s", "max_duration_s")


def resolve_item_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Traduit `{max_items?, since?, until?, min/max_duration_s?, title_contains?}`
    en kwargs pour `list_items_by_source` (`limit`, `since_date`, `until_date`, ...).

    `filters=None` ou `{}` → dict vide, équivalent à "aucun filtre" (match all).

    Raises:
        AcquisitionError(INVALID_FILTERS)
    """
    if not filters:
        return {}

    resolved: dict[str, Any] = {}
    for key in _INT_KEYS:
        if filters.get(key) is not None:
            resolved[key] = _as_non_negative_int(key, filters[key])
    if filters.get("title_contains") is not None:
        value = filters["title_contains"]
        if not isinstance(value, str):
            raise AcquisitionError("INVALID_FILTERS", "title_contains must be a string")
        resolved["title_contains"] = value
    for source_key, target_key in _DATE_KEYS.items():
        if filters.get(source_key) is not None:
            resolved[target_key] = _parse_date(source_key, filters[source_key])
    if filters.get("max_items") is not None:
        resolved["limit"] = _as_positive_int("max_items", filters["max_items"])
    return resolved


def _as_non_negative_int(key: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AcquisitionError("INVALID_FILTERS", f"{key} must be a non-negative integer")
    return value


def _as_positive_int(key: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcquisitionError("INVALID_FILTERS", f"{key} must be a positive integer")
    return value


def _parse_date(key: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise AcquisitionError("INVALID_FILTERS", f"{key} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AcquisitionError(
            "INVALID_FILTERS", f"{key} {value!r} is not an ISO 8601 timestamp"
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
