"""GatewayDepositor — squelette du dépôt réel via la passerelle MCP.

Posture client docflow de la stack (fondations §3) : identité machine
propre auprès de la passerelle, écriture via `docflow__create_document`.
Volontairement non implémenté : deux questions ouvertes bloquent le
contrat (spec v2/01 §7, fondations §9) et ne doivent PAS être inventées ici.
"""

from __future__ import annotations

from typing import Any

from role_builder.services.deposit.base import DepositResult

_BLOCKED_MESSAGE = (
    "GatewayDepositor n'est pas implémenté : deux questions ouvertes de la "
    "spec bloquent le contrat de dépôt. "
    "1) Convention docflow_target par défaut (workspace/bloc par tenant ? "
    "par requête ?) — à aligner avec la spec docflow (v2/01 §7, fondations §9). "
    "2) L'identité machine de la stack auprès de la passerelle "
    "(provisioning ${vault://...}, rotation) — fondations §3 et §9. "
    "En attendant, utiliser StubDepositor (deposit_backend=stub)."
)


class GatewayDepositor:
    """Implémentation passerelle de CorpusDepositor — à câbler une fois la
    convention docflow_target et l'identité machine tranchées."""

    async def deposit(
        self,
        *,
        item: dict[str, Any],
        transcript_text: str,
        metadata: dict[str, Any],
    ) -> DepositResult:
        raise NotImplementedError(_BLOCKED_MESSAGE)
