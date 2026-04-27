"""Tests TDD pour synthesis/document_writer.py — write_document + write_all_documents_for_plan."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from role_builder.services.agflow_client import ChatResult

# ---------------------------------------------------------------------------
# Stubs asyncpg pool
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "DELETE 0"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


# ---------------------------------------------------------------------------
# Stub agflow_client
# ---------------------------------------------------------------------------


class _StubClient:
    def __init__(self, content: str = "# Doc\n\nContent.", model: str = "mistral-test") -> None:
        self._content = content
        self._model = model
        self.calls: list[tuple[list[dict], dict | None]] = []

    async def invoke_chat(
        self, messages: list[dict], *, response_format: dict | None = None
    ) -> ChatResult:
        self.calls.append((messages, response_format))
        return ChatResult(
            content=self._content,
            tokens_input=10,
            tokens_output=20,
            cost_usd=None,
            model=self._model,
        )


# ---------------------------------------------------------------------------
# Helpers builders
# ---------------------------------------------------------------------------


def _make_version(
    template: str = (
        "Section: {section}\nName: {doc_name}\nBrief: {doc_brief}\n"
        "Directives: {global_directives}\nSignals: {signals}\nChunks: {chunks}"
    ),
) -> dict:
    return {
        "id": uuid4(),
        "template": template,
        "prompt_name": "document_writer",
        "version_number": 1,
    }


def _make_project(tenant_id: UUID | None = None) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or uuid4(),
        "global_directives": "Sois concis et précis.",
    }


def _make_signals(n: int) -> list[dict]:
    return [
        {"id": uuid4(), "type": "heuristique", "content": f"Signal content {i}"} for i in range(n)
    ]


def _make_rag_chunks(n: int) -> list[dict]:
    return [{"similarity": 0.8 - i * 0.05, "text": f"Chunk text {i}"} for i in range(n)]


def _make_doc_plan(signal_ids: list[UUID] | None = None) -> dict:
    return {
        "name": "principe-autonomie",
        "brief": "L'agent agit de façon autonome.",
        "supporting_signals": [str(sid) for sid in (signal_ids or [])],
    }


# ---------------------------------------------------------------------------
# Shared mock setup helper
# ---------------------------------------------------------------------------


def _patch_document_writer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: dict,
    project: dict,
    signals: list[dict],
    rag_chunks: list[dict],
    run_id: UUID,
    doc_id: UUID,
    stub_client: _StubClient,
    mark_done_calls: list[dict] | None = None,
    mark_failed_calls: list[dict] | None = None,
    delete_count: int = 0,
    insert_doc_id: UUID | None = None,
) -> dict[str, list]:
    """Monkeypatche toutes les dépendances du document_writer.
    Retourne un dict de registres d'appels pour assertions."""
    from role_builder.synthesis import document_writer

    if mark_done_calls is None:
        mark_done_calls = []
    if mark_failed_calls is None:
        mark_failed_calls = []
    inserted_docs: list[UUID] = []
    deleted_runs: list[UUID] = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict:
        return project

    async def fake_get_signals_by_ids(ids: list[UUID], *, pool: Any) -> list[dict]:
        return signals

    async def fake_find_relevant_chunks(
        pid: UUID, query: str, *, top_k: int, min_similarity: float, pool: Any
    ) -> list[dict]:
        return rag_chunks

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, *, output: Any, **kwargs: Any) -> None:
        if mark_done_calls is not None:
            mark_done_calls.append({"run_id": rid, **kwargs})

    async def fake_mark_failed(rid: UUID, error: str, *, pool: Any) -> None:
        if mark_failed_calls is not None:
            mark_failed_calls.append({"run_id": rid, "error": error})

    async def fake_insert_role_document(**kwargs: Any) -> UUID:
        d = insert_doc_id or doc_id
        inserted_docs.append(d)
        return d

    async def fake_delete_by_run(rid: UUID, *, pool: Any) -> int:
        deleted_runs.append(rid)
        return delete_count

    monkeypatch.setattr(
        document_writer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(document_writer.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(
        document_writer.signals_helper, "get_signals_by_ids", fake_get_signals_by_ids
    )
    monkeypatch.setattr(
        document_writer.corpus_search, "find_relevant_chunks", fake_find_relevant_chunks
    )
    monkeypatch.setattr(document_writer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(document_writer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(document_writer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(document_writer.runs, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(
        document_writer.role_documents_helper, "insert_role_document", fake_insert_role_document
    )
    monkeypatch.setattr(
        document_writer.role_documents_helper, "delete_documents_by_run", fake_delete_by_run
    )
    monkeypatch.setattr(document_writer, "get_agflow_client", lambda: stub_client)

    return {"inserted_docs": inserted_docs, "deleted_runs": deleted_runs}


# ---------------------------------------------------------------------------
# E2.1 — Happy path
# ---------------------------------------------------------------------------


async def test_write_document_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path : 2 signaux, 3 chunks RAG → INSERT role_document is_current=False,
    mark_done, run_id retourné."""
    from role_builder.synthesis import document_writer

    signal_ids = [uuid4(), uuid4()]
    version = _make_version()
    project = _make_project()
    signals = _make_signals(2)
    chunks = _make_rag_chunks(3)
    run_id = uuid4()
    doc_id = uuid4()
    mark_done_calls: list[dict] = []
    stub_client = _StubClient("# Principle\n\nContent du document.")

    registry = _patch_document_writer(
        monkeypatch,
        version=version,
        project=project,
        signals=signals,
        rag_chunks=chunks,
        run_id=run_id,
        doc_id=doc_id,
        stub_client=stub_client,
        mark_done_calls=mark_done_calls,
    )

    doc_plan = _make_doc_plan(signal_ids)
    pool = _StubPool(_StubConn())
    result = await document_writer.write_document(project["id"], "Role", doc_plan, pool=pool)

    assert result == run_id
    # 1 doc inséré
    assert len(registry["inserted_docs"]) == 1
    # mark_done appelé
    assert len(mark_done_calls) == 1
    # pas d'appel delete
    assert len(registry["deleted_runs"]) == 0
    # response_format absent (markdown libre)
    messages, response_format = stub_client.calls[0]
    assert response_format is None
    # system message contient section et name
    system_content = messages[0]["content"]
    assert "Role" in system_content
    assert "principe-autonomie" in system_content


# ---------------------------------------------------------------------------
# E2.2 — RAG vide
# ---------------------------------------------------------------------------


async def test_write_document_empty_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG vide → continue, doc inséré quand même."""
    from role_builder.synthesis import document_writer

    version = _make_version()
    project = _make_project()
    signals = _make_signals(1)
    run_id = uuid4()
    doc_id = uuid4()
    mark_done_calls: list[dict] = []
    stub_client = _StubClient()

    registry = _patch_document_writer(
        monkeypatch,
        version=version,
        project=project,
        signals=signals,
        rag_chunks=[],
        run_id=run_id,
        doc_id=doc_id,
        stub_client=stub_client,
        mark_done_calls=mark_done_calls,
    )

    pool = _StubPool(_StubConn())
    result = await document_writer.write_document(
        project["id"], "Missions", _make_doc_plan(), pool=pool
    )

    assert result == run_id
    assert len(registry["inserted_docs"]) == 1
    assert len(mark_done_calls) == 1


# ---------------------------------------------------------------------------
# E2.3 — Pas de supporting_signals
# ---------------------------------------------------------------------------


async def test_write_document_no_supporting_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """supporting_signals=[] → continue, doc inséré."""
    from role_builder.synthesis import document_writer

    version = _make_version()
    project = _make_project()
    run_id = uuid4()
    doc_id = uuid4()
    mark_done_calls: list[dict] = []
    stub_client = _StubClient()

    registry = _patch_document_writer(
        monkeypatch,
        version=version,
        project=project,
        signals=[],
        rag_chunks=_make_rag_chunks(2),
        run_id=run_id,
        doc_id=doc_id,
        stub_client=stub_client,
        mark_done_calls=mark_done_calls,
    )

    doc_plan = {"name": "capability", "brief": "Une capacité.", "supporting_signals": []}
    pool = _StubPool(_StubConn())
    result = await document_writer.write_document(project["id"], "Skills", doc_plan, pool=pool)

    assert result == run_id
    assert len(registry["inserted_docs"]) == 1
    assert len(mark_done_calls) == 1


# ---------------------------------------------------------------------------
# E2.4 — invoke_chat échoue → cleanup + mark_failed + raise
# ---------------------------------------------------------------------------


async def test_write_document_invoke_chat_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """invoke_chat échoue → delete_documents_by_run + mark_failed + raise."""
    import httpx

    from role_builder.synthesis import document_writer

    version = _make_version()
    project = _make_project()
    run_id = uuid4()
    doc_id = uuid4()
    mark_failed_calls: list[dict] = []

    class _FailingClient:
        async def invoke_chat(
            self, messages: list[dict], *, response_format: dict | None = None
        ) -> ChatResult:
            raise httpx.HTTPError("LLM unreachable")

    registry = _patch_document_writer(
        monkeypatch,
        version=version,
        project=project,
        signals=_make_signals(1),
        rag_chunks=_make_rag_chunks(1),
        run_id=run_id,
        doc_id=doc_id,
        stub_client=_FailingClient(),  # type: ignore[arg-type]
        mark_failed_calls=mark_failed_calls,
    )

    pool = _StubPool(_StubConn())
    with pytest.raises(httpx.HTTPError):
        await document_writer.write_document(project["id"], "Role", _make_doc_plan(), pool=pool)

    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0]["run_id"] == run_id
    # Cleanup appelé (même si 0 docs insérés)
    assert len(registry["deleted_runs"]) == 1
    assert registry["deleted_runs"][0] == run_id


# ---------------------------------------------------------------------------
# E2.5 — instruction_override propagé dans messages
# ---------------------------------------------------------------------------


async def test_write_document_instruction_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """instruction_override → message user ajouté."""
    from role_builder.synthesis import document_writer

    version = _make_version()
    project = _make_project()
    run_id = uuid4()
    stub_client = _StubClient()

    _patch_document_writer(
        monkeypatch,
        version=version,
        project=project,
        signals=_make_signals(1),
        rag_chunks=_make_rag_chunks(1),
        run_id=run_id,
        doc_id=uuid4(),
        stub_client=stub_client,
    )

    pool = _StubPool(_StubConn())
    await document_writer.write_document(
        project["id"],
        "Skills",
        _make_doc_plan(),
        instruction_override="Rends le texte plus direct.",
        pool=pool,
    )

    messages, _ = stub_client.calls[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Rends le texte plus direct."


# ---------------------------------------------------------------------------
# E3.1 — write_all_documents_for_plan happy path
# ---------------------------------------------------------------------------


async def test_write_all_documents_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan avec 3 docs → write_document appelé 3 fois, 3 run_ids retournés."""
    from role_builder.synthesis import document_writer

    plan_id = uuid4()
    project_id = uuid4()
    run_ids = [uuid4(), uuid4(), uuid4()]
    call_count = 0
    run_idx = 0

    planned = [
        {"name": f"doc-{i}", "brief": f"Brief {i}", "supporting_signals": []} for i in range(3)
    ]

    async def fake_get_plan(pid: UUID, *, pool: Any) -> dict:
        return {
            "id": plan_id,
            "section": "Role",
            "planned_documents": planned,
        }

    async def fake_write_document(
        role_project_id: UUID, section: str, doc_plan: dict, *, pool: Any, **kwargs: Any
    ) -> UUID:
        nonlocal call_count, run_idx
        call_count += 1
        rid = run_ids[run_idx % len(run_ids)]
        run_idx += 1
        return rid

    monkeypatch.setattr(document_writer.document_plans, "get_by_id", fake_get_plan)
    monkeypatch.setattr(document_writer, "write_document", fake_write_document)

    pool = _StubPool(_StubConn())
    results = await document_writer.write_all_documents_for_plan(
        project_id, plan_id, parallelism=2, pool=pool
    )

    assert len(results) == 3
    assert call_count == 3
    assert set(results) == set(run_ids)


# ---------------------------------------------------------------------------
# E3.2 — write_all_documents_for_plan tous échouent → RuntimeError
# ---------------------------------------------------------------------------


async def test_write_all_documents_all_fail_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tous write_document échouent → RuntimeError 'all documents failed to write'."""
    from role_builder.synthesis import document_writer

    plan_id = uuid4()
    project_id = uuid4()

    planned = [
        {"name": f"doc-{i}", "brief": f"Brief {i}", "supporting_signals": []} for i in range(2)
    ]

    async def fake_get_plan(pid: UUID, *, pool: Any) -> dict:
        return {
            "id": plan_id,
            "section": "Missions",
            "planned_documents": planned,
        }

    async def fake_write_document(
        role_project_id: UUID, section: str, doc_plan: dict, *, pool: Any, **kwargs: Any
    ) -> UUID:
        raise RuntimeError("Simulated failure")

    monkeypatch.setattr(document_writer.document_plans, "get_by_id", fake_get_plan)
    monkeypatch.setattr(document_writer, "write_document", fake_write_document)

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError, match="all documents failed to write"):
        await document_writer.write_all_documents_for_plan(
            project_id, plan_id, parallelism=2, pool=pool
        )
