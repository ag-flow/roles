"""Provider abstrait commun à tous les moteurs de transcription."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from worker.pivot import PivotTranscript


@dataclass
class CreditInfo:
    """Information sur le crédit restant (None si non exposé par le provider)."""
    balance_usd: float | None
    last_check_at: str
    raw: dict[str, Any]


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Interface unifiée pour tous les providers de transcription.

    Chaque provider concret normalise sa sortie au format PivotTranscript.
    """

    name: str
    supports_language_detection: bool
    supports_diarization: bool
    supports_word_timestamps: bool
    cost_per_minute_usd: float | None  # None pour les providers locaux (gratuits modulo électricité)

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        ...

    def estimate_cost(self, duration_s: float) -> float:
        ...

    async def get_remaining_credit(self) -> CreditInfo | None:
        """Retourne le crédit restant si l'API du provider l'expose, None sinon."""
        ...
