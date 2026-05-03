"""Tests unitaires pour VaultResolver."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from role_builder.services.vault_resolver import VaultResolver


def _make_resolver(monkeypatch: pytest.MonkeyPatch, token: str = "hrpv_1_fake") -> VaultResolver:
    monkeypatch.setenv("HARPOCRATE_API_TOKEN", token)
    monkeypatch.setenv("HARPOCRATE_API_URL", "https://vault.yoops.org")
    mock_client = MagicMock()
    mock_client.secrets.get.side_effect = lambda k: f"resolved_{k}"
    with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
        return VaultResolver()


def test_no_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARPOCRATE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="No Harpocrate API key configured"):
        VaultResolver()


def test_resolve_vault_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARPOCRATE_API_TOKEN", "hrpv_1_fake")
    mock_client = MagicMock()
    mock_client.secrets.get.return_value = "sk-mistral-abc123"
    with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
        r = VaultResolver()
        result = r.resolve("${vault://api1:mistral_api_key}")
    assert result == "sk-mistral-abc123"
    mock_client.secrets.get.assert_called_once_with("mistral_api_key")


def test_non_vault_ref_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_resolver(monkeypatch)
    assert r.resolve("plain_value") == "plain_value"
    assert r.resolve("") == ""
    assert r.resolve("https://api.mistral.ai") == "https://api.mistral.ai"


def test_cache_avoids_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARPOCRATE_API_TOKEN", "hrpv_1_fake")
    mock_client = MagicMock()
    mock_client.secrets.get.return_value = "cached_value"
    with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
        r = VaultResolver()
        r.resolve("${vault://api1:my_secret}")
        r.resolve("${vault://api1:my_secret}")
    mock_client.secrets.get.assert_called_once()


def test_resolve_embedded_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_resolver(monkeypatch)
    result = r.resolve("postgresql://rb:${vault://api1:pg_pass}@localhost/rb")
    assert result == "postgresql://rb:resolved_pg_pass@localhost/rb"


def test_resolve_settings_patches_vault_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_resolver(monkeypatch)
    from role_builder.config import Settings
    s = Settings(
        database_url="postgresql://rb:pass@localhost/rb",
        minio_endpoint="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        mistral_api_key="${vault://api1:mistral_api_key}",
        local_admin_password="${vault://api1:local_admin_password}",
    )
    r.resolve_settings(s)
    assert s.mistral_api_key == "resolved_mistral_api_key"
    assert s.local_admin_password == "resolved_local_admin_password"
    assert s.database_url == "postgresql://rb:pass@localhost/rb"


def test_resolve_settings_leaves_non_str_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_resolver(monkeypatch)
    from role_builder.config import Settings
    s = Settings(
        database_url="postgresql://rb:pass@localhost/rb",
        minio_endpoint="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        max_concurrent_scrapers=7,
    )
    r.resolve_settings(s)
    assert s.max_concurrent_scrapers == 7


def test_secret_not_found_raises_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from harpocrate import SecretNotFound
    monkeypatch.setenv("HARPOCRATE_API_TOKEN", "hrpv_1_fake")
    mock_client = MagicMock()
    mock_client.secrets.get.side_effect = SecretNotFound("mistral_api_key not found")
    with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
        r = VaultResolver()
        with pytest.raises(RuntimeError, match="mistral_api_key"):
            r.resolve("${vault://api1:mistral_api_key}")


def test_auth_refused_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from harpocrate.exceptions import VaultHttpError
    monkeypatch.setenv("HARPOCRATE_API_TOKEN", "hrpv_1_fake")
    mock_client = MagicMock()
    mock_client.secrets.get.side_effect = VaultHttpError(401, "Unauthorized")
    with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
        r = VaultResolver()
        with pytest.raises(RuntimeError, match="refused.*401"):
            r.resolve("${vault://api1:mistral_api_key}")
        with pytest.raises(RuntimeError, match="refused.*401"):
            r.resolve("${vault://api1:mistral_api_key}")


def test_other_http_error_propagates_with_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from harpocrate.exceptions import VaultHttpError
    monkeypatch.setenv("HARPOCRATE_API_TOKEN", "hrpv_1_fake")
    mock_client = MagicMock()
    mock_client.secrets.get.side_effect = VaultHttpError(503, "Service Unavailable")
    with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
        r = VaultResolver()
        with pytest.raises(RuntimeError, match="503"):
            r.resolve("${vault://api1:some_secret}")
