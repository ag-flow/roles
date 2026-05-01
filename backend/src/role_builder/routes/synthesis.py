"""Endpoints REST pour le pipeline de synthèse.

Routes :
- POST /api/role-projects/{project_id}/runs/extract
- POST /api/role-projects/{project_id}/runs/cluster
- POST /api/role-projects/{project_id}/runs/decompose
- POST /api/role-projects/{project_id}/runs/write-documents
- POST /api/role-projects/{project_id}/runs/synthesize-identity
- POST /api/role-documents/{doc_id}/regenerate
- POST /api/role-documents/{doc_id}/set-current
- GET  /api/role-projects/{project_id}/runs
- GET  /api/runs/{run_id}

Tous protégés par ``Depends(get_current_user)``.
Les triggers await directement la fonction synthesis (MVP mono-user).
Le frontend pollera /runs/{id} ou écoutera WebSocket pour les updates de statut.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import document_plans, role_documents, runs
from role_builder.schemas.runs import RunOut
from role_builder.schemas.synthesis import (
    FullPipelineResponse,
    RegenerateDocumentRequest,
    TriggerClusterRequest,
    TriggerDecomposeRequest,
    TriggerExtractRequest,
    TriggerFullPipelineRequest,
    TriggerIdentityRequest,
    TriggerOutMultipleRuns,
    TriggerOutSingleRun,
    TriggerWriteDocumentsRequest,
)
from role_builder.synthesis import (
    clusterer,
    decomposer,
    document_writer,
    extractor,
    identity_synthesizer,
)

log = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/role-projects/{project_id}/runs/extract",
    status_code=202,
    response_model=TriggerOutSingleRun,
)
async def trigger_extraction(
    project_id: UUID,
    request: TriggerExtractRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TriggerOutSingleRun:
    """Lance l'étage 1 (extraction de signaux) pour le projet."""
    pool = db_pool.pool
    run_id = await extractor.run_extraction(
        project_id,
        prompt_version_id=request.prompt_version_id,
        instruction_override=request.instruction_override,
        chunks_per_batch=request.chunks_per_batch,
        parallelism=request.parallelism,
        pool=pool,
    )
    log.info("api.synthesis.extract_triggered", project_id=str(project_id), run_id=str(run_id))
    return TriggerOutSingleRun(run_id=run_id)


@router.post(
    "/role-projects/{project_id}/runs/cluster",
    status_code=202,
    response_model=TriggerOutSingleRun,
)
async def trigger_clustering(
    project_id: UUID,
    request: TriggerClusterRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TriggerOutSingleRun:
    """Lance l'étage 2 (clustering thématique) pour le projet."""
    pool = db_pool.pool
    run_id = await clusterer.run_clustering(
        project_id,
        signal_run_id=request.signal_run_id,
        prompt_version_id=request.prompt_version_id,
        instruction_override=request.instruction_override,
        pool=pool,
    )
    log.info("api.synthesis.cluster_triggered", project_id=str(project_id), run_id=str(run_id))
    return TriggerOutSingleRun(run_id=run_id)


@router.post(
    "/role-projects/{project_id}/runs/decompose",
    status_code=202,
    response_model=TriggerOutSingleRun,
)
async def trigger_decomposition(
    project_id: UUID,
    request: TriggerDecomposeRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TriggerOutSingleRun:
    """Lance l'étage 3 (décomposition en plan de documents) pour le projet."""
    pool = db_pool.pool
    run_id = await decomposer.run_decomposition(
        project_id,
        cluster_run_id=request.cluster_run_id,
        prompt_version_id=request.prompt_version_id,
        instruction_override=request.instruction_override,
        pool=pool,
    )
    log.info("api.synthesis.decompose_triggered", project_id=str(project_id), run_id=str(run_id))
    return TriggerOutSingleRun(run_id=run_id)


@router.post(
    "/role-projects/{project_id}/runs/write-documents",
    status_code=202,
    response_model=TriggerOutMultipleRuns,
)
async def trigger_document_writing(
    project_id: UUID,
    request: TriggerWriteDocumentsRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TriggerOutMultipleRuns:
    """Lance l'étage 4 (rédaction de tous les documents d'un plan) pour le projet."""
    pool = db_pool.pool
    run_ids = await document_writer.write_all_documents_for_plan(
        project_id,
        request.plan_id,
        parallelism=request.parallelism,
        pool=pool,
    )
    log.info(
        "api.synthesis.write_documents_triggered",
        project_id=str(project_id),
        plan_id=str(request.plan_id),
        runs_count=len(run_ids),
    )
    return TriggerOutMultipleRuns(run_ids=run_ids)


@router.post(
    "/role-projects/{project_id}/runs/synthesize-identity",
    status_code=202,
    response_model=TriggerOutSingleRun,
)
async def trigger_identity_synthesis(
    project_id: UUID,
    request: TriggerIdentityRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TriggerOutSingleRun:
    """Lance l'étage 5 (synthèse d'identité) pour le projet."""
    pool = db_pool.pool
    run_id = await identity_synthesizer.synthesize_identity(
        project_id,
        prompt_version_id=request.prompt_version_id,
        instruction_override=request.instruction_override,
        pool=pool,
    )
    log.info("api.synthesis.identity_triggered", project_id=str(project_id), run_id=str(run_id))
    return TriggerOutSingleRun(run_id=run_id)


@router.post(
    "/role-projects/{project_id}/runs/full-pipeline",
    status_code=202,
    response_model=FullPipelineResponse,
)
async def trigger_full_pipeline(
    project_id: UUID,
    request: TriggerFullPipelineRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> FullPipelineResponse:
    """Enchaîne les 5 étages de synthèse en un seul appel.

    Ordre d'exécution séquentiel :
    1. Extract (signaux) → ``extract_run_id``
    2. Cluster (groupes thématiques) → ``cluster_run_id``
    3. Decompose (plans de documents par section) → ``decompose_run_id``
    4. Pour chaque plan créé par 3 : write_all_documents_for_plan en
       parallèle (limite ``parallelism``) → ``document_run_ids``
    5. Si ``include_identity=True`` : synthesize_identity →
       ``identity_run_id`` (sinon ``None``)

    L'endpoint est synchrone bloquant — pour un corpus typique (~30
    chunks), le pipeline complet prend 2-5 min selon la latence Mistral.
    Pour gros corpus (> 100 chunks), préférer les endpoints individuels
    et un orchestrateur côté frontend pour pouvoir interrompre.
    """
    pool = db_pool.pool

    extract_run_id = await extractor.run_extraction(
        project_id,
        instruction_override=request.extract_instruction_override,
        chunks_per_batch=request.chunks_per_batch,
        parallelism=request.parallelism,
        pool=pool,
    )
    log.info(
        "api.full_pipeline.extract_done",
        project_id=str(project_id),
        run_id=str(extract_run_id),
    )

    cluster_run_id = await clusterer.run_clustering(
        project_id,
        signal_run_id=extract_run_id,
        instruction_override=request.cluster_instruction_override,
        pool=pool,
    )
    log.info(
        "api.full_pipeline.cluster_done",
        project_id=str(project_id),
        run_id=str(cluster_run_id),
    )

    decompose_run_id = await decomposer.run_decomposition(
        project_id,
        cluster_run_id=cluster_run_id,
        instruction_override=request.decompose_instruction_override,
        pool=pool,
    )
    log.info(
        "api.full_pipeline.decompose_done",
        project_id=str(project_id),
        run_id=str(decompose_run_id),
    )

    plans = await document_plans.list_plans_by_run(decompose_run_id, pool=pool)
    document_run_ids: list[UUID] = []
    for plan in plans:
        run_ids = await document_writer.write_all_documents_for_plan(
            project_id,
            plan["id"],
            parallelism=request.parallelism,
            pool=pool,
        )
        document_run_ids.extend(run_ids)
    log.info(
        "api.full_pipeline.documents_done",
        project_id=str(project_id),
        plans_count=len(plans),
        runs_count=len(document_run_ids),
    )

    identity_run_id: UUID | None = None
    if request.include_identity:
        identity_run_id = await identity_synthesizer.synthesize_identity(
            project_id,
            instruction_override=request.identity_instruction_override,
            pool=pool,
        )
        log.info(
            "api.full_pipeline.identity_done",
            project_id=str(project_id),
            run_id=str(identity_run_id),
        )

    return FullPipelineResponse(
        extract_run_id=extract_run_id,
        cluster_run_id=cluster_run_id,
        decompose_run_id=decompose_run_id,
        document_run_ids=document_run_ids,
        identity_run_id=identity_run_id,
    )


@router.post(
    "/role-documents/{doc_id}/regenerate",
    status_code=202,
    response_model=TriggerOutSingleRun,
)
async def regenerate_document(
    doc_id: UUID,
    request: RegenerateDocumentRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TriggerOutSingleRun:
    """Régénère un document existant (nouvelle version, is_current=False).

    Retrouve le doc en base, construit un doc_plan minimal (name + brief générique),
    puis appelle write_document avec l'instruction_override fourni.
    """
    pool = db_pool.pool
    doc = await role_documents.get_by_id(doc_id, pool=pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")

    doc_plan = {
        "name": doc["name"],
        "brief": f"Régénération du document '{doc['name']}' (section {doc['section']}).",
        "supporting_signals": [],
    }
    run_id = await document_writer.write_document(
        doc["role_project_id"],
        doc["section"],
        doc_plan,
        instruction_override=request.instruction_override,
        pool=pool,
    )
    log.info("api.synthesis.regenerate_triggered", doc_id=str(doc_id), run_id=str(run_id))
    return TriggerOutSingleRun(run_id=run_id)


@router.post("/role-documents/{doc_id}/set-current")
async def set_current_version(
    doc_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    """Promeut un document comme version courante (is_current=True)."""
    pool = db_pool.pool
    try:
        await role_documents.set_current(doc_id, pool=pool)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log.info("api.synthesis.set_current", doc_id=str(doc_id))
    return {"status": "ok"}


@router.get(
    "/role-projects/{project_id}/runs",
    response_model=list[RunOut],
)
async def list_runs_endpoint(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RunOut]:
    """Retourne les runs d'un projet, triés par created_at DESC."""
    pool = db_pool.pool
    rows = await runs.list_runs(project_id, status=status, limit=limit, pool=pool)
    return [RunOut(**r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run_endpoint(
    run_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RunOut:
    """Retourne un run par son id."""
    pool = db_pool.pool
    row = await runs.get_run(run_id, pool=pool)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return RunOut(**row)
