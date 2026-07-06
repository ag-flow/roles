"""Chiffrement symétrique des secrets stockés en base (Fernet).

La clé SECRET_ENCRYPTION_KEY est un secret d'infrastructure : générée par
dev-deploy.sh dans le .env, jamais dans le coffre (elle protège précisément
ce qui ne peut pas y aller — tokens de wallets et secrets « local »).
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SecretDecryptError(RuntimeError):
    """La valeur chiffrée ne se déchiffre pas (clé changée ou donnée corrompue)."""


class SecretCipher:
    """Chiffre/déchiffre les valeurs sensibles persistées en base."""

    def __init__(self, key: str) -> None:
        if not key:
            raise RuntimeError(
                "SECRET_ENCRYPTION_KEY manquante — requise pour chiffrer les "
                "secrets en base (générée par dev-deploy.sh)."
            )
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "SECRET_ENCRYPTION_KEY invalide — attendu une clé Fernet "
                "(32 octets encodés base64 url-safe)."
            ) from exc

    def encrypt(self, value: str) -> bytes:
        """Chiffre une valeur en clair ; le résultat est non déterministe."""
        return self._fernet.encrypt(value.encode())

    def decrypt(self, token: bytes) -> str:
        """Déchiffre un token Fernet produit par encrypt()."""
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken as exc:
            raise SecretDecryptError(
                "Échec de déchiffrement d'un secret — SECRET_ENCRYPTION_KEY "
                "a changé ou la valeur en base est corrompue."
            ) from exc


def cipher_from_settings() -> SecretCipher:
    """Construit le cipher depuis settings.secret_encryption_key."""
    from role_builder.config import settings

    return SecretCipher(settings.secret_encryption_key)
