"""Tests pour routes.synthesis — triggers pipeline + list/get runs + set-current + regenerate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers de fabrication de données fictives
# ---------------------------------------------------------------------------


def _make_run_row(
    project_id: UUID | None = None,
    run_id: UUID | None = None,
    status: str = "done",
) -> dict[str, Any]:
    """Construit un dict simulant une ligne de la table runs."""
    now = datetime.now(tz=UTC)
    return {
        "id": run_id or uuid4(),
        "role_project_id": project_id or uuid4(),
        "prompt_version_id": uuid4(),
        "status": status,
        "output": '{"signals_count": 12}',
        "llm_provider": "mistral",
        "llm_model": "mistral-medium",
        "tokens_input": 1000,
        "tokens_output": 500,
        "cost_usd": 0.002,
        "instruction_override": None,
        "started_at": now,
        "completed_at": now,
        "error": None,
        "created_at": now,
    }


def _make_doc_row(doc_id: UUID | None = None, project_id: UUID | None = None) -> dict[str, Any]:
    """Construit un dict simulant une ligne de la table role_documents."""
    now = datetime.now(tz=UTC)
    return {
        "id": doc_id or uuid4(),
        "role_project_id": project_id or uuid4(),
        "tenant_id": uuid4(),
        "section": "Role",
        "name": "Identité principale",
        "content": "Contenu du document...",
        "source_run_id": uuid4(),
        "version": 1,
        "is_current": False,
        "locked": False,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Tests triggers pipeline
# ---------------------------------------------------------------------------


def test_trigger_extraction_returns_202_and_run_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-projects/{id}/runs/extract → 202 + run_id."""
    from role_builder.routes import synthesis as synthesis_route

    project_id = uuid4()
    expected_run_id = uuid4()

    async def fake_run_extraction(pid: UUID, *, pool: Any, **kwargs: Any) -> UUID:
        assert pid == project_id
        return expected_run_id

    monkeypatch.setattr(synthesis_route.extractor, "run_extraction", fake_run_extraction)

    resp = client.post(
        f"/api/role-projects/{project_id}/runs/extract",
        json={"chunks_per_batch": 5},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"] == str(expected_run_id)


def test_trigger_clustering_returns_202_and_run_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-projects/{id}/runs/cluster → 202 + run_id."""
    from role_builder.routes import synthesis as synthesis_route

    project_id = uuid4()
    expected_run_id = uuid4()

    async def fake_run_clustering(pid: UUID, *, pool: Any, **kwargs: Any) -> UUID:
        assert pid == project_id
        return expected_run_id

    monkeypatch.setattr(synthesis_route.clusterer, "run_clustering", fake_run_clustering)

    resp = client.post(
        f"/api/role-projects/{project_id}/runs/cluster",
        json={},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"] == str(expected_run_id)


def test_trigger_decomposition_returns_202_and_run_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-projects/{id}/runs/decompose → 202 + run_id."""
    from role_builder.routes import synthesis as synthesis_route

    project_id = uuid4()
    expected_run_id = uuid4()

    async def fake_run_decomposition(pid: UUID, *, pool: Any, **kwargs: Any) -> UUID:
        assert pid == project_id
        return expected_run_id

    monkeypatch.setattr(synthesis_route.decomposer, "run_decomposition", fake_run_decomposition)

    resp = client.post(
        f"/api/role-projects/{project_id}/runs/decompose",
        json={},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"] == str(expected_run_id)


def test_trigger_write_documents_returns_202_and_run_ids(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-projects/{id}/runs/write-documents → 202 + run_ids."""
    from role_builder.routes import synthesis as synthesis_route

    project_id = uuid4()
    plan_id = uuid4()
    expected_run_ids = [uuid4(), uuid4(), uuid4()]

    async def fake_write_all(pid: UUID, p_id: UUID, *, pool: Any, **kwargs: Any) -> list[UUID]:
        assert pid == project_id
        assert p_id == plan_id
        return expected_run_ids

    monkeypatch.setattr(
        synthesis_route.document_writer, "write_all_documents_for_plan", fake_write_all
    )

    resp = client.post(
        f"/api/role-projects/{project_id}/runs/write-documents",
        json={"plan_id": str(plan_id), "parallelism": 3},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert len(body["run_ids"]) == 3
    assert body["run_ids"][0] == str(expected_run_ids[0])


def test_trigger_identity_synthesis_returns_202_and_run_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-projects/{id}/runs/synthesize-identity → 202 + run_id."""
    from role_builder.routes import synthesis as synthesis_route

    project_id = uuid4()
    expected_run_id = uuid4()

    async def fake_synthesize_identity(pid: UUID, *, pool: Any, **kwargs: Any) -> UUID:
        assert pid == project_id
        return expected_run_id

    monkeypatch.setattr(
        synthesis_route.identity_synthesizer, "synthesize_identity", fake_synthesize_identity
    )

    resp = client.post(
        f"/api/role-projects/{project_id}/runs/synthesize-identity",
        json={},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"] == str(expected_run_id)


# ---------------------------------------------------------------------------
# Tests regenerate_document
# ---------------------------------------------------------------------------


def test_regenerate_document_returns_404_if_doc_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-documents/{doc_id}/regenerate → 404 si doc inconnu."""
    from role_builder.routes import synthesis as synthesis_route

    doc_id = uuid4()

    async def fake_get_by_id(did: UUID, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(synthesis_route.role_documents, "get_by_id", fake_get_by_id)

    resp = client.post(f"/api/role-documents/{doc_id}/regenerate", json={})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "document not found"


def test_regenerate_document_returns_202_and_run_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-documents/{doc_id}/regenerate → 202 + run_id si doc connu."""
    from role_builder.routes import synthesis as synthesis_route

    doc_id = uuid4()
    project_id = uuid4()
    expected_run_id = uuid4()
    doc_row = _make_doc_row(doc_id=doc_id, project_id=project_id)

    async def fake_get_by_id(did: UUID, *, pool: Any) -> dict[str, Any]:
        assert did == doc_id
        return doc_row

    async def fake_write_document(
        pid: UUID,
        section: str,
        doc_plan: dict,
        *,
        pool: Any,
        **kwargs: Any,
    ) -> UUID:
        assert pid == project_id
        assert section == doc_row["section"]
        assert doc_plan["name"] == doc_row["name"]
        return expected_run_id

    monkeypatch.setattr(synthesis_route.role_documents, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(synthesis_route.document_writer, "write_document", fake_write_document)

    resp = client.post(
        f"/api/role-documents/{doc_id}/regenerate",
        json={"instruction_override": "Réécris en français soutenu."},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"] == str(expected_run_id)


# ---------------------------------------------------------------------------
# Tests set-current
# ---------------------------------------------------------------------------


def test_set_current_version_returns_ok(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-documents/{doc_id}/set-current → 200 {"status": "ok"}."""
    from role_builder.routes import synthesis as synthesis_route

    doc_id = uuid4()
    called: dict[str, Any] = {}

    async def fake_set_current(did: UUID, *, pool: Any) -> None:
        called["doc_id"] = did

    monkeypatch.setattr(synthesis_route.role_documents, "set_current", fake_set_current)

    resp = client.post(f"/api/role-documents/{doc_id}/set-current")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}
    assert called["doc_id"] == doc_id


def test_set_current_version_returns_404_on_value_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/role-documents/{doc_id}/set-current → 404 si ValueError."""
    from role_builder.routes import synthesis as synthesis_route

    doc_id = uuid4()

    async def fake_set_current_raises(did: UUID, *, pool: Any) -> None:
        raise ValueError(f"doc_id {did} not found in role_documents")

    monkeypatch.setattr(synthesis_route.role_documents, "set_current", fake_set_current_raises)

    resp = client.post(f"/api/role-documents/{doc_id}/set-current")
    assert resp.status_code == 404, resp.text
    assert "not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests list + get runs
# ---------------------------------------------------------------------------


def test_list_runs_returns_list(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects/{id}/runs → 200 + list[RunOut]."""
    from role_builder.routes import synthesis as synthesis_route

    project_id = uuid4()
    rows = [_make_run_row(project_id=project_id) for _ in range(3)]

    async def fake_list_runs(
        pid: UUID,
        *,
        status: str | None,
        limit: int,
        pool: Any,
    ) -> list[dict[str, Any]]:
        assert pid == project_id
        assert status == "done"
        assert limit == 10
        return rows

    monkeypatch.setattr(synthesis_route.runs, "list_runs", fake_list_runs)

    resp = client.get(f"/api/role-projects/{project_id}/runs?status=done&limit=10")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 3
    assert body[0]["status"] == "done"
    assert body[0]["llm_provider"] == "mistral"


def test_get_run_returns_run_out(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/runs/{run_id} → 200 + RunOut."""
    from role_builder.routes import synthesis as synthesis_route

    run_id = uuid4()
    row = _make_run_row(run_id=run_id)

    async def fake_get_run(rid: UUID, *, pool: Any) -> dict[str, Any]:
        assert rid == run_id
        return row

    monkeypatch.setattr(synthesis_route.runs, "get_run", fake_get_run)

    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(run_id)
    assert body["status"] == "done"


def test_get_run_returns_404_if_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/runs/{run_id} → 404 si run inconnu."""
    from role_builder.routes import synthesis as synthesis_route

    run_id = uuid4()

    async def fake_get_run(rid: UUID, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(synthesis_route.runs, "get_run", fake_get_run)

    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "run not found"
