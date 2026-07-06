"""Déduction de la plateforme à partir de l'URL (spec §2.1 `platform?`)."""

from __future__ import annotations

from urllib.parse import urlparse

from role_builder.services.acquisition.errors import AcquisitionError

_SUPPORTED_PLATFORMS = {"youtube", "instagram", "tiktok"}

# Suffixes de domaine → plateforme : couvre les sous-domaines courants
# (m., music., vm., vt., www.) sans les énumérer un par un (BUG-30).
_DOMAIN_SUFFIXES = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
}


def _match_host(host: str) -> str | None:
    host = host.lower()
    for domain, platform in _DOMAIN_SUFFIXES.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return None


def deduce_platform(url: str, *, platform_hint: str | None) -> str:
    """Retourne la plateforme, déduite de l'URL ou du hint explicite.

    Raises:
        AcquisitionError(UNSUPPORTED_PLATFORM): hint ou host non reconnu.
        AcquisitionError(INVALID_URL): URL non parseable (pas de host).
    """
    if platform_hint is not None:
        if platform_hint not in _SUPPORTED_PLATFORMS:
            raise AcquisitionError(
                "UNSUPPORTED_PLATFORM", f"unsupported platform: {platform_hint!r}"
            )
        return platform_hint

    # Tolère une URL sans schéma (`youtube.com/watch?v=x`) : urlparse la met
    # dans `path`, pas `netloc` — on re-parse avec `//` en préfixe, mais
    # seulement si le premier segment ressemble à un host (contient un `.`),
    # pour qu'une vraie chaîne non-URL reste INVALID_URL.
    if "//" not in url and "." in url.split("/", 1)[0]:
        url = "//" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise AcquisitionError("INVALID_URL", f"cannot parse URL: {url!r}")

    platform = _match_host(parsed.hostname or parsed.netloc)
    if platform is None:
        raise AcquisitionError("UNSUPPORTED_PLATFORM", f"unsupported host: {parsed.netloc!r}")
    return platform


_SINGLE_VIDEO_MARKERS = {
    "youtube": ("watch",),
    "tiktok": ("/video/",),
    "instagram": ("/p/", "/reel/"),
}


def infer_source_type(platform: str, url: str) -> str:
    """Heuristique best-effort : chaîne/playlist/compte vs vidéo unique.

    La distinction fine (channel vs account) n'a pas d'impact sur le
    contrat scraper (stdin/NDJSON figé, cf. spec 03) — le scraper décide
    lui-même comment traiter l'URL. `source_type` reste une colonne
    descriptive de traçabilité, jamais lue par ce lot pour changer de
    comportement.
    """
    path = urlparse(url).path
    if any(marker in path for marker in _SINGLE_VIDEO_MARKERS.get(platform, ())):
        return "single"
    if "playlist" in path or "list=" in url:
        return "playlist"
    return "channel"
