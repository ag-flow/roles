"""Tests TDD pour le runner de migrations (Phase 2 — bundle migrations)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Stubs asyncpg
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.try_lock_return: bool = True
        self.applied_versions: list[str] = []
        self.in_transaction: int = 0
        # SQL exécuté (filtré sur ce qui n'est pas du lock/insert)
        self.applied_sql: list[str] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        if "pg_try_advisory_lock" in query:
            return self.try_lock_return
        return None

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        if "FROM schema_migrations" in query:
            return [{"version": v} for v in self.applied_versions]
        return []

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        is_lock_admin = (
            "pg_advisory_lock" in query
            or "pg_advisory_unlock" in query
            or "schema_migrations" in query
        )
        if not is_lock_admin and self.in_transaction > 0:
            self.applied_sql.append(query)
        return "OK"

    def transaction(self) -> _StubTx:
        return _StubTx(self)


class _StubTx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> None:
        self._conn.in_transaction += 1
        return None

    async def __aexit__(self, *_: Any) -> None:
        self._conn.in_transaction -= 1


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_migration(dir_: Path, name: str, sql: str) -> None:
    (dir_ / name).write_text(sql, encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_migrations_applies_all_when_table_missing(tmp_path: Path) -> None:
    from role_builder.migrations import run_migrations

    _write_migration(tmp_path, "0001_init.sql", "CREATE TABLE foo (id int);")
    _write_migration(tmp_path, "0002_more.sql", "ALTER TABLE foo ADD c text;")

    conn = _StubConn()
    pool = _StubPool(conn)
    applied = await run_migrations(tmp_path, pool=pool)

    assert applied == ["0001_init.sql", "0002_more.sql"]
    # Les 2 SQLs ont été exécutés
    assert any("CREATE TABLE foo" in s for s in conn.applied_sql)
    assert any("ALTER TABLE foo" in s for s in conn.applied_sql)


@pytest.mark.asyncio
async def test_run_migrations_skips_already_applied(tmp_path: Path) -> None:
    from role_builder.migrations import run_migrations

    _write_migration(tmp_path, "0001_init.sql", "CREATE TABLE foo (id int);")
    _write_migration(tmp_path, "0002_more.sql", "ALTER TABLE foo ADD c text;")

    conn = _StubConn()
    conn.applied_versions = ["0001_init.sql"]
    pool = _StubPool(conn)
    applied = await run_migrations(tmp_path, pool=pool)

    assert applied == ["0002_more.sql"]
    # Seule la 0002 a été exécutée
    assert all("CREATE TABLE foo" not in s for s in conn.applied_sql)
    assert any("ALTER TABLE foo" in s for s in conn.applied_sql)


@pytest.mark.asyncio
async def test_run_migrations_idempotent_when_all_applied(tmp_path: Path) -> None:
    from role_builder.migrations import run_migrations

    _write_migration(tmp_path, "0001_init.sql", "CREATE TABLE foo (id int);")

    conn = _StubConn()
    conn.applied_versions = ["0001_init.sql"]
    pool = _StubPool(conn)
    applied = await run_migrations(tmp_path, pool=pool)

    assert applied == []
    assert conn.applied_sql == []


@pytest.mark.asyncio
async def test_run_migrations_blank_sql_still_recorded(tmp_path: Path) -> None:
    """Une migration vide / 100% commentaires est marquée comme appliquée
    sans tenter d'execute du SQL vide."""
    from role_builder.migrations import run_migrations

    _write_migration(
        tmp_path, "0001_marker.sql",
        "-- juste un commentaire\n-- pas de SQL\n",
    )
    _write_migration(tmp_path, "0002_real.sql", "CREATE TABLE bar (id int);")

    conn = _StubConn()
    pool = _StubPool(conn)
    applied = await run_migrations(tmp_path, pool=pool)

    assert applied == ["0001_marker.sql", "0002_real.sql"]
    # La 0001 ne doit avoir produit aucun execute SQL business
    assert all("commentaire" not in s for s in conn.applied_sql)
    assert any("CREATE TABLE bar" in s for s in conn.applied_sql)


@pytest.mark.asyncio
async def test_run_migrations_acquires_advisory_lock(tmp_path: Path) -> None:
    from role_builder.migrations import _lock_key, run_migrations

    _write_migration(tmp_path, "0001_init.sql", "CREATE TABLE foo (id int);")
    conn = _StubConn()
    pool = _StubPool(conn)
    await run_migrations(tmp_path, pool=pool)

    key = _lock_key()
    # try_lock + unlock doivent avoir été appelés avec la même clé
    try_lock_calls = [c for c in conn.calls if "pg_try_advisory_lock" in c[1]]
    unlock_calls = [c for c in conn.calls if "pg_advisory_unlock" in c[1]]
    assert len(try_lock_calls) == 1
    assert try_lock_calls[0][2] == (key,)
    assert len(unlock_calls) == 1
    assert unlock_calls[0][2] == (key,)


@pytest.mark.asyncio
async def test_run_migrations_falls_back_to_blocking_lock(tmp_path: Path) -> None:
    """Si pg_try_advisory_lock retourne false, on prend le bloquant."""
    from role_builder.migrations import run_migrations

    _write_migration(tmp_path, "0001_init.sql", "CREATE TABLE foo (id int);")
    conn = _StubConn()
    conn.try_lock_return = False
    pool = _StubPool(conn)
    await run_migrations(tmp_path, pool=pool)

    blocking_calls = [
        c for c in conn.calls
        if c[0] == "execute" and "pg_advisory_lock" in c[1] and "unlock" not in c[1]
    ]
    assert len(blocking_calls) == 1


@pytest.mark.asyncio
async def test_run_migrations_ignores_non_matching_files(tmp_path: Path) -> None:
    from role_builder.migrations import run_migrations

    _write_migration(tmp_path, "0001_init.sql", "CREATE TABLE foo (id int);")
    _write_migration(tmp_path, "README.md", "# pas une migration")
    _write_migration(tmp_path, "rollback.sql", "DROP TABLE foo;")

    conn = _StubConn()
    pool = _StubPool(conn)
    applied = await run_migrations(tmp_path, pool=pool)

    assert applied == ["0001_init.sql"]


@pytest.mark.asyncio
async def test_run_migrations_raises_when_dir_missing(tmp_path: Path) -> None:
    from role_builder.migrations import run_migrations

    with pytest.raises(FileNotFoundError):
        await run_migrations(tmp_path / "does-not-exist", pool=_StubPool(_StubConn()))


def test_lock_key_stable_and_int64() -> None:
    from role_builder.migrations import _lock_key

    key = _lock_key()
    # Doit tenir dans int8 signed (PostgreSQL bigint)
    assert -(2**63) <= key < 2**63
    # Stable entre appels
    assert _lock_key() == key
