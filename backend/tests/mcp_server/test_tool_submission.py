"""Tests for mcp_server.tools.submission — adaptateur roles__submit_acquisition.

Vérifie l'enveloppe d'erreur uniforme {code, message, details} (§5.6) et le
branchement vers le service (tenant par défaut, date du jour injectée).
Le service lui-même (role_builder.services.acquisition.submission) est
mocké : déjà couvert par ses propres tests d'intégration.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from role_builder.mcp_server.tools import submission as tool
from role_builder.services.acquisition.errors import AcquisitionError


@pytest.fixture(autouse=True)
def _stub_db_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le pool réel n'est pas connecté hors lifespan FastAPI : stub opaque."""
    monkeypatch.setattr(tool.db_pool, "_pool", object(), raising=False)


async def test_submit_acquisition_forwards_to_service_with_default_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.config import TENANT_ID_DEFAULT

    captured: dict[str, Any] = {}

    async def fake_submit(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"request_key": "yt-x-2026-07-05", "status": "discovering", "platform": "youtube", "url": kwargs["url"]}

    monkeypatch.setattr(tool, "_submit_acquisition", fake_submit)

    result = await tool.submit_acquisition(
        "https://youtube.com/@clea-ux", submitted_by="claude-web"
    )

    assert result["request_key"] == "yt-x-2026-07-05"
    assert captured["tenant_id"] == TENANT_ID_DEFAULT
    assert captured["submitted_by"] == "claude-web"
    assert captured["mode"] == "discover_only"
    assert isinstance(captured["today"], date)


async def test_submit_acquisition_returns_uniform_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_submit(**kwargs: Any) -> dict[str, Any]:
        raise AcquisitionError("NO_CREDENTIALS", "no active credential for platform 'youtube'")

    monkeypatch.setattr(tool, "_submit_acquisition", fake_submit)

    result = await tool.submit_acquisition(
        "https://youtube.com/@clea-ux", submitted_by="claude-web"
    )

    assert result == {
        "error": {
            "code": "NO_CREDENTIALS",
            "message": "no active credential for platform 'youtube'",
            "details": {},
        }
    }


async def test_submit_acquisition_forwards_optional_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_submit(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"request_key": "k", "status": "discovering", "platform": "youtube", "url": "u"}

    monkeypatch.setattr(tool, "_submit_acquisition", fake_submit)

    await tool.submit_acquisition(
        "https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        platform="youtube",
        mode="auto",
        filters={"max_items": 5},
        docflow_target={"workspace": "roles"},
        note="corpus UX",
    )

    assert captured["platform"] == "youtube"
    assert captured["mode"] == "auto"
    assert captured["filters"] == {"max_items": 5}
    assert captured["docflow_target"] == {"workspace": "roles"}
    assert captured["note"] == "corpus UX"
