"""Test que le VaultResolver échoue proprement si aucun token n'est configuré."""
from __future__ import annotations

import pytest


def test_vault_resolver_raises_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """VaultResolver() lève RuntimeError si HARPOCRATE_API_TOKEN n'est pas défini."""
    monkeypatch.delenv("HARPOCRATE_API_TOKEN", raising=False)

    from role_builder.services.vault_resolver import VaultResolver

    with pytest.raises(RuntimeError, match="No Harpocrate API key configured"):
        VaultResolver()
