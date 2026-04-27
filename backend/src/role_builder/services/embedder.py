"""Wrapper minimaliste autour de :mod:`agflow_client` pour les embeddings de chunks.

Point d'extension futur : cache local, normalisation, stratégies de retry.
"""
from __future__ import annotations

from role_builder.services import agflow_client as agflow_module


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed une liste de textes. Délègue au singleton :class:`AgflowClient`.

    Liste vide → ``[]`` sans appel réseau.
    """
    if not texts:
        return []
    client = agflow_module.get_agflow_client()
    return await client.invoke_embeddings(texts)
