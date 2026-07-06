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
import contextlib
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import structlog
from harpocrate import SecretNotFound, VaultClient
from harpocrate.exceptions import HarpocrateError, VaultHttpError

from role_builder.db_helpers import user_secrets as secrets_helper
from role_builder.db_helpers import user_wallets as wallets_helper
from role_builder.services.secret_cipher import (
    SecretCipher,
    SecretDecryptError,
    cipher_from_settings,
)

log = structlog.get_logger(__name__)

ClientFactory = Callable[[str, str], Any]


class UnknownWalletError(Exception):
    """Le wallet demandé n'existe pas ou n'appartient pas à cet utilisateur."""


class InvalidWalletTokenError(Exception):
    """Le token fourni est refusé par Harpocrate (format ou droits)."""


class WalletUnavailableError(Exception):
    """Le wallet est joignable en base mais l'opération Harpocrate a échoué
    (token révoqué, coffre indisponible, valeur indéchiffrable)."""


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
        except VaultHttpError as exc:
            # status_code 0 = échec de connexion (Harpocrate injoignable) : ce
            # n'est PAS un token refusé → 502, pas 400 (BUG-37). L'utilisateur
            # ne doit pas re-saisir un token pourtant valide.
            if exc.status_code == 0:
                raise WalletUnavailableError(str(exc)) from exc
            raise InvalidWalletTokenError(str(exc)) from exc
        except (HarpocrateError, ValueError, TypeError, KeyError) as exc:
            # ValueError couvre notamment une api_url http:// refusée par le
            # client et une réponse non-JSON ; KeyError un wallet_id absent.
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
        """Valeur en clair du secret ; None si elle est devenue inaccessible.

        Inaccessible = objet disparu du wallet, wallet en erreur (token
        révoqué, coffre injoignable) ou valeur locale indéchiffrable. Les
        appelants traitent None comme « secret invalide, re-saisie requise ».
        """
        if secret["storage"] == "local":
            try:
                return self._cipher.decrypt(bytes(secret["value_encrypted"]))
            except SecretDecryptError:
                log.warning("secret_store.local_decrypt_failed", secret_id=str(secret["id"]))
                return None
        try:
            client = await self._wallet_client(
                wallet_id=secret["wallet_id"], user_id=secret["user_id"], pool=pool
            )
            return await asyncio.to_thread(client.secrets.get, secret["wallet_path"])
        except SecretNotFound:
            return None
        except (HarpocrateError, SecretDecryptError):
            log.warning("secret_store.wallet_read_failed", secret_id=str(secret["id"]))
            return None

    async def read_secret_by_id(
        self, *, secret_id: UUID, user_id: UUID, pool: asyncpg.Pool
    ) -> str | None:
        """Valeur en clair d'un secret par id ; None si absent ou disparu.

        Point d'entrée des consommateurs (routes de service, workers,
        credit monitor) qui ne détiennent que le secret_id d'une ligne.
        """
        secret = await secrets_helper.get_secret(
            secret_id=secret_id, user_id=user_id, pool=pool
        )
        if secret is None:
            return None
        return await self.read_value(secret, pool=pool)

    async def delete_secret(self, secret: dict[str, Any], *, pool: asyncpg.Pool) -> None:
        """Supprime la ligne en base PUIS la valeur wallet (best-effort).

        Ordre important (BUG-38) : si le DELETE SQL échoue (FK RESTRICT — une
        clé/credential référence encore le secret, créé entre le pré-check et
        ici), la valeur wallet n'a PAS été purgée → le secret reste utilisable.
        L'inverse détruisait la valeur d'un secret qui survivait en base.
        """
        await secrets_helper.delete_secret(
            secret_id=secret["id"], user_id=secret["user_id"], pool=pool
        )
        if secret["storage"] == "wallet":
            await self._try_delete_in_wallet(secret, pool=pool)

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
        path = f"roles/{secret_type}/{secret_id}"
        try:
            client = await self._wallet_client(wallet_id=wallet_id, user_id=user_id, pool=pool)
            await self._vault_upsert(client, path, value)
        except (HarpocrateError, SecretDecryptError) as exc:
            raise WalletUnavailableError(str(exc)) from exc
        try:
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
        except Exception:
            # Compensation : l'insert a échoué après l'écriture wallet — on
            # retire la valeur pour ne pas laisser d'orphelin dans le coffre.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(client.secrets.delete, path)
            raise

    async def _wallet_client(
        self, *, wallet_id: UUID, user_id: UUID, pool: asyncpg.Pool
    ) -> Any:
        # Le contrôle de propriété (scoping user_id) s'exécute à CHAQUE appel,
        # avant toute consultation du cache : le store est un singleton
        # partagé entre requêtes, un client en cache ne prouve rien sur le
        # droit de l'appelant courant à utiliser ce wallet.
        wallet = await wallets_helper.get_wallet(
            wallet_id=wallet_id, user_id=user_id, pool=pool
        )
        if wallet is None:
            raise UnknownWalletError(f"wallet {wallet_id} introuvable pour cet utilisateur")
        cached = self._clients.get(wallet_id)
        if cached is not None:
            return cached
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
