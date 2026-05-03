"""Tests for db_helpers.transcription_keys — Sprint 3 (read-only) + Sprint 6 (CRUD complet)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Stubs asyncpg pool (pattern test_db_helpers_role_documents — avec transaction)
# ---------------------------------------------------------------------------


class _StubTransactionCtx:
    """Context manager no-op qui simule conn.transaction()."""

    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        self._conn.transaction_count += 1
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "UPDATE 0"
        self.transaction_count: int = 0

    def transaction(self) -> _StubTransactionCtx:
        return _StubTransactionCtx(self)

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
# Tests Sprint 3 — fonctions read-only existantes
# ---------------------------------------------------------------------------


async def test_list_active_keys_filters_status_active(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_active_keys runs a SELECT WHERE status='active'."""
    from role_builder.db_helpers import transcription_keys

    rows = [
        {"id": uuid4(), "user_id": uuid4(), "provider": "openai-whisper"},
        {"id": uuid4(), "user_id": uuid4(), "provider": "deepgram"},
    ]
    stub_conn.fetch_return = rows

    result = await transcription_keys.list_active_keys(pool=stub_pool)
    assert result == rows

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_transcription_keys" in query
    assert "status = 'active'" in query or "status='active'" in query.replace(" ", "")
    # No user_id filter for the global variant
    assert args == ()


async def test_list_active_keys_for_user_filters_user_and_status(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_active_keys_for_user passes user_id arg + filters status='active'."""
    from role_builder.db_helpers import transcription_keys

    user_id = uuid4()
    rows = [{"id": uuid4(), "user_id": user_id, "provider": "openai-whisper"}]
    stub_conn.fetch_return = rows

    result = await transcription_keys.list_active_keys_for_user(user_id, pool=stub_pool)
    assert result == rows

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_transcription_keys" in query
    assert "user_id = $1" in query
    assert "status = 'active'" in query or "status='active'" in query.replace(" ", "")
    assert user_id in args


async def test_get_primary_key_returns_row_or_none(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_primary_key picks is_primary=true AND status='active'."""
    from role_builder.db_helpers import transcription_keys

    user_id = uuid4()
    row = {"id": uuid4(), "user_id": user_id, "is_primary": True, "status": "active"}
    stub_conn.fetchrow_return = row

    result = await transcription_keys.get_primary_key(user_id, pool=stub_pool)
    assert result == row

    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM user_transcription_keys" in query
    assert "is_primary = true" in query
    assert "status = 'active'" in query or "status='active'" in query.replace(" ", "")
    assert user_id in args

    # None case
    stub_conn.fetchrow_return = None
    stub_conn.calls.clear()
    result2 = await transcription_keys.get_primary_key(user_id, pool=stub_pool)
    assert result2 is None


async def test_mark_exhausted_updates_status(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_exhausted updates status to 'exhausted'."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.mark_exhausted(key_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_transcription_keys" in query
    assert "exhausted" in query
    assert key_id in args


async def test_mark_invalid_updates_status(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_invalid updates status to 'invalid'."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.mark_invalid(key_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_transcription_keys" in query
    assert "invalid" in query
    assert key_id in args


# ---------------------------------------------------------------------------
# Tests Sprint 6 — CRUD complet
# ---------------------------------------------------------------------------


async def test_insert_transcription_key_simple_no_transaction(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_transcription_key sans is_primary → INSERT direct, pas de transaction."""
    from role_builder.db_helpers import transcription_keys

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    tenant_id = uuid4()
    user_id = uuid4()
    result = await transcription_keys.insert_transcription_key(
        tenant_id=tenant_id,
        user_id=user_id,
        provider="deepgram",
        label="Clé Deepgram",
        vault_secret_name="users/test_at_example.com/transcription/deepgram/k1",
        pool=stub_pool,
    )

    assert result == expected_id
    assert stub_conn.transaction_count == 0
    fetchval_calls = [c for c in stub_conn.calls if c[0] == "fetchval"]
    assert len(fetchval_calls) == 1
    method, query, args = fetchval_calls[0]
    assert "INSERT INTO user_transcription_keys" in query
    assert "RETURNING id" in query
    assert tenant_id in args
    assert user_id in args
    assert "deepgram" in args


async def test_insert_transcription_key_with_is_primary_uses_transaction(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_transcription_key avec is_primary=True → transaction + UPDATE démote + INSERT."""
    from role_builder.db_helpers import transcription_keys

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    tenant_id = uuid4()
    user_id = uuid4()
    result = await transcription_keys.insert_transcription_key(
        tenant_id=tenant_id,
        user_id=user_id,
        provider="openai-whisper",
        label=None,
        vault_secret_name="users/test_at_example.com/transcription/openai-whisper/k2",
        is_primary=True,
        pool=stub_pool,
    )

    assert result == expected_id
    assert stub_conn.transaction_count == 1  # Une transaction ouverte
    # Premier appel = UPDATE démote, dernier = INSERT RETURNING
    execute_calls = [c for c in stub_conn.calls if c[0] == "execute"]
    assert len(execute_calls) >= 1
    demote_query = execute_calls[0][1]
    assert "is_primary = false" in demote_query
    assert "user_id = $1" in demote_query


async def test_list_keys_for_user_returns_all_statuses(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_keys_for_user retourne toutes les clés (pas juste active), ORDER BY created_at DESC."""
    from role_builder.db_helpers import transcription_keys

    user_id = uuid4()
    rows = [
        {"id": uuid4(), "user_id": user_id, "status": "active"},
        {"id": uuid4(), "user_id": user_id, "status": "revoked"},
    ]
    stub_conn.fetch_return = rows

    result = await transcription_keys.list_keys_for_user(user_id, pool=stub_pool)

    assert result == rows
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_transcription_keys" in query
    assert "user_id = $1" in query
    assert "status" not in query  # pas de filtre status
    assert "ORDER BY created_at DESC" in query
    assert args == (user_id,)


async def test_get_key_sends_select_with_id_and_user_id(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_key envoie SELECT WHERE id=$1 AND user_id=$2, retourne None ou dict."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    user_id = uuid4()

    stub_conn.fetchrow_return = None
    result = await transcription_keys.get_key(key_id, user_id=user_id, pool=stub_pool)
    assert result is None

    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM user_transcription_keys" in query
    assert "id = $1" in query
    assert "user_id = $2" in query
    assert args == (key_id, user_id)


async def test_update_key_settings_workers_count_only_no_transaction(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_key_settings avec uniquement workers_count → SET workers_count + updated_at, pas de transaction."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.update_key_settings(key_id, workers_count=3, pool=stub_pool)

    assert stub_conn.transaction_count == 0
    execute_calls = [c for c in stub_conn.calls if c[0] == "execute"]
    assert len(execute_calls) == 1
    method, query, args = execute_calls[0]
    assert "UPDATE user_transcription_keys" in query
    assert "workers_count" in query
    assert "updated_at" in query
    assert key_id in args
    assert 3 in args


async def test_update_key_settings_is_primary_true_uses_transaction(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_key_settings avec is_primary=True → transaction pour démote + UPDATE."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    user_id = uuid4()
    stub_conn.fetchrow_return = {"user_id": user_id}

    await transcription_keys.update_key_settings(key_id, is_primary=True, pool=stub_pool)

    assert stub_conn.transaction_count == 1
    # Vérifier qu'il y a eu un fetchrow pour récupérer user_id, puis les UPDATEs
    fetchrow_calls = [c for c in stub_conn.calls if c[0] == "fetchrow"]
    assert len(fetchrow_calls) == 1


async def test_update_key_settings_all_none_is_noop(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_key_settings avec tous params None → no-op, 0 appels SQL."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.update_key_settings(key_id, pool=stub_pool)

    assert len(stub_conn.calls) == 0


async def test_update_key_balance_sends_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_key_balance envoie UPDATE current_balance_usd + last_balance_check_at."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    checked_at = datetime.now(tz=UTC)
    await transcription_keys.update_key_balance(
        key_id, balance_usd=42.50, checked_at=checked_at, pool=stub_pool
    )

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_transcription_keys" in query
    assert "current_balance_usd" in query
    assert "last_balance_check_at" in query
    assert key_id in args
    assert 42.50 in args
    assert checked_at in args


async def test_increment_spend_returns_new_total(stub_conn: _StubConn, stub_pool: Any) -> None:
    """increment_spend retourne le nouveau total via fetchval."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    stub_conn.fetchval_return = 15.75

    result = await transcription_keys.increment_spend(key_id, 5.25, pool=stub_pool)

    assert result == 15.75
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "current_month_spend_usd" in query
    assert "RETURNING current_month_spend_usd" in query
    assert key_id in args
    assert 5.25 in args


async def test_reset_monthly_spend_all_parses_count(stub_conn: _StubConn, stub_pool: Any) -> None:
    """reset_monthly_spend_all parse 'UPDATE N' et retourne le count."""
    from role_builder.db_helpers import transcription_keys

    stub_conn.execute_return = "UPDATE 5"
    result = await transcription_keys.reset_monthly_spend_all(pool=stub_pool)

    assert result == 5
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "current_month_spend_usd = 0" in query


async def test_revoke_key_sets_status_revoked_and_clears_flags(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """revoke_key UPDATE status='revoked' + is_primary=false + is_fallback=false."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.revoke_key(key_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_transcription_keys" in query
    assert "revoked" in query
    assert "is_primary = false" in query
    assert "is_fallback = false" in query
    assert key_id in args


async def test_delete_key_sends_delete(stub_conn: _StubConn, stub_pool: Any) -> None:
    """delete_key envoie DELETE FROM user_transcription_keys WHERE id=$1."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.delete_key(key_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM user_transcription_keys" in query
    assert key_id in args


async def test_list_active_keys_for_balance_polling_filters_deepgram(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_active_keys_for_balance_polling filtre provider IN ('deepgram') + status='active'."""
    from role_builder.db_helpers import transcription_keys

    rows = [{"id": uuid4(), "provider": "deepgram", "status": "active"}]
    stub_conn.fetch_return = rows

    result = await transcription_keys.list_active_keys_for_balance_polling(pool=stub_pool)

    assert result == rows
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_transcription_keys" in query
    assert "status = 'active'" in query
    assert "deepgram" in query
    assert args == ()
