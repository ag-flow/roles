"""Sélection de l'implémentation CorpusDepositor selon la config.

`deposit_backend=stub` (défaut actuel) tant que le contrat de dépôt réel
n'est pas tranché (cf. gateway.py) ; `gateway` pour la passerelle MCP.
"""

from __future__ import annotations

from pathlib import Path

from role_builder.config import Settings
from role_builder.services.deposit.base import CorpusDepositor
from role_builder.services.deposit.gateway import GatewayDepositor
from role_builder.services.deposit.stub import StubDepositor


def build_depositor(settings: Settings) -> CorpusDepositor:
    """Instancie le depositor configuré ; ValueError si backend inconnu."""
    if settings.deposit_backend == "stub":
        return StubDepositor(output_dir=Path(settings.stub_deposit_dir))
    if settings.deposit_backend == "gateway":
        return GatewayDepositor()
    raise ValueError(
        f"deposit_backend inconnu : {settings.deposit_backend!r} (attendu : stub | gateway)"
    )
