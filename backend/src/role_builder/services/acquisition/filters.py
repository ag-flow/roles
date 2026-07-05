"""Résolution des filtres déclaratifs (§2.1) vers les kwargs de
`source_items.list_items_by_source`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_DATE_KEYS = {"since": "since_date", "until": "until_date"}
_PASSTHROUGH_KEYS = ("min_duration_s", "max_duration_s", "title_contains")


def resolve_item_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Traduit `{max_items?, since?, until?, min/max_duration_s?, title_contains?}`
    en kwargs pour `list_items_by_source` (`limit`, `since_date`, `until_date`, ...).

    `filters=None` ou `{}` → dict vide, équivalent à "aucun filtre" (match all).
    """
    if not filters:
        return {}

    resolved: dict[str, Any] = {}
    for key in _PASSTHROUGH_KEYS:
        if key in filters:
            resolved[key] = filters[key]
    for source_key, target_key in _DATE_KEYS.items():
        if source_key in filters:
            parsed = datetime.fromisoformat(filters[source_key])
            resolved[target_key] = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if "max_items" in filters:
        resolved["limit"] = filters["max_items"]
    return resolved
