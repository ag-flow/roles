"""Tests for the /health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """/health/ returns ok when DB responds."""
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True}
