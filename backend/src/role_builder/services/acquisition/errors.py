"""Erreur métier façade MCP — format uniforme {code, message, details} (spec §5.6)."""

from __future__ import annotations

from typing import Any


class AcquisitionError(Exception):
    """Erreur métier portant un code stable, consommée par l'adaptateur MCP.

    L'adaptateur MCP (mcp_server/tools/*) catch cette exception et la
    convertit en payload de retour ``{"error": {...}}`` plutôt que de la
    laisser remonter comme erreur de transport : le format d'erreur fait
    partie du contrat du tool, pas du protocole.
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}
