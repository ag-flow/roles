"""Critères d'acceptation §6 du lot dépôt docflow (spec v2/01-protocole-mcp.md) :

- ligne 5 : `only_new` — deux pulls successifs, le second ne retourne que les
  items déposés entre-temps ; deux appelants ont des curseurs indépendants ;
- ligne 7 : échec de dépôt docflow — item `failed` avec code dédié,
  transcript conservé, `retry_failed` le récupère ;
- ligne 10 : aucun contenu (texte de transcript) ne transite par un tool
  `roles__*`.

Exercés à travers la façade MCP réelle (mcp_server.tools.*) + le
DepositWorker réel (StubDepositor + MinIO fake), pas les services internes.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from role_builder.db import db_pool as db_pool_singleton
from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.mcp_server.tools import admin as admin_tool
from role_builder.mcp_server.tools import corpus as corpus_tool
from role_builder.mcp_server.tools import discovery as discovery_tool
from role_builder.mcp_server.tools import status as status_tool
from role_builder.mcp_server.tools import submission as submission_tool
from role_builder.services import event_handlers
from role_builder.services.deposit.stub import StubDepositor
from role_builder.services.deposit.worker import DepositWorker
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential
from tests.services.deposit.helpers import FakeMinio, make_pivot

pytestmark = pytest.mark.asyncio

_MARKER = "MARQUEUR-TEXTE-TRANSCRIPT-NE-DOIT-PAS-TRANSITER"


@pytest.fixture(autouse=True)
def _wire_real_pool(pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_pool_singleton, "_pool", pool, raising=False)


async def _submit_and_select(pool: asyncpg.Pool, *, item_count: int) -> dict[str, Any]:
    """Cycle façade réel : submit → discovered → select_items sur tout."""
    await insert_active_credential(pool, platform="youtube")
    submitted = await submission_tool.submit_acquisition(
        "https://youtube.com/@clea-ux", submitted_by="claude-web"
    )
    request_key = submitted["request_key"]
    request = await ar.get_by_key(request_key, pool=pool)
    items = [
        {"id": f"vid-{i}", "title": f"Interview UX {i}", "duration_s": 900}
        for i in range(item_count)
    ]
    job = {"id": uuid4(), "source_id": request["source_id"], "tenant_id": TENANT_ID}
    await event_handlers.handle_scraper_event(
        {"type": "discovered", "total": len(items), "items": items}, job, pool=pool
    )
    discovered = await discovery_tool.list_discovered(request_key, limit=50)
    await discovery_tool.select_items(
        request_key, item_ids=[str(item["item_id"]) for item in discovered["items"]]
    )
    return {"request_key": request_key, "source_id": request["source_id"]}


async def _advance_to_transcribed(
    pool: asyncpg.Pool, source_id: Any, platform_item_id: str
) -> str:
    """Simule download + transcription : l'item a son pivot dans MinIO."""
    transcript_key = f"t/{platform_item_id}.json"
    await source_items_helper.update_source_item_status(
        source_id, platform_item_id, "transcribed",
        transcript_s3_key=transcript_key, pool=pool,
    )
    return transcript_key


def _worker(pool: asyncpg.Pool, depositor: Any, minio: FakeMinio) -> DepositWorker:
    return DepositWorker(
        pool=pool, depositor=depositor, minio=minio, max_attempts=2, backoff_base_s=0.0
    )


class _BrokenDepositor:
    async def deposit(self, **_: Any) -> Any:
        raise ConnectionError("passerelle injoignable")


async def test_criterion_5_only_new_and_independent_cursors(
    pool: asyncpg.Pool, tmp_path
) -> None:
    """Deux pulls successifs : le second ne retourne que les items déposés
    entre-temps ; deux appelants ont des curseurs indépendants."""
    ctx = await _submit_and_select(pool, item_count=2)
    minio = FakeMinio(
        {f"t/vid-{i}.json": make_pivot(f"Contenu vidéo {i}.") for i in range(2)}
    )
    worker = _worker(pool, StubDepositor(output_dir=tmp_path), minio)

    await _advance_to_transcribed(pool, ctx["source_id"], "vid-0")
    await worker.tick()

    first = await corpus_tool.get_corpus(ctx["request_key"], caller="claude-web", only_new=True)
    assert len(first["documents"]) == 1
    assert first["complete"] is False

    await _advance_to_transcribed(pool, ctx["source_id"], "vid-1")
    await worker.tick()

    second = await corpus_tool.get_corpus(ctx["request_key"], caller="claude-web", only_new=True)
    assert len(second["documents"]) == 1  # uniquement le dépôt intervenu entre-temps
    assert second["documents"][0]["docflow"]["title"] == "Interview UX 1"
    assert second["complete"] is True

    other = await corpus_tool.get_corpus(ctx["request_key"], caller="agent-b", only_new=True)
    assert len(other["documents"]) == 2  # curseur indépendant : B voit tout


async def test_criterion_7_deposit_failure_then_retry(pool: asyncpg.Pool, tmp_path) -> None:
    """Échec de dépôt : item failed avec code dédié, transcript conservé,
    retry_failed le récupère et le worker redépose."""
    ctx = await _submit_and_select(pool, item_count=1)
    transcript_key = await _advance_to_transcribed(pool, ctx["source_id"], "vid-0")
    minio = FakeMinio({transcript_key: make_pivot("Contenu.")})

    await _worker(pool, _BrokenDepositor(), minio).tick()

    status = await status_tool.request_status(ctx["request_key"])
    assert status["status"] == "partially_failed"
    failed_item = status["items"][0]
    assert failed_item["status"] == "failed"
    assert "DOCFLOW_DEPOSIT_FAILED" in failed_item["error"]
    row = await source_items_helper.get_by_id(failed_item["item_id"], pool=pool)
    assert row["transcript_s3_key"] == transcript_key  # transcript conservé

    retried = await admin_tool.retry_failed(ctx["request_key"])
    assert retried == {"retried_count": 1}

    await _worker(pool, StubDepositor(output_dir=tmp_path), minio).tick()

    corpus = await corpus_tool.get_corpus(ctx["request_key"], caller="claude-web")
    assert len(corpus["documents"]) == 1
    assert corpus["failed_items"] == []
    assert corpus["complete"] is True


async def test_criterion_10_no_transcript_content_through_roles_tools(
    pool: asyncpg.Pool, tmp_path
) -> None:
    """Aucun texte de transcript ne transite par un tool roles__* : seules les
    refs docflow sortent — la lecture passe par docflow__get_document."""
    ctx = await _submit_and_select(pool, item_count=1)
    transcript_key = await _advance_to_transcribed(pool, ctx["source_id"], "vid-0")
    minio = FakeMinio({transcript_key: make_pivot(f"Début. {_MARKER} Fin.")})
    await _worker(pool, StubDepositor(output_dir=tmp_path), minio).tick()

    # Le stub a bien déposé le texte (il est dans le "docflow" local)…
    deposited_files = list(tmp_path.glob("transcript-*.json"))
    assert len(deposited_files) == 1
    assert _MARKER in deposited_files[0].read_text(encoding="utf-8")

    # …mais aucune réponse de tool roles__* ne le contient.
    responses = [
        await corpus_tool.get_corpus(ctx["request_key"], caller="claude-web"),
        await status_tool.request_status(ctx["request_key"]),
        await status_tool.list_requests(),
        await discovery_tool.list_discovered(ctx["request_key"], limit=50),
    ]
    for response in responses:
        assert _MARKER not in json.dumps(response, default=str)

    corpus = responses[0]
    document = corpus["documents"][0]
    assert set(document.keys()) == {"item_id", "docflow", "metadata"}
    assert document["docflow"]["doc_id"]  # des refs, rien d'autre
