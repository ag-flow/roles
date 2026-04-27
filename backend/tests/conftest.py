"""Shared pytest fixtures."""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Stub env vars set at import time so that modules instantiating Settings()
# at module load (e.g. role_builder.config) do not fail during test collection.
os.environ.setdefault("DATABASE_URL", "postgresql://stub")
os.environ.setdefault("MINIO_ENDPOINT", "http://stub")
os.environ.setdefault("MINIO_ACCESS_KEY", "stub")
os.environ.setdefault("MINIO_SECRET_KEY", "stub")
os.environ.setdefault("OPENBAO_URL", "http://stub")
os.environ.setdefault("OPENBAO_TOKEN", "stub")


class _StubConn:
    async def fetchval(self, query: str) -> int:
        assert query == "SELECT 1"
        return 1


class _StubAcquireCtx:
    async def __aenter__(self) -> _StubConn:
        return _StubConn()

    async def __aexit__(self, *args: Any) -> None:
        return None


class _StubPool:
    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx()

    async def close(self) -> None:
        return None


@pytest.fixture()
def stubbed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the minimal env vars required by Settings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://stub")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "stub")
    monkeypatch.setenv("MINIO_SECRET_KEY", "stub")
    monkeypatch.setenv("OPENBAO_URL", "http://stub")
    monkeypatch.setenv("OPENBAO_TOKEN", "stub")


@pytest.fixture()
def client(stubbed_env: None, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient with a stubbed DB pool and orchestrator disabled."""
    from role_builder import db as db_module
    from role_builder.config import settings as _settings
    from role_builder.main import app

    monkeypatch.setattr(_settings, "disable_orchestrator", True, raising=False)
    monkeypatch.setattr(_settings, "disable_ws_relay", True, raising=False)
    monkeypatch.setattr(db_module.db_pool, "_pool", _StubPool(), raising=False)
    return TestClient(app)
