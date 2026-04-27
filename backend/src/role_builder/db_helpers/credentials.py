"""Lecture des cookies de scraping depuis la config (pas d'OpenBao en MVP).

Les cookies arrivent par env vars passées au backend via docker-compose.
Le backend les retransmet au container scraper via `docker run -e ...`.
Rebranchage OpenBao reporté au sprint "Ma stack".
"""
from __future__ import annotations

from role_builder.config import settings


def get_cookies_b64(platform: str) -> str:
    """Return the platform-specific cookies B64 from Settings.

    Empty string for unknown platform or unset cookie. Lookup is
    case-insensitive on the platform name.
    """
    key = platform.lower()
    if key == "youtube":
        return settings.youtube_cookies_b64
    if key == "instagram":
        return settings.instagram_cookies_b64
    if key == "tiktok":
        return settings.tiktok_cookies_b64
    return ""
