"""SecretStore — écriture/lecture/suppression des secrets utilisateur.

Deux destinations, choisies à la saisie (spec chantier self-service) :
  - local  : la valeur est chiffrée (Fernet) et vit dans user_secrets ;
  - wallet : la valeur est écrite dans le wallet Harpocrate de l'utilisateur
    (token déchiffré à la volée), la base ne garde que le chemin.

Le chemin wallet est ``roles/{secret_type}/{secret_id}`` : pas de hash
d'email (le wallet appartient déjà à l'utilisateur), l'id garantit
l'unicité.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import structlog
from harpocrate import SecretNotFound, VaultClient
from harpocrate.exceptions import HarpocrateError

from role_builder.db_helpers import user_secrets as secrets_helper
from role_builder.db_helpers import user_wallets as wallets_helper
from role_builder.services.secret_cipher import SecretCipher, cipher_from_settings

log = structlog.get_logger(__name__)

ClientFactory = Callable[[str, str], Any]


class UnknownWalletError(Exception):
    """Le wallet demandé n'existe pas ou n'appartient pas à cet utilisateur."""


class InvalidWalletTokenError(Exception):
    """Le token fourni est refusé par Harpocrate (format ou droits)."""


def _default_client_factory(token: str, base_url: str) -> VaultClient:
    return VaultClient(token=token, base_url=base_url)


class SecretStore:
    """Orchestre cipher local et clients wallet (un client par wallet, en cache)."""

    def __init__(
        self,
        cipher: SecretCipher,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._cipher = cipher
        self._client_factory = client_factory or _default_client_factory
        self._clients: dict[UUID, Any] = {}

    async def register_wallet(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        label: str,
        token: str,
        api_url: str,
        pool: asyncpg.Pool,
    ) -> UUID:
        """Valide le token en direct (construction du client) puis l'enregistre chiffré."""
        try:
            await asyncio.to_thread(self._client_factory, token, api_url)
        except HarpocrateError as exc:
            raise InvalidWalletTokenError(str(exc)) from exc
        return await wallets_helper.insert_wallet(
            tenant_id=tenant_id,
            user_id=user_id,
            label=label,
            api_token_encrypted=self._cipher.encrypt(token),
            api_url=api_url,
            pool=pool,
        )

    async def create_secret(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        secret_type: str,
        label: str,
        value: str,
        wallet_id: UUID | None,
        pool: asyncpg.Pool,
    ) -> UUID:
        """Stocke la valeur (local ou wallet) puis insère la ligne user_secrets."""
        secret_id = uuid4()
        if wallet_id is None:
            return await self._create_local(
                secret_id=secret_id,
                tenant_id=tenant_id,
                user_id=user_id,
                secret_type=secret_type,
                label=label,
                value=value,
                pool=pool,
            )
        return await self._create_in_wallet(
            secret_id=secret_id,
            tenant_id=tenant_id,
            user_id=user_id,
            secret_type=secret_type,
            label=label,
            value=value,
            wallet_id=wallet_id,
            pool=pool,
        )

    async def read_value(self, secret: dict[str, Any], *, pool: asyncpg.Pool) -> str | None:
        """Valeur en clair du secret ; None si l'objet wallet a disparu."""
        if secret["storage"] == "local":
            return self._cipher.decrypt(bytes(secret["value_encrypted"]))
        client = await self._wallet_client(
            wallet_id=secret["wallet_id"], user_id=secret["user_id"], pool=pool
        )
        try:
            return await asyncio.to_thread(client.secrets.get, secret["wallet_path"])
        except SecretNotFound:
            return None

    async def delete_secret(self, secret: dict[str, Any], *, pool: asyncpg.Pool) -> None:
        """Supprime la valeur wallet (best-effort) puis la ligne en base."""
        if secret["storage"] == "wallet":
            await self._try_delete_in_wallet(secret, pool=pool)
        await secrets_helper.delete_secret(
            secret_id=secret["id"], user_id=secret["user_id"], pool=pool
        )

    def invalidate_wallet(self, wallet_id: UUID) -> None:
        """Évince le client en cache (wallet supprimé ou token modifié)."""
        self._clients.pop(wallet_id, None)

    # -- internes -----------------------------------------------------------

    async def _create_local(
        self,
        *,
        secret_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        secret_type: str,
        label: str,
        value: str,
        pool: asyncpg.Pool,
    ) -> UUID:
        return await secrets_helper.insert_secret(
            secret_id=secret_id,
            tenant_id=tenant_id,
            user_id=user_id,
            secret_type=secret_type,
            label=label,
            storage="local",
            value_encrypted=self._cipher.encrypt(value),
            wallet_id=None,
            wallet_path=None,
            pool=pool,
        )

    async def _create_in_wallet(
        self,
        *,
        secret_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        secret_type: str,
        label: str,
        value: str,
        wallet_id: UUID,
        pool: asyncpg.Pool,
    ) -> UUID:
        client = await self._wallet_client(wallet_id=wallet_id, user_id=user_id, pool=pool)
        path = f"roles/{secret_type}/{secret_id}"
        await self._vault_upsert(client, path, value)
        return await secrets_helper.insert_secret(
            secret_id=secret_id,
            tenant_id=tenant_id,
            user_id=user_id,
            secret_type=secret_type,
            label=label,
            storage="wallet",
            value_encrypted=None,
            wallet_id=wallet_id,
            wallet_path=path,
            pool=pool,
        )

    async def _wallet_client(
        self, *, wallet_id: UUID, user_id: UUID, pool: asyncpg.Pool
    ) -> Any:
        cached = self._clients.get(wallet_id)
        if cached is not None:
            return cached
        wallet = await wallets_helper.get_wallet(
            wallet_id=wallet_id, user_id=user_id, pool=pool
        )
        if wallet is None:
            raise UnknownWalletError(f"wallet {wallet_id} introuvable pour cet utilisateur")
        token = self._cipher.decrypt(bytes(wallet["api_token_encrypted"]))
        # La construction du VaultClient résout le wallet_id côté Harpocrate
        # (appel réseau) — toujours hors event loop.
        client = await asyncio.to_thread(self._client_factory, token, wallet["api_url"])
        self._clients[wallet_id] = client
        return client

    @staticmethod
    async def _vault_upsert(client: Any, path: str, value: str) -> None:
        try:
            await asyncio.to_thread(client.secrets.put, path, value)
        except SecretNotFound:
            await asyncio.to_thread(client.secrets.create, path, value)

    async def _try_delete_in_wallet(
        self, secret: dict[str, Any], *, pool: asyncpg.Pool
    ) -> None:
        try:
            client = await self._wallet_client(
                wallet_id=secret["wallet_id"], user_id=secret["user_id"], pool=pool
            )
            await asyncio.to_thread(client.secrets.delete, secret["wallet_path"])
        except Exception:
            log.exception("secret_store.wallet_delete_failed", path=secret["wallet_path"])


_store: SecretStore | None = None


def get_secret_store() -> SecretStore:
    """Singleton paresseux construit depuis settings (pas d'I/O au boot)."""
    global _store
    if _store is None:
        _store = SecretStore(cipher_from_settings())
    return _store
