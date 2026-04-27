"""Étage 1 du pipeline de synthèse : extraction de signaux depuis le corpus.

Le pipeline lit tous les chunks indexés d'un projet, les envoie par batch
au LLM (extractor prompt), et stocke les signaux extraits dans la table signals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ValidationError

from role_builder.config import settings
from role_builder.db_helpers import corpus_chunks, role_projects, runs
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.db_helpers import signals as signals_helper
from role_builder.services.agflow_client import get_agflow_client

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "extractor_v1.md"

_PROMPT_NAME = "extractor"


class _ExtractorSignal(BaseModel):
    type: Literal["heuristique", "anecdote", "vocab", "cadre", "opinion"]
    content: dict
    source_chunks: list[str]  # UUIDs en str depuis le LLM


class _ExtractorResponse(BaseModel):
    signals: list[_ExtractorSignal]


def _format_chunks_for_prompt(chunks: list[dict]) -> str:
    """Format texte des chunks pour le prompt extractor."""
    parts: list[str] = []
    for c in chunks:
        parts.append(f"--- chunk_id: {c['id']} ---\n{c['text']}")
    return "\n\n".join(parts)


async def run_extraction(
    role_project_id: UUID,
    *,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    chunks_per_batch: int = 5,
    pool: asyncpg.Pool,
) -> UUID:
    """Extrait des signaux depuis tous les chunks indexés du projet.

    Étapes :
      1. Resolve prompt_version : si None, get_system_default_version("extractor"),
         sinon get_version_by_id(prompt_version_id). Si non trouvé → RuntimeError.
      2. Get role_project via role_projects.get_by_id. Si None → RuntimeError.
      3. List corpus_chunks.list_by_project(role_project_id, limit=10000). Si vide → RuntimeError.
      4. Create run (status='pending') puis mark_running.
      5. Pour chaque batch de chunks_per_batch chunks :
         a. Format prompt template.
         b. Construire messages.
         c. Appel LLM → ChatResult.
         d. Parse réponse JSON.
         e. Insert signals.
         f. Accumuler tokens.
      6. Calculer cost_usd.
      7. mark_done.
      8. Si exception : mark_failed + re-raise.

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

    # 3. List corpus chunks
    all_chunks = await corpus_chunks.list_by_project(role_project_id, limit=10000, pool=pool)
    if not all_chunks:
        raise RuntimeError("no corpus_chunks for this project")

    # 4. Create run
    run_id = await runs.create_run(
        role_project_id=role_project_id,
        tenant_id=tenant_id,
        prompt_version_id=resolved_prompt_version_id,
        input_summary={"chunks_count": len(all_chunks)},
        parameters={"chunks_per_batch": chunks_per_batch},
        instruction_override=instruction_override,
        pool=pool,
    )
    await runs.mark_running(run_id, pool=pool)

    # 5. Boucle par batch
    total_tokens_input = 0
    total_tokens_output = 0
    signals_count = 0
    last_model = settings.mistral_chat_model
    agflow_client = get_agflow_client()

    try:
        for batch_start in range(0, len(all_chunks), chunks_per_batch):
            batch = all_chunks[batch_start : batch_start + chunks_per_batch]
            chunks_text = _format_chunks_for_prompt(batch)

            prompt_text = template.format(
                global_directives=global_directives,
                chunks=chunks_text,
            )

            messages: list[dict] = [{"role": "system", "content": prompt_text}]
            if instruction_override:
                messages.append({"role": "user", "content": instruction_override})

            result = await agflow_client.invoke_chat(
                messages, response_format={"type": "json_object"}
            )
            last_model = result.model
            total_tokens_input += result.tokens_input
            total_tokens_output += result.tokens_output

            try:
                parsed = _ExtractorResponse.model_validate_json(result.content)
            except (ValidationError, ValueError) as exc:
                raise RuntimeError(f"ValidationError parsing extractor response: {exc}") from exc

            for signal in parsed.signals:
                chunk_uuids = [UUID(s) for s in signal.source_chunks]
                await signals_helper.insert_signal(
                    run_id=run_id,
                    role_project_id=role_project_id,
                    tenant_id=tenant_id,
                    source_item_id=None,
                    source_chunks=chunk_uuids,
                    signal_type=signal.type,
                    content=signal.content,
                    pool=pool,
                )
                signals_count += 1

    except Exception as exc:
        await runs.mark_failed(run_id, str(exc), pool=pool)
        raise

    # 6. Cost calculation
    cost_usd = (
        total_tokens_input * settings.mistral_input_token_rate_usd
        + total_tokens_output * settings.mistral_output_token_rate_usd
    )

    # 7. Mark done
    await runs.mark_done(
        run_id,
        output=json.dumps({"signals_count": signals_count}),
        llm_model=last_model,
        tokens_input=total_tokens_input,
        tokens_output=total_tokens_output,
        cost_usd=cost_usd,
        pool=pool,
    )

    return run_id
