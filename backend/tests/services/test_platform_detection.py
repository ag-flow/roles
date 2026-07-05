"""Tests for services.acquisition.platform_detection — déduction plateforme + INVALID_URL/UNSUPPORTED_PLATFORM."""

from __future__ import annotations

import pytest

from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.platform_detection import deduce_platform


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtube.com/@clea-ux", "youtube"),
        ("https://www.youtube.com/@clea-ux", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://instagram.com/somehandle", "instagram"),
        ("https://www.tiktok.com/@handle", "tiktok"),
    ],
)
def test_deduce_platform_from_known_hosts(url: str, expected: str) -> None:
    assert deduce_platform(url, platform_hint=None) == expected


def test_deduce_platform_uses_explicit_hint_over_url() -> None:
    assert deduce_platform("https://youtube.com/@x", platform_hint="instagram") == "instagram"


def test_deduce_platform_rejects_unsupported_hint() -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        deduce_platform("https://youtube.com/@x", platform_hint="vimeo")
    assert exc_info.value.code == "UNSUPPORTED_PLATFORM"


def test_deduce_platform_rejects_unknown_host() -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        deduce_platform("https://vimeo.com/12345", platform_hint=None)
    assert exc_info.value.code == "UNSUPPORTED_PLATFORM"


def test_deduce_platform_rejects_unparseable_url() -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        deduce_platform("not-a-url", platform_hint=None)
    assert exc_info.value.code == "INVALID_URL"


def test_deduce_platform_rejects_empty_url() -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        deduce_platform("", platform_hint=None)
    assert exc_info.value.code == "INVALID_URL"
