"""Smoke test — le mount /mcp boote réellement (session_manager.run() non désactivé).

Un seul test dans tout le process exerce ce chemin (disable_mcp_server=False) :
StreamableHTTPSessionManager.run() est mono-usage par instance (cf. Settings.
disable_mcp_server) — les autres tests passent par le `client` fixture qui le
désactive pour pouvoir recréer un TestClient(app) par test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_app_boots_with_mcp_mount_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql://stub")
    os.environ.setdefault("MINIO_ENDPOINT", "http://stub")
    os.environ.setdefault("MINIO_ACCESS_KEY", "stub")
    os.environ.setdefault("MINIO_SECRET_KEY", "stub")

    from role_builder import db as db_module
    from role_builder.config import settings
    from role_builder.main import app

    class _StubConn:
        async def fetchval(self, query: str) -> int:
            return 1

    class _StubAcquireCtx:
        async def __aenter__(self) -> _StubConn:
            return _StubConn()

        async def __aexit__(self, *args: object) -> None:
            return None

    class _StubPool:
        def acquire(self) -> _StubAcquireCtx:
            return _StubAcquireCtx()

        async def close(self) -> None:
            return None

    monkeypatch.setattr(settings, "disable_orchestrator", True, raising=False)
    monkeypatch.setattr(settings, "disable_ws_relay", True, raising=False)
    monkeypatch.setattr(settings, "disable_worker_manager", True, raising=False)
    monkeypatch.setattr(settings, "disable_scheduler", True, raising=False)
    monkeypatch.setattr(settings, "disable_auth", True, raising=False)
    monkeypatch.setattr(settings, "disable_migrations", True, raising=False)
    monkeypatch.setattr(settings, "disable_vault", True, raising=False)
    monkeypatch.setattr(settings, "disable_mcp_server", False, raising=False)
    monkeypatch.setattr(db_module.db_pool, "_pool", _StubPool(), raising=False)

    with TestClient(app) as client:
        resp = client.get("/health/")
        assert resp.status_code == 200
