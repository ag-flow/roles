"""Tests TDD pour secret_cipher — chiffrement Fernet des secrets locaux."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from role_builder.services.secret_cipher import SecretCipher, cipher_from_settings


def test_encrypt_decrypt_roundtrip() -> None:
    cipher = SecretCipher(Fernet.generate_key().decode())
    token = cipher.encrypt("sk-super-secret")
    assert isinstance(token, bytes)
    assert b"sk-super-secret" not in token
    assert cipher.decrypt(token) == "sk-super-secret"


def test_encrypt_is_non_deterministic() -> None:
    cipher = SecretCipher(Fernet.generate_key().decode())
    assert cipher.encrypt("same") != cipher.encrypt("same")


def test_empty_key_raises() -> None:
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"):
        SecretCipher("")


def test_invalid_key_raises() -> None:
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"):
        SecretCipher("not-a-fernet-key")


def test_decrypt_with_wrong_key_raises() -> None:
    token = SecretCipher(Fernet.generate_key().decode()).encrypt("value")
    other = SecretCipher(Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match="déchiffrement"):
        other.decrypt(token)


def test_cipher_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.config import settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "secret_encryption_key", key, raising=False)
    cipher = cipher_from_settings()
    assert cipher.decrypt(cipher.encrypt("v")) == "v"


def test_cipher_from_settings_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.config import settings

    monkeypatch.setattr(settings, "secret_encryption_key", "", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"):
        cipher_from_settings()
