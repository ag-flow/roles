"""Garde au boot : SECRET_ENCRYPTION_KEY manquante → échec bruyant du lifespan."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_lifespan_fails_fast_without_encryption_key(
    stubbed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.config import settings as _settings
    from role_builder.main import app

    monkeypatch.setattr(_settings, "secret_encryption_key", "", raising=False)
    monkeypatch.setattr(_settings, "disable_mcp_server", True, raising=False)

    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"), TestClient(app):
        pass
