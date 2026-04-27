"""Tests for synthesis.extractor — run_extraction pipeline."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from role_builder.services.agflow_client import ChatResult

# ---------------------------------------------------------------------------
# Stubs asyncpg pool (stateless — on n'a pas besoin de transaction ici)
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> None:
        self.calls.append(("execute", query, args))


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
    """Stub AgflowClient avec réponse pré-réglée et capture des appels."""

    def __init__(self, content: str, model: str = "mistral-test") -> None:
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
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_version(template: str = "Sys: {global_directives}\nChunks:\n{chunks}") -> dict:
    return {
        "id": uuid4(),
        "template": template,
        "prompt_name": "extractor",
        "version_number": 1,
    }


def _make_stub_project(
    tenant_id: UUID | None = None, global_directives: str = "Directives test"
) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or uuid4(),
        "display_name": "Projet test",
        "global_directives": global_directives,
    }


def _make_chunks(n: int) -> list[dict]:
    return [
        {
            "id": uuid4(),
            "source_item_id": uuid4(),
            "text": f"Texte chunk {i}",
            "chunk_index": i,
            "start_s": float(i * 10),
            "end_s": float(i * 10 + 10),
            "source_title": "Source test",
        }
        for i in range(n)
    ]


_VALID_RESPONSE = json.dumps(
    {
        "signals": [
            {
                "type": "heuristique",
                "content": {"title": "Règle pratique", "description": "desc"},
                "source_chunks": [],
            },
            {
                "type": "vocab",
                "content": {"title": "Terme clé", "description": "desc vocab"},
                "source_chunks": [],
            },
        ]
    }
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_happy_path_extracts_signals_and_marks_done(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path : 5 chunks, prompt system_default, 2 signaux insérés, mark_done appelé."""
    from role_builder.synthesis import extractor

    version = _make_stub_version()
    project = _make_stub_project()
    chunks = _make_chunks(5)

    stub_client = _StubClient(_VALID_RESPONSE)
    run_id = uuid4()
    inserted_signal_ids: list[UUID] = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        assert name == "extractor"
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_by_project(project_id: UUID, *, limit: int, pool: Any) -> list[dict]:
        return chunks

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        assert rid == run_id

    mark_done_calls: list[dict] = []

    async def fake_mark_done(rid: UUID, *, output: Any, **kwargs: Any) -> None:
        mark_done_calls.append({"run_id": rid, "output": output, **kwargs})

    async def fake_insert_signal(**kwargs: Any) -> UUID:
        sig_id = uuid4()
        inserted_signal_ids.append(sig_id)
        return sig_id

    monkeypatch.setattr(
        extractor.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(extractor.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(extractor.corpus_chunks, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(extractor.runs, "create_run", fake_create_run)
    monkeypatch.setattr(extractor.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(extractor.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(extractor.signals_helper, "insert_signal", fake_insert_signal)
    monkeypatch.setattr(extractor, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    result = await extractor.run_extraction(project["id"], pool=pool)

    assert result == run_id
    assert len(inserted_signal_ids) == 2
    assert len(mark_done_calls) == 1
    output = json.loads(mark_done_calls[0]["output"])
    assert output["signals_count"] == 2
    assert len(stub_client.calls) == 1  # 5 chunks, 1 batch de 5


async def test_no_chunks_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """list_by_project retourne [] → RuntimeError levée avant create_run."""
    from role_builder.synthesis import extractor

    version = _make_stub_version()
    project = _make_stub_project()

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_by_project(project_id: UUID, *, limit: int, pool: Any) -> list[dict]:
        return []

    create_run_called = False

    async def fake_create_run(**kwargs: Any) -> UUID:
        nonlocal create_run_called
        create_run_called = True
        return uuid4()

    monkeypatch.setattr(
        extractor.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(extractor.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(extractor.corpus_chunks, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(extractor.runs, "create_run", fake_create_run)

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError, match="no corpus_chunks"):
        await extractor.run_extraction(project["id"], pool=pool)

    assert not create_run_called


async def test_invalid_json_calls_mark_failed_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON invalide retourné par LLM → mark_failed appelé, exception re-raised."""
    from role_builder.synthesis import extractor

    version = _make_stub_version()
    project = _make_stub_project()
    chunks = _make_chunks(2)
    run_id = uuid4()

    stub_client = _StubClient("invalid json {{{")

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_by_project(project_id: UUID, *, limit: int, pool: Any) -> list[dict]:
        return chunks

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    mark_failed_calls: list[dict] = []

    async def fake_mark_failed(rid: UUID, error: str, *, pool: Any) -> None:
        mark_failed_calls.append({"run_id": rid, "error": error})

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pytest.fail("mark_done should NOT be called on failure")

    async def fake_delete_signals_by_run(rid: UUID, *, pool: Any) -> int:
        return 0

    monkeypatch.setattr(
        extractor.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(extractor.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(extractor.corpus_chunks, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(extractor.runs, "create_run", fake_create_run)
    monkeypatch.setattr(extractor.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(extractor.runs, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(extractor.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(
        extractor.signals_helper, "delete_signals_by_run", fake_delete_signals_by_run
    )
    monkeypatch.setattr(extractor, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError) as exc_info:
        await extractor.run_extraction(project["id"], pool=pool)

    assert "ValidationError" in str(exc_info.value) or "JSON" in str(exc_info.value)
    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0]["run_id"] == run_id


async def test_multi_batches_accumulate_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """10 chunks + batch=5 → 2 appels invoke_chat, tokens accumulés."""
    from role_builder.synthesis import extractor

    version = _make_stub_version()
    project = _make_stub_project()
    chunks = _make_chunks(10)
    run_id = uuid4()

    stub_client = _StubClient(_VALID_RESPONSE)

    mark_done_calls: list[dict] = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_by_project(project_id: UUID, *, limit: int, pool: Any) -> list[dict]:
        return chunks

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(
        rid: UUID, *, output: Any, tokens_input: int, tokens_output: int, **kwargs: Any
    ) -> None:
        mark_done_calls.append({"tokens_input": tokens_input, "tokens_output": tokens_output})

    async def fake_insert_signal(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        extractor.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(extractor.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(extractor.corpus_chunks, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(extractor.runs, "create_run", fake_create_run)
    monkeypatch.setattr(extractor.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(extractor.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(extractor.signals_helper, "insert_signal", fake_insert_signal)
    monkeypatch.setattr(extractor, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    result = await extractor.run_extraction(project["id"], chunks_per_batch=5, pool=pool)

    assert result == run_id
    # 2 batches de 5 chunks
    assert len(stub_client.calls) == 2
    # tokens accumulés : 2 × 10 input, 2 × 20 output
    assert mark_done_calls[0]["tokens_input"] == 20
    assert mark_done_calls[0]["tokens_output"] == 40


async def test_failure_mid_pipeline_cleans_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Échec en milieu de pipeline : delete_signals_by_run appelé avant mark_failed."""
    from role_builder.synthesis import extractor

    version = _make_stub_version()
    project = _make_stub_project()
    # 10 chunks → 2 batches de 5 : batch 0 OK, batch 1 JSON invalide
    chunks = _make_chunks(10)
    run_id = uuid4()

    call_order: list[str] = []

    class _TwoBatchClient:
        """1er appel OK, 2e appel retourne JSON invalide."""

        async def invoke_chat(
            self, messages: list[dict], *, response_format: dict | None = None
        ) -> ChatResult:
            if len(call_order) == 0:
                call_order.append("llm_batch_0")
                return ChatResult(
                    content=_VALID_RESPONSE,
                    tokens_input=10,
                    tokens_output=20,
                    cost_usd=None,
                    model="mistral-test",
                )
            call_order.append("llm_batch_1_invalid")
            return ChatResult(
                content="invalid json {{{",
                tokens_input=10,
                tokens_output=5,
                cost_usd=None,
                model="mistral-test",
            )

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_by_project(project_id: UUID, *, limit: int, pool: Any) -> list[dict]:
        return chunks

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    delete_calls: list[UUID] = []

    async def fake_delete_signals_by_run(rid: UUID, *, pool: Any) -> int:
        call_order.append("delete_signals")
        delete_calls.append(rid)
        return 2

    mark_failed_calls: list[dict] = []

    async def fake_mark_failed(rid: UUID, error: str, *, pool: Any) -> None:
        call_order.append("mark_failed")
        mark_failed_calls.append({"run_id": rid, "error": error})

    async def fake_insert_signal(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        extractor.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(extractor.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(extractor.corpus_chunks, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(extractor.runs, "create_run", fake_create_run)
    monkeypatch.setattr(extractor.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(extractor.runs, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(extractor.signals_helper, "insert_signal", fake_insert_signal)
    monkeypatch.setattr(
        extractor.signals_helper, "delete_signals_by_run", fake_delete_signals_by_run
    )
    monkeypatch.setattr(extractor, "get_agflow_client", lambda: _TwoBatchClient())

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError):
        await extractor.run_extraction(project["id"], chunks_per_batch=5, pool=pool)

    # delete_signals_by_run doit être appelé avec le run_id
    assert len(delete_calls) == 1
    assert delete_calls[0] == run_id

    # delete doit précéder mark_failed dans l'ordre d'appel
    assert call_order.index("delete_signals") < call_order.index("mark_failed")

    # mark_failed doit être appelé une fois
    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0]["run_id"] == run_id


async def test_instruction_override_added_to_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """instruction_override passé → message user ajouté dans la liste messages."""
    from role_builder.synthesis import extractor

    version = _make_stub_version()
    project = _make_stub_project()
    chunks = _make_chunks(2)
    run_id = uuid4()

    stub_client = _StubClient(_VALID_RESPONSE)

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_by_project(project_id: UUID, *, limit: int, pool: Any) -> list[dict]:
        return chunks

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pass

    async def fake_insert_signal(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        extractor.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(extractor.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(extractor.corpus_chunks, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(extractor.runs, "create_run", fake_create_run)
    monkeypatch.setattr(extractor.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(extractor.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(extractor.signals_helper, "insert_signal", fake_insert_signal)
    monkeypatch.setattr(extractor, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    await extractor.run_extraction(
        project["id"],
        instruction_override="Focus sur les heuristiques uniquement.",
        pool=pool,
    )

    assert len(stub_client.calls) == 1
    messages, _ = stub_client.calls[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Focus sur les heuristiques uniquement."
