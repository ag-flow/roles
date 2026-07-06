"""Parsing défensif des entrées des tools MCP → AcquisitionError (§5.6).

Convertir un `item_id`/`cursor` mal formé en `AcquisitionError` (et non en
`ValueError` de transport) garde le contrat d'erreur uniforme du tool : les
adaptateurs `except AcquisitionError` renvoient alors `{"error": {...}}` au
lieu de laisser fuiter un message Python interne (BUG-27, BUG-28).
"""

from __future__ import annotations

from uuid import UUID

from role_builder.services.acquisition.errors import AcquisitionError


def parse_item_ids(item_ids: list[str] | None) -> list[UUID] | None:
    """Convertit une liste d'item_ids en UUID ; None reste None."""
    if item_ids is None:
        return None
    return [parse_item_id(item_id) for item_id in item_ids]


def parse_item_id(item_id: str) -> UUID:
    try:
        return UUID(str(item_id))
    except ValueError as exc:
        raise AcquisitionError(
            "INVALID_ITEM_ID", f"item_id {item_id!r} is not a valid UUID"
        ) from exc
