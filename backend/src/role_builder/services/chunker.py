"""Chunking d'un transcript pivot en fenêtres avec overlap, timestamps préservés.

Stratégie MVP : taille fixe par tokens approximés (1 token ~= 4 caractères),
frontières de phrases (segments) respectées, overlap configurable.

Référence : ``docs/specs/05-corpus-indexing.md`` § Stratégie de chunking.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TranscriptChunk:
    """Chunk produit par le chunker. word_count = approximation tokens."""

    text: str
    start_s: float
    end_s: float
    word_count: int


def _approx_tokens(text: str) -> int:
    """Approximation : 1 token ~= 4 caractères en français. Précis ~20%."""
    return max(1, len(text) // 4)


def chunk_transcript(
    transcript: dict[str, Any],
    *,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[TranscriptChunk]:
    """Découpe un PivotTranscript en chunks avec overlap.

    Args:
        transcript: dict pivot avec key ``segments`` (chaque segment a
            start/end/text).
        target_tokens: taille cible par chunk (~500 tokens).
        overlap_tokens: backtrack en tokens entre chunks consécutifs.

    Returns:
        Liste de :class:`TranscriptChunk`, chacun avec text concaténé +
        start_s/end_s couvrant les segments inclus.
    """
    segments_raw = transcript.get("segments", [])
    if not segments_raw:
        return []

    sentences: list[dict[str, Any]] = [
        {
            "text": str(seg["text"]).strip(),
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "tokens": _approx_tokens(str(seg["text"])),
        }
        for seg in segments_raw
        if str(seg.get("text", "")).strip()
    ]
    if not sentences:
        return []

    chunks: list[TranscriptChunk] = []
    i = 0
    n = len(sentences)
    while i < n:
        # Accumuler des phrases jusqu'à atteindre target_tokens.
        buf_text: list[str] = []
        buf_tokens = 0
        start_s = sentences[i]["start"]
        end_s = sentences[i]["end"]
        j = i
        while j < n and buf_tokens < target_tokens:
            buf_text.append(sentences[j]["text"])
            buf_tokens += sentences[j]["tokens"]
            end_s = sentences[j]["end"]
            j += 1

        chunks.append(
            TranscriptChunk(
                text=" ".join(buf_text),
                start_s=start_s,
                end_s=end_s,
                word_count=buf_tokens,
            )
        )

        if j >= n:
            break

        # Backtrack pour overlap : reculer i de manière à inclure ~overlap_tokens.
        if overlap_tokens <= 0:
            i = j
        else:
            backtrack = 0
            k = j
            while k > i + 1 and backtrack < overlap_tokens:
                k -= 1
                backtrack += sentences[k]["tokens"]
            i = max(k, i + 1)

    return chunks
