"""Liste blanche des media_type acceptés à l'upload (spec v2/01 §2.2, §5.5).

Table pure : media_type → (kind, extension de la clé objet MinIO). Une
entrée `video` déclenche l'extraction audio ffmpeg au finalize ; une entrée
`audio` est transcrite telle quelle.
"""

from __future__ import annotations

_AUDIO = "audio"
_VIDEO = "video"

_WHITELIST: dict[str, tuple[str, str]] = {
    "audio/mpeg": (_AUDIO, ".mp3"),
    "audio/wav": (_AUDIO, ".wav"),
    "audio/mp4": (_AUDIO, ".m4a"),
    "audio/ogg": (_AUDIO, ".ogg"),
    "audio/flac": (_AUDIO, ".flac"),
    "video/mp4": (_VIDEO, ".mp4"),
    "video/quicktime": (_VIDEO, ".mov"),
    "video/webm": (_VIDEO, ".webm"),
}


def is_supported(media_type: str) -> bool:
    return media_type in _WHITELIST


def is_video(media_type: str) -> bool:
    return _WHITELIST[media_type][0] == _VIDEO


def extension_for(media_type: str) -> str:
    return _WHITELIST[media_type][1]


def supported_types() -> list[str]:
    """Pour les messages d'erreur UNSUPPORTED_MEDIA."""
    return sorted(_WHITELIST)
