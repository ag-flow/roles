"""Tests des implémentations de CorpusDepositor (spec v2/01 §3, §5.2).

- StubDepositor : dépôt local (fichier JSON) + refs factices — permet de
  tester tout le cycle sans docflow.
- GatewayDepositor : squelette, lève NotImplementedError tant que la
  convention docflow_target et l'identité machine ne sont pas tranchées.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from role_builder.services.deposit.base import DepositResult
from role_builder.services.deposit.gateway import GatewayDepositor
from role_builder.services.deposit.stub import StubDepositor

pytestmark = pytest.mark.asyncio

_ITEM = {"id": "0f8b7c9a-0000-0000-0000-000000000001", "platform_item_id": "vid-1"}
_METADATA = {
    "platform": "youtube",
    "source_url": "https://youtube.com/@clea-ux",
    "title": "Interview UX : observer avant de questionner",
    "duration_s": 913,
    "published_at": "2025-11-02T00:00:00+00:00",
    "request_key": "yt-clea-ux-2026-07-04-a3f2",
    "provider": "faster-whisper",
}


async def test_stub_depositor_returns_refs_and_writes_json(tmp_path: Path) -> None:
    depositor = StubDepositor(output_dir=tmp_path / "deposits")

    result = await depositor.deposit(
        item=_ITEM, transcript_text="Bonjour, dans cette vidéo…", metadata=_METADATA
    )

    assert isinstance(result, DepositResult)
    assert result.doc_id.startswith("stub-")
    assert result.slug.startswith("transcript-")
    assert "interview-ux" in result.slug

    written = tmp_path / "deposits" / f"{result.slug}.json"
    assert written.is_file()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["doc_id"] == result.doc_id
    assert payload["slug"] == result.slug
    assert payload["transcript_text"] == "Bonjour, dans cette vidéo…"
    assert payload["metadata"] == _METADATA


async def test_stub_depositor_slugs_are_unique_for_same_title(tmp_path: Path) -> None:
    depositor = StubDepositor(output_dir=tmp_path)

    first = await depositor.deposit(item=_ITEM, transcript_text="a", metadata=_METADATA)
    second = await depositor.deposit(item=_ITEM, transcript_text="b", metadata=_METADATA)

    assert first.slug != second.slug
    assert first.doc_id != second.doc_id


async def test_stub_depositor_falls_back_to_platform_item_id(tmp_path: Path) -> None:
    depositor = StubDepositor(output_dir=tmp_path)
    metadata = dict(_METADATA, title=None)

    result = await depositor.deposit(item=_ITEM, transcript_text="x", metadata=metadata)

    assert "vid-1" in result.slug


async def test_gateway_depositor_is_an_explicit_skeleton() -> None:
    depositor = GatewayDepositor()

    with pytest.raises(NotImplementedError) as excinfo:
        await depositor.deposit(item=_ITEM, transcript_text="x", metadata=_METADATA)

    message = str(excinfo.value)
    assert "docflow_target" in message
    assert "identité machine" in message
