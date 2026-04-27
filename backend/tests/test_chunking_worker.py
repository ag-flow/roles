"""Tests for ChunkingWorker — orchestration download → chunk → embed → insert."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest


class _StubPool:
    """Pool sans état — les db_helpers sont monkeypatchés directement."""

    def acquire(self) -> Any:
        raise AssertionError(
            "Pool.acquire ne doit pas être appelé : db_helpers monkeypatchés"
        )


@pytest.fixture()
def fake_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Patch toutes les dépendances I/O de ChunkingWorker."""
    from role_builder.db_helpers import chunking_jobs as cj_module
    from role_builder.db_helpers import corpus_chunks as cc_module
    from role_builder.db_helpers import source_items as si_module
    from role_builder.services import chunker as chunker_module
    from role_builder.services import chunking_worker as cw_module
    from role_builder.services import embedder as embedder_module

    calls: dict[str, list[Any]] = {
        "mark_processing": [],
        "mark_done": [],
        "mark_failed": [],
        "download": [],
        "chunk": [],
        "embed": [],
        "insert_bulk": [],
        "update_item_status": [],
    }

    async def fake_mark_processing(job_id: Any, *, pool: Any) -> None:
        calls["mark_processing"].append(job_id)

    async def fake_mark_done(job_id: Any, *, chunks_produced: int, pool: Any) -> None:
        calls["mark_done"].append({"job_id": job_id, "chunks_produced": chunks_produced})

    async def fake_mark_failed(job_id: Any, error: str, *, pool: Any) -> None:
        calls["mark_failed"].append({"job_id": job_id, "error": error})

    def fake_download_bytes(self_: Any, bucket: str, key: str) -> bytes:
        calls["download"].append({"bucket": bucket, "key": key})
        return json.dumps({"segments": [{"id": 0, "start": 0.0, "end": 5.0, "text": "hi"}]}).encode(
            "utf-8"
        )

    def fake_chunk_transcript(transcript: dict, **kwargs: Any) -> list[Any]:
        from role_builder.services.chunker import TranscriptChunk

        calls["chunk"].append({"transcript": transcript, "kwargs": kwargs})
        return [
            TranscriptChunk(text="chunk-0", start_s=0.0, end_s=5.0, word_count=1),
            TranscriptChunk(text="chunk-1", start_s=5.0, end_s=10.0, word_count=1),
        ]

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        calls["embed"].append(list(texts))
        return [[0.1] * 1024 for _ in texts]

    async def fake_insert_bulk(
        chunks: list[dict], *, source_item_id: Any, role_project_id: Any,
        tenant_id: Any, pool: Any,
    ) -> int:
        calls["insert_bulk"].append({
            "chunks": chunks,
            "source_item_id": source_item_id,
            "role_project_id": role_project_id,
            "tenant_id": tenant_id,
        })
        return len(chunks)

    async def fake_update_item_status(
        item_id: Any, status: str, *, pool: Any
    ) -> None:
        calls["update_item_status"].append({"item_id": item_id, "status": status})

    monkeypatch.setattr(cj_module, "mark_processing", fake_mark_processing)
    monkeypatch.setattr(cj_module, "mark_done", fake_mark_done)
    monkeypatch.setattr(cj_module, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(cw_module.MinioWrapper, "download_bytes", fake_download_bytes)
    monkeypatch.setattr(chunker_module, "chunk_transcript", fake_chunk_transcript)
    monkeypatch.setattr(embedder_module, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(cc_module, "insert_chunks_bulk", fake_insert_bulk)
    monkeypatch.setattr(
        si_module, "update_source_item_status_by_id", fake_update_item_status,
        raising=False,
    )
    return calls


async def test_process_one_job_chains_all_steps(
    fake_calls: dict[str, list[Any]], stubbed_env: None
) -> None:
    """process_one_job : mark_processing → download → chunk → embed → insert → mark_done."""
    from role_builder.services.chunking_worker import ChunkingWorker

    worker = ChunkingWorker(pool=_StubPool())
    job_id = uuid4()
    item_id = uuid4()
    project_id = uuid4()
    tenant_id = uuid4()
    job = {
        "id": job_id,
        "source_item_id": item_id,
        "role_project_id": project_id,
        "tenant_id": tenant_id,
        "transcript_s3_key": "corpus-transcripts/x.json",
    }

    await worker.process_one_job(job)

    assert fake_calls["mark_processing"] == [job_id]
    assert len(fake_calls["download"]) == 1
    assert fake_calls["download"][0]["key"] == "corpus-transcripts/x.json"
    assert len(fake_calls["chunk"]) == 1
    assert fake_calls["embed"] == [["chunk-0", "chunk-1"]]
    assert len(fake_calls["insert_bulk"]) == 1
    inserted = fake_calls["insert_bulk"][0]
    assert inserted["source_item_id"] == item_id
    assert inserted["role_project_id"] == project_id
    assert inserted["tenant_id"] == tenant_id
    assert len(inserted["chunks"]) == 2
    assert inserted["chunks"][0]["chunk_index"] == 0
    assert inserted["chunks"][1]["chunk_index"] == 1
    assert all(len(c["embedding"]) == 1024 for c in inserted["chunks"])
    assert fake_calls["mark_done"] == [{"job_id": job_id, "chunks_produced": 2}]
    assert fake_calls["update_item_status"] == [{"item_id": item_id, "status": "indexed"}]
    assert fake_calls["mark_failed"] == []


async def test_process_one_job_empty_chunks_marks_done_zero(
    fake_calls: dict[str, list[Any]],
    stubbed_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si chunk_transcript retourne [], mark_done(chunks_produced=0) + status=indexed."""
    from role_builder.services import chunker as chunker_module
    from role_builder.services.chunking_worker import ChunkingWorker

    monkeypatch.setattr(chunker_module, "chunk_transcript", lambda transcript, **kw: [])

    worker = ChunkingWorker(pool=_StubPool())
    job_id = uuid4()
    item_id = uuid4()
    job = {
        "id": job_id,
        "source_item_id": item_id,
        "role_project_id": uuid4(),
        "tenant_id": uuid4(),
        "transcript_s3_key": "corpus-transcripts/x.json",
    }

    await worker.process_one_job(job)

    assert fake_calls["mark_done"] == [{"job_id": job_id, "chunks_produced": 0}]
    assert fake_calls["embed"] == []
    assert fake_calls["insert_bulk"] == []
    assert fake_calls["update_item_status"] == [{"item_id": item_id, "status": "indexed"}]


async def test_process_one_job_marks_failed_on_exception(
    fake_calls: dict[str, list[Any]],
    stubbed_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sur exception (ex: embed throws), le job passe en failed avec error message."""
    from role_builder.services import embedder as embedder_module
    from role_builder.services.chunking_worker import ChunkingWorker

    async def boom(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embed exploded")

    monkeypatch.setattr(embedder_module, "embed_texts", boom)

    worker = ChunkingWorker(pool=_StubPool())
    job_id = uuid4()
    job = {
        "id": job_id,
        "source_item_id": uuid4(),
        "role_project_id": uuid4(),
        "tenant_id": uuid4(),
        "transcript_s3_key": "corpus-transcripts/x.json",
    }

    await worker.process_one_job(job)

    assert fake_calls["mark_failed"] == [
        {"job_id": job_id, "error": "embed exploded"}
    ]
    assert fake_calls["mark_done"] == []
    assert fake_calls["insert_bulk"] == []


async def test_run_loop_stops_on_event(
    fake_calls: dict[str, list[Any]],
    stubbed_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_loop sort proprement quand stop_event.set() est appelé."""
    from role_builder.db_helpers import chunking_jobs as cj_module
    from role_builder.services.chunking_worker import ChunkingWorker

    async def fake_claim(worker_id: str, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(cj_module, "claim_next_pending_job", fake_claim)

    worker = ChunkingWorker(pool=_StubPool())
    stop = asyncio.Event()

    async def stop_soon() -> None:
        await asyncio.sleep(0.01)
        stop.set()

    await asyncio.gather(
        worker.run_loop(stop, poll_interval_s=0.01),
        stop_soon(),
    )
    # Si on arrive ici, la boucle a bien terminé.
    assert stop.is_set()
