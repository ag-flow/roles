"""Format pivot du transcript (cf. spec 04 § Format pivot)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Word:
    word: str
    start: float
    end: float
    probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "start": self.start,
            "end": self.end,
            "probability": self.probability,
        }


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "avg_logprob": self.avg_logprob,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class PivotTranscript:
    """Format pivot indépendant du provider. Cf. spec 04 § Format pivot."""
    provider: str
    model: str
    language: str
    language_confidence: float | None
    duration_s: float
    segments: list[Segment]
    metadata: dict[str, Any]

    SCHEMA_VERSION = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "duration_s": self.duration_s,
            "segments": [s.to_dict() for s in self.segments],
            "metadata": self.metadata,
        }
