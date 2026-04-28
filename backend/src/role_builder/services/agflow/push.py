"""Orchestration du push d'un rôle vers ag.flow."""

from __future__ import annotations

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
    """Orchestration complète du push.

    1. Fetch project + docs grouped
    2. Validate (raise RuntimeError if missing pieces)
    3. Build ZIP
    4. Create role in ag.flow if target_role_id is null
    5. Upload ZIP via /import
    6. Optionally /generate-prompts
    7. Return summary dict.

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

    build: BuildResult = build_role_zip(project, docs_by_section)
    log.info(
        "agflow.push.zip_built",
        project_id=str(project_id),
        zip_size=len(build.zip_bytes),
        documents_count=build.documents_count,
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
            project_id=str(project_id),
            target_role_id=target_role_id,
        )

    import_result = await api.import_role_zip(target_role_id, build.zip_bytes)
    log.info(
        "agflow.push.zip_uploaded",
        project_id=str(project_id),
        target_role_id=target_role_id,
    )

    prompt_generated = False
    if generate_prompts:
        await api.generate_prompts(target_role_id)
        prompt_generated = True
        log.info(
            "agflow.push.prompts_generated",
            project_id=str(project_id),
            target_role_id=target_role_id,
        )

    return {
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
