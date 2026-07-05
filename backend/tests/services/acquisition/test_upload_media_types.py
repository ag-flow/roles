"""Tests purs de services.acquisition.upload.media_types (liste blanche §2.2)."""

from __future__ import annotations

import pytest

from role_builder.services.acquisition.upload import media_types


@pytest.mark.parametrize(
    ("media_type", "is_video", "extension"),
    [
        ("audio/mpeg", False, ".mp3"),
        ("audio/wav", False, ".wav"),
        ("audio/mp4", False, ".m4a"),
        ("audio/ogg", False, ".ogg"),
        ("audio/flac", False, ".flac"),
        ("video/mp4", True, ".mp4"),
        ("video/quicktime", True, ".mov"),
        ("video/webm", True, ".webm"),
    ],
)
def test_whitelist(media_type: str, is_video: bool, extension: str) -> None:
    assert media_types.is_supported(media_type)
    assert media_types.is_video(media_type) is is_video
    assert media_types.extension_for(media_type) == extension


@pytest.mark.parametrize(
    "media_type",
    ["application/pdf", "text/plain", "image/png", "video/x-msvideo", "", "audio/"],
)
def test_unsupported_types_rejected(media_type: str) -> None:
    assert not media_types.is_supported(media_type)
