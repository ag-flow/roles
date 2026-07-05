"""Critères d'acceptation §6 du lot upload (spec v2/01-protocole-mcp.md) :

- ligne 3 : cycle upload — `create_upload_request` → `request_upload_slot` →
  PUT présigné → `finalize_upload` → item transcrit et déposé dans docflow,
  indiscernable d'un item scrapé côté corpus (`platform=upload`,
  `source_url=null`) ;
- ligne 4 : slot expiré — `finalize_upload` → `UPLOAD_EXPIRED` ; item nettoyé.

Exercés à travers la façade MCP réelle (mcp_server.tools.upload) + le
DepositWorker réel (StubDepositor + object store fake). Le PUT client est
simulé par une écriture directe dans le store (le contenu binaire ne
transite jamais par un tool, spec §1 point 3) ; la transcription est
simulée en avançant l'item à `transcribed` avec un pivot dans
corpus-transcripts, comme dans test_acceptance_deposit.py.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from role_builder.db import db_pool as db_pool_singleton
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.mcp_server.tools import corpus as corpus_tool
from role_builder.mcp_server.tools import status as status_tool
from role_builder.mcp_server.tools import upload as upload_tool
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from role_builder.services.deposit.stub import StubDepositor
from role_builder.services.deposit.worker import TRANSCRIPT_BUCKET, DepositWorker
from tests.services.acquisition.upload_helpers import FakeObjectStore
from tests.services.deposit.helpers import make_pivot

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _wire_real_pool(pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_pool_singleton, "_pool", pool, raising=False)


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    """Object store fake injecté à la place du singleton MinIO des adaptateurs."""
    fake = FakeObjectStore()
    monkeypatch.setattr("role_builder.services.minio_client.minio_client", fake)
    return fake


async def _simulate_transcription(
    pool: asyncpg.Pool, store: FakeObjectStore, item_id: Any, *, text: str
) -> None:
    """Simule le worker de transcription : pivot dans MinIO + item transcribed."""
    item = await source_items_helper.get_by_id(item_id, pool=pool)
    transcript_key = f"t/{item['platform_item_id']}.json"
    store.put_json(TRANSCRIPT_BUCKET, transcript_key, make_pivot(text))
    await source_items_helper.update_source_item_status(
        item["source_id"],
        item["platform_item_id"],
        "transcribed",
        transcript_s3_key=transcript_key,
        pool=pool,
    )


async def test_criterion_3_full_upload_cycle(
    pool: asyncpg.Pool, store: FakeObjectStore, tmp_path
) -> None:
    """create → slot → PUT → finalize → transcription → dépôt : le document
    du corpus est indiscernable d'un item scrapé (platform=upload, source_url=null)."""
    created = await upload_tool.create_upload_request(
        "Conférence UX interne", submitted_by="claude-web"
    )
    assert created["status"] == "open_for_upload"
    request_key = created["request_key"]

    slot = await upload_tool.request_upload_slot(
        request_key,
        filename="pleniere.mp3",
        media_type="audio/mpeg",
        title="Plénière : recherche utilisateur",
        duration_s=1800,
    )
    assert "upload_url" in slot and "expires_at" in slot

    # PUT client sur l'URL présignée (simulé : écriture directe dans le store).
    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    store.objects[(AUDIO_BUCKET, item["upload_s3_key"])] = b"audio-bytes"

    finalized = await upload_tool.finalize_upload(request_key, item_id=str(slot["item_id"]))
    assert finalized["status"] == "queued_transcription"

    closed = await upload_tool.close_upload_request(request_key)
    assert closed["status"] == "acquiring"

    await _simulate_transcription(pool, store, slot["item_id"], text="Contenu de la plénière.")
    worker = DepositWorker(
        pool=pool,
        depositor=StubDepositor(output_dir=tmp_path),
        minio=store,
        max_attempts=2,
        backoff_base_s=0.0,
    )
    assert await worker.tick() is True

    status = await status_tool.request_status(request_key)
    assert status["kind"] == "upload"
    assert status["status"] == "completed"

    corpus = await corpus_tool.get_corpus(request_key, caller="claude-web")
    assert corpus["complete"] is True
    assert corpus["failed_items"] == []
    assert len(corpus["documents"]) == 1

    document = corpus["documents"][0]
    # Même forme que pour un item scrapé (cf. test_acceptance_deposit) —
    # seuls platform/source_url trahissent l'origine, conformément à la spec.
    assert set(document.keys()) == {"item_id", "docflow", "metadata"}
    assert document["docflow"]["doc_id"]
    assert document["docflow"]["title"] == "Plénière : recherche utilisateur"
    assert document["metadata"]["platform"] == "upload"
    assert document["metadata"]["source_url"] is None
    assert document["metadata"]["duration_s"] == 1800


async def test_criterion_4_expired_slot(pool: asyncpg.Pool, store: FakeObjectStore) -> None:
    """Slot expiré : finalize_upload → UPLOAD_EXPIRED ; item nettoyé."""
    created = await upload_tool.create_upload_request(
        "Conférence UX interne", submitted_by="claude-web"
    )
    request_key = created["request_key"]
    slot = await upload_tool.request_upload_slot(
        request_key, filename="pleniere.mp3", media_type="audio/mpeg"
    )

    # Le TTL du slot est passé sans PUT ni finalize.
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE source_items SET upload_expires_at = now() - interval '1 minute' "
            "WHERE id = $1",
            slot["item_id"],
        )

    result = await upload_tool.finalize_upload(request_key, item_id=str(slot["item_id"]))
    assert result["error"]["code"] == "UPLOAD_EXPIRED"

    assert await source_items_helper.get_by_id(slot["item_id"], pool=pool) is None
