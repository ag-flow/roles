"""Tests pour provider_keys — dont le garde anti-drift de l'enum providers."""

from __future__ import annotations

from role_builder.schemas.user_secrets import TRANSCRIPTION_PROVIDER_TYPES
from role_builder.services.provider_keys import (
    PROVIDER_TO_SETTINGS_ATTR,
    provider_env_key,
)


def test_settings_mapping_covers_all_transcription_provider_types() -> None:
    """Chaque provider de l'enum a une entrée de fallback machine.

    Sans cette couverture, un provider ajouté à l'enum mais oublié ici
    démarrerait des workers sans clé API, en silence (.get(provider, "")).
    """
    missing = TRANSCRIPTION_PROVIDER_TYPES - set(PROVIDER_TO_SETTINGS_ATTR)
    assert not missing, f"providers sans fallback .env : {missing}"


def test_provider_env_key_shape() -> None:
    assert provider_env_key("openai-whisper") == "OPENAI_API_KEY"
    assert provider_env_key("deepgram") == "DEEPGRAM_API_KEY"
