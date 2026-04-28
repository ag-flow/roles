"""Tests TDD pour credentials_validator (parse Netscape cookies + validation plateforme)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest

# ---------------------------------------------------------------------------
# Fixtures : fichiers cookies.txt en base64
# ---------------------------------------------------------------------------

YOUTUBE_VALID = base64.b64encode(
    b"# Netscape HTTP Cookie File\n"
    b".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSID\tabc123def456\n"
    b".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSAPISID\txyz789\n"
).decode()

YOUTUBE_NO_REQUIRED = base64.b64encode(
    b"# Netscape\n.youtube.com\tTRUE\t/\tTRUE\t1799999999\trandomcookie\tvalue\n"
).decode()

INSTAGRAM_VALID = base64.b64encode(
    b"# Netscape HTTP Cookie File\n"
    b".instagram.com\tTRUE\t/\tFALSE\t1799999999\tsessionid\tabc123\n"
    b".instagram.com\tTRUE\t/\tFALSE\t1799999999\tcsrftoken\tdef456\n"
).decode()

INVALID_FORMAT = base64.b64encode(
    b"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1799999999\n"  # seulement 5 champs
).decode()

INVALID_EXPIRY = base64.b64encode(
    b"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\tnot-a-number\tSID\tabc123\n"
).decode()


# ---------------------------------------------------------------------------
# Tests parse_netscape_cookies
# ---------------------------------------------------------------------------


def test_parse_netscape_cookies_parses_deux_cookies() -> None:
    """parse_netscape_cookies parse correctement 2 cookies valides."""
    from role_builder.services.credentials_validator import parse_netscape_cookies

    content = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSID\tabc123def456\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSAPISID\txyz789\n"
    )
    cookies = parse_netscape_cookies(content)

    assert len(cookies) == 2
    assert cookies[0]["name"] == "SID"
    assert cookies[0]["value"] == "abc123def456"
    assert cookies[0]["domain"] == ".youtube.com"
    assert cookies[0]["flag"] is True
    assert cookies[0]["secure"] is True
    assert cookies[0]["expiry"] == 1799999999
    assert cookies[1]["name"] == "SAPISID"


def test_parse_netscape_cookies_ignore_lignes_vides_et_commentaires() -> None:
    """parse_netscape_cookies ignore les lignes vides et commençant par #."""
    from role_builder.services.credentials_validator import parse_netscape_cookies

    content = (
        "# Netscape HTTP Cookie File\n"
        "\n"
        "  \n"
        "# Another comment\n"
        ".instagram.com\tTRUE\t/\tFALSE\t1799999999\tsessionid\tabc\n"
    )
    cookies = parse_netscape_cookies(content)

    assert len(cookies) == 1
    assert cookies[0]["name"] == "sessionid"


def test_parse_netscape_cookies_leve_valueerror_si_format_invalide() -> None:
    """parse_netscape_cookies lève ValueError si une ligne a le mauvais nombre de champs."""
    from role_builder.services.credentials_validator import parse_netscape_cookies

    content = ".youtube.com\tTRUE\t/\tTRUE\t1799999999\n"  # 5 champs au lieu de 7

    with pytest.raises(ValueError, match="expected 7 tab-separated fields"):
        parse_netscape_cookies(content)


def test_parse_netscape_cookies_leve_valueerror_si_expiry_invalide() -> None:
    """parse_netscape_cookies lève ValueError si l'expiry n'est pas un entier."""
    from role_builder.services.credentials_validator import parse_netscape_cookies

    content = ".youtube.com\tTRUE\t/\tTRUE\tnot-a-number\tSID\tabc123\n"

    with pytest.raises(ValueError, match="invalid expiry"):
        parse_netscape_cookies(content)


# ---------------------------------------------------------------------------
# Tests validate_cookies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_cookies_youtube_valid_retourne_valid_true() -> None:
    """validate_cookies avec cookies YouTube valides → valid=True, expires_at non None."""
    from role_builder.services.credentials_validator import validate_cookies

    result = await validate_cookies("youtube", YOUTUBE_VALID)

    assert result["valid"] is True
    assert result["error"] is None
    assert result["expires_at"] is not None
    assert isinstance(result["expires_at"], datetime)
    assert result["expires_at"].tzinfo == UTC
    assert result["cookies_count"] == 2


@pytest.mark.asyncio
async def test_validate_cookies_youtube_sans_cookies_requis_retourne_invalid() -> None:
    """validate_cookies YouTube sans cookies requis → valid=False, error 'missing required'."""
    from role_builder.services.credentials_validator import validate_cookies

    result = await validate_cookies("youtube", YOUTUBE_NO_REQUIRED)

    assert result["valid"] is False
    assert result["error"] is not None
    assert "missing required" in result["error"]
    assert result["expires_at"] is None


@pytest.mark.asyncio
async def test_validate_cookies_instagram_valid_retourne_valid_true() -> None:
    """validate_cookies avec sessionid Instagram → valid=True."""
    from role_builder.services.credentials_validator import validate_cookies

    result = await validate_cookies("instagram", INSTAGRAM_VALID)

    assert result["valid"] is True
    assert result["error"] is None
    assert result["cookies_count"] == 2


@pytest.mark.asyncio
async def test_validate_cookies_plateforme_inconnue_retourne_invalid() -> None:
    """validate_cookies avec plateforme inconnue → valid=False, error 'unknown platform'."""
    from role_builder.services.credentials_validator import validate_cookies

    result = await validate_cookies("unknown", "dGVzdA==")

    assert result["valid"] is False
    assert result["error"] is not None
    assert "unknown platform" in result["error"]
    assert result["cookies_count"] == 0


@pytest.mark.asyncio
async def test_validate_cookies_base64_invalide_retourne_invalid() -> None:
    """validate_cookies avec base64 invalide → valid=False, error 'invalid base64'."""
    from role_builder.services.credentials_validator import validate_cookies

    result = await validate_cookies("youtube", "not-base64-!!!@#$")

    assert result["valid"] is False
    assert result["error"] is not None
    assert "invalid base64" in result["error"]
    assert result["cookies_count"] == 0
