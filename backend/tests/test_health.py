"""Tests for the /health endpoint."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


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


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient with a stubbed DB pool."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://stub")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "stub")
    monkeypatch.setenv("MINIO_SECRET_KEY", "stub")
    monkeypatch.setenv("OPENBAO_URL", "http://stub")
    monkeypatch.setenv("OPENBAO_TOKEN", "stub")

    from role_builder import db as db_module
    from role_builder.main import app

    monkeypatch.setattr(db_module.db_pool, "_pool", _StubPool(), raising=False)
    return TestClient(app)


def test_health_returns_ok(client: TestClient) -> None:
    """/health/ returns ok when DB responds."""
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True}
