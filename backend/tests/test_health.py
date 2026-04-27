"""Tests for the /health endpoint."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """/health/ returns ok with db=true when DB responds."""
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True}


def test_health_returns_db_false_on_db_error(
    stubbed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health/ never 5xx — DB acquire failures degrade to db=false."""

    class _RaisingPool:
        def acquire(self) -> Any:
            raise RuntimeError("simulated DB outage")

    from role_builder import db as db_module
    from role_builder.main import app

    monkeypatch.setattr(db_module.db_pool, "_pool", _RaisingPool(), raising=False)
    client = TestClient(app)
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": False}
