"""Test que le VaultResolver échoue proprement si aucun token n'est configuré."""
from __future__ import annotations

import os

import pytest


def test_vault_resolver_raises_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """VaultResolver() lève RuntimeError si aucun HARPOCRATE_API_TOKEN_* n'est défini."""
    # Supprimer tous les tokens Harpocrate présents dans l'environnement
    for key in list(os.environ):
        if key.startswith("HARPOCRATE_API_TOKEN_"):
            monkeypatch.delenv(key, raising=False)

    from role_builder.services.vault_resolver import VaultResolver

    with pytest.raises(RuntimeError, match="No Harpocrate API key configured"):
        VaultResolver()
