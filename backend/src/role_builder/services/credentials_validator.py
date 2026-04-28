"""Validation des cookies de scraping (format Netscape).

Parse un fichier cookies.txt et vérifie que les cookies requis
pour la plateforme cible sont présents.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any, Final

import structlog

log = structlog.get_logger(__name__)

# Cookies clés requis pour qu'une auth soit considérée présente.
# Si aucun de ces noms n'apparaît dans le fichier, on considère les
# cookies invalides — ils risquent de ne pas suffire au scraper.
PLATFORM_REQUIRED_COOKIES: Final[dict[str, list[str]]] = {
    "youtube": ["SID", "SAPISID", "__Secure-3PSID"],  # au moins un
    "instagram": ["sessionid"],
    "tiktok": ["sessionid", "sid_tt"],
}


def parse_netscape_cookies(content: str) -> list[dict[str, Any]]:
    """Parse un fichier cookies.txt format Netscape.

    Format : domain<TAB>flag<TAB>path<TAB>secure<TAB>expiry<TAB>name<TAB>value
    Lignes vides ou commençant par # ignorées.
    Retourne list de dicts {domain, flag, path, secure, expiry, name, value}.
    Lève ValueError si une ligne ne respecte pas le format (7 champs séparés par tab).
    """
    cookies: list[dict[str, Any]] = []
    for lineno, raw in enumerate(content.splitlines(), start=1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            # Tolérer "#HttpOnly_..." (préfixe Netscape spécial) — extraire le reste si présent
            stripped = line.lstrip()
            if stripped.startswith("#HttpOnly_"):
                line = stripped[len("#HttpOnly_") :]
            else:
                continue
        parts = line.split("\t")
        if len(parts) != 7:
            raise ValueError(f"line {lineno}: expected 7 tab-separated fields, got {len(parts)}")
        domain, flag, path, secure, expiry, name, value = parts
        try:
            expiry_int = int(expiry)
        except ValueError as exc:
            raise ValueError(f"line {lineno}: invalid expiry '{expiry}'") from exc
        cookies.append(
            {
                "domain": domain,
                "flag": flag == "TRUE",
                "path": path,
                "secure": secure == "TRUE",
                "expiry": expiry_int,
                "name": name,
                "value": value,
            }
        )
    return cookies


async def validate_cookies(platform: str, cookies_b64: str) -> dict[str, Any]:
    """Décode base64 + parse + vérifie qu'au moins un cookie clé est présent.

    Retourne {valid: bool, error: str | None, expires_at: datetime | None,
              cookies_count: int}.

    expires_at = max expiry parmi les cookies clés (ou None si pas dispo / 0).
    Si platform inconnue → valid=False, error="unknown platform".
    Si base64 invalide → valid=False, error="invalid base64".
    Si parse échoue → valid=False, error=str(ValueError).
    Si aucun cookie clé présent → valid=False, error="missing required cookies for <platform>".
    """
    required = PLATFORM_REQUIRED_COOKIES.get(platform)
    if required is None:
        return {
            "valid": False,
            "error": f"unknown platform: {platform}",
            "expires_at": None,
            "cookies_count": 0,
        }

    try:
        decoded = base64.b64decode(cookies_b64).decode("utf-8")
    except Exception as exc:
        return {
            "valid": False,
            "error": f"invalid base64: {exc}",
            "expires_at": None,
            "cookies_count": 0,
        }

    try:
        cookies = parse_netscape_cookies(decoded)
    except ValueError as exc:
        return {
            "valid": False,
            "error": f"parse error: {exc}",
            "expires_at": None,
            "cookies_count": 0,
        }

    found_required = [c for c in cookies if c["name"] in required]
    if not found_required:
        return {
            "valid": False,
            "error": (f"missing required cookies for {platform} (need one of {required})"),
            "expires_at": None,
            "cookies_count": len(cookies),
        }

    # max expiry parmi cookies clés (ignore expiry=0 = session cookie)
    max_expiry = max((c["expiry"] for c in found_required if c["expiry"] > 0), default=None)
    expires_at = datetime.fromtimestamp(max_expiry, tz=UTC) if max_expiry else None

    log.info(
        "credentials_validator.validate_cookies.ok",
        platform=platform,
        cookies_count=len(cookies),
        expires_at=expires_at.isoformat() if expires_at else None,
    )

    return {
        "valid": True,
        "error": None,
        "expires_at": expires_at,
        "cookies_count": len(cookies),
    }
