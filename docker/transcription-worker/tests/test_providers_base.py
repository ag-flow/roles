"""Tests pour le framework provider abstrait."""
from __future__ import annotations

import pytest

from worker.pivot import PivotTranscript


@pytest.mark.asyncio
async def test_provider_protocol_runtime_check() -> None:
    """Une classe minimaliste implémentant le Protocol passe runtime_checkable."""
    from worker.providers.base import (
        CreditInfo,
        TranscriptionProvider,
    )

    class _Impl:
        name = "stub"
        supports_language_detection = False
        supports_diarization = False
        supports_word_timestamps = False
        cost_per_minute_usd = 0.01

        async def transcribe(self, audio_path, *, language=None, options=None):
            return PivotTranscript(
                provider="stub", model="m", language="fr",
                language_confidence=None, duration_s=1.0,
                segments=[], metadata={},
            )

        def estimate_cost(self, duration_s):
            return duration_s / 60 * self.cost_per_minute_usd

        async def get_remaining_credit(self):
            return CreditInfo(balance_usd=42.0, last_check_at="2026-04-27T08:00:00Z", raw={})

    p: TranscriptionProvider = _Impl()
    assert isinstance(p, TranscriptionProvider)
    assert p.estimate_cost(60.0) == 0.01


def test_credit_info_dataclass() -> None:
    """CreditInfo accepte balance None pour les providers sans API balance."""
    from worker.providers.base import CreditInfo

    info = CreditInfo(balance_usd=None, last_check_at="2026-04-27T08:00:00Z", raw={})
    assert info.balance_usd is None
