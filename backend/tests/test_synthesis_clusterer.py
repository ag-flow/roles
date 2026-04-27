"""Tests for synthesis.clusterer — run_clustering pipeline."""

from __future__ import annotations

import json
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


def _make_stub_version(
    template: str = "Directives: {global_directives}\nSignaux:\n{signals}",
) -> dict:
    return {
        "id": uuid4(),
        "template": template,
        "prompt_name": "clusterer",
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


def _make_signals(n: int) -> list[dict]:
    return [
        {
            "id": uuid4(),
            "type": "heuristique",
            "content": {"title": f"Signal {i}", "description": f"Desc {i}"},
        }
        for i in range(n)
    ]


def _make_valid_response(signal_ids: list[UUID]) -> str:
    return json.dumps(
        {
            "clusters": [
                {
                    "name": "Cluster alpha",
                    "description": "Premier cluster",
                    "signal_ids": [str(signal_ids[0])],
                },
                {
                    "name": "Cluster beta",
                    "description": "Second cluster",
                    "signal_ids": [str(signal_ids[1]), str(signal_ids[2])],
                },
            ]
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_happy_path_clusters_signals_and_marks_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path : 3 signaux, 2 clusters insérés, mark_done appelé, run_id retourné."""
    from role_builder.synthesis import clusterer

    version = _make_stub_version()
    project = _make_stub_project()
    signals = _make_signals(3)
    run_id = uuid4()
    valid_response = _make_valid_response([s["id"] for s in signals])

    stub_client = _StubClient(valid_response)
    inserted_cluster_ids: list[UUID] = []

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        assert name == "clusterer"
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_signals_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        assert rid == run_id

    mark_done_calls: list[dict] = []

    async def fake_mark_done(rid: UUID, *, output: Any, **kwargs: Any) -> None:
        mark_done_calls.append({"run_id": rid, "output": output, **kwargs})

    async def fake_insert_cluster(**kwargs: Any) -> UUID:
        cid = uuid4()
        inserted_cluster_ids.append(cid)
        return cid

    monkeypatch.setattr(
        clusterer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(clusterer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        clusterer.signals_helper, "list_signals_by_project", fake_list_signals_by_project
    )
    monkeypatch.setattr(clusterer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(clusterer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(clusterer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(clusterer.clusters_helper, "insert_cluster", fake_insert_cluster)
    monkeypatch.setattr(clusterer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    result = await clusterer.run_clustering(project["id"], pool=pool)

    assert result == run_id
    assert len(inserted_cluster_ids) == 2
    assert len(mark_done_calls) == 1
    output = json.loads(mark_done_calls[0]["output"])
    assert output["clusters_count"] == 2
    assert len(stub_client.calls) == 1  # une seule passe LLM


async def test_no_signals_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pas de signaux → RuntimeError avant create_run."""
    from role_builder.synthesis import clusterer

    version = _make_stub_version()
    project = _make_stub_project()

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_signals_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return []

    create_run_called = False

    async def fake_create_run(**kwargs: Any) -> UUID:
        nonlocal create_run_called
        create_run_called = True
        return uuid4()

    monkeypatch.setattr(
        clusterer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(clusterer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        clusterer.signals_helper, "list_signals_by_project", fake_list_signals_by_project
    )
    monkeypatch.setattr(clusterer.runs, "create_run", fake_create_run)

    pool = _StubPool(_StubConn())
    with pytest.raises(RuntimeError, match="no signals to cluster"):
        await clusterer.run_clustering(project["id"], pool=pool)

    assert not create_run_called


async def test_invalid_json_calls_mark_failed_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON invalide retourné par LLM → delete_clusters_by_run + mark_failed, re-raise."""
    from role_builder.synthesis import clusterer

    version = _make_stub_version()
    project = _make_stub_project()
    signals = _make_signals(2)
    run_id = uuid4()

    stub_client = _StubClient("invalid json {{{")

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_signals_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    call_order: list[str] = []

    async def fake_delete_clusters_by_run(rid: UUID, *, pool: Any) -> int:
        call_order.append("delete_clusters")
        return 0

    mark_failed_calls: list[dict] = []

    async def fake_mark_failed(rid: UUID, error: str, *, pool: Any) -> None:
        call_order.append("mark_failed")
        mark_failed_calls.append({"run_id": rid, "error": error})

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pytest.fail("mark_done should NOT be called on failure")

    monkeypatch.setattr(
        clusterer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(clusterer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        clusterer.signals_helper, "list_signals_by_project", fake_list_signals_by_project
    )
    monkeypatch.setattr(clusterer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(clusterer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(clusterer.runs, "mark_failed", fake_mark_failed)
    monkeypatch.setattr(clusterer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(
        clusterer.clusters_helper, "delete_clusters_by_run", fake_delete_clusters_by_run
    )
    monkeypatch.setattr(clusterer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    with pytest.raises((RuntimeError, ValueError)):
        await clusterer.run_clustering(project["id"], pool=pool)

    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0]["run_id"] == run_id
    # delete_clusters doit précéder mark_failed
    assert call_order.index("delete_clusters") < call_order.index("mark_failed")


async def test_instruction_override_added_to_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """instruction_override → message user ajouté dans la liste messages."""
    from role_builder.synthesis import clusterer

    version = _make_stub_version()
    project = _make_stub_project()
    signals = _make_signals(3)
    run_id = uuid4()
    valid_response = _make_valid_response([s["id"] for s in signals])

    stub_client = _StubClient(valid_response)

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_signals_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pass

    async def fake_insert_cluster(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        clusterer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(clusterer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        clusterer.signals_helper, "list_signals_by_project", fake_list_signals_by_project
    )
    monkeypatch.setattr(clusterer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(clusterer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(clusterer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(clusterer.clusters_helper, "insert_cluster", fake_insert_cluster)
    monkeypatch.setattr(clusterer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    await clusterer.run_clustering(
        project["id"],
        instruction_override="Insiste sur les heuristiques.",
        pool=pool,
    )

    assert len(stub_client.calls) == 1
    messages, _ = stub_client.calls[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Insiste sur les heuristiques."


async def test_signal_run_id_uses_list_by_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si signal_run_id fourni → list_signals_by_run appelé (pas list_signals_by_project)."""
    from role_builder.synthesis import clusterer

    version = _make_stub_version()
    project = _make_stub_project()
    signals = _make_signals(3)
    run_id = uuid4()
    signal_run_id = uuid4()
    valid_response = _make_valid_response([s["id"] for s in signals])

    stub_client = _StubClient(valid_response)
    list_by_run_called = False
    list_by_project_called = False

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_signals_by_run(rid: UUID, *, pool: Any) -> list[dict]:
        nonlocal list_by_run_called
        list_by_run_called = True
        assert rid == signal_run_id
        return signals

    async def fake_list_signals_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        nonlocal list_by_project_called
        list_by_project_called = True
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pass

    async def fake_insert_cluster(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        clusterer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(clusterer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(clusterer.signals_helper, "list_signals_by_run", fake_list_signals_by_run)
    monkeypatch.setattr(
        clusterer.signals_helper, "list_signals_by_project", fake_list_signals_by_project
    )
    monkeypatch.setattr(clusterer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(clusterer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(clusterer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(clusterer.clusters_helper, "insert_cluster", fake_insert_cluster)
    monkeypatch.setattr(clusterer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    await clusterer.run_clustering(
        project["id"],
        signal_run_id=signal_run_id,
        pool=pool,
    )

    assert list_by_run_called is True
    assert list_by_project_called is False


async def test_no_signal_run_id_uses_list_by_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si signal_run_id absent → list_signals_by_project appelé."""
    from role_builder.synthesis import clusterer

    version = _make_stub_version()
    project = _make_stub_project()
    signals = _make_signals(3)
    run_id = uuid4()
    valid_response = _make_valid_response([s["id"] for s in signals])

    stub_client = _StubClient(valid_response)
    list_by_run_called = False
    list_by_project_called = False

    async def fake_get_system_default(name: str, *, pool: Any) -> dict:
        return version

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict:
        return project

    async def fake_list_signals_by_run(rid: UUID, *, pool: Any) -> list[dict]:
        nonlocal list_by_run_called
        list_by_run_called = True
        return signals

    async def fake_list_signals_by_project(project_id: UUID, *, pool: Any) -> list[dict]:
        nonlocal list_by_project_called
        list_by_project_called = True
        return signals

    async def fake_create_run(**kwargs: Any) -> UUID:
        return run_id

    async def fake_mark_running(rid: UUID, *, pool: Any) -> None:
        pass

    async def fake_mark_done(rid: UUID, **kwargs: Any) -> None:
        pass

    async def fake_insert_cluster(**kwargs: Any) -> UUID:
        return uuid4()

    monkeypatch.setattr(
        clusterer.prompts_helper, "get_system_default_version", fake_get_system_default
    )
    monkeypatch.setattr(clusterer.role_projects, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(clusterer.signals_helper, "list_signals_by_run", fake_list_signals_by_run)
    monkeypatch.setattr(
        clusterer.signals_helper, "list_signals_by_project", fake_list_signals_by_project
    )
    monkeypatch.setattr(clusterer.runs, "create_run", fake_create_run)
    monkeypatch.setattr(clusterer.runs, "mark_running", fake_mark_running)
    monkeypatch.setattr(clusterer.runs, "mark_done", fake_mark_done)
    monkeypatch.setattr(clusterer.clusters_helper, "insert_cluster", fake_insert_cluster)
    monkeypatch.setattr(clusterer, "get_agflow_client", lambda: stub_client)

    pool = _StubPool(_StubConn())
    await clusterer.run_clustering(project["id"], pool=pool)

    assert list_by_run_called is False
    assert list_by_project_called is True
