"""Tests for the Settings module."""
from __future__ import annotations

import pytest


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads required values from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("OPENBAO_URL", "http://bao:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "token")

    from role_builder.config import Settings

    s = Settings()
    assert s.database_url == "postgresql://test:test@localhost/test"
    assert s.minio_endpoint == "http://minio:9000"
    assert s.minio_access_key == "key"
    assert s.minio_secret_key == "secret"
    assert s.openbao_url == "http://bao:8200"
    assert s.openbao_token == "token"
    assert s.log_level == "INFO"  # default
    assert s.agflow_base_url == "https://docker-agflow.yoops.org"  # default
