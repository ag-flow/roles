"""Tests for db_helpers.credentials — get_cookies_b64 (Sprint 1) + CRUD Sprint 6."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Stubs asyncpg pool (pattern test_db_helpers_role_documents)
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "INSERT 1"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


# ---------------------------------------------------------------------------
# Tests existants Sprint 1 — get_cookies_b64
# ---------------------------------------------------------------------------


def test_get_cookies_b64_returns_per_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_cookies_b64('youtube') reads settings.youtube_cookies_b64, etc."""
    from role_builder.config import settings as _settings
    from role_builder.db_helpers import credentials

    monkeypatch.setattr(_settings, "youtube_cookies_b64", "yt-cookies", raising=False)
    monkeypatch.setattr(_settings, "instagram_cookies_b64", "ig-cookies", raising=False)
    monkeypatch.setattr(_settings, "tiktok_cookies_b64", "tt-cookies", raising=False)

    assert credentials.get_cookies_b64("youtube") == "yt-cookies"
    assert credentials.get_cookies_b64("instagram") == "ig-cookies"
    assert credentials.get_cookies_b64("tiktok") == "tt-cookies"


def test_get_cookies_b64_unknown_platform_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown platform returns ''; lookup is case-insensitive on the known ones."""
    from role_builder.config import settings as _settings
    from role_builder.db_helpers import credentials

    monkeypatch.setattr(_settings, "youtube_cookies_b64", "yt-cookies", raising=False)

    assert credentials.get_cookies_b64("foo") == ""
    assert credentials.get_cookies_b64("YOUTUBE") == "yt-cookies"  # case-insensitive


# ---------------------------------------------------------------------------
# Tests Sprint 6 — CRUD
# ---------------------------------------------------------------------------


async def test_insert_user_credential_sends_insert_returns_uuid(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_user_credential envoie INSERT avec 8 args et retourne UUID via fetchval."""
    from role_builder.db_helpers import credentials

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    tenant_id = uuid4()
    user_id = uuid4()
    result = await credentials.insert_user_credential(
        tenant_id=tenant_id,
        user_id=user_id,
        platform="youtube",
        label="Mon compte YT",
        vault_secret_name="users/test_at_example.com/scraping/youtube/abc",
        pool=stub_pool,
    )

    assert result == expected_id
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO user_credentials" in query
    assert "RETURNING id" in query
    # Les 8 args ordonnés
    assert args[0] == tenant_id
    assert args[1] == user_id
    assert args[2] == "youtube"
    assert args[3] == "Mon compte YT"
    assert args[4] == "users/test_at_example.com/scraping/youtube/abc"
    assert args[5] == "active"
    assert args[6] is None  # last_validated_at
    assert args[7] is None  # expires_at


async def test_list_credentials_without_platform_no_and_clause(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_credentials sans platform → query sans AND platform."""
    from role_builder.db_helpers import credentials

    user_id = uuid4()
    rows = [{"id": uuid4(), "user_id": user_id, "platform": "youtube"}]
    stub_conn.fetch_return = rows

    result = await credentials.list_credentials(user_id=user_id, pool=stub_pool)

    assert result == rows
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_credentials" in query
    assert "user_id = $1" in query
    assert "platform" not in query
    assert "ORDER BY created_at DESC" in query
    assert args == (user_id,)


async def test_list_credentials_with_platform_adds_filter(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_credentials avec platform → query avec AND platform = $2."""
    from role_builder.db_helpers import credentials

    user_id = uuid4()
    rows = [{"id": uuid4(), "user_id": user_id, "platform": "instagram"}]
    stub_conn.fetch_return = rows

    result = await credentials.list_credentials(
        user_id=user_id, platform="instagram", pool=stub_pool
    )

    assert result == rows
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "platform = $2" in query
    assert args == (user_id, "instagram")


async def test_get_credential_sends_select_with_id_and_user_id(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_credential envoie SELECT WHERE id=$1 AND user_id=$2, retourne None ou dict."""
    from role_builder.db_helpers import credentials

    cred_id = uuid4()
    user_id = uuid4()

    # None case
    stub_conn.fetchrow_return = None
    result = await credentials.get_credential(cred_id, user_id=user_id, pool=stub_pool)
    assert result is None

    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM user_credentials" in query
    assert "id = $1" in query
    assert "user_id = $2" in query
    assert args == (cred_id, user_id)

    # Dict case
    stub_conn.calls.clear()
    row_data = {"id": cred_id, "user_id": user_id, "platform": "tiktok"}
    stub_conn.fetchrow_return = row_data
    result2 = await credentials.get_credential(cred_id, user_id=user_id, pool=stub_pool)
    assert result2 == row_data


async def test_update_credential_status_sends_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_credential_status envoie UPDATE avec status + updated_at."""
    from role_builder.db_helpers import credentials

    cred_id = uuid4()
    now = datetime.now(tz=UTC)

    await credentials.update_credential_status(
        cred_id, status="invalid", last_validated_at=now, pool=stub_pool
    )

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_credentials" in query
    assert "status" in query
    assert "updated_at" in query
    assert cred_id in args
    assert "invalid" in args
    assert now in args


async def test_revoke_credential_sets_status_revoked(stub_conn: _StubConn, stub_pool: Any) -> None:
    """revoke_credential envoie UPDATE status='revoked'."""
    from role_builder.db_helpers import credentials

    cred_id = uuid4()
    await credentials.revoke_credential(cred_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_credentials" in query
    assert "revoked" in query
    assert cred_id in args


async def test_delete_credential_sends_delete(stub_conn: _StubConn, stub_pool: Any) -> None:
    """delete_credential envoie DELETE FROM user_credentials WHERE id=$1."""
    from role_builder.db_helpers import credentials

    cred_id = uuid4()
    await credentials.delete_credential(cred_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM user_credentials" in query
    assert cred_id in args


async def test_get_active_credential_for_platform_returns_row(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """Façade MCP : NO_CREDENTIALS repose sur l'existence d'une credential active.

    MVP mono-tenant/mono-user (cf. TENANT_ID_DEFAULT) : pas de filtre user_id,
    seule la plateforme + le statut 'active' comptent.
    """
    from role_builder.db_helpers import credentials

    cred_id = uuid4()
    stub_conn.fetchrow_return = {"id": cred_id, "platform": "youtube", "status": "active"}

    row = await credentials.get_active_credential_for_platform("youtube", pool=stub_pool)

    assert row is not None
    assert row["id"] == cred_id
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM user_credentials" in query
    assert "active" in query
    assert "youtube" in args


async def test_get_active_credential_for_platform_returns_none_when_missing(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    from role_builder.db_helpers import credentials

    stub_conn.fetchrow_return = None

    row = await credentials.get_active_credential_for_platform("tiktok", pool=stub_pool)

    assert row is None
