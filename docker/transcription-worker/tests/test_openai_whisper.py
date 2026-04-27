"""Tests pour le provider OpenAI Whisper API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from httpx import HTTPStatusError, Request, Response
            raise HTTPStatusError(
                "fake", request=Request("POST", "http://x"),
                response=Response(status_code=self.status_code, json=self._body),
            )


class _StubAsyncClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_response: _StubResponse | None = None

    async def post(self, path: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"path": path, **kwargs})
        return self.next_response or _StubResponse(200, {})

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def openai_response_verbose() -> dict[str, Any]:
    """Sortie typique de OpenAI Whisper API en verbose_json + word timestamps."""
    return {
        "task": "transcribe",
        "language": "french",
        "duration": 12.34,
        "text": "Bonjour à tous, bienvenue.",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.32,
                "text": "Bonjour à tous,",
                "avg_logprob": -0.21,
                "words": [
                    {"word": "Bonjour", "start": 0.0, "end": 0.42},
                    {"word": "à", "start": 0.42, "end": 0.55},
                    {"word": "tous", "start": 0.55, "end": 1.10},
                ],
            },
            {
                "id": 1,
                "start": 4.32,
                "end": 6.50,
                "text": "bienvenue.",
                "avg_logprob": -0.18,
                "words": [{"word": "bienvenue", "start": 4.32, "end": 6.50}],
            },
        ],
    }


@pytest.mark.asyncio
async def test_transcribe_calls_audio_endpoint_with_verbose_json_and_word(
    tmp_path: Path, openai_response_verbose: dict[str, Any],
) -> None:
    audio = tmp_path / "v1.mp3"
    audio.write_bytes(b"fake audio")

    from worker.providers.openai_whisper import OpenAIWhisperProvider

    p = OpenAIWhisperProvider(api_key="sk-test")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(200, openai_response_verbose)
    p._http = stub  # type: ignore[assignment]

    pivot = await p.transcribe(str(audio), language="fr")

    # 1 appel à /audio/transcriptions
    call = stub.calls[0]
    assert call["path"] == "/audio/transcriptions"
    # response_format + timestamp_granularities + langue dans le multipart
    data = call["data"]
    assert data["model"] == "whisper-1"
    assert data["response_format"] == "verbose_json"
    assert data["timestamp_granularities[]"] == "word"
    assert data["language"] == "fr"

    # Adaptation pivot
    assert pivot.provider == "openai-whisper"
    assert pivot.language == "french"
    assert pivot.duration_s == 12.34
    assert len(pivot.segments) == 2
    assert pivot.segments[0].words[0].word == "Bonjour"


def test_estimate_cost_at_006_per_minute() -> None:
    from worker.providers.openai_whisper import OpenAIWhisperProvider

    p = OpenAIWhisperProvider(api_key="sk-test")
    assert p.estimate_cost(60.0) == pytest.approx(0.006)
    assert p.estimate_cost(600.0) == pytest.approx(0.06)


@pytest.mark.asyncio
async def test_get_remaining_credit_returns_none() -> None:
    """OpenAI n'expose pas de balance API publique."""
    from worker.providers.openai_whisper import OpenAIWhisperProvider

    p = OpenAIWhisperProvider(api_key="sk-test")
    assert await p.get_remaining_credit() is None
