"""Tests for the transcript chunker."""

from __future__ import annotations


def _make_segment(start: float, end: float, text: str) -> dict:
    return {"id": 0, "start": start, "end": end, "text": text}


def test_chunk_short_transcript_returns_one_chunk() -> None:
    """Un transcript court (< target_tokens) tient dans 1 chunk."""
    from role_builder.services.chunker import chunk_transcript

    transcript = {
        "segments": [
            _make_segment(0.0, 2.0, "Bonjour à tous."),
            _make_segment(2.0, 5.0, "Bienvenue dans cette vidéo."),
        ],
    }
    chunks = chunk_transcript(transcript, target_tokens=500, overlap_tokens=50)
    assert len(chunks) == 1
    assert chunks[0].start_s == 0.0
    assert chunks[0].end_s == 5.0
    assert "Bonjour" in chunks[0].text
    assert "Bienvenue" in chunks[0].text


def test_chunk_preserves_timestamps() -> None:
    """Les start_s / end_s des chunks correspondent aux segments inclus."""
    from role_builder.services.chunker import chunk_transcript

    transcript = {
        "segments": [
            _make_segment(0.0, 10.0, "x" * 200),  # ~50 tokens
            _make_segment(10.0, 20.0, "y" * 200),  # ~50 tokens
            _make_segment(20.0, 30.0, "z" * 200),  # ~50 tokens
        ],
    }
    chunks = chunk_transcript(transcript, target_tokens=100, overlap_tokens=0)
    # Avec target=100 et 50 tokens/segment, on a 2 segments par chunk.
    # Premier chunk : seg 1+2 → 0.0-20.0
    # Deuxième chunk : seg 3 → 20.0-30.0
    assert chunks[0].start_s == 0.0
    assert chunks[0].end_s == 20.0
    assert chunks[-1].end_s == 30.0


def test_chunk_overlap_creates_repetition() -> None:
    """Avec overlap > 0, les chunks consécutifs partagent du contenu."""
    from role_builder.services.chunker import chunk_transcript

    # 4 segments de 80 chars (~20 tokens chacun) → ~80 tokens total
    transcript = {
        "segments": [_make_segment(i * 5.0, (i + 1) * 5.0, "x" * 80) for i in range(4)],
    }
    chunks = chunk_transcript(transcript, target_tokens=40, overlap_tokens=20)
    # Premier chunk : 2 segments = 40 tokens. Backtrack 1 segment (20 tokens).
    # 2e chunk démarre au segment 2 (index 1).
    assert len(chunks) >= 2
    # Le 2e chunk commence dans le temps du 1er
    assert chunks[1].start_s < chunks[0].end_s


def test_chunk_empty_transcript_returns_empty() -> None:
    """Pas de segments → pas de chunks."""
    from role_builder.services.chunker import chunk_transcript

    chunks = chunk_transcript({"segments": []}, target_tokens=500, overlap_tokens=50)
    assert chunks == []
