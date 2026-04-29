# Sprint 7 — Phase D — Frontend onglet Rôle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Patterns établis Sprint 5/6 (db_helpers asyncpg, structlog, ≤300 lignes, TDD strict, schemas Pydantic, SWR + clients API typés frontend).

**Goal:** Construire l'onglet "Rôle" complet du frontend (`/projects/[id]/role`) — éditeur de documents avec versioning + flux Push vers ag.flow avec progression temps réel via WebSocket — plus le backend manquant pour le supporter (5 routes CRUD `role_documents` + canal WS `agflow_push_events`).

**Architecture:**
- **Backend D0** : nouveau router `role_documents.py` (lecture par projet groupée + détail + versions + édition manuelle + lock/unlock), extension de `ws_relay` (5e canal `agflow_push_events`) + émission `pg_notify` à chaque étape de `services/agflow/push.py`. L'endpoint HTTP `push-to-agflow` reste **synchrone** : il renvoie le résultat final, le canal WS sert uniquement à afficher les étapes intermédiaires en live.
- **Frontend D1 (push)** : `lib/api/agflow-export.ts` + page `role/page.tsx` + 4 composants (`PushToAgflowButton`, `PushPreview`, `PushProgressDialog`, `PostPushBanner`). Banner d'échec partiel = **rouge** (action requise) avec retry sur `generate-prompts-on-agflow`. 409 sur le nom = modale d'erreur explicite "Renommez votre projet d'abord", pas de rename inline.
- **Frontend D2 (editor)** : `lib/api/role-documents.ts` + composant `RoleDocumentEditor` avec arborescence sections/docs, vue détail + versions, édition manuelle, lock/unlock, régénération, diff side-by-side.

**Tech Stack:** asyncpg `pool.execute("SELECT pg_notify(...)")` côté backend (pas de migration nouvelle), `react-diff-viewer-continued` côté frontend pour le diff (lib légère, MIT), reste = SWR + WebSocket existants.

**Décisions actées (cf. brainstorm) :**
- Variante A confirmée : push sync HTTP + WS pour progression intermédiaire.
- Banner échec partiel = **rouge** (convention StatusIndicator : action requise).
- 409 sur display_name = bloquant, l'utilisateur renomme d'abord son projet.
- WS pour la progression du push, SWR pour le `preview-zip`.
- `RoleDocumentEditor` livré dans cette phase (pas reporté).

---

## File Structure

```
backend/
├── src/role_builder/
│   ├── services/
│   │   ├── ws_relay.py                    # D0.2 : ajouter "agflow_push_events" aux _CHANNELS
│   │   └── agflow/
│   │       └── push.py                    # D0.2 : émettre pg_notify à chaque étape
│   ├── schemas/
│   │   └── role_documents.py              # D0.1 : nouveau (RoleDocumentOut, etc.)
│   ├── db_helpers/
│   │   └── role_documents.py              # D0.1 : ajouter update_content
│   └── routes/
│       ├── role_documents.py              # D0.1 : nouveau router (5 endpoints)
│       └── __init__.py                    # D0.1 : include_router(role_documents)
└── tests/
    ├── test_db_helpers_role_documents.py  # D0.1 : étendre (update_content)
    ├── test_role_documents_route.py       # D0.1 : nouveau
    ├── test_ws_relay.py                   # D0.2 : étendre (5e canal)
    └── test_agflow_push.py                # D0.2 : étendre (assertions pg_notify)

frontend/
├── package.json                           # D2.5 : ajouter react-diff-viewer-continued
└── src/
    ├── lib/
    │   ├── types.ts                       # D1.1 : RoleDocument, PushPreview, PushEvent
    │   └── api/
    │       ├── agflow-export.ts           # D1.1 : nouveau
    │       └── role-documents.ts          # D1.1 : nouveau
    └── app/projects/[id]/
        ├── layout.tsx                     # D1.2 : ajouter onglet "Rôle" dans TABS
        └── role/
            ├── page.tsx                   # D1.2 : nouveau
            ├── PushToAgflowButton.tsx     # D1.4
            ├── PushPreview.tsx            # D1.3
            ├── PushProgressDialog.tsx     # D1.4
            ├── PostPushBanner.tsx         # D1.5
            ├── RoleDocumentEditor.tsx     # D2.1
            ├── DocumentTree.tsx           # D2.1
            ├── DocumentDetail.tsx         # D2.2
            ├── VersionList.tsx            # D2.2
            ├── DocumentEditor.tsx         # D2.3
            ├── DocumentActions.tsx        # D2.4 (lock/unlock + regenerate)
            └── VersionDiff.tsx            # D2.5

frontend/src/lib/api/role-documents.ts utilise les conventions des autres lib/api/ (api<T>(...))
```

---

## Phase D0 — Backend prerequisites

### D0.1 — Routes `role_documents` (CRUD + lock/unlock + grouped)

**Files:**
- Modify: `backend/src/role_builder/db_helpers/role_documents.py` (ajouter `update_content`)
- Create: `backend/src/role_builder/schemas/role_documents.py`
- Create: `backend/src/role_builder/routes/role_documents.py`
- Modify: `backend/src/role_builder/routes/__init__.py` (include_router)
- Modify: `backend/tests/test_db_helpers_role_documents.py` (test update_content)
- Create: `backend/tests/test_role_documents_route.py`

#### D0.1.1 — Helper `update_content` (TDD)

- [ ] **Step 1: Test rouge — `update_content` modifie le contenu d'un doc**

```python
# backend/tests/test_db_helpers_role_documents.py — append at end of file
async def test_update_content_changes_content_and_updated_at(pool, fixture_project_with_doc):
    project_id, doc_id = fixture_project_with_doc
    before = await role_documents.get_by_id(doc_id, pool=pool)

    await role_documents.update_content(doc_id, "nouveau contenu manuel", pool=pool)

    after = await role_documents.get_by_id(doc_id, pool=pool)
    assert after["content"] == "nouveau contenu manuel"
    assert after["updated_at"] > before["updated_at"]


async def test_update_content_unknown_id_raises_value_error(pool):
    with pytest.raises(ValueError, match="not found"):
        await role_documents.update_content(uuid4(), "x", pool=pool)
```

- [ ] **Step 2: Run le test, vérifier qu'il échoue (AttributeError: update_content)**

Run: `cd backend && uv run pytest tests/test_db_helpers_role_documents.py::test_update_content_changes_content_and_updated_at -v`
Expected: FAIL `AttributeError: module 'role_builder.db_helpers.role_documents' has no attribute 'update_content'`

- [ ] **Step 3: Implémentation minimale**

```python
# backend/src/role_builder/db_helpers/role_documents.py — append after _UNLOCK_SQL
_UPDATE_CONTENT_SQL = """
    UPDATE role_documents
    SET content = $2, updated_at = now()
    WHERE id = $1
    RETURNING id
"""


async def update_content(doc_id: UUID, content: str, *, pool: asyncpg.Pool) -> None:
    """Met à jour le contenu d'un document (édition manuelle).

    Lève ValueError si doc_id inexistant. Ne crée PAS de nouvelle version :
    c'est une édition in-place de la version actuelle.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchval(_UPDATE_CONTENT_SQL, doc_id, content)
    if row is None:
        raise ValueError(f"doc_id {doc_id} not found in role_documents")
```

- [ ] **Step 4: Run, vérifier passing**

Run: `cd backend && uv run pytest tests/test_db_helpers_role_documents.py -v`
Expected: PASS (full file)

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/db_helpers/role_documents.py backend/tests/test_db_helpers_role_documents.py
git commit -m "feat(backend): db_helpers/role_documents.update_content (édition manuelle in-place)"
```

#### D0.1.2 — Schémas Pydantic

- [ ] **Step 1: Créer le fichier schemas**

```python
# backend/src/role_builder/schemas/role_documents.py
"""DTOs Pydantic pour les role_documents (Sprint 7 Phase D)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RoleDocumentOut(BaseModel):
    id: UUID
    role_project_id: UUID
    section: str
    name: str
    content: str
    version: int
    is_current: bool
    locked: bool
    source_run_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class RoleDocumentSummary(BaseModel):
    """Variante allégée (sans `content`) pour les listings groupés."""
    id: UUID
    section: str
    name: str
    version: int
    is_current: bool
    locked: bool
    updated_at: datetime


class RoleDocumentsBySection(BaseModel):
    """Réponse de GET /role-projects/{id}/role-documents — groupé par section."""
    sections: dict[str, list[RoleDocumentSummary]]


class UpdateRoleDocumentRequest(BaseModel):
    content: str = Field(min_length=1)
```

- [ ] **Step 2: Pas de test direct sur les schemas (Pydantic est testé en transit via les routes)**

- [ ] **Step 3: Commit après route — combiné avec D0.1.3**

#### D0.1.3 — Router `role_documents.py` (5 endpoints, TDD)

- [ ] **Step 1: Test rouge — GET liste groupée**

```python
# backend/tests/test_role_documents_route.py
"""Tests des routes /role-documents et /role-projects/{id}/role-documents."""
from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_list_grouped_returns_sections_with_current_docs(
    client, auth_headers, fixture_project_with_docs,
):
    project_id, _doc_ids = fixture_project_with_docs

    resp = await client.get(
        f"/api/role-projects/{project_id}/role-documents",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "sections" in body
    assert "Role" in body["sections"]
    assert all("content" not in d for d in body["sections"]["Role"])  # summary, pas full
    assert all("name" in d and "version" in d for d in body["sections"]["Role"])


@pytest.mark.asyncio
async def test_get_document_returns_full_content(client, auth_headers, fixture_doc):
    doc_id = fixture_doc

    resp = await client.get(f"/api/role-documents/{doc_id}", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(doc_id)
    assert body["content"]


@pytest.mark.asyncio
async def test_get_document_404_when_unknown(client, auth_headers):
    resp = await client.get(f"/api/role-documents/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_versions_returns_all_versions_desc(
    client, auth_headers, fixture_doc_with_versions,
):
    doc_id = fixture_doc_with_versions  # v1 + v2 + v3 same (project, section, name)

    resp = await client.get(
        f"/api/role-documents/{doc_id}/versions",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert body[0]["version"] > body[-1]["version"]  # ORDER BY version DESC


@pytest.mark.asyncio
async def test_patch_updates_content(client, auth_headers, fixture_doc):
    doc_id = fixture_doc

    resp = await client.patch(
        f"/api/role-documents/{doc_id}",
        json={"content": "édité à la main"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "édité à la main"


@pytest.mark.asyncio
async def test_patch_404_when_unknown(client, auth_headers):
    resp = await client.patch(
        f"/api/role-documents/{uuid4()}",
        json={"content": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lock_and_unlock(client, auth_headers, fixture_doc):
    doc_id = fixture_doc

    r1 = await client.post(f"/api/role-documents/{doc_id}/lock", headers=auth_headers)
    assert r1.status_code == 200

    detail = await client.get(f"/api/role-documents/{doc_id}", headers=auth_headers)
    assert detail.json()["locked"] is True

    r2 = await client.post(f"/api/role-documents/{doc_id}/unlock", headers=auth_headers)
    assert r2.status_code == 200

    detail2 = await client.get(f"/api/role-documents/{doc_id}", headers=auth_headers)
    assert detail2.json()["locked"] is False
```

- [ ] **Step 2: Run les tests, vérifier qu'ils échouent (404 sur tous les endpoints)**

Run: `cd backend && uv run pytest tests/test_role_documents_route.py -v`
Expected: FAIL — endpoints absents.

- [ ] **Step 3: Implémenter le router**

```python
# backend/src/role_builder/routes/role_documents.py
"""Routes Sprint 7 Phase D — lecture/édition des role_documents.

Conventions :
- Toutes protégées par `Depends(get_current_user)`.
- Erreurs : 404 si introuvable, 422 si Pydantic.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import role_documents
from role_builder.schemas.role_documents import (
    RoleDocumentOut,
    RoleDocumentSummary,
    RoleDocumentsBySection,
    UpdateRoleDocumentRequest,
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get(
    "/role-projects/{project_id}/role-documents",
    response_model=RoleDocumentsBySection,
)
async def list_grouped(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> RoleDocumentsBySection:
    grouped = await role_documents.list_current_by_project_grouped(
        project_id, pool=db_pool.pool,
    )
    sections: dict[str, list[RoleDocumentSummary]] = {}
    for section_name, docs in grouped.items():
        sections[section_name] = [
            RoleDocumentSummary(
                id=d["id"],
                section=str(d["section"]),
                name=str(d["name"]),
                version=int(d["version"]),
                is_current=bool(d["is_current"]),
                locked=bool(d["locked"]),
                updated_at=d["updated_at"],
            )
            for d in docs
        ]
    return RoleDocumentsBySection(sections=sections)


@router.get("/role-documents/{doc_id}", response_model=RoleDocumentOut)
async def get_document(
    doc_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> RoleDocumentOut:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    return RoleDocumentOut(**doc)


@router.get(
    "/role-documents/{doc_id}/versions",
    response_model=list[RoleDocumentOut],
)
async def list_versions(
    doc_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> list[RoleDocumentOut]:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    versions = await role_documents.list_versions(
        doc["role_project_id"],
        str(doc["section"]),
        str(doc["name"]),
        pool=db_pool.pool,
    )
    return [RoleDocumentOut(**v) for v in versions]


@router.patch("/role-documents/{doc_id}", response_model=RoleDocumentOut)
async def update_document(
    doc_id: UUID,
    body: UpdateRoleDocumentRequest,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> RoleDocumentOut:
    try:
        await role_documents.update_content(doc_id, body.content, pool=db_pool.pool)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    log.info("api.role_documents.updated", doc_id=str(doc_id))
    return RoleDocumentOut(**doc)


@router.post("/role-documents/{doc_id}/lock")
async def lock_document_endpoint(
    doc_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> dict[str, str]:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    await role_documents.lock_document(doc_id, pool=db_pool.pool)
    log.info("api.role_documents.locked", doc_id=str(doc_id))
    return {"status": "locked"}


@router.post("/role-documents/{doc_id}/unlock")
async def unlock_document_endpoint(
    doc_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> dict[str, str]:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    await role_documents.unlock_document(doc_id, pool=db_pool.pool)
    log.info("api.role_documents.unlocked", doc_id=str(doc_id))
    return {"status": "unlocked"}
```

- [ ] **Step 4: Inclure le router dans `routes/__init__.py`**

```python
# backend/src/role_builder/routes/__init__.py — ajouter
from role_builder.routes import role_documents as _role_documents

# dans la fonction include_routers (ou équivalent existant)
app.include_router(_role_documents.router, prefix="/api", tags=["role-documents"])
```

- [ ] **Step 5: Run tests, vérifier qu'ils passent**

Run: `cd backend && uv run pytest tests/test_role_documents_route.py -v`
Expected: PASS (toutes les fixtures conftest doivent fournir `fixture_project_with_docs`, `fixture_doc`, `fixture_doc_with_versions` — voir conftest existant pour le pattern, créer si manquant).

- [ ] **Step 6: Commit**

```bash
git add backend/src/role_builder/schemas/role_documents.py \
        backend/src/role_builder/routes/role_documents.py \
        backend/src/role_builder/routes/__init__.py \
        backend/tests/test_role_documents_route.py
git commit -m "feat(backend): routes role_documents (list-grouped + detail + versions + patch + lock/unlock)"
```

---

### D0.2 — WebSocket `agflow_push_events` + émission depuis `push.py`

**Files:**
- Modify: `backend/src/role_builder/services/ws_relay.py:30-35` (ajouter canal)
- Modify: `backend/src/role_builder/services/agflow/push.py` (émettre pg_notify)
- Modify: `backend/tests/test_ws_relay.py` (asserter le 5e canal)
- Modify: `backend/tests/test_agflow_push.py` (asserter les NOTIFY)

#### D0.2.1 — Ajouter le canal au relay

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_ws_relay.py — append
@pytest.mark.asyncio
async def test_relay_listens_to_agflow_push_events_channel(real_pool, monkeypatch):
    relay = WSRelay(dsn=settings.database_url)
    await relay.start()
    try:
        # Vérifie qu'une notif sur le canal est bien dispatched
        tenant_id = uuid4()
        queue = relay.subscribe(tenant_id=tenant_id)

        async with real_pool.acquire() as conn:
            payload = json.dumps({
                "tenant_id": str(tenant_id),
                "project_id": str(uuid4()),
                "step": "zip_built",
                "status": "in_progress",
            })
            await conn.execute("SELECT pg_notify('agflow_push_events', $1)", payload)

        event = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert event["channel"] == "agflow_push_events"
        assert event["payload"]["step"] == "zip_built"
    finally:
        await relay.stop()
```

- [ ] **Step 2: Run, vérifier FAIL (canal pas écouté)**

Run: `cd backend && uv run pytest tests/test_ws_relay.py::test_relay_listens_to_agflow_push_events_channel -v`
Expected: FAIL — timeout (canal non listened).

- [ ] **Step 3: Ajouter le canal dans `_CHANNELS`**

```python
# backend/src/role_builder/services/ws_relay.py:30-35 — remplacer le tuple
_CHANNELS = (
    "source_items_changes",
    "runs_changes",
    "workers_changes",
    "keys_changes",
    "agflow_push_events",
)
```

- [ ] **Step 4: Run, vérifier PASS**

Run: `cd backend && uv run pytest tests/test_ws_relay.py -v`
Expected: PASS (tous les tests existants + le nouveau).

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/services/ws_relay.py backend/tests/test_ws_relay.py
git commit -m "feat(backend): ws_relay écoute agflow_push_events (5e canal)"
```

#### D0.2.2 — Émettre pg_notify dans `push_role_to_agflow`

- [ ] **Step 1: Test rouge — push émet 4 NOTIFY successifs (zip_built, role_ready, zip_uploaded, done)**

```python
# backend/tests/test_agflow_push.py — append (ou créer test_agflow_push_notifications.py)
@pytest.mark.asyncio
async def test_push_emits_progress_events_in_order(
    real_pool, fixture_pushable_project, mock_agflow_client,
):
    project_id, tenant_id = fixture_pushable_project
    received: list[dict] = []

    async def collector(connection, pid, channel, payload):  # noqa: ARG001
        received.append({"channel": channel, "payload": json.loads(payload)})

    listener_conn = await asyncpg.connect(settings.database_url)
    await listener_conn.add_listener("agflow_push_events", collector)
    try:
        await push.push_role_to_agflow(
            project_id,
            generate_prompts=True,
            pool=real_pool,
            client=mock_agflow_client,
        )
        # NOTIFY est asynchrone côté Postgres : laisser le scheduler tourner
        await asyncio.sleep(0.2)

        steps = [r["payload"]["step"] for r in received]
        assert steps == ["zip_built", "role_ready", "zip_uploaded", "prompts_generated", "done"]
        assert all(r["payload"]["tenant_id"] == str(tenant_id) for r in received)
        assert all(r["payload"]["project_id"] == str(project_id) for r in received)
    finally:
        await listener_conn.close()


@pytest.mark.asyncio
async def test_push_emits_failed_event_on_upstream_error(
    real_pool, fixture_pushable_project, mock_agflow_client_failing_on_import,
):
    project_id, tenant_id = fixture_pushable_project
    received: list[dict] = []

    async def collector(connection, pid, channel, payload):  # noqa: ARG001
        received.append(json.loads(payload))

    listener_conn = await asyncpg.connect(settings.database_url)
    await listener_conn.add_listener("agflow_push_events", collector)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await push.push_role_to_agflow(
                project_id,
                generate_prompts=False,
                pool=real_pool,
                client=mock_agflow_client_failing_on_import,
            )
        await asyncio.sleep(0.2)
        steps = [r["step"] for r in received]
        assert "failed" in steps
        assert any(r.get("status") == "failed" for r in received)
    finally:
        await listener_conn.close()
```

- [ ] **Step 2: Run, vérifier FAIL (aucun NOTIFY émis)**

Run: `cd backend && uv run pytest tests/test_agflow_push.py::test_push_emits_progress_events_in_order -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter l'émission**

```python
# backend/src/role_builder/services/agflow/push.py — modifier le module
"""Orchestration du push d'un rôle vers ag.flow."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import structlog

from role_builder.config import settings
from role_builder.db_helpers import role_documents, role_projects
from role_builder.services.agflow.api_client import (
    AgflowAdminClient,
    get_agflow_admin_client,
)
from role_builder.services.agflow.exporter import BuildResult, build_role_zip

log = structlog.get_logger(__name__)

LOCKED_SECTIONS_REQUIRED = ["Role", "Missions", "Skills"]
WS_CHANNEL = "agflow_push_events"


async def _emit(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    project_id: str,
    step: str,
    status: str = "in_progress",
    detail: dict[str, Any] | None = None,
) -> None:
    """Émet un NOTIFY sur le canal `agflow_push_events`.

    Best-effort : on log mais on ne casse pas le push si le NOTIFY échoue
    (le pool peut être saturé, etc.).
    """
    payload = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "step": step,
        "status": status,
    }
    if detail:
        payload["detail"] = detail
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "SELECT pg_notify($1, $2)",
                WS_CHANNEL,
                json.dumps(payload),
            )
    except Exception as exc:  # noqa: BLE001 — best effort
        log.warning("agflow.push.notify_failed", step=step, exc=str(exc))


def check_missing_pieces(
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
) -> list[str]:
    missing: list[str] = []
    if not (project.get("identity") and str(project["identity"]).strip()):
        missing.append("Identity not generated")
    for required in LOCKED_SECTIONS_REQUIRED:
        if not docs_by_section.get(required):
            missing.append(f"Section '{required}' has no current documents")
    return missing


async def push_role_to_agflow(
    project_id: UUID,
    *,
    generate_prompts: bool = False,
    pool: asyncpg.Pool,
    client: AgflowAdminClient | None = None,
) -> dict[str, Any]:
    """Orchestration complète du push, avec émissions WS à chaque étape."""
    project = await role_projects.get_by_id(project_id, pool=pool)
    if project is None:
        raise RuntimeError(f"role_project {project_id} not found")

    tenant_id = str(project["tenant_id"])
    pid = str(project_id)

    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id, pool=pool,
    )
    missing = check_missing_pieces(project, docs_by_section)
    if missing:
        raise RuntimeError(f"cannot push: missing pieces — {missing}")

    try:
        build: BuildResult = build_role_zip(project, docs_by_section)
        await _emit(
            pool, tenant_id=tenant_id, project_id=pid, step="zip_built",
            detail={"size_bytes": len(build.zip_bytes),
                    "documents_count": build.documents_count},
        )

        api = client or get_agflow_admin_client()

        target_role_id: str | None = project.get("target_role_id")
        if not target_role_id:
            created = await api.create_role(
                display_name=str(project["display_name"]),
                description=project.get("description"),
            )
            target_role_id = str(created["id"])
            await role_projects.update_target_role_id(
                project_id, target_role_id, pool=pool,
            )
        await _emit(
            pool, tenant_id=tenant_id, project_id=pid, step="role_ready",
            detail={"target_role_id": target_role_id},
        )

        import_result = await api.import_role_zip(target_role_id, build.zip_bytes)
        await _emit(
            pool, tenant_id=tenant_id, project_id=pid, step="zip_uploaded",
        )

        prompt_generated = False
        if generate_prompts:
            await api.generate_prompts(target_role_id)
            prompt_generated = True
            await _emit(
                pool, tenant_id=tenant_id, project_id=pid, step="prompts_generated",
            )

        result = {
            "agflow_role_id": target_role_id,
            "zip_size_bytes": len(build.zip_bytes),
            "documents_count": (
                import_result.get("documents_count")
                if isinstance(import_result, dict) else None
            ) or build.documents_count,
            "prompt_generated": prompt_generated,
            "agflow_url": (
                f"{settings.agflow_base_url.rstrip('/')}/admin/roles/{target_role_id}"
            ),
        }
        await _emit(
            pool, tenant_id=tenant_id, project_id=pid,
            step="done", status="done", detail=result,
        )
        return result

    except (httpx.HTTPError, RuntimeError) as exc:
        await _emit(
            pool, tenant_id=tenant_id, project_id=pid,
            step="failed", status="failed",
            detail={"error": str(exc)},
        )
        raise
```

- [ ] **Step 4: Run, vérifier PASS**

Run: `cd backend && uv run pytest tests/test_agflow_push.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/services/agflow/push.py backend/tests/test_agflow_push.py
git commit -m "feat(backend): push agflow émet NOTIFY agflow_push_events à chaque étape (zip_built/role_ready/zip_uploaded/prompts_generated/done/failed)"
```

---

## Phase D1 — Frontend flux Push vers ag.flow

### D1.1 — Types + clients API

**Files:**
- Modify: `frontend/src/lib/types.ts` (ajouter types)
- Create: `frontend/src/lib/api/agflow-export.ts`
- Create: `frontend/src/lib/api/role-documents.ts`
- Create: `frontend/src/lib/api/agflow-export.test.ts` (Vitest)

#### D1.1.1 — Types

- [ ] **Step 1: Ajouter dans `types.ts` après le bloc existant**

```typescript
// frontend/src/lib/types.ts — append

// --- Sprint 7 Phase D : Role documents -----------------------------------

export interface RoleDocumentSummary {
  id: string;
  section: string;
  name: string;
  version: number;
  is_current: boolean;
  locked: boolean;
  updated_at: string;
}

export interface RoleDocument extends RoleDocumentSummary {
  role_project_id: string;
  content: string;
  source_run_id: string | null;
  created_at: string;
}

export interface RoleDocumentsBySection {
  sections: Record<string, RoleDocumentSummary[]>;
}

// --- Sprint 7 Phase D : Push to ag.flow ----------------------------------

export interface PreviewSectionDoc {
  name: string;
  size: number;
}

export interface PreviewSection {
  name: string;
  documents: PreviewSectionDoc[];
}

export interface PushPreview {
  display_name: string;
  description: string | null;
  identity_length: number;
  target_role_id: string | null;
  sections: PreviewSection[];
  ready_to_push: boolean;
  missing: string[];
}

export interface PushToAgflowRequest {
  generate_prompts: boolean;
}

export interface PushToAgflowResponse {
  agflow_role_id: string;
  zip_size_bytes: number;
  documents_count: number | null;
  prompt_generated: boolean;
  agflow_url: string;
}

export type PushStep =
  | 'zip_built'
  | 'role_ready'
  | 'zip_uploaded'
  | 'prompts_generated'
  | 'done'
  | 'failed';

export interface PushEventPayload {
  tenant_id: string;
  project_id: string;
  step: PushStep;
  status: 'in_progress' | 'done' | 'failed';
  detail?: Record<string, unknown>;
}
```

Et étendre `WSChannel` :

```typescript
export type WSChannel =
  | 'source_items_changes'
  | 'runs_changes'
  | 'workers_changes'
  | 'keys_changes'
  | 'agflow_push_events';
```

#### D1.1.2 — Client API `agflow-export.ts` (TDD)

- [ ] **Step 1: Test rouge**

```typescript
// frontend/src/lib/api/agflow-export.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as exporter from './agflow-export';
import * as client from './client';

describe('agflow-export client', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('previewZip GET le bon path', async () => {
    const apiSpy = vi.spyOn(client, 'api').mockResolvedValue({
      display_name: 'X',
      description: null,
      identity_length: 100,
      target_role_id: null,
      sections: [],
      ready_to_push: false,
      missing: ['Identity not generated'],
    });
    await exporter.previewZip('proj-1');
    expect(apiSpy).toHaveBeenCalledWith('/api/role-projects/proj-1/preview-zip');
  });

  it('pushToAgflow POST avec generate_prompts', async () => {
    const apiSpy = vi.spyOn(client, 'api').mockResolvedValue({
      agflow_role_id: 'r',
      zip_size_bytes: 1,
      documents_count: 1,
      prompt_generated: true,
      agflow_url: 'http://x',
    });
    await exporter.pushToAgflow('proj-1', { generate_prompts: true });
    expect(apiSpy).toHaveBeenCalledWith(
      '/api/role-projects/proj-1/push-to-agflow',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ generate_prompts: true }),
      }),
    );
  });

  it('generatePromptsOnAgflow POST', async () => {
    const apiSpy = vi.spyOn(client, 'api').mockResolvedValue({
      status: 'generated', target_role_id: 'r',
    });
    await exporter.generatePromptsOnAgflow('proj-1');
    expect(apiSpy).toHaveBeenCalledWith(
      '/api/role-projects/proj-1/generate-prompts-on-agflow',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
```

- [ ] **Step 2: Run, vérifier FAIL (module absent)**

Run: `cd frontend && npm test -- agflow-export`
Expected: FAIL.

- [ ] **Step 3: Implémenter le client**

```typescript
// frontend/src/lib/api/agflow-export.ts
import { api } from './client';
import type {
  PushPreview,
  PushToAgflowRequest,
  PushToAgflowResponse,
} from '../types';

export async function previewZip(projectId: string): Promise<PushPreview> {
  return api<PushPreview>(`/api/role-projects/${projectId}/preview-zip`);
}

export async function pushToAgflow(
  projectId: string,
  body: PushToAgflowRequest,
): Promise<PushToAgflowResponse> {
  return api<PushToAgflowResponse>(
    `/api/role-projects/${projectId}/push-to-agflow`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export async function generatePromptsOnAgflow(
  projectId: string,
): Promise<{ status: string; target_role_id: string }> {
  return api(
    `/api/role-projects/${projectId}/generate-prompts-on-agflow`,
    { method: 'POST' },
  );
}

export function downloadZipUrl(projectId: string): string {
  return `/api/role-projects/${projectId}/download-zip`;
}
```

- [ ] **Step 4: Run, vérifier PASS**

Run: `cd frontend && npm test -- agflow-export`
Expected: PASS.

#### D1.1.3 — Client API `role-documents.ts`

- [ ] **Step 1: Tests + implémentation (mêmes patterns que D1.1.2)**

```typescript
// frontend/src/lib/api/role-documents.ts
import { api } from './client';
import type { RoleDocument, RoleDocumentsBySection } from '../types';

export async function listGrouped(projectId: string): Promise<RoleDocumentsBySection> {
  return api(`/api/role-projects/${projectId}/role-documents`);
}

export async function getDocument(docId: string): Promise<RoleDocument> {
  return api(`/api/role-documents/${docId}`);
}

export async function listVersions(docId: string): Promise<RoleDocument[]> {
  return api(`/api/role-documents/${docId}/versions`);
}

export async function updateContent(
  docId: string,
  content: string,
): Promise<RoleDocument> {
  return api(`/api/role-documents/${docId}`, {
    method: 'PATCH',
    body: JSON.stringify({ content }),
  });
}

export async function lockDocument(docId: string): Promise<void> {
  await api(`/api/role-documents/${docId}/lock`, { method: 'POST' });
}

export async function unlockDocument(docId: string): Promise<void> {
  await api(`/api/role-documents/${docId}/unlock`, { method: 'POST' });
}

export async function setCurrent(docId: string): Promise<void> {
  await api(`/api/role-documents/${docId}/set-current`, { method: 'POST' });
}

export async function regenerate(
  docId: string,
  instructionOverride?: string,
): Promise<{ run_id: string }> {
  return api(`/api/role-documents/${docId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({
      instruction_override: instructionOverride ?? null,
    }),
  });
}
```

- [ ] **Step 2: Tests Vitest miroir de D1.1.2**

(Couvre listGrouped, getDocument, listVersions, updateContent, lock, unlock, setCurrent, regenerate. Format identique.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts \
        frontend/src/lib/api/agflow-export.ts \
        frontend/src/lib/api/role-documents.ts \
        frontend/src/lib/api/agflow-export.test.ts \
        frontend/src/lib/api/role-documents.test.ts
git commit -m "feat(frontend): types + clients API agflow-export + role-documents"
```

---

### D1.2 — Page rôle (layout + onglet "Rôle")

**Files:**
- Modify: `frontend/src/app/projects/[id]/layout.tsx` (ajouter onglet)
- Create: `frontend/src/app/projects/[id]/role/page.tsx`

- [ ] **Step 1: Ajouter "Rôle" à `TABS` dans layout.tsx**

```tsx
// frontend/src/app/projects/[id]/layout.tsx — modifier TABS
const TABS = [
  { key: 'sources', label: 'Sources' },
  { key: 'corpus', label: 'Corpus' },
  { key: 'prompts', label: 'Prompts' },
  { key: 'analyses', label: 'Analyses' },
  { key: 'role', label: 'Rôle' },
];
```

- [ ] **Step 2: Créer `role/page.tsx` avec squelette + SWR sur preview-zip + skeleton de RoleDocumentEditor (vide pour l'instant)**

```tsx
// frontend/src/app/projects/[id]/role/page.tsx
'use client';

import useSWR from 'swr';
import { use } from 'react';
import { previewZip } from '@/lib/api/agflow-export';
import { listGrouped } from '@/lib/api/role-documents';
import { PushToAgflowButton } from './PushToAgflowButton';
import { RoleDocumentEditor } from './RoleDocumentEditor';

export default function RolePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: projectId } = use(params);

  const preview = useSWR(`preview-${projectId}`, () => previewZip(projectId));
  const docs = useSWR(`role-docs-${projectId}`, () => listGrouped(projectId));

  if (preview.isLoading || docs.isLoading) {
    return <div>Chargement…</div>;
  }
  if (preview.error || docs.error) {
    return <div className="error">Erreur de chargement</div>;
  }

  return (
    <div className="role-page">
      <header className="role-header">
        <h1>{preview.data!.display_name}</h1>
        <PushToAgflowButton
          projectId={projectId}
          preview={preview.data!}
          onPushed={() => preview.mutate()}
        />
      </header>
      <RoleDocumentEditor
        projectId={projectId}
        sections={docs.data!.sections}
        onChange={() => docs.mutate()}
      />
    </div>
  );
}
```

- [ ] **Step 3: Stubs vides pour `PushToAgflowButton` et `RoleDocumentEditor` pour que la page compile**

```tsx
// frontend/src/app/projects/[id]/role/PushToAgflowButton.tsx
'use client';
import type { PushPreview } from '@/lib/types';

export function PushToAgflowButton(_props: {
  projectId: string;
  preview: PushPreview;
  onPushed: () => void;
}) {
  return <button disabled>Pousser vers ag.flow (stub)</button>;
}

// frontend/src/app/projects/[id]/role/RoleDocumentEditor.tsx
'use client';
import type { RoleDocumentSummary } from '@/lib/types';

export function RoleDocumentEditor(_props: {
  projectId: string;
  sections: Record<string, RoleDocumentSummary[]>;
  onChange: () => void;
}) {
  return <div className="editor-stub">Éditeur (stub)</div>;
}
```

- [ ] **Step 4: Vérifier build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS sans warning.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/projects/\[id\]/layout.tsx \
        frontend/src/app/projects/\[id\]/role/page.tsx \
        frontend/src/app/projects/\[id\]/role/PushToAgflowButton.tsx \
        frontend/src/app/projects/\[id\]/role/RoleDocumentEditor.tsx
git commit -m "feat(frontend): onglet Rôle + page squelette (preview-zip SWR + role-documents SWR)"
```

---

### D1.3 — Composant `PushPreview`

**Files:**
- Create: `frontend/src/app/projects/[id]/role/PushPreview.tsx`
- Create: `frontend/src/app/projects/[id]/role/PushPreview.test.tsx`

- [ ] **Step 1: Test rouge — affiche missing[] quand ready_to_push=false**

```tsx
// PushPreview.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PushPreview } from './PushPreview';
import type { PushPreview as PushPreviewT } from '@/lib/types';

const baseFixture: PushPreviewT = {
  display_name: 'UX Designer',
  description: null,
  identity_length: 1500,
  target_role_id: null,
  sections: [
    { name: 'Role', documents: [{ name: 'principe-empathie', size: 1200 }] },
  ],
  ready_to_push: false,
  missing: ['Section "Missions" has no current documents'],
};

describe('PushPreview', () => {
  it('affiche les sections et leurs documents', () => {
    render(<PushPreview preview={{ ...baseFixture, ready_to_push: true, missing: [] }} />);
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByText('principe-empathie')).toBeInTheDocument();
  });

  it('affiche les éléments manquants quand ready_to_push=false', () => {
    render(<PushPreview preview={baseFixture} />);
    expect(screen.getByText(/Section "Missions"/)).toBeInTheDocument();
    expect(screen.getByText(/manquant/i)).toBeInTheDocument();
  });

  it('affiche "déjà poussé" quand target_role_id est non null', () => {
    render(
      <PushPreview
        preview={{ ...baseFixture, target_role_id: 'role-abc', ready_to_push: true, missing: [] }}
      />,
    );
    expect(screen.getByText(/role-abc/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, FAIL (composant inexistant)**

- [ ] **Step 3: Implémenter**

```tsx
// PushPreview.tsx
'use client';
import type { PushPreview as PushPreviewT } from '@/lib/types';

export function PushPreview({ preview }: { preview: PushPreviewT }) {
  return (
    <div className="push-preview">
      <h3>Aperçu du push</h3>
      <p>Identity : {preview.identity_length} caractères</p>
      {preview.target_role_id && (
        <p className="info">Déjà poussé sur ag.flow (id : {preview.target_role_id})</p>
      )}
      <ul className="sections">
        {preview.sections.map(s => (
          <li key={s.name}>
            <strong>{s.name}</strong> ({s.documents.length} document{s.documents.length > 1 ? 's' : ''})
            <ul>
              {s.documents.map(d => (
                <li key={d.name}>
                  {d.name} <span className="size">({d.size} car.)</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {!preview.ready_to_push && (
        <div className="missing">
          <strong>Éléments manquants :</strong>
          <ul>
            {preview.missing.map(m => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run, PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(frontend): PushPreview (sections + missing[] + target_role_id)"
```

---

### D1.4 — `PushToAgflowButton` + `PushProgressDialog` (avec WS)

**Files:**
- Modify: `PushToAgflowButton.tsx` (remplacer le stub)
- Create: `PushProgressDialog.tsx`
- Create: `PushProgressDialog.test.tsx`

- [ ] **Step 1: `PushProgressDialog` avec hook WS — test rouge**

```tsx
// PushProgressDialog.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PushProgressDialog } from './PushProgressDialog';

vi.mock('@/lib/ws/hooks', () => ({
  useWebSocketEvent: vi.fn(),
}));

describe('PushProgressDialog', () => {
  it('affiche les 5 étapes avec leur état', () => {
    render(
      <PushProgressDialog
        projectId="p1"
        steps={['zip_built', 'role_ready']}
        finalStatus={null}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/Construction du ZIP/i)).toBeInTheDocument();
    expect(screen.getByText(/Création du rôle/i)).toBeInTheDocument();
  });

  it('affiche le bouton "Fermer" quand finalStatus=done', () => {
    render(
      <PushProgressDialog
        projectId="p1"
        steps={['zip_built', 'role_ready', 'zip_uploaded', 'done']}
        finalStatus="done"
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /fermer/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implémenter**

```tsx
// PushProgressDialog.tsx
'use client';
import { useEffect, useState } from 'react';
import { useWebSocketEvent } from '@/lib/ws/hooks';
import type { PushEventPayload, PushStep } from '@/lib/types';

const STEP_LABELS: Record<PushStep, string> = {
  zip_built: 'Construction du ZIP',
  role_ready: 'Création du rôle ag.flow',
  zip_uploaded: 'Upload du ZIP',
  prompts_generated: 'Génération du prompt orchestrateur',
  done: 'Terminé',
  failed: 'Échec',
};

const STEP_ORDER: PushStep[] = [
  'zip_built',
  'role_ready',
  'zip_uploaded',
  'prompts_generated',
];

interface Props {
  projectId: string;
  steps: PushStep[];                  // étapes déjà reçues
  finalStatus: 'done' | 'failed' | null;
  onClose: () => void;
}

export function PushProgressDialog({ steps, finalStatus, onClose }: Props) {
  return (
    <div className="dialog progress">
      <h3>Push en cours…</h3>
      <ol className="steps">
        {STEP_ORDER.map(step => {
          const reached = steps.includes(step);
          return (
            <li key={step} className={reached ? 'done' : 'pending'}>
              {reached ? '✓' : '◯'} {STEP_LABELS[step]}
            </li>
          );
        })}
      </ol>
      {finalStatus === 'done' && (
        <button onClick={onClose}>Fermer</button>
      )}
      {finalStatus === 'failed' && (
        <button onClick={onClose} className="error">Fermer (échec)</button>
      )}
    </div>
  );
}

// Hook qui collecte les étapes depuis le WS et les rend au composant ci-dessus.
export function usePushProgress(projectId: string, active: boolean) {
  const [steps, setSteps] = useState<PushStep[]>([]);
  const [finalStatus, setFinalStatus] = useState<'done' | 'failed' | null>(null);

  useWebSocketEvent('agflow_push_events', (payload: PushEventPayload) => {
    if (!active) return;
    if (payload.project_id !== projectId) return;
    setSteps(prev => (prev.includes(payload.step) ? prev : [...prev, payload.step]));
    if (payload.status === 'done') setFinalStatus('done');
    if (payload.status === 'failed') setFinalStatus('failed');
  });

  // Reset quand active passe de false à true
  useEffect(() => {
    if (active) {
      setSteps([]);
      setFinalStatus(null);
    }
  }, [active]);

  return { steps, finalStatus };
}
```

- [ ] **Step 4: Implémenter `PushToAgflowButton` (modale confirmation → push → progress dialog → banner)**

```tsx
// PushToAgflowButton.tsx
'use client';
import { useState } from 'react';
import { pushToAgflow } from '@/lib/api/agflow-export';
import { ApiError } from '@/lib/api/client';
import type { PushPreview, PushToAgflowResponse } from '@/lib/types';
import { PushPreview as PushPreviewView } from './PushPreview';
import { PushProgressDialog, usePushProgress } from './PushProgressDialog';
import { PostPushBanner } from './PostPushBanner';

interface Props {
  projectId: string;
  preview: PushPreview;
  onPushed: () => void;
}

export function PushToAgflowButton({ projectId, preview, onPushed }: Props) {
  const [step, setStep] = useState<'idle' | 'confirm' | 'pushing' | 'done' | 'error'>('idle');
  const [generatePrompts, setGeneratePrompts] = useState(false);
  const [result, setResult] = useState<PushToAgflowResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isConflict, setIsConflict] = useState(false);
  const { steps, finalStatus } = usePushProgress(projectId, step === 'pushing');

  const isUpdate = !!preview.target_role_id;
  const label = isUpdate ? 'Mettre à jour ag.flow' : 'Pousser vers ag.flow';

  async function confirm() {
    setStep('pushing');
    try {
      const res = await pushToAgflow(projectId, { generate_prompts: generatePrompts });
      setResult(res);
      setStep('done');
      onPushed();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setIsConflict(true);
      }
      setErrorMsg(err instanceof Error ? err.message : 'Erreur inconnue');
      setStep('error');
    }
  }

  return (
    <>
      <button
        disabled={!preview.ready_to_push}
        onClick={() => setStep('confirm')}
      >
        {label}
      </button>

      {step === 'confirm' && (
        <div className="dialog">
          <PushPreviewView preview={preview} />
          <label>
            <input
              type="checkbox"
              checked={generatePrompts}
              onChange={e => setGeneratePrompts(e.target.checked)}
            />
            Générer le prompt orchestrateur après l'import
          </label>
          <div className="actions">
            <button onClick={() => setStep('idle')}>Annuler</button>
            <button onClick={confirm}>Confirmer</button>
          </div>
        </div>
      )}

      {step === 'pushing' && (
        <PushProgressDialog
          projectId={projectId}
          steps={steps}
          finalStatus={finalStatus}
          onClose={() => setStep('idle')}
        />
      )}

      {step === 'done' && result && (
        <PostPushBanner
          projectId={projectId}
          result={result}
          partialFailure={null}
          onDismiss={() => setStep('idle')}
        />
      )}

      {step === 'error' && errorMsg && (
        <div className="dialog error">
          <h3>Échec du push</h3>
          {isConflict ? (
            <p>
              Le nom <strong>{preview.display_name}</strong> existe déjà sur ag.flow.
              Renommez votre projet (paramètres) avant de pousser.
            </p>
          ) : (
            <p>{errorMsg}</p>
          )}
          <button onClick={() => setStep('idle')}>Fermer</button>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 5: Run typecheck + tests**

Run: `cd frontend && npm run typecheck && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/projects/\[id\]/role/PushToAgflowButton.tsx \
        frontend/src/app/projects/\[id\]/role/PushProgressDialog.tsx \
        frontend/src/app/projects/\[id\]/role/PushProgressDialog.test.tsx
git commit -m "feat(frontend): PushToAgflowButton + PushProgressDialog (WS agflow_push_events) + 409 modale"
```

---

### D1.5 — `PostPushBanner` (succès + échec partiel rouge)

**Files:**
- Create: `frontend/src/app/projects/[id]/role/PostPushBanner.tsx`
- Create: `frontend/src/app/projects/[id]/role/PostPushBanner.test.tsx`

- [ ] **Step 1: Test rouge — banner vert si tout OK, rouge si prompt échoue**

```tsx
// PostPushBanner.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PostPushBanner } from './PostPushBanner';
import * as exporter from '@/lib/api/agflow-export';

const baseResult = {
  agflow_role_id: 'r-1',
  zip_size_bytes: 12345,
  documents_count: 7,
  prompt_generated: true,
  agflow_url: 'https://docker-agflow.yoops.org/admin/roles/r-1',
};

describe('PostPushBanner', () => {
  it('vert quand tout OK', () => {
    const { container } = render(
      <PostPushBanner
        projectId="p1"
        result={baseResult}
        partialFailure={null}
        onDismiss={() => {}}
      />,
    );
    expect(container.querySelector('.banner.success')).not.toBeNull();
    expect(screen.getByRole('link', { name: /admin/i })).toHaveAttribute(
      'href',
      baseResult.agflow_url,
    );
  });

  it('rouge avec retry quand échec partiel sur prompt', async () => {
    const spy = vi.spyOn(exporter, 'generatePromptsOnAgflow').mockResolvedValue({
      status: 'generated', target_role_id: 'r-1',
    });
    const { container } = render(
      <PostPushBanner
        projectId="p1"
        result={{ ...baseResult, prompt_generated: false }}
        partialFailure="prompt"
        onDismiss={() => {}}
      />,
    );
    expect(container.querySelector('.banner.error')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /réessayer/i }));
    expect(spy).toHaveBeenCalledWith('p1');
  });
});
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implémenter**

```tsx
// PostPushBanner.tsx
'use client';
import { useState } from 'react';
import { generatePromptsOnAgflow } from '@/lib/api/agflow-export';
import type { PushToAgflowResponse } from '@/lib/types';

interface Props {
  projectId: string;
  result: PushToAgflowResponse;
  partialFailure: 'prompt' | null;       // si import OK mais prompt KO
  onDismiss: () => void;
}

export function PostPushBanner({ projectId, result, partialFailure, onDismiss }: Props) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  if (partialFailure === 'prompt') {
    async function retry() {
      setRetrying(true);
      setRetryError(null);
      try {
        await generatePromptsOnAgflow(projectId);
        onDismiss();
      } catch (err) {
        setRetryError(err instanceof Error ? err.message : 'Erreur');
      } finally {
        setRetrying(false);
      }
    }

    return (
      <div className="banner error">
        <h4>⚠ Rôle uploadé sur ag.flow, mais la génération du prompt a échoué</h4>
        <p>Le rôle est bien créé mais son prompt orchestrateur n'a pas été généré.</p>
        {retryError && <p className="error">{retryError}</p>}
        <button onClick={retry} disabled={retrying}>
          {retrying ? 'Réessai en cours…' : 'Réessayer la génération du prompt'}
        </button>
        <button onClick={onDismiss}>Plus tard</button>
      </div>
    );
  }

  return (
    <div className="banner success">
      <h4>✓ Rôle poussé sur ag.flow</h4>
      <p>
        {result.documents_count ?? 0} document(s), {Math.round(result.zip_size_bytes / 1024)} Ko.
        {result.prompt_generated && ' Prompt orchestrateur généré.'}
      </p>
      <a href={result.agflow_url} target="_blank" rel="noopener noreferrer">
        Voir dans l'admin ag.flow →
      </a>
      <button onClick={onDismiss}>Fermer</button>
    </div>
  );
}
```

- [ ] **Step 4: Câbler la détection d'échec partiel dans `PushToAgflowButton`**

Dans `PushToAgflowButton.tsx`, modifier le `confirm()` pour détecter le cas où `pushToAgflow` retourne mais `result.prompt_generated === false` alors que `generatePrompts` était à `true` (l'API actuelle ne fait pas ça : si `generate_prompts=true` et que l'appel échoue, le push entier lève. Donc le banner partial-failure ne se déclenche que via le WS event `failed` reçu après `zip_uploaded`).

Pour MVP : on garde la détection simple via le **flag dérivé du WS** :
```tsx
const partialFailure = (
  steps.includes('zip_uploaded') && finalStatus === 'failed' && generatePrompts
) ? 'prompt' : null;
```

…et on passe ce flag au `PostPushBanner` même quand `step === 'error'` (refactor mineur de la state machine : `step === 'error' | 'partial'`). Détail à finaliser à l'implémentation.

- [ ] **Step 5: Run typecheck + tests**

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(frontend): PostPushBanner (success + partial failure rouge avec retry generate-prompts)"
```

---

## Phase D2 — Frontend `RoleDocumentEditor`

### D2.1 — `DocumentTree` + structure de l'éditeur

**Files:**
- Modify: `RoleDocumentEditor.tsx` (remplacer le stub)
- Create: `DocumentTree.tsx` + test

- [ ] **Step 1: Test rouge — DocumentTree affiche les sections + docs et émet onSelect**

```tsx
// DocumentTree.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DocumentTree } from './DocumentTree';

const sections = {
  Role: [
    { id: 'd1', section: 'Role', name: 'principe-empathie', version: 2,
      is_current: true, locked: false, updated_at: '2026-04-28T10:00:00Z' },
  ],
  Missions: [],
};

describe('DocumentTree', () => {
  it('liste sections et documents et appelle onSelect au clic', () => {
    const onSelect = vi.fn();
    render(<DocumentTree sections={sections} selectedId={null} onSelect={onSelect} />);
    expect(screen.getByText('Role')).toBeInTheDocument();
    fireEvent.click(screen.getByText('principe-empathie'));
    expect(onSelect).toHaveBeenCalledWith('d1');
  });

  it('marque la section vide comme empty', () => {
    render(<DocumentTree sections={sections} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText(/aucun document/i)).toBeInTheDocument();
  });

  it('affiche un cadenas si locked', () => {
    const locked = {
      ...sections,
      Role: [{ ...sections.Role[0], locked: true }],
    };
    render(<DocumentTree sections={locked} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByLabelText(/verrouillé/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implémenter**

```tsx
// DocumentTree.tsx
'use client';
import type { RoleDocumentSummary } from '@/lib/types';

interface Props {
  sections: Record<string, RoleDocumentSummary[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function DocumentTree({ sections, selectedId, onSelect }: Props) {
  const sectionNames = Object.keys(sections);
  return (
    <nav className="document-tree">
      {sectionNames.map(name => (
        <section key={name}>
          <h3>{name}</h3>
          {sections[name].length === 0 ? (
            <p className="empty">Aucun document</p>
          ) : (
            <ul>
              {sections[name].map(doc => (
                <li key={doc.id}>
                  <button
                    className={selectedId === doc.id ? 'selected' : ''}
                    onClick={() => onSelect(doc.id)}
                  >
                    {doc.name} <span className="version">v{doc.version}</span>
                    {doc.locked && <span aria-label="verrouillé"> 🔒</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: Réécrire `RoleDocumentEditor` pour utiliser le tree + un placeholder de détail**

```tsx
// RoleDocumentEditor.tsx
'use client';
import { useState } from 'react';
import type { RoleDocumentSummary } from '@/lib/types';
import { DocumentTree } from './DocumentTree';
import { DocumentDetail } from './DocumentDetail';

interface Props {
  projectId: string;
  sections: Record<string, RoleDocumentSummary[]>;
  onChange: () => void;
}

export function RoleDocumentEditor({ projectId, sections, onChange }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <div className="role-document-editor">
      <DocumentTree sections={sections} selectedId={selectedId} onSelect={setSelectedId} />
      <main className="detail">
        {selectedId ? (
          <DocumentDetail
            docId={selectedId}
            projectId={projectId}
            onChange={onChange}
          />
        ) : (
          <p className="empty">Sélectionnez un document</p>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Stub minimal de `DocumentDetail` (sera enrichi en D2.2)**

```tsx
// DocumentDetail.tsx (stub temporaire)
'use client';
import useSWR from 'swr';
import { getDocument } from '@/lib/api/role-documents';

export function DocumentDetail({
  docId, projectId, onChange,
}: { docId: string; projectId: string; onChange: () => void }) {
  const { data, isLoading } = useSWR(`doc-${docId}`, () => getDocument(docId));
  if (isLoading || !data) return <p>Chargement…</p>;
  return (
    <article>
      <h2>{data.name}</h2>
      <pre>{data.content}</pre>
    </article>
  );
}
```

- [ ] **Step 6: Run typecheck + tests, vérifier PASS**

- [ ] **Step 7: Commit**

```bash
git commit -am "feat(frontend): DocumentTree + RoleDocumentEditor squelette (sélection doc)"
```

---

### D2.2 — `DocumentDetail` + `VersionList`

**Files:**
- Replace: `DocumentDetail.tsx` (version complète)
- Create: `VersionList.tsx` + test

- [ ] **Step 1: Test rouge — VersionList affiche versions et appelle onPromote**

```tsx
// VersionList.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VersionList } from './VersionList';

const versions = [
  { id: 'v3', version: 3, is_current: true, created_at: '2026-04-28T12:00:00Z' },
  { id: 'v2', version: 2, is_current: false, created_at: '2026-04-27T12:00:00Z' },
  { id: 'v1', version: 1, is_current: false, created_at: '2026-04-26T12:00:00Z' },
];

describe('VersionList', () => {
  it('affiche les versions, marque la current, propose Promouvoir sur les autres', () => {
    const onPromote = vi.fn();
    render(<VersionList versions={versions as any} onPromote={onPromote} />);
    expect(screen.getByText(/v3.*current/i)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /promouvoir/i })[0]);
    expect(onPromote).toHaveBeenCalledWith('v2');
  });
});
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implémenter `VersionList`**

```tsx
// VersionList.tsx
'use client';
import type { RoleDocument } from '@/lib/types';

interface Props {
  versions: RoleDocument[];
  onPromote: (id: string) => void;
  onShowDiff?: (id: string) => void;
}

export function VersionList({ versions, onPromote, onShowDiff }: Props) {
  return (
    <aside className="version-list">
      <h4>Versions</h4>
      <ul>
        {versions.map(v => (
          <li key={v.id} className={v.is_current ? 'current' : ''}>
            v{v.version} — {new Date(v.created_at).toLocaleString('fr-FR')}
            {v.is_current && <span className="badge">current</span>}
            {!v.is_current && (
              <>
                <button onClick={() => onPromote(v.id)}>Promouvoir</button>
                {onShowDiff && (
                  <button onClick={() => onShowDiff(v.id)}>Comparer</button>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
```

- [ ] **Step 4: Enrichir `DocumentDetail` avec versions + sélection diff**

```tsx
// DocumentDetail.tsx (version complète)
'use client';
import { useState } from 'react';
import useSWR from 'swr';
import {
  getDocument, listVersions, setCurrent,
} from '@/lib/api/role-documents';
import { DocumentEditor } from './DocumentEditor';
import { VersionList } from './VersionList';
import { DocumentActions } from './DocumentActions';
import { VersionDiff } from './VersionDiff';

interface Props {
  docId: string;
  projectId: string;
  onChange: () => void;
}

export function DocumentDetail({ docId, projectId, onChange }: Props) {
  const doc = useSWR(`doc-${docId}`, () => getDocument(docId));
  const versions = useSWR(`doc-${docId}-versions`, () => listVersions(docId));
  const [diffWith, setDiffWith] = useState<string | null>(null);

  if (doc.isLoading || versions.isLoading || !doc.data || !versions.data) {
    return <p>Chargement…</p>;
  }

  async function promote(versionId: string) {
    await setCurrent(versionId);
    await doc.mutate();
    await versions.mutate();
    onChange();
  }

  return (
    <article className="document-detail">
      <header>
        <h2>{doc.data.name}</h2>
        <small>{doc.data.section} · v{doc.data.version}</small>
        <DocumentActions
          doc={doc.data}
          onLockChange={() => doc.mutate()}
          onRegenerated={() => { doc.mutate(); versions.mutate(); onChange(); }}
        />
      </header>
      <DocumentEditor
        doc={doc.data}
        onSaved={() => { doc.mutate(); versions.mutate(); onChange(); }}
      />
      <VersionList
        versions={versions.data}
        onPromote={promote}
        onShowDiff={setDiffWith}
      />
      {diffWith && (
        <VersionDiff
          currentContent={doc.data.content}
          otherDocId={diffWith}
          onClose={() => setDiffWith(null)}
        />
      )}
    </article>
  );
}
```

- [ ] **Step 5: Run typecheck (les composants D2.3-D2.5 ne sont pas encore là — créer les stubs maintenant)**

```tsx
// DocumentEditor.tsx (stub D2.3)
export function DocumentEditor(_p: any) { return <div>(éditeur)</div>; }
// DocumentActions.tsx (stub D2.4)
export function DocumentActions(_p: any) { return <div>(actions)</div>; }
// VersionDiff.tsx (stub D2.5)
export function VersionDiff(_p: any) { return <div>(diff)</div>; }
```

- [ ] **Step 6: Run tests**

- [ ] **Step 7: Commit**

```bash
git commit -am "feat(frontend): DocumentDetail + VersionList (promote + show diff) + stubs D2.3-2.5"
```

---

### D2.3 — `DocumentEditor` (édition manuelle markdown)

**Files:**
- Replace: `DocumentEditor.tsx`
- Create: `DocumentEditor.test.tsx`

- [ ] **Step 1: Test rouge — édition + save appelle updateContent + onSaved**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentEditor } from './DocumentEditor';
import * as api from '@/lib/api/role-documents';

const doc = {
  id: 'd1', role_project_id: 'p1', section: 'Role', name: 'x',
  content: 'origine', version: 1, is_current: true, locked: false,
  source_run_id: null, created_at: 'x', updated_at: 'y',
};

describe('DocumentEditor', () => {
  it('édite + save appelle updateContent', async () => {
    const updateSpy = vi.spyOn(api, 'updateContent').mockResolvedValue(doc as any);
    const onSaved = vi.fn();

    render(<DocumentEditor doc={doc as any} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: /éditer/i }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'modifié' } });
    fireEvent.click(screen.getByRole('button', { name: /enregistrer/i }));

    await waitFor(() => expect(updateSpy).toHaveBeenCalledWith('d1', 'modifié'));
    expect(onSaved).toHaveBeenCalled();
  });

  it('désactive l\'édition si locked', () => {
    render(<DocumentEditor doc={{ ...doc, locked: true } as any} onSaved={() => {}} />);
    expect(screen.getByRole('button', { name: /éditer/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Implémenter**

```tsx
// DocumentEditor.tsx
'use client';
import { useState } from 'react';
import { updateContent } from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

interface Props {
  doc: RoleDocument;
  onSaved: () => void;
}

export function DocumentEditor({ doc, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(doc.content);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await updateContent(doc.id, draft);
      setEditing(false);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <section className="editor read">
        <pre>{doc.content}</pre>
        <button onClick={() => { setDraft(doc.content); setEditing(true); }}
                disabled={doc.locked}>
          Éditer
        </button>
      </section>
    );
  }
  return (
    <section className="editor edit">
      <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={20} />
      <div className="actions">
        <button onClick={() => setEditing(false)}>Annuler</button>
        <button onClick={save} disabled={saving || draft === doc.content}>
          {saving ? 'Enregistrement…' : 'Enregistrer'}
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Run tests, PASS**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(frontend): DocumentEditor (édition manuelle markdown, désactivé si locked)"
```

---

### D2.4 — `DocumentActions` (lock/unlock + regenerate)

**Files:**
- Replace: `DocumentActions.tsx`
- Create: `DocumentActions.test.tsx`

- [ ] **Step 1: Test rouge — lock/unlock toggle + regenerate déclenche le run**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentActions } from './DocumentActions';
import * as api from '@/lib/api/role-documents';

const doc = {
  id: 'd1', section: 'Role', name: 'x', version: 1, is_current: true, locked: false,
} as any;

describe('DocumentActions', () => {
  it('lock toggle appelle lockDocument', async () => {
    const spy = vi.spyOn(api, 'lockDocument').mockResolvedValue();
    const onLockChange = vi.fn();
    render(<DocumentActions doc={doc} onLockChange={onLockChange} onRegenerated={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /verrouiller/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('d1'));
    expect(onLockChange).toHaveBeenCalled();
  });

  it('regenerate appelle regenerate', async () => {
    const spy = vi.spyOn(api, 'regenerate').mockResolvedValue({ run_id: 'r1' });
    const onRegen = vi.fn();
    render(<DocumentActions doc={doc} onLockChange={() => {}} onRegenerated={onRegen} />);
    fireEvent.click(screen.getByRole('button', { name: /régénérer/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('d1', undefined));
  });
});
```

- [ ] **Step 2: Implémenter**

```tsx
// DocumentActions.tsx
'use client';
import { useState } from 'react';
import { lockDocument, unlockDocument, regenerate } from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

interface Props {
  doc: RoleDocument;
  onLockChange: () => void;
  onRegenerated: () => void;
}

export function DocumentActions({ doc, onLockChange, onRegenerated }: Props) {
  const [busy, setBusy] = useState(false);

  async function toggleLock() {
    setBusy(true);
    try {
      if (doc.locked) {
        await unlockDocument(doc.id);
      } else {
        await lockDocument(doc.id);
      }
      onLockChange();
    } finally {
      setBusy(false);
    }
  }

  async function triggerRegen() {
    setBusy(true);
    try {
      await regenerate(doc.id);
      onRegenerated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="actions">
      <button onClick={toggleLock} disabled={busy}>
        {doc.locked ? 'Déverrouiller' : 'Verrouiller'}
      </button>
      <button onClick={triggerRegen} disabled={busy || doc.locked}>
        Régénérer
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Tests PASS**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(frontend): DocumentActions (lock/unlock + regenerate, regen désactivé si locked)"
```

---

### D2.5 — `VersionDiff` side-by-side

**Files:**
- Modify: `frontend/package.json` (ajouter `react-diff-viewer-continued`)
- Replace: `VersionDiff.tsx`
- Create: `VersionDiff.test.tsx`

- [ ] **Step 1: Installer la dépendance**

Run: `cd frontend && npm install react-diff-viewer-continued`

- [ ] **Step 2: Test rouge — affiche le diff entre current et version sélectionnée**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { VersionDiff } from './VersionDiff';
import * as api from '@/lib/api/role-documents';

vi.mock('react-diff-viewer-continued', () => ({
  default: ({ oldValue, newValue }: any) => (
    <div data-testid="diff">{oldValue}|{newValue}</div>
  ),
}));

describe('VersionDiff', () => {
  it('charge le contenu de l\'autre version et affiche le diff', async () => {
    vi.spyOn(api, 'getDocument').mockResolvedValue({ content: 'ancien' } as any);
    render(
      <VersionDiff currentContent="actuel" otherDocId="d2" onClose={() => {}} />,
    );
    await waitFor(() => expect(screen.getByTestId('diff')).toHaveTextContent('ancien|actuel'));
  });
});
```

- [ ] **Step 3: Implémenter**

```tsx
// VersionDiff.tsx
'use client';
import useSWR from 'swr';
import ReactDiffViewer from 'react-diff-viewer-continued';
import { getDocument } from '@/lib/api/role-documents';

interface Props {
  currentContent: string;
  otherDocId: string;
  onClose: () => void;
}

export function VersionDiff({ currentContent, otherDocId, onClose }: Props) {
  const other = useSWR(`doc-${otherDocId}`, () => getDocument(otherDocId));
  if (other.isLoading || !other.data) {
    return <div className="dialog">Chargement…</div>;
  }
  return (
    <div className="dialog diff">
      <header>
        <h3>Diff vs v{other.data.version}</h3>
        <button onClick={onClose}>Fermer</button>
      </header>
      <ReactDiffViewer
        oldValue={other.data.content}
        newValue={currentContent}
        splitView={true}
        leftTitle={`v${other.data.version}`}
        rightTitle="version actuelle"
      />
    </div>
  );
}
```

- [ ] **Step 4: Run typecheck + tests + build**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
        frontend/src/app/projects/\[id\]/role/VersionDiff.tsx \
        frontend/src/app/projects/\[id\]/role/VersionDiff.test.tsx
git commit -m "feat(frontend): VersionDiff side-by-side (react-diff-viewer-continued)"
```

---

## Phase E — Closure du Sprint 7

### E.1 — Update `12-open-decisions.md`

- [ ] **Step 1: Ajouter une entrée Sprint 7 dans `docs/specs/12-open-decisions.md`**

```markdown
## Sprint 7 — Décisions actées

### Push to ag.flow
- **HTTP sync + WS pour progression** : l'endpoint `POST /push-to-agflow` reste synchrone et renvoie le résultat final. Le canal WS `agflow_push_events` sert à afficher les étapes intermédiaires (zip_built, role_ready, zip_uploaded, prompts_generated) sans bloquer l'UI.
- **Échec partiel `prompts_generated`** = banner ROUGE (action requise) avec retry sur `/generate-prompts-on-agflow`.
- **409 sur display_name** = bloquant, message UI "Renommez votre projet d'abord". Pas de rename inline.
- **Convention canal WS push** : payload `{tenant_id, project_id, step, status, detail?}`. `step ∈ {zip_built, role_ready, zip_uploaded, prompts_generated, done, failed}`.

### Reportés Phase 2
- **Suppression du rôle ag.flow** : pas dans le scope MVP, l'utilisateur supprime via l'admin ag.flow.
- **Endpoint multipart streamé** pour ZIP > 10 MB : pas nécessaire pour les rôles typiques (~100-200 KB).
```

- [ ] **Step 2: Commit**

```bash
git commit -am "docs(specs): décisions Sprint 7 actées (push sync+WS, banner rouge, 409 bloquant)"
```

### E.2 — Tag `v0.7.0-sprint-7`

- [ ] **Step 1: Tag annoté**

```bash
git tag -a v0.7.0-sprint-7 -m "Sprint 7 — Export ag.flow

- Backend Phase A+B : services/agflow/{exporter, role_json_builder, api_client, push} + routes agflow_export
- Backend Phase D0 : routes role_documents (CRUD lock/unlock) + ws_relay agflow_push_events
- Frontend Phase D1 : page Rôle + flux Push (PushToAgflowButton, PushPreview, PushProgressDialog WS, PostPushBanner rouge sur échec partiel)
- Frontend Phase D2 : RoleDocumentEditor (DocumentTree + DocumentDetail + DocumentEditor + DocumentActions + VersionList + VersionDiff)
- Décisions actées : push sync HTTP + WS pour progression, 409 bloquant (rename d'abord), banner échec partiel rouge avec retry."
```

- [ ] **Step 2: Vérifier**

Run: `git tag -n10 v0.7.0-sprint-7`
Expected: tag présent avec le message complet.

---

## Self-Review

### Spec coverage
- ✅ Endpoint `/push-to-agflow` (déjà livré Phase B) : consommé par D1.4
- ✅ Endpoint `/preview-zip` (déjà livré Phase B) : consommé par D1.2 via SWR
- ✅ Endpoint `/generate-prompts-on-agflow` (déjà livré Phase B) : consommé par D1.5 (retry)
- ✅ Endpoint `/download-zip` (déjà livré Phase B) : exposé en `downloadZipUrl` (D1.1.2)
- ✅ Validations avant push : déjà côté backend, l'UI consomme `missing[]`
- ✅ UI : intégration page rôle (D1.2), 4 composants push (D1.3-1.5)
- ✅ Affichage `target_role_id` : dans `PushPreview` (D1.3) + `PostPushBanner` (D1.5)
- ✅ Republication (label "Mettre à jour" si `target_role_id` non null) : D1.4
- ✅ Conflit display_name 409 : D1.4 modale d'erreur dédiée
- ✅ RoleDocumentEditor (spec 10) : D2 complet

### Placeholder scan
- Aucun TBD/TODO dans les steps.
- Tous les chemins de fichiers sont absolus relatifs au repo.
- Tous les tests ont du code complet, pas de "Write tests for X" sans code.
- Une seule zone légèrement abstraite : D1.5 step 4 (le câblage de la state machine `partial` dans `PushToAgflowButton`) — détail à finaliser à l'implémentation, mais l'essentiel est là.

### Type consistency
- `PushStep` défini dans `types.ts` (D1.1) et utilisé dans `PushProgressDialog.tsx` (D1.4) — cohérent.
- `RoleDocument`/`RoleDocumentSummary` : Summary sans `content`, Document avec — utilisés cohéremment (D1.1, D2.1, D2.2).
- `pushToAgflow` signature `(projectId, body)` cohérente entre client API (D1.1.2) et appelant (D1.4).
- `WSChannel` étendu avec `agflow_push_events` cohérent avec `_CHANNELS` backend (D0.2.1).

---

**Plan complet et sauvegardé dans `docs/superpowers/plans/2026-04-28-sprint-07-phase-d-role-frontend.md`.**

**Phases proposées (~14 commits) :**
- D0 backend (2 commits) : helper update_content + routes role_documents, puis ws_relay + push.py NOTIFY
- D1 frontend push (5 commits) : types/clients, page rôle, PushPreview, PushToAgflowButton+ProgressDialog, PostPushBanner
- D2 frontend editor (5 commits) : Tree+Editor squelette, Detail+VersionList, DocumentEditor, DocumentActions, VersionDiff
- E (2 commits) : open-decisions + tag

Total estimé : 14 commits, ~3 jours de travail TDD soutenu.
