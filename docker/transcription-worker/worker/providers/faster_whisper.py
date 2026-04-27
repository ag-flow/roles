"""Provider faster-whisper local (CPU ou CUDA)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from worker.pivot import PivotTranscript, Segment, Word
from worker.providers.base import CreditInfo


class FasterWhisperProvider:
    """Provider local. Charge le modèle en mémoire à l'init.

    Sur CPU : compute_type='int8' recommandé.
    Sur CUDA : compute_type='float16' recommandé (RTX 4090 sur pve2).
    """

    name = "faster-whisper"
    supports_language_detection = True
    supports_diarization = False
    supports_word_timestamps = True
    cost_per_minute_usd = None  # local : pas de coût marginal

    def __init__(
        self,
        *,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "float16",
    ) -> None:
        # Import lazy : faster-whisper est lourd à importer.
        from faster_whisper import WhisperModel

        self._model_name = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        opts = options or {}
        beam_size = int(opts.get("beam_size", 5))

        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            beam_size=beam_size,
        )

        segments_out: list[Segment] = []
        for seg in segments_iter:
            words_out = [
                Word(word=w.word, start=w.start, end=w.end, probability=w.probability)
                for w in (seg.words or [])
            ]
            segments_out.append(Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=seg.text,
                avg_logprob=seg.avg_logprob,
                words=words_out,
            ))

        return PivotTranscript(
            provider="faster-whisper",
            model=self._model_name,
            language=info.language,
            language_confidence=info.language_probability,
            duration_s=info.duration,
            segments=segments_out,
            metadata={
                "transcribed_at": datetime.now(UTC).isoformat(),
                "device": self._device,
                "compute_type": self._compute_type,
            },
        )

    def estimate_cost(self, duration_s: float) -> float:
        return 0.0

    async def get_remaining_credit(self) -> CreditInfo | None:
        return None
