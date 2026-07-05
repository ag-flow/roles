"""StubDepositor — dépôt local de développement/test (défaut actuel).

Écrit un fichier JSON par transcript dans `output_dir` et génère des refs
docflow factices (`stub-…`). Permet d'exercer tout le cycle
`transcribed → depositing → deposited` + `roles__get_corpus` sans docflow.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from role_builder.services.deposit.base import DepositResult

_SLUG_MAX_LEN = 60


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:_SLUG_MAX_LEN] or "sans-titre"


class StubDepositor:
    """Implémentation locale de CorpusDepositor — aucun appel réseau."""

    def __init__(self, *, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def deposit(
        self,
        *,
        item: dict[str, Any],
        transcript_text: str,
        metadata: dict[str, Any],
    ) -> DepositResult:
        base = metadata.get("title") or item.get("platform_item_id") or str(item.get("id"))
        slug = f"transcript-{_slugify(str(base))}-{uuid4().hex[:6]}"
        doc_id = f"stub-{uuid4().hex[:12]}"

        payload = json.dumps(
            {
                "doc_id": doc_id,
                "slug": slug,
                "transcript_text": transcript_text,
                "metadata": metadata,
            },
            ensure_ascii=False,
            indent=2,
        )
        path = self._output_dir / f"{slug}.json"
        await asyncio.to_thread(path.write_text, payload, encoding="utf-8")
        return DepositResult(doc_id=doc_id, slug=slug)
