"""Gestion async des secrets utilisateurs dans le coffre Harpocrate.

Les clés utilisateur sont stockées avec un chemin hiérarchique :

    users/{email_slug}/transcription/{provider}/{key_id}  — clés de transcription
    users/{email_slug}/scraping/{platform}/{cred_id}      — cookies de scraping
    github/{tenant_id}/{user_id}                           — tokens GitHub OAuth

L'email/user_id sert de compartiment : les secrets de deux utilisateurs ne se mélangent pas.
"""
from __future__ import annotations

import asyncio
import os
import re
from uuid import UUID

import structlog
from harpocrate import SecretNotFound, VaultClient

log = structlog.get_logger(__name__)

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_VAULT_REF_RE = re.compile(r'^\$\{vault://[^:]+:(.+)\}$')


def build_vault_secret_name(email: str | None, provider: str, key_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour une clé de transcription.

    Exemple : users/john_at_example.com/transcription/openai/550e8400-e29b-...
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/transcription/{provider}/{key_id}"


def build_credentials_vault_name(email: str | None, platform: str, cred_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour les cookies de scraping.

    Exemple : users/john_at_example.com/scraping/youtube/550e8400-...
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/scraping/{platform}/{cred_id}"


def build_github_vault_name(user_id: UUID, tenant_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour un token GitHub OAuth.

    Exemple : github/00000000-0000-0000-0000-000000000001/12345678-...
    """
    return f"github/{tenant_id}/{user_id}"


def _primary_vault_identifier() -> str:
    """Retourne le suffixe lowercase du premier HARPOCRATE_API_TOKEN_* configuré."""
    for key in os.environ:
        if key.startswith("HARPOCRATE_API_TOKEN_"):
            return key[len("HARPOCRATE_API_TOKEN_"):].lower()
    return "api1"


def build_transcription_vault_path(email: str | None, provider: str, key_name: str) -> str:
    """Path plain pour une clé de transcription avec nom personnalisé.

    Exemple : users/john_at_example.com/transcription/deepgram/ma_cle
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/transcription/{provider}/{key_name}"


def build_vault_ref(path: str) -> str:
    """Enveloppe un path dans une ref vault : ${vault://api1:path}.

    L'identifiant est déduit du premier HARPOCRATE_API_TOKEN_* configuré.
    """
    identifier = _primary_vault_identifier()
    return f"${{vault://{identifier}:{path}}}"


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
        """Crée ou met à jour un secret dans le coffre."""
        await asyncio.to_thread(
            self._client.secrets.populate, secret_name, False, value
        )
        log.info("user_vault.written", name=secret_name)

    async def read(self, secret_name: str) -> str | None:
        """Lit un secret ; retourne None s'il est absent."""
        try:
            return await asyncio.to_thread(self._client.secrets.get, secret_name)
        except SecretNotFound:
            return None

    async def try_delete(self, secret_name: str) -> None:
        """Best-effort : écrase le secret avec une valeur vide pour l'invalider."""
        try:
            await asyncio.to_thread(
                self._client.secrets.populate, secret_name, False, ""
            )
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
