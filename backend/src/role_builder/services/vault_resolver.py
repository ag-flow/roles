"""Résolution des références ${vault://id:key} via le coffre Harpocrate."""

from __future__ import annotations

import os
import re
from typing import Any

import structlog
from harpocrate import SecretNotFound, VaultClient
from harpocrate.exceptions import VaultHttpError

log = structlog.get_logger(__name__)

# Regex pour ${vault://identifier:secret_name} en full-string ou embedded
_VAULT_RE = re.compile(r"\$\{vault://([^:}]+):([^}]+)\}")


class VaultResolver:
    """Résout les références vault://id:key depuis HARPOCRATE_API_TOKEN."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        token = os.environ.get("HARPOCRATE_API_TOKEN", "")
        if not token:
            raise RuntimeError(
                "No Harpocrate API key configured. Set HARPOCRATE_API_TOKEN in your environment."
            )
        url = os.environ.get("HARPOCRATE_API_URL", "https://vault.yoops.org")
        self._client = VaultClient(token=token, base_url=url)

    def get_client(self, identifier: str | None = None) -> VaultClient:
        """Retourne le VaultClient unique."""
        return self._client

    def _resolve_one(self, secret_name: str) -> str:
        if secret_name in self._cache:
            return self._cache[secret_name]

        try:
            value = self._client.secrets.get(secret_name)
        except VaultHttpError as exc:
            if exc.status_code in (401, 403):
                raise RuntimeError(
                    f"Harpocrate API key refused (HTTP {exc.status_code}). "
                    "Check that the token is valid and not revoked."
                ) from None
            raise RuntimeError(
                f"Vault error fetching '{secret_name}': HTTP {exc.status_code}"
            ) from None
        except SecretNotFound:
            raise RuntimeError(
                f"Secret '{secret_name}' not found in vault"
            ) from None

        self._cache[secret_name] = value
        log.info("vault.secret.resolved", secret=secret_name)
        return value

    def resolve(self, value: str) -> str:
        """Résout les refs vault dans une chaîne (full ou embedded)."""
        if "${vault://" not in value:
            return value

        def _sub(m: re.Match[str]) -> str:
            return self._resolve_one(m.group(2))

        return _VAULT_RE.sub(_sub, value)

    def resolve_settings(self, settings: Any) -> None:
        """Résout toutes les refs vault dans les champs str du Settings Pydantic."""
        for field_name in type(settings).model_fields:
            raw = getattr(settings, field_name)
            if not isinstance(raw, str) or "${vault://" not in raw:
                continue
            resolved = self.resolve(raw)
            if resolved != raw:
                setattr(settings, field_name, resolved)
                log.debug("vault.settings.patched", field=field_name)
