"""Gestion async des secrets utilisateurs dans le coffre Harpocrate.

Les clés utilisateur sont stockées avec un chemin hiérarchique :

    users/{email_hash}/transcription/{provider}/{key_id}  — clés de transcription
    users/{email_hash}/scraping/{platform}/{cred_id}      — cookies de scraping

{email_hash} est un SHA-256 hex de l'email en minuscules (RGPD : pas de donnée
personnelle en clair dans les paths vault).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from uuid import UUID

import structlog
from harpocrate import SecretNotFound, VaultClient

log = structlog.get_logger(__name__)

_VAULT_REF_RE = re.compile(r'^\$\{vault://[^:]+:(.+)\}$')


def _email_hash(email: str | None) -> str:
    """SHA-256 hex de l'email normalisé, ou 'no_email' si absent."""
    if not email:
        return "no_email"
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def build_vault_secret_name(email: str | None, provider: str, key_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour une clé de transcription."""
    return f"users/{_email_hash(email)}/transcription/{provider}/{key_id}"


def build_credentials_vault_name(email: str | None, platform: str, cred_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour les cookies de scraping."""
    return f"users/{_email_hash(email)}/scraping/{platform}/{cred_id}"


def build_transcription_vault_path(email: str | None, provider: str, key_name: str) -> str:
    """Path plain pour une clé de transcription avec nom personnalisé."""
    return f"users/{_email_hash(email)}/transcription/{provider}/{key_name}"


def build_vault_ref(path: str) -> str:
    """Enveloppe un path dans une ref vault : ${vault://api1:path}."""
    return f"${{vault://api1:{path}}}"


def extract_vault_path(vault_secret_name: str) -> str:
    """Extrait le path depuis une ref vault, ou retourne le plain path (compat legacy).

    "${vault://api1:users/john/transcription/deepgram/ma_cle}" → "users/john/..."
    "users/john/transcription/deepgram/uuid"                  → "users/john/..."
    """
    m = _VAULT_REF_RE.match(vault_secret_name)
    return m.group(1) if m else vault_secret_name


class UserVaultService:
    """Wrapper async autour du VaultClient pour les secrets utilisateurs."""

    def __init__(self, client: VaultClient) -> None:
        self._client = client

    async def write(self, secret_name: str, value: str) -> None:
        """Crée ou met à jour un secret dans le coffre (upsert)."""
        try:
            await asyncio.to_thread(self._client.secrets.put, secret_name, value)
        except SecretNotFound:
            await asyncio.to_thread(self._client.secrets.create, secret_name, value)
        log.info("user_vault.written", name=secret_name)

    async def read(self, secret_name: str) -> str | None:
        """Lit un secret ; retourne None s'il est absent."""
        try:
            return await asyncio.to_thread(self._client.secrets.get, secret_name)
        except SecretNotFound:
            return None

    async def try_delete(self, secret_name: str) -> None:
        """Best-effort : supprime le secret du coffre."""
        try:
            await asyncio.to_thread(self._client.secrets.delete, secret_name)
        except Exception:
            log.exception("user_vault.delete_failed", name=secret_name)


_service: UserVaultService | None = None


def init_service(client: VaultClient) -> None:
    """Initialise le singleton (appelé une fois dans le lifespan FastAPI)."""
    global _service
    _service = UserVaultService(client)


def get_service() -> UserVaultService:
    """Retourne le singleton ; lève RuntimeError si vault non initialisé."""
    if _service is None:
        raise RuntimeError(
            "UserVaultService non initialisé — vault désactivé ou lifespan non démarré"
        )
    return _service
