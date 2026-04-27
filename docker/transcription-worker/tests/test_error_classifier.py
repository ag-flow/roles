"""Tests pour le classifier d'erreurs de transcription."""
from __future__ import annotations


def test_classify_401_invalid_key() -> None:
    from worker.error_classifier import ErrorCategory, classify_error

    err = classify_error(provider_name="openai-whisper", status_code=401,
                         body={"error": {"code": "invalid_api_key", "message": "Invalid API key"}})
    assert err.category == ErrorCategory.INVALID_KEY
    assert err.should_disable_key is True
    assert err.should_retry is False


def test_classify_402_exhausted() -> None:
    from worker.error_classifier import ErrorCategory, classify_error

    err = classify_error(provider_name="openai-whisper", status_code=402,
                         body={"error": {"code": "insufficient_quota"}})
    assert err.category == ErrorCategory.EXHAUSTED
    assert err.should_disable_key is True


def test_classify_429_rate_limit_not_quota() -> None:
    from worker.error_classifier import ErrorCategory, classify_error

    err = classify_error(provider_name="openai-whisper", status_code=429,
                         body={"error": {"code": "rate_limit_exceeded"}})
    assert err.category == ErrorCategory.RATE_LIMIT
    assert err.should_retry is True
    assert err.should_disable_key is False


def test_classify_429_quota_is_exhausted() -> None:
    from worker.error_classifier import ErrorCategory, classify_error

    err = classify_error(provider_name="openai-whisper", status_code=429,
                         body={"error": {"code": "monthly_quota_exceeded"}})
    assert err.category == ErrorCategory.EXHAUSTED
    assert err.should_disable_key is True


def test_classify_5xx_transient() -> None:
    from worker.error_classifier import ErrorCategory, classify_error

    err = classify_error(provider_name="openai-whisper", status_code=502, body={})
    assert err.category == ErrorCategory.TRANSIENT
    assert err.should_retry is True


def test_classify_unknown_defaults_to_transient() -> None:
    """Si on ne sait pas, on retry — moins risqué que de désactiver une clé valide."""
    from worker.error_classifier import ErrorCategory, classify_error

    err = classify_error(provider_name="unknown-provider", status_code=418, body={})
    assert err.category == ErrorCategory.TRANSIENT
    assert err.should_disable_key is False
    assert err.should_retry is True
