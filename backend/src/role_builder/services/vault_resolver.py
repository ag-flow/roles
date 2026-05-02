"""Résolution des références ${vault://id:key} via le coffre Harpocrate."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import structlog
from harpocrate import SecretNotFound, VaultClient
from harpocrate.exceptions import VaultHttpError

log = structlog.get_logger(__name__)

# Regex pour ${vault://identifier:secret_name} en full-string ou embedded
_VAULT_RE = re.compile(r"\$\{vault://([^:}]+):([^}]+)\}")


@dataclass(frozen=True)
class _ApiKeyConfig:
    identifier: str
    url: str
    token: str


class VaultResolver:
    """Résout les références vault://id:key depuis les env vars HARPOCRATE_API_TOKEN_*."""

    def __init__(self) -> None:
        self._configs: dict[str, _ApiKeyConfig] = {}
        self._clients: dict[str, VaultClient] = {}
        self._cache: dict[str, str] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        for key, value in os.environ.items():
            if not key.startswith("HARPOCRATE_API_TOKEN_"):
                continue
            identifier = key[len("HARPOCRATE_API_TOKEN_"):].lower()
            if not identifier:
                log.warning("vault.config.empty_identifier", env_key=key)
                continue
            url_env = f"HARPOCRATE_API_URL_{identifier.upper()}"
            url = os.environ.get(url_env, "https://vault.yoops.org")
            cfg = _ApiKeyConfig(identifier=identifier, url=url, token=value)
            self._configs[identifier] = cfg
            # Instanciation immédiate : permet aux mocks de patch être actifs à __init__.
            self._clients[identifier] = VaultClient(token=cfg.token, base_url=cfg.url)

        if not self._configs:
            raise RuntimeError(
                "No Harpocrate API key configured, cannot resolve secrets. "
                "Set HARPOCRATE_API_TOKEN_<IDENTIFIER> in your environment."
            )

    def _client(self, identifier: str) -> VaultClient:
        if identifier not in self._clients:
            raise RuntimeError(
                f"Unknown Harpocrate identifier: {identifier!r}. "
                f"Known identifiers: {list(self._configs)}"
            )
        return self._clients[identifier]

    def _resolve_one(self, identifier: str, secret_name: str) -> str:
        cache_key = f"{identifier}:{secret_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            value = self._client(identifier).secrets.get(secret_name)
        except VaultHttpError as exc:
            if exc.status_code in (401, 403):
                raise RuntimeError(
                    f"Harpocrate API key '{identifier}' refused (HTTP {exc.status_code}). "
                    "Check that the token is valid and not revoked."
                ) from None
            raise RuntimeError(
                f"Vault error fetching '{secret_name}' via '{identifier}': "
                f"HTTP {exc.status_code}"
            ) from None
        except SecretNotFound:
            raise RuntimeError(
                f"Secret '{secret_name}' not found in vault for identifier '{identifier}'"
            ) from None

        self._cache[cache_key] = value
        log.info("vault.secret.resolved", identifier=identifier, secret=secret_name)
        return value

    def resolve(self, value: str) -> str:
        """Résout les refs vault dans une chaîne (full ou embedded)."""
        if "${vault://" not in value:
            return value

        def _sub(m: re.Match[str]) -> str:
            return self._resolve_one(m.group(1), m.group(2))

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
