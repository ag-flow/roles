"""Tests unitaires pour services/user_vault.py."""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from role_builder.services.user_vault import (
    UserVaultService,
    _email_hash,
    build_credentials_vault_name,
    build_github_vault_name,
    build_transcription_vault_path,
    build_vault_ref,
    build_vault_secret_name,
    extract_vault_path,
    get_service,
    init_service,
)


def _sha256(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# _email_hash
# ---------------------------------------------------------------------------


def test_email_hash_returns_sha256_hex() -> None:
    """Hash SHA-256 hex de l'email normalisé en minuscules."""
    result = _email_hash("John@Example.COM")
    assert result == _sha256("john@example.com")
    assert len(result) == 64


def test_email_hash_none_returns_no_email() -> None:
    """Email None → 'no_email'."""
    assert _email_hash(None) == "no_email"


def test_email_hash_empty_returns_no_email() -> None:
    """Email vide → 'no_email'."""
    assert _email_hash("") == "no_email"


def test_email_hash_is_deterministic() -> None:
    """Même email → même hash."""
    assert _email_hash("a@b.com") == _email_hash("a@b.com")


def test_email_hash_case_insensitive() -> None:
    """L'email est normalisé en minuscules avant le hash."""
    assert _email_hash("User@Example.com") == _email_hash("user@example.com")


def test_email_hash_no_pii_in_output() -> None:
    """Le hash ne contient pas l'email en clair."""
    h = _email_hash("secret@example.com")
    assert "secret" not in h
    assert "@" not in h
    assert "example" not in h


# ---------------------------------------------------------------------------
# build_vault_secret_name
# ---------------------------------------------------------------------------


def test_build_vault_secret_name_normal_email() -> None:
    """Email standard → chemin avec hash SHA-256."""
    key_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_vault_secret_name("john@example.com", "openai-whisper", key_id)
    expected_hash = _sha256("john@example.com")
    assert name == f"users/{expected_hash}/transcription/openai-whisper/{key_id}"


def test_build_vault_secret_name_no_pii_in_path() -> None:
    """L'email ne doit pas apparaître en clair dans le path."""
    key_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_vault_secret_name("llm.beard.family@gmail.com", "deepgram", key_id)
    assert "llm" not in name
    assert "beard" not in name
    assert "gmail" not in name
    assert "@" not in name


def test_build_vault_secret_name_none_email() -> None:
    """Email None → slug 'no_email'."""
    key_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_vault_secret_name(None, "deepgram", key_id)
    assert name.startswith("users/no_email/transcription/deepgram/")


def test_build_vault_secret_name_contains_key_id() -> None:
    """Le key_id doit apparaître en fin de chemin."""
    key_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    name = build_vault_secret_name("a@b.com", "assemblyai", key_id)
    assert str(key_id) in name


# ---------------------------------------------------------------------------
# UserVaultService.write / read / try_delete
# ---------------------------------------------------------------------------


def _make_fake_client(
    *,
    put_raises: Exception | None = None,
    create_raises: Exception | None = None,
    delete_raises: Exception | None = None,
    get_returns: str | None = "secret_value",
    get_raises: Exception | None = None,
) -> MagicMock:
    """Crée un VaultClient mock avec secrets.put/create/delete/get configurables."""
    mock_secrets = MagicMock()

    mock_secrets.put.side_effect = put_raises
    mock_secrets.create.side_effect = create_raises
    mock_secrets.delete.side_effect = delete_raises

    if get_raises:
        mock_secrets.get.side_effect = get_raises
    elif get_returns is not None:
        mock_secrets.get.return_value = get_returns
    else:
        from harpocrate import SecretNotFound
        mock_secrets.get.side_effect = SecretNotFound("not found")

    client = MagicMock()
    client.secrets = mock_secrets
    return client


@pytest.mark.asyncio
async def test_write_calls_put_when_secret_exists() -> None:
    """write() appelle put() si le secret existe déjà."""
    client = _make_fake_client()
    svc = UserVaultService(client)
    await svc.write("users/test/transcription/openai/uuid", "sk-test")
    client.secrets.put.assert_called_once_with(
        "users/test/transcription/openai/uuid", "sk-test"
    )
    client.secrets.create.assert_not_called()


@pytest.mark.asyncio
async def test_write_calls_create_when_secret_not_found() -> None:
    """write() bascule sur create() si put() lève SecretNotFound."""
    from harpocrate import SecretNotFound
    client = _make_fake_client(put_raises=SecretNotFound("not found"))
    svc = UserVaultService(client)
    await svc.write("users/test/transcription/openai/uuid", "sk-new")
    client.secrets.put.assert_called_once()
    client.secrets.create.assert_called_once_with(
        "users/test/transcription/openai/uuid", "sk-new"
    )


@pytest.mark.asyncio
async def test_read_returns_value() -> None:
    """read() retourne la valeur déchiffrée."""
    client = _make_fake_client(get_returns="sk-actual")
    svc = UserVaultService(client)
    result = await svc.read("users/test/transcription/openai/uuid")
    assert result == "sk-actual"


@pytest.mark.asyncio
async def test_read_returns_none_on_secret_not_found() -> None:
    """read() retourne None si SecretNotFound."""
    from harpocrate import SecretNotFound
    client = _make_fake_client(get_returns=None, get_raises=SecretNotFound("not found"))
    svc = UserVaultService(client)
    result = await svc.read("users/test/transcription/openai/missing")
    assert result is None


@pytest.mark.asyncio
async def test_try_delete_calls_delete() -> None:
    """try_delete() appelle delete() sur le client."""
    client = _make_fake_client()
    svc = UserVaultService(client)
    await svc.try_delete("users/test/transcription/openai/uuid")
    client.secrets.delete.assert_called_once_with(
        "users/test/transcription/openai/uuid"
    )


@pytest.mark.asyncio
async def test_try_delete_swallows_exceptions() -> None:
    """try_delete() ne propage pas les exceptions (best-effort)."""
    client = _make_fake_client(delete_raises=RuntimeError("vault down"))
    svc = UserVaultService(client)
    await svc.try_delete("users/test/transcription/openai/uuid")  # pas de raise


# ---------------------------------------------------------------------------
# Singleton init_service / get_service
# ---------------------------------------------------------------------------


def test_get_service_raises_if_not_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_service() lève RuntimeError si init_service n'a pas été appelé."""
    import role_builder.services.user_vault as uv_mod
    monkeypatch.setattr(uv_mod, "_service", None)
    with pytest.raises(RuntimeError, match="non initialisé"):
        get_service()


def test_init_service_sets_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """init_service() initialise le singleton, get_service() le retourne."""
    import role_builder.services.user_vault as uv_mod
    monkeypatch.setattr(uv_mod, "_service", None)
    fake_client = MagicMock()
    init_service(fake_client)
    svc = get_service()
    assert isinstance(svc, UserVaultService)
    # Nettoyage
    monkeypatch.setattr(uv_mod, "_service", None)


# ---------------------------------------------------------------------------
# build_credentials_vault_name
# ---------------------------------------------------------------------------


def test_build_credentials_vault_name_normal_email() -> None:
    """Email standard → chemin avec hash SHA-256."""
    cred_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_credentials_vault_name("john@example.com", "youtube", cred_id)
    assert name == f"users/{_sha256('john@example.com')}/scraping/youtube/{cred_id}"


def test_build_credentials_vault_name_no_pii_in_path() -> None:
    """L'email ne doit pas apparaître en clair dans le path."""
    cred_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_credentials_vault_name("john@example.com", "instagram", cred_id)
    assert "john" not in name
    assert "@" not in name


def test_build_credentials_vault_name_none_email() -> None:
    """Email None → slug 'no_email'."""
    cred_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_credentials_vault_name(None, "instagram", cred_id)
    assert name.startswith("users/no_email/scraping/instagram/")


def test_build_credentials_vault_name_cred_id_in_path() -> None:
    """Le cred_id doit apparaître en fin de chemin."""
    cred_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    name = build_credentials_vault_name("a@b.com", "tiktok", cred_id)
    assert str(cred_id) in name


# ---------------------------------------------------------------------------
# build_github_vault_name
# ---------------------------------------------------------------------------


def test_build_github_vault_name_normal() -> None:
    """user_id UUID + tenant_id → chemin github correct."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    tenant_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    name = build_github_vault_name(user_id, tenant_id)
    assert name == f"github/{tenant_id}/{user_id}"


# ---------------------------------------------------------------------------
# build_transcription_vault_path
# ---------------------------------------------------------------------------


def test_build_transcription_vault_path_normal_email() -> None:
    result = build_transcription_vault_path("john@example.com", "deepgram", "ma_cle")
    assert result == f"users/{_sha256('john@example.com')}/transcription/deepgram/ma_cle"


def test_build_transcription_vault_path_no_pii_in_path() -> None:
    result = build_transcription_vault_path("john@example.com", "deepgram", "ma_cle")
    assert "john" not in result
    assert "@" not in result


def test_build_transcription_vault_path_none_email() -> None:
    result = build_transcription_vault_path(None, "openai-whisper", "my_key")
    assert result == "users/no_email/transcription/openai-whisper/my_key"


# ---------------------------------------------------------------------------
# build_vault_ref
# ---------------------------------------------------------------------------


def test_build_vault_ref_wraps_path() -> None:
    ref = build_vault_ref("users/john/transcription/deepgram/ma_cle")
    assert ref == "${vault://api1:users/john/transcription/deepgram/ma_cle}"


def test_build_vault_ref_always_uses_api1_identifier() -> None:
    ref = build_vault_ref("some/path")
    assert ref == "${vault://api1:some/path}"


# ---------------------------------------------------------------------------
# extract_vault_path
# ---------------------------------------------------------------------------


def test_extract_vault_path_from_vault_ref() -> None:
    ref = "${vault://api1:users/john/transcription/deepgram/ma_cle}"
    assert extract_vault_path(ref) == "users/john/transcription/deepgram/ma_cle"


def test_extract_vault_path_plain_path_passthrough() -> None:
    plain = "users/john/transcription/deepgram/some-uuid"
    assert extract_vault_path(plain) == plain
