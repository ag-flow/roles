"""Tests for services.acquisition.request_key — génération du slug lisible."""

from __future__ import annotations

from datetime import date

import pytest

from role_builder.services.acquisition.request_key import (
    build_request_key_base,
    with_random_suffix,
)


def test_build_request_key_base_uses_platform_prefix_and_url_hint() -> None:
    """youtube → préfixe 'yt', hint dérivé du dernier segment de l'URL."""
    key = build_request_key_base(
        "youtube", "https://youtube.com/@clea-ux", today=date(2026, 7, 5)
    )
    assert key == "yt-clea-ux-2026-07-05"


def test_build_request_key_base_strips_at_sign_and_lowercases() -> None:
    key = build_request_key_base(
        "youtube", "https://youtube.com/@Clea-UX/videos", today=date(2026, 7, 5)
    )
    assert key.startswith("yt-clea-ux-")


def test_build_request_key_base_uses_note_hint_when_provided() -> None:
    """Une note explicite prime sur le hint dérivé de l'URL (plus lisible)."""
    key = build_request_key_base(
        "instagram",
        "https://instagram.com/somehandle",
        note="Corpus UX designer",
        today=date(2026, 7, 5),
    )
    assert key == "ig-corpus-ux-designer-2026-07-05"


def test_build_request_key_base_falls_back_when_url_has_no_hint() -> None:
    key = build_request_key_base("tiktok", "https://tiktok.com/", today=date(2026, 7, 5))
    assert key == "tt-src-2026-07-05"


def test_build_request_key_base_truncates_long_hints() -> None:
    long_note = "a" * 80
    key = build_request_key_base(
        "youtube", "https://youtube.com/@x", note=long_note, today=date(2026, 7, 5)
    )
    hint_part = key.removeprefix("yt-").removesuffix("-2026-07-05")
    assert len(hint_part) <= 30


def test_build_request_key_base_rejects_unknown_platform() -> None:
    with pytest.raises(ValueError, match="platform"):
        build_request_key_base("unknown", "https://example.com/x", today=date(2026, 7, 5))


def test_with_random_suffix_appends_four_hex_chars() -> None:
    suffixed = with_random_suffix("yt-clea-ux-2026-07-05")
    prefix, _, suffix = suffixed.rpartition("-")
    assert prefix == "yt-clea-ux-2026-07-05"
    assert len(suffix) == 4
    int(suffix, 16)  # must be valid hex
