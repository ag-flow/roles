"""Tests pour le provider faster-whisper local."""
from __future__ import annotations

from typing import Any

import pytest


class _StubSegment:
    """Mimique un Segment de faster-whisper."""
    def __init__(self, id, start, end, text, avg_logprob, words=None):
        self.id, self.start, self.end, self.text, self.avg_logprob = id, start, end, text, avg_logprob
        self.words = words or []


class _StubWord:
    def __init__(self, word, start, end, probability):
        self.word, self.start, self.end, self.probability = word, start, end, probability


class _StubInfo:
    def __init__(self, language, language_probability, duration):
        self.language = language
        self.language_probability = language_probability
        self.duration = duration


class _StubModel:
    """Simule WhisperModel.transcribe()."""
    def __init__(self, segments, info):
        self.segments = segments
        self.info = info
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, audio_path, **kwargs):
        self.calls.append({"audio_path": audio_path, **kwargs})
        return iter(self.segments), self.info


@pytest.fixture()
def stub_model_with_one_segment() -> _StubModel:
    return _StubModel(
        segments=[
            _StubSegment(
                id=0, start=0.0, end=4.32, text="Bonjour", avg_logprob=-0.21,
                words=[_StubWord("Bonjour", 0.0, 0.42, 0.98)],
            )
        ],
        info=_StubInfo(language="fr", language_probability=0.99, duration=812.0),
    )


@pytest.mark.asyncio
async def test_transcribe_calls_model_and_adapts_to_pivot(stub_model_with_one_segment) -> None:
    from worker.providers.faster_whisper import FasterWhisperProvider

    p = FasterWhisperProvider.__new__(FasterWhisperProvider)
    p._model_name = "large-v3"
    p._device = "cpu"
    p._compute_type = "int8"
    p._model = stub_model_with_one_segment  # bypass __init__ heavy load

    pivot = await p.transcribe("/tmp/v1.mp3", language="fr")

    assert pivot.provider == "faster-whisper"
    assert pivot.model == "large-v3"
    assert pivot.language == "fr"
    assert pivot.language_confidence == pytest.approx(0.99)
    assert pivot.duration_s == 812.0
    assert pivot.segments[0].words[0].probability == pytest.approx(0.98)


def test_estimate_cost_returns_zero_for_local_provider() -> None:
    from worker.providers.faster_whisper import FasterWhisperProvider

    p = FasterWhisperProvider.__new__(FasterWhisperProvider)
    p._model_name = "large-v3"
    assert p.estimate_cost(3600.0) == 0.0


@pytest.mark.asyncio
async def test_get_remaining_credit_is_none_for_local() -> None:
    from worker.providers.faster_whisper import FasterWhisperProvider

    p = FasterWhisperProvider.__new__(FasterWhisperProvider)
    assert await p.get_remaining_credit() is None
