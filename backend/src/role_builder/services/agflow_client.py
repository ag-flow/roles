"""Abstraction LLM/embeddings.

MVP : appel direct ``api.mistral.ai``. Phase 2 : swap interne vers ag.flow
quand son OpenAPI sera figé, sans changer l'interface des callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from role_builder.config import settings


@dataclass
class ChatResult:
    """Résultat d'un appel chat completion (DTO neutre, indépendant du provider)."""

    content: str
    tokens_input: int
    tokens_output: int
    cost_usd: float | None
    model: str


class AgflowClient:
    """Client unifié pour les LLM/embeddings (Mistral MVP)."""

    EMBED_BATCH_SIZE = 32

    def __init__(
        self,
        *,
        api_key: str | None = None,
        embed_model: str | None = None,
        chat_model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else getattr(settings, "mistral_api_key", "")
        self._embed_model = (
            embed_model
            if embed_model is not None
            else getattr(settings, "mistral_embed_model", "mistral-embed")
        )
        self._chat_model = (
            chat_model
            if chat_model is not None
            else getattr(settings, "mistral_chat_model", "mistral-large-latest")
        )
        self._base_url = (
            base_url
            if base_url is not None
            else getattr(settings, "mistral_base_url", "https://api.mistral.ai")
        )
        self._http: Any = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=120.0,
        )

    async def invoke_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed une liste de textes. Auto-batches si > ``EMBED_BATCH_SIZE``."""
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.EMBED_BATCH_SIZE):
            batch = texts[i : i + self.EMBED_BATCH_SIZE]
            resp = await self._http.post(
                "/v1/embeddings",
                json={"model": self._embed_model, "input": batch},
            )
            resp.raise_for_status()
            body = resp.json()
            all_vectors.extend(item["embedding"] for item in body["data"])
        return all_vectors

    async def invoke_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        """Appel chat completion. ``response_format`` peut forcer du JSON strict."""
        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": messages,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if temperature is not None:
            payload["temperature"] = temperature

        resp = await self._http.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        body = resp.json()
        usage = body.get("usage", {})
        return ChatResult(
            content=body["choices"][0]["message"]["content"],
            tokens_input=int(usage.get("prompt_tokens", 0)),
            tokens_output=int(usage.get("completion_tokens", 0)),
            cost_usd=None,  # Mistral n'expose pas de cost direct (calcul post-hoc)
            model=body.get("model", payload["model"]),
        )

    async def aclose(self) -> None:
        await self._http.aclose()


_singleton: AgflowClient | None = None


def get_agflow_client() -> AgflowClient:
    """Singleton FastAPI dependency-style. Lazy init pour respect du settings."""
    global _singleton
    if _singleton is None:
        _singleton = AgflowClient()
    return _singleton
