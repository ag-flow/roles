"""Tests unitaires pour SecretsClient._normalize_name, _path, _resolve_id_if_pathstyle, _path_for_op."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from harpocrate.exceptions import SecretNotFound

from role_builder.secrets.harpocrate.client import SecretsClient

_WALLET_ID = UUID("12345678-1234-5678-1234-567812345678")
_SECRET_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_secrets_client(http: MagicMock | None = None) -> SecretsClient:
    return SecretsClient(
        http=http or MagicMock(),
        wallet_id=_WALLET_ID,
        parsed_token=MagicMock(),
        cache=MagicMock(),
    )


# ---------------------------------------------------------------------------
# _normalize_name
# ---------------------------------------------------------------------------


def test_normalize_name_adds_slash_to_hierarchical_path() -> None:
    """`users/a/b` (contient '/' sans en avoir en tête) → `/users/a/b`."""
    result = SecretsClient._normalize_name("users/no_email/transcription/deepgram/ma_cle")
    assert result == "/users/no_email/transcription/deepgram/ma_cle"


def test_normalize_name_preserves_existing_leading_slash() -> None:
    """Chemin déjà préfixé → inchangé, pas de double slash."""
    result = SecretsClient._normalize_name("/users/john/transcription/openai/uuid")
    assert result == "/users/john/transcription/openai/uuid"


def test_normalize_name_simple_key_unchanged() -> None:
    """Nom sans '/' (clé simple) → inchangé, pas de slash ajouté."""
    result = SecretsClient._normalize_name("MY_SECRET")
    assert result == "MY_SECRET"


def test_normalize_name_simple_key_no_slash_added() -> None:
    """SDK ne préfixe PAS les noms simples."""
    assert not SecretsClient._normalize_name("ANTHROPIC_API_KEY").startswith("/")


# ---------------------------------------------------------------------------
# _path
# ---------------------------------------------------------------------------


def test_path_without_name_returns_base() -> None:
    """Sans nom → URL de collection."""
    client = _make_secrets_client()
    assert client._path() == f"/v1/wallets/{_WALLET_ID}/secrets"


def test_path_simple_name_appended_without_encoding() -> None:
    """Nom simple (sans '/') → `base/NAME` sans double slash."""
    client = _make_secrets_client()
    path = client._path("MY_SECRET")
    assert path == f"/v1/wallets/{_WALLET_ID}/secrets/MY_SECRET"
    assert "//" not in path


def test_path_hierarchical_name_slashes_are_encoded() -> None:
    """Nom path-style → les '/' sont encodés en '%2F' (safe='')."""
    client = _make_secrets_client()
    path = client._path("users/no_email/transcription/deepgram/ma_cle")
    assert "%2F" in path
    assert "//" not in path


def test_path_hierarchical_starts_with_base() -> None:
    client = _make_secrets_client()
    base = f"/v1/wallets/{_WALLET_ID}/secrets"
    path = client._path("users/no_email/transcription/openai-whisper/ma_cle")
    assert path.startswith(base)


# ---------------------------------------------------------------------------
# _resolve_id_if_pathstyle
# ---------------------------------------------------------------------------


def test_resolve_id_returns_none_for_simple_name() -> None:
    """Sans '/' dans le nom → None (chemin non-path-style)."""
    client = _make_secrets_client()
    result = client._resolve_id_if_pathstyle("MY_SECRET")
    assert result is None


def test_resolve_id_returns_uuid_when_found() -> None:
    """Nom path-style → liste le parent path et retourne l'UUID du secret trouvé."""
    mock_http = MagicMock()
    mock_http.get.return_value = {
        "secrets": [
            {"name": "/users/abc123/transcription/deepgram/ma_cle", "id": _SECRET_ID},
            {"name": "/users/abc123/transcription/deepgram/autre_cle", "id": "other-id"},
        ]
    }
    client = _make_secrets_client(mock_http)
    result = client._resolve_id_if_pathstyle("users/abc123/transcription/deepgram/ma_cle")
    assert result == _SECRET_ID


def test_resolve_id_raises_secret_not_found_when_absent() -> None:
    """Nom path-style absent de la liste → lève SecretNotFound."""
    mock_http = MagicMock()
    mock_http.get.return_value = {"secrets": []}
    client = _make_secrets_client(mock_http)
    with pytest.raises(SecretNotFound):
        client._resolve_id_if_pathstyle("users/abc123/transcription/deepgram/inexistant")


def test_resolve_id_queries_parent_path() -> None:
    """La requête de listing doit utiliser le path parent du secret."""
    mock_http = MagicMock()
    mock_http.get.return_value = {"secrets": []}
    client = _make_secrets_client(mock_http)
    try:
        client._resolve_id_if_pathstyle("users/abc123/transcription/deepgram/ma_cle")
    except SecretNotFound:
        pass
    # Vérifie que le listing a bien été fait
    mock_http.get.assert_called_once()
    call_kwargs = mock_http.get.call_args
    assert f"/v1/wallets/{_WALLET_ID}/secrets" in call_kwargs[0][0]


# ---------------------------------------------------------------------------
# _path_for_op
# ---------------------------------------------------------------------------


def test_path_for_op_simple_name_uses_path() -> None:
    """Nom simple → pas de résolution ID → URL name-based."""
    client = _make_secrets_client()
    path = client._path_for_op("MY_SECRET")
    assert "by-id" not in path
    assert "MY_SECRET" in path


def test_path_for_op_path_style_uses_by_id() -> None:
    """Nom path-style → résolution par UUID → URL `/by-id/{id}`."""
    mock_http = MagicMock()
    mock_http.get.return_value = {
        "secrets": [
            {"name": "/users/abc123/transcription/deepgram/ma_cle", "id": _SECRET_ID},
        ]
    }
    client = _make_secrets_client(mock_http)
    path = client._path_for_op("users/abc123/transcription/deepgram/ma_cle")
    assert f"/by-id/{_SECRET_ID}" in path
    assert "//" not in path


def test_path_for_op_raises_when_secret_not_found() -> None:
    """Nom path-style absent → lève SecretNotFound."""
    mock_http = MagicMock()
    mock_http.get.return_value = {"secrets": []}
    client = _make_secrets_client(mock_http)
    with pytest.raises(SecretNotFound):
        client._path_for_op("users/abc123/transcription/deepgram/inexistant")
