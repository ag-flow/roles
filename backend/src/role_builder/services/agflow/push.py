"""Orchestration du push d'un rôle vers ag.flow.

Émet aussi des événements PG NOTIFY sur le canal ``agflow_push_events``
à chaque étape (zip_built / role_ready / zip_uploaded / prompts_generated /
done / failed) pour permettre à l'UI d'afficher la progression en live via
WebSocket. Les émissions sont best-effort : un échec d'émission ne casse
jamais le push.

Payload des événements ::

    {
        "tenant_id": "<uuid>",
        "project_id": "<uuid>",
        "step": "<step>",
        "status": "in_progress" | "done" | "failed",
        "detail": {...}  // optionnel
    }
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
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
    """Émet un NOTIFY sur ``agflow_push_events``.

    Best-effort : si l'émission échoue (pool saturé, connexion fermée, etc.),
    on log un warning mais on n'interrompt pas le push.
    """
    payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "step": step,
        "status": status,
    }
    if detail is not None:
        payload["detail"] = detail
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "SELECT pg_notify($1, $2)",
                WS_CHANNEL,
                json.dumps(payload),
            )
    except Exception as exc:  # noqa: BLE001 — best effort, never break the push
        log.warning("agflow.push.notify_failed", step=step, exc=str(exc))


def check_missing_pieces(
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Liste des éléments manquants pour un push valide."""
    missing: list[str] = []
    if not (project.get("identity") and str(project["identity"]).strip()):
        missing.append("Identity not generated")
    for required in LOCKED_SECTIONS_REQUIRED:
        docs = docs_by_section.get(required, [])
        if not docs:
            missing.append(f"Section '{required}' has no current documents")
    return missing


async def push_role_to_agflow(
    project_id: UUID,
    *,
    generate_prompts: bool = False,
    pool: asyncpg.Pool,
    client: AgflowAdminClient | None = None,
) -> dict[str, Any]:
    """Orchestration complète du push, avec émissions WS à chaque étape.

    1. Fetch project + docs grouped + validation (raise RuntimeError si manquant)
    2. Build ZIP → emit zip_built
    3. Create role si target_role_id null + update DB → emit role_ready
    4. Upload ZIP → emit zip_uploaded
    5. Optionally /generate-prompts → emit prompts_generated
    6. Emit done(status=done) avec le résultat complet
    7. Si exception après l'étape 1 : emit failed(status=failed) avec l'erreur,
       puis re-raise.

    Le ``client`` est injectable pour les tests ; sinon utilise le singleton.
    """
    project = await role_projects.get_by_id(project_id, pool=pool)
    if project is None:
        raise RuntimeError(f"role_project {project_id} not found")

    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id, pool=pool,
    )
    missing = check_missing_pieces(project, docs_by_section)
    if missing:
        raise RuntimeError(f"cannot push: missing pieces — {missing}")

    tenant_id = str(project["tenant_id"])
    pid = str(project_id)

    try:
        build: BuildResult = build_role_zip(project, docs_by_section)
        log.info(
            "agflow.push.zip_built",
            project_id=pid,
            zip_size=len(build.zip_bytes),
            documents_count=build.documents_count,
        )
        await _emit(
            pool,
            tenant_id=tenant_id,
            project_id=pid,
            step="zip_built",
            detail={
                "size_bytes": len(build.zip_bytes),
                "documents_count": build.documents_count,
            },
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
            log.info(
                "agflow.push.role_created",
                project_id=pid,
                target_role_id=target_role_id,
            )
        await _emit(
            pool,
            tenant_id=tenant_id,
            project_id=pid,
            step="role_ready",
            detail={"target_role_id": target_role_id},
        )

        import_result = await api.import_role_zip(target_role_id, build.zip_bytes)
        log.info(
            "agflow.push.zip_uploaded",
            project_id=pid,
            target_role_id=target_role_id,
        )
        await _emit(
            pool,
            tenant_id=tenant_id,
            project_id=pid,
            step="zip_uploaded",
        )

        prompt_generated = False
        if generate_prompts:
            await api.generate_prompts(target_role_id)
            prompt_generated = True
            log.info(
                "agflow.push.prompts_generated",
                project_id=pid,
                target_role_id=target_role_id,
            )
            await _emit(
                pool,
                tenant_id=tenant_id,
                project_id=pid,
                step="prompts_generated",
            )

        result = {
            "agflow_role_id": target_role_id,
            "zip_size_bytes": len(build.zip_bytes),
            "documents_count": (
                import_result.get("documents_count")
                if isinstance(import_result, dict)
                else None
            ) or build.documents_count,
            "prompt_generated": prompt_generated,
            "agflow_url": (
                f"{settings.agflow_base_url.rstrip('/')}/admin/roles/{target_role_id}"
            ),
        }
        await _emit(
            pool,
            tenant_id=tenant_id,
            project_id=pid,
            step="done",
            status="done",
            detail=result,
        )
        return result

    except Exception as exc:
        await _emit(
            pool,
            tenant_id=tenant_id,
            project_id=pid,
            step="failed",
            status="failed",
            detail={"error": str(exc)},
        )
        raise
