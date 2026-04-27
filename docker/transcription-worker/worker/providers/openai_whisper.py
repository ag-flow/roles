"""Provider OpenAI Whisper API."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from worker.pivot import PivotTranscript, Segment, Word
from worker.providers.base import CreditInfo


class OpenAIWhisperProvider:
    """Implémentation TranscriptionProvider via OpenAI /v1/audio/transcriptions."""

    name = "openai-whisper"
    supports_language_detection = True
    supports_diarization = False
    supports_word_timestamps = True
    cost_per_minute_usd = 0.006

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300.0,
        )

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        # Lecture synchrone acceptable : audio MP3 quelques MB, lu une seule fois
        # avant l'upload HTTP. Évite la dépendance à anyio/trio pour ce worker.
        audio_bytes = Path(audio_path).read_bytes()  # noqa: ASYNC240
        files = {"file": (audio_path.rsplit("/", 1)[-1], audio_bytes, "audio/mpeg")}
        data: dict[str, Any] = {
            "model": "whisper-1",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        if language:
            data["language"] = language

        resp = await self._http.post("/audio/transcriptions", data=data, files=files)
        resp.raise_for_status()
        body = resp.json()
        return self._adapt(body)

    @staticmethod
    def _adapt(body: dict[str, Any]) -> PivotTranscript:
        segments_in = body.get("segments") or []
        segments_out: list[Segment] = []
        for seg in segments_in:
            words_out = [
                Word(
                    word=w["word"],
                    start=w["start"],
                    end=w["end"],
                    probability=None,  # OpenAI ne renvoie pas de prob par mot
                )
                for w in seg.get("words", [])
            ]
            segments_out.append(Segment(
                id=seg["id"],
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
                avg_logprob=seg.get("avg_logprob"),
                words=words_out,
            ))

        return PivotTranscript(
            provider="openai-whisper",
            model="whisper-1",
            language=body.get("language", ""),
            language_confidence=None,
            duration_s=float(body.get("duration", 0.0)),
            segments=segments_out,
            metadata={
                "transcribed_at": datetime.now(UTC).isoformat(),
            },
        )

    def estimate_cost(self, duration_s: float) -> float:
        return (duration_s / 60.0) * self.cost_per_minute_usd

    async def get_remaining_credit(self) -> CreditInfo | None:
        # OpenAI n'expose pas de balance API publique. La détection à l'usage
        # (HTTP 402 / insufficient_quota) est gérée par error_classifier.
        return None

    async def aclose(self) -> None:
        await self._http.aclose()
