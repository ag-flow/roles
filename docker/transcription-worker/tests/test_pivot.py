"""Tests pour le format pivot des transcripts."""
from __future__ import annotations

import json


def test_pivot_transcript_to_dict_round_trip() -> None:
    """PivotTranscript.to_dict produit un JSON conforme spec 04 § Format pivot."""
    from worker.pivot import PivotTranscript, Segment, Word

    pivot = PivotTranscript(
        provider="openai-whisper",
        model="whisper-1",
        language="fr",
        language_confidence=None,
        duration_s=812.3,
        segments=[
            Segment(
                id=0, start=0.0, end=4.32,
                text="Bonjour à tous",
                avg_logprob=-0.21,
                words=[Word(word="Bonjour", start=0.0, end=0.42, probability=0.98)],
            ),
        ],
        metadata={"transcribed_at": "2026-04-27T08:00:00Z", "cost_estimate_usd": 0.0043},
    )
    data = pivot.to_dict()
    assert data["schema_version"] == "1.0"
    assert data["provider"] == "openai-whisper"
    assert data["segments"][0]["words"][0]["word"] == "Bonjour"
    # Round-trip JSON ne casse rien
    assert json.loads(json.dumps(data))["language"] == "fr"


def test_pivot_transcript_handles_no_words() -> None:
    """Provider sans word-timestamps : Segment.words=[]."""
    from worker.pivot import PivotTranscript, Segment

    pivot = PivotTranscript(
        provider="x", model="y", language="fr", language_confidence=None,
        duration_s=10.0,
        segments=[Segment(id=0, start=0.0, end=10.0, text="hello", avg_logprob=None, words=[])],
        metadata={},
    )
    data = pivot.to_dict()
    assert data["segments"][0]["words"] == []
