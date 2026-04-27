"""Étage 2 du pipeline de synthèse : clustering thématique des signaux.

Le pipeline lit tous les signaux d'un projet (ou d'un run spécifique),
les envoie en une seule passe au LLM (clusterer prompt), et stocke les
clusters thématiques résultants dans la table clusters.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import asyncpg
import structlog
from pydantic import BaseModel

from role_builder.config import settings
from role_builder.db_helpers import clusters as clusters_helper
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.db_helpers import role_projects, runs
from role_builder.db_helpers import signals as signals_helper
from role_builder.services.agflow_client import get_agflow_client

log = structlog.get_logger(__name__)

_PROMPT_NAME = "clusterer"
_TEMPLATE_PATH = Path(__file__).parent / "templates" / "clusterer_v1.md"


class _Cluster(BaseModel):
    name: str
    description: str | None = None
    signal_ids: list[UUID]  # Pydantic v2 coerce str→UUID automatiquement


class _ClustererResponse(BaseModel):
    clusters: list[_Cluster]


async def run_clustering(
    role_project_id: UUID,
    *,
    signal_run_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """Signaux → clusters thématiques.

    Steps :
      1. Resolve prompt_version (system_default "clusterer" si None, get_version_by_id sinon).
         Si non trouvé → RuntimeError.
      2. Get role_project via role_projects.get_by_id pour global_directives. Si None → RuntimeError.
      3. Get signaux :
         - Si signal_run_id fourni : signals.list_signals_by_run(signal_run_id)
         - Sinon : signals.list_signals_by_project(role_project_id)
         Si liste vide → RuntimeError "no signals to cluster".
      4. Create run (status='pending'), mark_running.
      5. Format prompt.
      6. Construire messages + instruction_override optionnel.
      7. invoke_chat → ChatResult.
      8. Parse via _ClustererResponse.model_validate_json(content).
      9. Pour chaque cluster : insert_cluster.
     10. Cost calc.
     11. mark_done.
     12. Si exception : log.exception + delete_clusters_by_run + mark_failed + raise.

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

    # 3. Get signaux
    if signal_run_id is not None:
        all_signals = await signals_helper.list_signals_by_run(signal_run_id, pool=pool)
    else:
        all_signals = await signals_helper.list_signals_by_project(role_project_id, pool=pool)

    if not all_signals:
        raise RuntimeError("no signals to cluster")

    # 4. Create run
    run_id = await runs.create_run(
        role_project_id=role_project_id,
        tenant_id=tenant_id,
        prompt_version_id=resolved_prompt_version_id,
        input_summary={"signals_count": len(all_signals)},
        parameters={"signal_run_id": str(signal_run_id) if signal_run_id else None},
        instruction_override=instruction_override,
        pool=pool,
    )
    await runs.mark_running(run_id, pool=pool)

    log.info(
        "synthesis.clusterer.run_started",
        run_id=str(run_id),
        role_project_id=str(role_project_id),
        signals_count=len(all_signals),
    )

    try:
        # 5. Format prompt
        signals_payload = [
            {"id": str(s["id"]), "type": s["type"], "content": s["content"]} for s in all_signals
        ]
        signals_text = json.dumps(signals_payload, ensure_ascii=False)

        prompt_text = template.format(
            global_directives=global_directives,
            signals=signals_text,
        )

        # 6. Construire messages
        messages: list[dict] = [{"role": "system", "content": prompt_text}]
        if instruction_override:
            messages.append({"role": "user", "content": instruction_override})

        # 7. invoke_chat
        agflow_client = get_agflow_client()
        result = await agflow_client.invoke_chat(messages, response_format={"type": "json_object"})
        llm_model = result.model
        tokens_input = result.tokens_input
        tokens_output = result.tokens_output

        # 8. Parse réponse
        parsed = _ClustererResponse.model_validate_json(result.content)

        # 9. Insert clusters
        clusters_count = 0
        for cluster in parsed.clusters:
            await clusters_helper.insert_cluster(
                run_id=run_id,
                role_project_id=role_project_id,
                tenant_id=tenant_id,
                name=cluster.name,
                description=cluster.description,
                signal_ids=list(cluster.signal_ids),
                pool=pool,
            )
            clusters_count += 1

    except Exception as exc:
        log.exception("synthesis.clusterer.run_failed", run_id=str(run_id), error=str(exc))
        try:
            deleted = await clusters_helper.delete_clusters_by_run(run_id, pool=pool)
            if deleted:
                log.info(
                    "synthesis.clusterer.clusters_cleaned",
                    run_id=str(run_id),
                    deleted=deleted,
                )
        except Exception:
            log.exception("synthesis.clusterer.cleanup_failed", run_id=str(run_id))
        await runs.mark_failed(run_id, str(exc), pool=pool)
        raise

    # 10. Cost calculation
    cost_usd = (
        tokens_input * settings.mistral_input_token_rate_usd
        + tokens_output * settings.mistral_output_token_rate_usd
    )

    log.info(
        "synthesis.clusterer.run_completed",
        run_id=str(run_id),
        clusters_total=clusters_count,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )

    # 11. Mark done
    await runs.mark_done(
        run_id,
        output=json.dumps({"clusters_count": clusters_count}),
        llm_model=llm_model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        pool=pool,
    )

    return run_id
