"""Tests TDD pour SecretStore — écriture/lecture/suppression local vs wallet."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from role_builder.services.secret_cipher import SecretCipher
from role_builder.services.secret_store import (
    InvalidWalletTokenError,
    SecretStore,
    UnknownWalletError,
    WalletUnavailableError,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Stubs — pool asyncpg + client vault
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.execute_return: str = "DELETE 1"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        if "INSERT INTO user_secrets" in query:
            return args[0]  # écho du RETURNING id, comme en vraie base
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return []

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


class _FakeSecrets:
    """Sous-client secrets d'un VaultClient factice."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.deleted: list[str] = []

    def put(self, name: str, value: str) -> int:
        from harpocrate import SecretNotFound

        if name not in self.store:
            raise SecretNotFound(name)
        self.store[name] = value
        return 1

    def create(self, name: str, value: str) -> None:
        self.store[name] = value

    def get(self, name: str) -> str:
        from harpocrate import SecretNotFound

        if name not in self.store:
            raise SecretNotFound(name)
        return self.store[name]

    def delete(self, name: str) -> None:
        self.deleted.append(name)
        self.store.pop(name, None)


class _FakeVaultClient:
    def __init__(self) -> None:
        self.secrets = _FakeSecrets()


@pytest.fixture()
def cipher() -> SecretCipher:
    return SecretCipher(Fernet.generate_key().decode())


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


def _make_store(
    cipher: SecretCipher,
) -> tuple[SecretStore, list[tuple[str, str]], _FakeVaultClient]:
    """SecretStore avec factory de client factice ; retourne (store, appels, client)."""
    factory_calls: list[tuple[str, str]] = []
    fake_client = _FakeVaultClient()

    def factory(token: str, base_url: str) -> Any:
        factory_calls.append((token, base_url))
        return fake_client

    return SecretStore(cipher, client_factory=factory), factory_calls, fake_client


def _wallet_row(cipher: SecretCipher, wallet_id: UUID, user_id: UUID) -> dict[str, Any]:
    return {
        "id": wallet_id,
        "tenant_id": TENANT_ID,
        "user_id": user_id,
        "label": "perso",
        "api_token_encrypted": cipher.encrypt("hrpv_1_abc"),
        "api_url": "https://vault.example.org",
        "status": "active",
    }


# ---------------------------------------------------------------------------
# create_secret — local
# ---------------------------------------------------------------------------


async def test_create_local_secret_encrypts_value(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, factory_calls, _ = _make_store(cipher)
    stub_conn.fetchval_return = uuid4()

    secret_id = await store.create_secret(
        tenant_id=TENANT_ID,
        user_id=uuid4(),
        secret_type="openai-whisper",
        label="Ma clé",
        value="sk-plain",
        wallet_id=None,
        pool=stub_pool,
    )

    assert secret_id is not None
    assert factory_calls == []  # aucun client vault construit
    _, query, args = stub_conn.calls[0]
    assert "INSERT INTO user_secrets" in query
    encrypted = next(a for a in args if isinstance(a, bytes))
    assert cipher.decrypt(encrypted) == "sk-plain"
    assert "sk-plain" not in [a for a in args if isinstance(a, str)]


# ---------------------------------------------------------------------------
# create_secret — wallet
# ---------------------------------------------------------------------------


async def test_create_wallet_secret_writes_to_vault(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, factory_calls, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)
    stub_conn.fetchval_return = uuid4()

    secret_id = await store.create_secret(
        tenant_id=TENANT_ID,
        user_id=user_id,
        secret_type="deepgram",
        label="Clé DG",
        value="dg-secret",
        wallet_id=wallet_id,
        pool=stub_pool,
    )

    # Client construit avec le token déchiffré et l'URL du wallet
    assert factory_calls == [("hrpv_1_abc", "https://vault.example.org")]
    # La valeur est dans le vault, sous un path roles/{type}/{secret_id}
    assert len(fake_client.secrets.store) == 1
    path = next(iter(fake_client.secrets.store))
    assert path == f"roles/deepgram/{secret_id}"
    assert fake_client.secrets.store[path] == "dg-secret"
    # En base : wallet_id + wallet_path, pas de valeur
    insert_call = next(c for c in stub_conn.calls if "INSERT INTO user_secrets" in c[1])
    assert wallet_id in insert_call[2]
    assert path in insert_call[2]
    assert not any(isinstance(a, bytes) for a in insert_call[2])


async def test_create_wallet_secret_unknown_wallet_raises(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, _ = _make_store(cipher)
    stub_conn.fetchrow_return = None  # wallet absent ou pas à ce user

    with pytest.raises(UnknownWalletError):
        await store.create_secret(
            tenant_id=TENANT_ID,
            user_id=uuid4(),
            secret_type="deepgram",
            label="x",
            value="v",
            wallet_id=uuid4(),
            pool=stub_pool,
        )


# ---------------------------------------------------------------------------
# read_value
# ---------------------------------------------------------------------------


async def test_read_value_local(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, _ = _make_store(cipher)
    secret = {
        "id": uuid4(),
        "user_id": uuid4(),
        "storage": "local",
        "value_encrypted": cipher.encrypt("plain-value"),
        "wallet_id": None,
        "wallet_path": None,
    }

    assert await store.read_value(secret, pool=stub_pool) == "plain-value"


async def test_read_value_wallet(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)
    fake_client.secrets.create("roles/deepgram/xyz", "dg-secret")
    secret = {
        "id": uuid4(),
        "user_id": user_id,
        "storage": "wallet",
        "value_encrypted": None,
        "wallet_id": wallet_id,
        "wallet_path": "roles/deepgram/xyz",
    }

    assert await store.read_value(secret, pool=stub_pool) == "dg-secret"


async def test_read_value_wallet_secret_gone_returns_none(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, _ = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)
    secret = {
        "id": uuid4(),
        "user_id": user_id,
        "storage": "wallet",
        "value_encrypted": None,
        "wallet_id": wallet_id,
        "wallet_path": "roles/deepgram/disparu",
    }

    assert await store.read_value(secret, pool=stub_pool) is None


# ---------------------------------------------------------------------------
# read_secret_by_id — point d'entrée des consommateurs (routes, workers…)
# ---------------------------------------------------------------------------


async def test_read_secret_by_id_local(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, _ = _make_store(cipher)
    secret_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = {
        "id": secret_id,
        "user_id": user_id,
        "storage": "local",
        "value_encrypted": cipher.encrypt("sk-abc"),
        "wallet_id": None,
        "wallet_path": None,
    }

    value = await store.read_secret_by_id(
        secret_id=secret_id, user_id=user_id, pool=stub_pool
    )

    assert value == "sk-abc"


async def test_read_secret_by_id_missing_row_returns_none(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, _ = _make_store(cipher)
    stub_conn.fetchrow_return = None

    value = await store.read_secret_by_id(
        secret_id=uuid4(), user_id=uuid4(), pool=stub_pool
    )

    assert value is None


# ---------------------------------------------------------------------------
# delete_secret
# ---------------------------------------------------------------------------


async def test_delete_local_secret_deletes_row(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, factory_calls, _ = _make_store(cipher)
    secret = {
        "id": uuid4(),
        "user_id": uuid4(),
        "storage": "local",
        "value_encrypted": b"x",
        "wallet_id": None,
        "wallet_path": None,
    }

    await store.delete_secret(secret, pool=stub_pool)

    assert factory_calls == []
    assert any("DELETE FROM user_secrets" in c[1] for c in stub_conn.calls)


async def test_delete_wallet_secret_deletes_vault_then_row(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, _, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)
    fake_client.secrets.create("roles/deepgram/xyz", "v")
    secret = {
        "id": uuid4(),
        "user_id": user_id,
        "storage": "wallet",
        "value_encrypted": None,
        "wallet_id": wallet_id,
        "wallet_path": "roles/deepgram/xyz",
    }

    await store.delete_secret(secret, pool=stub_pool)

    assert fake_client.secrets.deleted == ["roles/deepgram/xyz"]
    assert any("DELETE FROM user_secrets" in c[1] for c in stub_conn.calls)


# ---------------------------------------------------------------------------
# register_wallet — validation live + chiffrement du token
# ---------------------------------------------------------------------------


async def test_register_wallet_validates_then_encrypts(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, factory_calls, _ = _make_store(cipher)
    stub_conn.fetchval_return = uuid4()

    wallet_id = await store.register_wallet(
        tenant_id=TENANT_ID,
        user_id=uuid4(),
        label="perso",
        token="hrpv_1_abc",
        api_url="https://vault.example.org",
        pool=stub_pool,
    )

    assert wallet_id is not None
    # Validation live : le client a été construit avec le token fourni
    assert factory_calls == [("hrpv_1_abc", "https://vault.example.org")]
    # Le token est chiffré en base, jamais en clair
    insert_call = next(c for c in stub_conn.calls if "INSERT INTO user_wallets" in c[1])
    encrypted = next(a for a in insert_call[2] if isinstance(a, bytes))
    assert cipher.decrypt(encrypted) == "hrpv_1_abc"
    assert "hrpv_1_abc" not in [a for a in insert_call[2] if isinstance(a, str)]


async def test_register_wallet_invalid_token_raises(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    from harpocrate.exceptions import HarpocrateError

    def failing_factory(token: str, base_url: str) -> Any:
        raise HarpocrateError("bad token")

    store = SecretStore(cipher, client_factory=failing_factory)

    with pytest.raises(InvalidWalletTokenError):
        await store.register_wallet(
            tenant_id=TENANT_ID,
            user_id=uuid4(),
            label="x",
            token="pas-un-token",
            api_url="https://vault.example.org",
            pool=stub_pool,
        )
    # Rien n'a été inséré
    assert not any("INSERT INTO user_wallets" in c[1] for c in stub_conn.calls)


# ---------------------------------------------------------------------------
# Cache des clients par wallet + invalidation
# ---------------------------------------------------------------------------


async def test_cached_wallet_client_still_enforces_ownership(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    """Cache chaud ou pas, un wallet d'un autre utilisateur reste inaccessible."""
    store, _, fake_client = _make_store(cipher)
    wallet_id, owner_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, owner_id)
    fake_client.secrets.create("roles/deepgram/a", "v")
    secret = {
        "id": uuid4(),
        "user_id": owner_id,
        "storage": "wallet",
        "value_encrypted": None,
        "wallet_id": wallet_id,
        "wallet_path": "roles/deepgram/a",
    }
    # Amorce le cache en tant que propriétaire
    assert await store.read_value(secret, pool=stub_pool) == "v"

    # Un autre utilisateur tente de créer un secret dans ce wallet :
    # get_wallet scopé user ne retourne rien → UnknownWalletError,
    # même si le client est déjà en cache.
    stub_conn.fetchrow_return = None
    with pytest.raises(UnknownWalletError):
        await store.create_secret(
            tenant_id=TENANT_ID,
            user_id=uuid4(),  # pas le propriétaire
            secret_type="deepgram",
            label="intrusion",
            value="x",
            wallet_id=wallet_id,
            pool=stub_pool,
        )
    assert len(fake_client.secrets.store) == 1  # rien n'a été écrit


async def test_read_value_local_decrypt_failure_returns_none(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    """Valeur locale indéchiffrable (clé changée) → None, pas d'exception."""
    store, _, _ = _make_store(cipher)
    other_cipher = SecretCipher(Fernet.generate_key().decode())
    secret = {
        "id": uuid4(),
        "user_id": uuid4(),
        "storage": "local",
        "value_encrypted": other_cipher.encrypt("v"),
        "wallet_id": None,
        "wallet_path": None,
    }

    assert await store.read_value(secret, pool=stub_pool) is None


async def test_read_value_wallet_error_returns_none(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    """Erreur Harpocrate à la lecture (token révoqué…) → None, pas d'exception."""
    from harpocrate.exceptions import HarpocrateError

    store, _, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)

    def failing_get(name: str) -> str:
        raise HarpocrateError("token révoqué")

    fake_client.secrets.get = failing_get  # type: ignore[method-assign]
    secret = {
        "id": uuid4(),
        "user_id": user_id,
        "storage": "wallet",
        "value_encrypted": None,
        "wallet_id": wallet_id,
        "wallet_path": "roles/deepgram/a",
    }

    assert await store.read_value(secret, pool=stub_pool) is None


async def test_create_wallet_secret_upsert_failure_raises_unavailable(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    """Échec Harpocrate à l'écriture → WalletUnavailableError (mappée 502 en route)."""
    from harpocrate.exceptions import HarpocrateError

    store, _, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)

    def failing_put(name: str, value: str) -> int:
        raise HarpocrateError("coffre indisponible")

    fake_client.secrets.put = failing_put  # type: ignore[method-assign]
    fake_client.secrets.create = failing_put  # type: ignore[method-assign]

    with pytest.raises(WalletUnavailableError):
        await store.create_secret(
            tenant_id=TENANT_ID,
            user_id=user_id,
            secret_type="deepgram",
            label="x",
            value="v",
            wallet_id=wallet_id,
            pool=stub_pool,
        )
    # Aucune ligne insérée
    assert not any("INSERT INTO user_secrets" in c[1] for c in stub_conn.calls)


async def test_create_wallet_secret_compensates_on_insert_failure(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    """Insert DB en échec après l'écriture wallet → la valeur est retirée du coffre."""
    store, _, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)

    original_fetchval = stub_conn.fetchval

    async def failing_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO user_secrets" in query:
            raise RuntimeError("connexion perdue")
        return await original_fetchval(query, *args)

    stub_conn.fetchval = failing_fetchval  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="connexion perdue"):
        await store.create_secret(
            tenant_id=TENANT_ID,
            user_id=user_id,
            secret_type="deepgram",
            label="x",
            value="v",
            wallet_id=wallet_id,
            pool=stub_pool,
        )
    # La valeur écrite a été retirée (compensation) : coffre vide
    assert fake_client.secrets.store == {}
    assert len(fake_client.secrets.deleted) == 1


async def test_register_wallet_value_error_maps_to_invalid_token(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    """Une ValueError du client (ex. api_url http:// refusée) → InvalidWalletTokenError."""

    def failing_factory(token: str, base_url: str) -> Any:
        raise ValueError("Production requires https:// base_url")

    store = SecretStore(cipher, client_factory=failing_factory)

    with pytest.raises(InvalidWalletTokenError):
        await store.register_wallet(
            tenant_id=TENANT_ID,
            user_id=uuid4(),
            label="x",
            token="hrpv_1_abc",
            api_url="http://vault.local",
            pool=stub_pool,
        )


async def test_wallet_client_is_cached_per_wallet(
    cipher: SecretCipher, stub_pool: Any, stub_conn: _StubConn
) -> None:
    store, factory_calls, fake_client = _make_store(cipher)
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = _wallet_row(cipher, wallet_id, user_id)
    fake_client.secrets.create("roles/deepgram/a", "v")
    secret = {
        "id": uuid4(),
        "user_id": user_id,
        "storage": "wallet",
        "value_encrypted": None,
        "wallet_id": wallet_id,
        "wallet_path": "roles/deepgram/a",
    }

    await store.read_value(secret, pool=stub_pool)
    await store.read_value(secret, pool=stub_pool)

    assert len(factory_calls) == 1

    store.invalidate_wallet(wallet_id)
    await store.read_value(secret, pool=stub_pool)
    assert len(factory_calls) == 2
