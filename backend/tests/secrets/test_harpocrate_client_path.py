"""Tests unitaires pour SecretsClient._normalize_name et _path."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from role_builder.secrets.harpocrate.client import SecretsClient

_WALLET_ID = UUID("12345678-1234-5678-1234-567812345678")


def _make_secrets_client() -> SecretsClient:
    return SecretsClient(
        http=MagicMock(),
        wallet_id=_WALLET_ID,
        parsed_token=MagicMock(),
        cache=MagicMock(),
    )


# ---------------------------------------------------------------------------
# _normalize_name
# ---------------------------------------------------------------------------


def test_normalize_name_adds_leading_slash_to_hierarchical_path() -> None:
    """Un path sans '/' initial doit recevoir un '/' en tête."""
    result = SecretsClient._normalize_name("users/no_email/transcription/deepgram/ma_cle")
    assert result.startswith("/")


def test_normalize_name_preserves_existing_leading_slash() -> None:
    """/already/prefixed ne doit pas recevoir un second '/'."""
    result = SecretsClient._normalize_name("/users/john/transcription/openai/uuid")
    assert result.startswith("/")
    assert not result.startswith("//")


def test_normalize_name_simple_key_gets_slash() -> None:
    """Un nom simple sans '/' reçoit aussi un '/' en tête."""
    result = SecretsClient._normalize_name("MY_SECRET")
    assert result == "/MY_SECRET"


# ---------------------------------------------------------------------------
# _path — construction de l'URL
# ---------------------------------------------------------------------------


def test_path_without_name_returns_base() -> None:
    """_path() sans nom retourne la base du wallet."""
    client = _make_secrets_client()
    path = client._path()
    assert path == f"/v1/wallets/{_WALLET_ID}/secrets"


def test_path_hierarchical_name_no_double_slash() -> None:
    """Un path hiérarchique NE doit PAS produire de double slash '//' dans l'URL."""
    client = _make_secrets_client()
    path = client._path("users/no_email/transcription/openai-whisper/ma_cle")
    assert "//" not in path


def test_path_hierarchical_name_contains_segments() -> None:
    """Les segments du path hiérarchique doivent être présents dans l'URL (non encodés)."""
    client = _make_secrets_client()
    path = client._path("users/no_email/transcription/deepgram/my_key")
    assert "users" in path
    assert "no_email" in path
    assert "transcription" in path
    assert "deepgram" in path
    assert "my_key" in path


def test_path_simple_name_no_double_slash() -> None:
    """Un nom simple ne doit pas non plus produire de double slash."""
    client = _make_secrets_client()
    path = client._path("MY_SECRET")
    assert "//" not in path
    assert "MY_SECRET" in path


def test_path_already_slash_prefixed_no_double_slash() -> None:
    """Un nom déjà préfixé de '/' ne doit pas produire '//secrets//' ."""
    client = _make_secrets_client()
    path = client._path("/users/john/transcription/assemblyai/uuid")
    assert "//" not in path


def test_path_ends_with_secret_name_segment() -> None:
    """Le path doit se terminer par le nom du secret (dernier segment)."""
    client = _make_secrets_client()
    path = client._path("users/john_at_example.com/transcription/speechmatics/ma_cle")
    assert path.endswith("/ma_cle")


def test_path_starts_with_wallet_base() -> None:
    """Le path doit toujours commencer par la base du wallet."""
    client = _make_secrets_client()
    base = f"/v1/wallets/{_WALLET_ID}/secrets"
    path = client._path("users/no_email/scraping/youtube/some-uuid")
    assert path.startswith(base)
