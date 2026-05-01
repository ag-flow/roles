"""Étage 3 du pipeline de synthèse : décomposition en plan de documents.

Le pipeline lit les clusters d'un projet, les envoie au LLM (decomposer prompt),
et produit un plan de documents par section (Role / Missions / Skills).
"""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

import asyncpg
import structlog
from pydantic import BaseModel

from role_builder.config import settings
from role_builder.db_helpers import clusters as clusters_helper
from role_builder.db_helpers import document_plans as document_plans_helper
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.db_helpers import role_projects, runs
from role_builder.db_helpers import signals as signals_helper
from role_builder.services.agflow_client import get_agflow_client

log = structlog.get_logger(__name__)

_PROMPT_NAME = "decomposer"


# ---------------------------------------------------------------------------
# Schémas Pydantic internes
# ---------------------------------------------------------------------------


class _PlannedDoc(BaseModel):
    name: str
    brief: str
    supporting_signals: list[UUID]  # Pydantic v2 coerce str→UUID automatiquement


class _SectionPlan(BaseModel):
    documents: list[_PlannedDoc]


class _DecomposerResponse(BaseModel):
    sections: dict[Literal["Role", "Missions", "Skills"], _SectionPlan]


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------


async def run_decomposition(
    role_project_id: UUID,
    *,
    cluster_run_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """Clusters → plan de documents par section (Role/Missions/Skills).

    Steps :
      1. Resolve prompt_version (system_default "decomposer" si None).
      2. Get role_project. Si None → RuntimeError.
      3. Get clusters (par run ou par projet). Si vide → RuntimeError.
      4. Récupère les signaux référencés par les clusters.
      5. Create run, mark_running.
      6. Format prompt avec global_directives, clusters_text, signals_text.
      7. messages [system + optionnel user instruction_override].
      8. invoke_chat(response_format=json_object) → ChatResult.
      9. Parse via _DecomposerResponse.model_validate_json(content).
     10. Pour chaque section : insert_document_plan (3 inserts max).
     11. Cost calc + mark_done.
     12. Sur exception : log.exception + delete_plans_by_run + mark_failed + raise.

    Retourne run_id.
    """
    # 1. Resolve prompt version
    if prompt_version_id is None:
        version = await prompts_helper.get_system_default_version(_PROMPT_NAME, pool=pool)
    else:
        version = await prompts_helper.get_version_by_id(prompt_version_id, pool=pool)

    if version is None:
        raise RuntimeError(f"prompt version not found for '{_PROMPT_NAME}'")

    template: str = version["template"]
    resolved_prompt_version_id: UUID = version["id"]

    # 2. Get role_project
    project = await role_projects.get_by_id(role_project_id, pool=pool)
    if project is None:
        raise RuntimeError(f"role_project {role_project_id} not found")

    tenant_id: UUID = project["tenant_id"]
    global_directives: str = project.get("global_directives") or ""
    # Phase 2 sous-projet G : sections custom du projet à inclure dans le plan.
    custom_sections: list[str] = project.get("custom_sections") or []

    # 3. Get clusters
    if cluster_run_id is not None:
        all_clusters = await clusters_helper.list_clusters_by_run(cluster_run_id, pool=pool)
    else:
        all_clusters = await clusters_helper.list_clusters_by_project(role_project_id, pool=pool)

    if not all_clusters:
        raise RuntimeError("no clusters to decompose")

    # 4. Get signaux référencés
    signal_ids_set: set[str] = set()
    for c in all_clusters:
        for sid in c.get("signal_ids") or []:
            signal_ids_set.add(str(sid))
    signals_list = await signals_helper.get_signals_by_ids(
        [UUID(sid) for sid in signal_ids_set], pool=pool
    )

    # 5. Create run
    run_id = await runs.create_run(
        role_project_id=role_project_id,
        tenant_id=tenant_id,
        prompt_version_id=resolved_prompt_version_id,
        input_summary={
            "clusters_count": len(all_clusters),
            "signals_count": len(signals_list),
        },
        parameters={"cluster_run_id": str(cluster_run_id) if cluster_run_id else None},
        instruction_override=instruction_override,
        pool=pool,
    )
    await runs.mark_running(run_id, pool=pool)

    log.info(
        "synthesis.decomposer.run_started",
        run_id=str(run_id),
        role_project_id=str(role_project_id),
        clusters_count=len(all_clusters),
        signals_count=len(signals_list),
    )

    try:
        # 6. Format prompt
        clusters_payload = [
            {
                "id": str(c["id"]),
                "name": c["name"],
                "description": c.get("description"),
                "signal_ids": [str(sid) for sid in (c.get("signal_ids") or [])],
            }
            for c in all_clusters
        ]
        clusters_text = json.dumps(clusters_payload, ensure_ascii=False)

        signals_payload = [
            {
                "id": str(s["id"]),
                "type": s["type"],
                "content": s["content"],
            }
            for s in signals_list
        ]
        signals_text = json.dumps(signals_payload, ensure_ascii=False)

        prompt_text = template.format(
            global_directives=global_directives,
            clusters=clusters_text,
            signals=signals_text,
        )

        # Phase 2 sous-projet G : ajout des sections custom au prompt
        # via concat (post-traitement) pour rester rétro-compatible avec
        # les versions de template qui n'ont pas la variable.
        if custom_sections:
            prompt_text += (
                "\n\nSections supplémentaires à produire en plus des 3 "
                "obligatoires (Role / Missions / Skills). Pour chacune, "
                "renvoie une entrée dans `sections` avec le même schéma :\n"
                + "\n".join(f"- {name}" for name in custom_sections)
            )

        # 7. Construire messages
        messages: list[dict] = [{"role": "system", "content": prompt_text}]
        if instruction_override:
            messages.append({"role": "user", "content": instruction_override})

        # 8. invoke_chat
        agflow_client = get_agflow_client()
        result = await agflow_client.invoke_chat(messages, response_format={"type": "json_object"})
        llm_model = result.model
        tokens_input = result.tokens_input
        tokens_output = result.tokens_output

        # 9. Parse réponse
        parsed = _DecomposerResponse.model_validate_json(result.content)

        # 10. Insert plans (un par section, 3 max)
        plans_count = 0
        sections_written: list[str] = []
        for section_name, section_plan in parsed.sections.items():
            await document_plans_helper.insert_document_plan(
                run_id=run_id,
                role_project_id=role_project_id,
                tenant_id=tenant_id,
                section=section_name,
                planned_documents=[doc.model_dump(mode="json") for doc in section_plan.documents],
                pool=pool,
            )
            plans_count += 1
            sections_written.append(section_name)

    except Exception as exc:
        log.exception("synthesis.decomposer.run_failed", run_id=str(run_id), error=str(exc))
        try:
            deleted = await document_plans_helper.delete_plans_by_run(run_id, pool=pool)
            if deleted is not None:
                log.info(
                    "synthesis.decomposer.plans_cleaned",
                    run_id=str(run_id),
                    deleted=deleted,
                )
        except Exception:
            log.exception("synthesis.decomposer.cleanup_failed", run_id=str(run_id))
        await runs.mark_failed(run_id, str(exc), pool=pool)
        raise

    # 11. Cost calculation
    cost_usd = (
        tokens_input * settings.mistral_input_token_rate_usd
        + tokens_output * settings.mistral_output_token_rate_usd
    )

    total_docs = sum(len(section_plan.documents) for section_plan in parsed.sections.values())

    log.info(
        "synthesis.decomposer.run_completed",
        run_id=str(run_id),
        sections_count=plans_count,
        total_documents_planned=total_docs,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )

    # 12. Mark done
    await runs.mark_done(
        run_id,
        output=json.dumps({"plans_count": plans_count, "sections": sections_written}),
        llm_model=llm_model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        pool=pool,
    )

    return run_id
