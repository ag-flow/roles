"""Tests for db_helpers.credentials — read cookies B64 from Settings."""
from __future__ import annotations

import pytest


def test_get_cookies_b64_returns_per_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_cookies_b64('youtube') reads settings.youtube_cookies_b64, etc."""
    from role_builder.config import settings as _settings
    from role_builder.db_helpers import credentials

    monkeypatch.setattr(_settings, "youtube_cookies_b64", "yt-cookies", raising=False)
    monkeypatch.setattr(_settings, "instagram_cookies_b64", "ig-cookies", raising=False)
    monkeypatch.setattr(_settings, "tiktok_cookies_b64", "tt-cookies", raising=False)

    assert credentials.get_cookies_b64("youtube") == "yt-cookies"
    assert credentials.get_cookies_b64("instagram") == "ig-cookies"
    assert credentials.get_cookies_b64("tiktok") == "tt-cookies"


def test_get_cookies_b64_unknown_platform_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown platform returns ''; lookup is case-insensitive on the known ones."""
    from role_builder.config import settings as _settings
    from role_builder.db_helpers import credentials

    monkeypatch.setattr(_settings, "youtube_cookies_b64", "yt-cookies", raising=False)

    assert credentials.get_cookies_b64("foo") == ""
    assert credentials.get_cookies_b64("YOUTUBE") == "yt-cookies"  # case-insensitive
