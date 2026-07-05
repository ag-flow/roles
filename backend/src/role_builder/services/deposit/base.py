"""Interface de dépôt d'un transcript dans docflow (spec v2/01 §3, §5.2).

Un dépôt = un document docflow par vidéo (type `transcript`), métadonnées :
plateforme, URL source, durée, date, request_key, provider. Le worker de
dépôt ne dépend que de ce protocol — l'implémentation réelle (passerelle)
et le stub local sont interchangeables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class DepositResult:
    """Références docflow retournées par un dépôt réussi."""

    doc_id: str
    slug: str


class DepositFailedError(Exception):
    """Échec de dépôt (après épuisement des retries côté implémentation).

    Le worker la convertit en item `failed` avec
    ``error.code=DOCFLOW_DEPOSIT_FAILED`` ; le transcript reste dans MinIO.
    """


class CorpusDepositor(Protocol):
    """Contrat de dépôt d'un transcript — une implémentation par backend."""

    async def deposit(
        self,
        *,
        item: dict[str, Any],
        transcript_text: str,
        metadata: dict[str, Any],
    ) -> DepositResult:
        """Dépose le texte + métadonnées, retourne les refs docflow créées."""
        ...
