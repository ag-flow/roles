"""Tests TDD pour transcription_validator (validation clés API + balance Deepgram)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

# ---------------------------------------------------------------------------
# Stub httpx.AsyncClient
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict[str, Any]:
        return self._body


class _StubAsyncClient:
    """Stub minimal pour httpx.AsyncClient avec context manager async."""

    def __init__(self, responses: list[_StubResponse] | None = None) -> None:
        self._responses = list(responses or [])
        self._call_index = 0
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> _StubAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"url": url, **kwargs})
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        return _StubResponse(200)


def make_client_factory(*responses: _StubResponse) -> type[_StubAsyncClient]:
    """Retourne une classe-stub capturant les réponses données."""
    stub_instance = _StubAsyncClient(list(responses))

    class _Factory:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _StubAsyncClient:
            return stub_instance

        async def __aexit__(self, *args: Any) -> None:
            return None

    _Factory._stub = stub_instance  # type: ignore[attr-defined]
    return _Factory  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tests validate_transcription_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_openai_whisper_valid_key_retourne_valid_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_transcription_key openai-whisper avec clé valide → valid=True."""
    import role_builder.services.transcription_validator as mod

    factory = make_client_factory(_StubResponse(200, {"data": []}))
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)

    result = await mod.validate_transcription_key("openai-whisper", "valid-key")

    assert result["valid"] is True
    assert result["error"] is None
    assert result["balance_usd"] is None


@pytest.mark.asyncio
async def test_validate_openai_whisper_bad_key_retourne_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_transcription_key openai-whisper avec clé invalide (401) → valid=False."""
    import role_builder.services.transcription_validator as mod

    factory = make_client_factory(_StubResponse(401))
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)

    result = await mod.validate_transcription_key("openai-whisper", "bad-key")

    assert result["valid"] is False
    assert result["error"] is not None
    assert "auth failed" in result["error"]
    assert "401" in result["error"]


@pytest.mark.asyncio
async def test_validate_openai_whisper_server_error_retourne_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_transcription_key openai-whisper sur HTTP 500 → valid=False."""
    import role_builder.services.transcription_validator as mod

    factory = make_client_factory(_StubResponse(500))
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)

    result = await mod.validate_transcription_key("openai-whisper", "key")

    assert result["valid"] is False
    assert result["error"] is not None
    assert "500" in result["error"]


@pytest.mark.asyncio
async def test_validate_openai_whisper_timeout_retourne_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_transcription_key sur TimeoutException → valid=False, error='timeout'."""
    import role_builder.services.transcription_validator as mod

    class _TimeoutClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _TimeoutClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> _StubResponse:
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(mod.httpx, "AsyncClient", _TimeoutClient)

    result = await mod.validate_transcription_key("openai-whisper", "key")

    assert result["valid"] is False
    assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_validate_provider_inconnu_retourne_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_transcription_key avec provider inconnu → valid=False, error 'unsupported'."""
    import role_builder.services.transcription_validator as mod

    result = await mod.validate_transcription_key("unknown-provider", "key")

    assert result["valid"] is False
    assert result["error"] is not None
    assert "unsupported" in result["error"]


@pytest.mark.asyncio
async def test_validate_deepgram_valid_retourne_valid_true_et_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_transcription_key deepgram valide → valid=True ET balance_usd renseigné."""
    import role_builder.services.transcription_validator as mod

    # Séquence : 1) GET /v1/projects (validate) 2) GET /v1/projects (fetch_balance) 3) GET balances
    projects_body = {"projects": [{"project_id": "proj-1"}]}
    balances_body = {"balances": [{"amount": 42.5, "units": "usd"}]}

    responses = [
        _StubResponse(200, projects_body),  # validate_transcription_key
        _StubResponse(200, projects_body),  # fetch_balance → projects
        _StubResponse(200, balances_body),  # fetch_balance → balances proj-1
    ]

    factory = make_client_factory(*responses)
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)

    result = await mod.validate_transcription_key("deepgram", "valid-key")

    assert result["valid"] is True
    assert result["error"] is None
    assert result["balance_usd"] == 42.5


@pytest.mark.asyncio
async def test_fetch_balance_deepgram_retourne_somme_usd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_balance deepgram avec 2 projets à 50$ chacun → 100.0."""
    import role_builder.services.transcription_validator as mod

    projects_body = {
        "projects": [
            {"project_id": "proj-1"},
            {"project_id": "proj-2"},
        ]
    }
    balances_body = {"balances": [{"amount": 50.0, "units": "usd"}]}

    responses = [
        _StubResponse(200, projects_body),
        _StubResponse(200, balances_body),  # proj-1
        _StubResponse(200, balances_body),  # proj-2
    ]

    factory = make_client_factory(*responses)
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)

    balance = await mod.fetch_balance("deepgram", "valid-key")

    assert balance == 100.0


@pytest.mark.asyncio
async def test_fetch_balance_openai_retourne_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_balance pour un provider non Deepgram → None sans appel HTTP."""
    import role_builder.services.transcription_validator as mod

    # Aucun appel HTTP ne doit être fait
    called = []

    class _NeverCalledClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _NeverCalledClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> _StubResponse:
            called.append(url)
            return _StubResponse(200)

    monkeypatch.setattr(mod.httpx, "AsyncClient", _NeverCalledClient)

    result = await mod.fetch_balance("openai-whisper", "key")

    assert result is None
    assert len(called) == 0


@pytest.mark.asyncio
async def test_fetch_balance_deepgram_sur_erreur_500_retourne_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_balance deepgram sur erreur HTTP 500 → None, pas d'exception."""
    import role_builder.services.transcription_validator as mod

    factory = make_client_factory(_StubResponse(500))
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)

    result = await mod.fetch_balance("deepgram", "key")

    assert result is None
