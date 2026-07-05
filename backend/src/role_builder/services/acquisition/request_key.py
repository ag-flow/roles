"""Génération du `request_key` — slug lisible, clé de reprise conversationnelle.

Cf. spec v2/01-protocole-mcp.md §2.1 : ``yt-clea-ux-2026-07-04-a3f2``.
`build_request_key_base` est pure (le `today` est injecté par l'appelant,
pas lu depuis l'horloge système, pour rester testable) ; l'unicité en base
est garantie par retry côté service via `with_random_suffix` sur collision
(cf. `acquisition_requests.insert_request` qui propage
`asyncpg.UniqueViolationError`).
"""

from __future__ import annotations

import re
import secrets
from datetime import date
from urllib.parse import urlparse

_PLATFORM_PREFIXES = {
    "youtube": "yt",
    "instagram": "ig",
    "tiktok": "tt",
    "upload": "up",
}

_MAX_HINT_LEN = 30


def build_request_key_base(
    platform: str,
    url: str,
    *,
    note: str | None = None,
    today: date,
) -> str:
    """Construit la base du slug : ``{préfixe}-{hint}-{date}``.

    `note` prime sur l'URL quand fourni (plus lisible pour l'humain qui
    reprend la conversation). Sinon, le hint est dérivé de l'URL : le
    segment `@handle` s'il existe (chaînes/comptes), sinon le dernier
    segment du chemin, sinon "src".
    """
    prefix = _PLATFORM_PREFIXES.get(platform)
    if prefix is None:
        raise ValueError(f"unsupported platform: {platform!r}")

    hint = _slugify(note) if note else _hint_from_url(url)
    hint = hint[:_MAX_HINT_LEN].rstrip("-") or "src"

    return f"{prefix}-{hint}-{today.isoformat()}"


def with_random_suffix(base: str) -> str:
    """Ajoute un suffixe hexadécimal aléatoire (4 chars) pour lever une collision."""
    return f"{base}-{secrets.token_hex(2)}"


def _hint_from_url(url: str) -> str:
    segments = [seg for seg in urlparse(url).path.strip("/").split("/") if seg]
    handle = next((seg for seg in segments if seg.startswith("@")), None)
    raw = (handle or (segments[-1] if segments else "")).lstrip("@")
    return _slugify(raw) or "src"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
