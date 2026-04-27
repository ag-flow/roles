"""Classification des erreurs renvoyées par les providers de transcription.

Spec : docs/specs/04-transcription.md § Classification des erreurs et bascule.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    INVALID_KEY = "invalid_key"
    EXHAUSTED = "exhausted"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    category: ErrorCategory
    message: str
    should_retry: bool
    should_disable_key: bool


_QUOTA_HINT_KEYWORDS = ("quota", "insufficient", "billing", "exceeded")


def _looks_like_quota(body: dict[str, Any]) -> bool:
    err = body.get("error", {}) if isinstance(body, dict) else {}
    code = (err.get("code") or "").lower()
    msg = (err.get("message") or "").lower()
    blob = code + " " + msg
    return any(k in blob for k in _QUOTA_HINT_KEYWORDS) and "rate_limit" not in blob


def classify_error(
    *,
    provider_name: str,
    status_code: int,
    body: dict[str, Any],
) -> ClassifiedError:
    """Map une erreur HTTP du provider vers une ClassifiedError."""
    err_obj = body.get("error", {}) if isinstance(body, dict) else {}
    code = (err_obj.get("code") or "").lower()
    message = err_obj.get("message") or f"HTTP {status_code}"

    if status_code == 401 or "invalid_api_key" in code:
        return ClassifiedError(
            category=ErrorCategory.INVALID_KEY, message=message,
            should_retry=False, should_disable_key=True,
        )

    if status_code == 402:
        return ClassifiedError(
            category=ErrorCategory.EXHAUSTED, message=message,
            should_retry=False, should_disable_key=True,
        )

    if status_code == 429:
        if _looks_like_quota(body):
            return ClassifiedError(
                category=ErrorCategory.EXHAUSTED, message=message,
                should_retry=False, should_disable_key=True,
            )
        return ClassifiedError(
            category=ErrorCategory.RATE_LIMIT, message=message,
            should_retry=True, should_disable_key=False,
        )

    if status_code >= 500:
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT, message=message,
            should_retry=True, should_disable_key=False,
        )

    # Default conservateur : transient (retry max_attempts gère la cap)
    return ClassifiedError(
        category=ErrorCategory.TRANSIENT, message=message,
        should_retry=True, should_disable_key=False,
    )
