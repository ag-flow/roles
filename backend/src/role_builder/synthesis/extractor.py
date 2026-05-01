"""Étage 1 du pipeline de synthèse : extraction de signaux depuis le corpus.

Le pipeline lit tous les chunks indexés d'un projet, les envoie par batch
au LLM (extractor prompt), et stocke les signaux extraits dans la table signals.
"""

from __future__ import annotations

import asyncio
import json
from typing import Literal
from uuid import UUID

import asyncpg
import structlog
from pydantic import BaseModel, ValidationError

from role_builder.config import settings
from role_builder.db_helpers import corpus_chunks, role_projects, runs
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.db_helpers import signals as signals_helper
from role_builder.services.agflow_client import get_agflow_client

log = structlog.get_logger(__name__)

_PROMPT_NAME = "extractor"


class _ExtractorSignal(BaseModel):
    type: Literal["heuristique", "anecdote", "vocab", "cadre", "opinion"]
    content: dict
    source_chunks: list[UUID]  # Pydantic v2 coerce str→UUID automatiquement


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
    parallelism: int = 1,
    pool: asyncpg.Pool,
) -> UUID:
    """Extrait des signaux depuis tous les chunks indexés du projet.

    Étapes :
      1. Resolve prompt_version : si None, get_system_default_version("extractor"),
         sinon get_version_by_id(prompt_version_id). Si non trouvé → RuntimeError.
      2. Get role_project via role_projects.get_by_id. Si None → RuntimeError.
      3. List corpus_chunks.list_by_project(role_project_id, limit=10000). Si vide → RuntimeError.
      4. Create run (status='pending') puis mark_running.
      5. Pour chaque batch de chunks_per_batch chunks (jusqu'à ``parallelism``
         en parallèle via asyncio.Semaphore) :
         a. Format prompt template.
         b. Construire messages.
         c. Appel LLM → ChatResult.
         d. Parse réponse JSON.
         e. Insert signals.
         f. Accumuler tokens.
      6. Calculer cost_usd.
      7. mark_done.
      8. Si exception : mark_failed + re-raise.

    ``parallelism`` (Phase 2 sous-projet F) : nombre maximum de batches LLM
    en vol simultanément. Default 1 = séquentiel (comportement Sprint 5).
    Pour les gros corpus (> 500 chunks), monter à 5-10 réduit drastiquement
    le temps total. Borné par le rate limit Mistral et la mémoire LLM.

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
        parameters={
            "chunks_per_batch": chunks_per_batch,
            "parallelism": parallelism,
        },
        instruction_override=instruction_override,
        pool=pool,
    )
    await runs.mark_running(run_id, pool=pool)

    # 5. Boucle par batch (parallèle via Semaphore)
    agflow_client = get_agflow_client()
    batches_count = (len(all_chunks) + chunks_per_batch - 1) // chunks_per_batch
    semaphore = asyncio.Semaphore(max(1, parallelism))

    log.info(
        "synthesis.extractor.run_started",
        run_id=str(run_id),
        role_project_id=str(role_project_id),
        chunks_count=len(all_chunks),
        batches=batches_count,
        parallelism=parallelism,
    )

    async def _process_batch(
        batch_index: int, batch: list[dict],
    ) -> tuple[int, int, int, str]:
        """Traite un batch de chunks et insère ses signaux. Retourne
        ``(tokens_input, tokens_output, signals_count, model)``.
        """
        async with semaphore:
            chunks_text = _format_chunks_for_prompt(batch)
            prompt_text = template.format(
                global_directives=global_directives,
                chunks=chunks_text,
            )
            messages: list[dict] = [{"role": "system", "content": prompt_text}]
            if instruction_override:
                messages.append({"role": "user", "content": instruction_override})

            result = await agflow_client.invoke_chat(
                messages, response_format={"type": "json_object"},
            )

            try:
                parsed = _ExtractorResponse.model_validate_json(result.content)
            except (ValidationError, ValueError) as exc:
                raise RuntimeError(
                    f"ValidationError parsing extractor response: {exc}",
                ) from exc

            inserted = 0
            for signal in parsed.signals:
                await signals_helper.insert_signal(
                    run_id=run_id,
                    role_project_id=role_project_id,
                    tenant_id=tenant_id,
                    source_item_id=None,
                    source_chunks=signal.source_chunks,
                    signal_type=signal.type,
                    content=signal.content,
                    pool=pool,
                )
                inserted += 1

            log.info(
                "synthesis.extractor.batch_completed",
                run_id=str(run_id),
                batch_index=batch_index,
                tokens_input=result.tokens_input,
                tokens_output=result.tokens_output,
                signals_extracted=inserted,
            )
            return (
                result.tokens_input, result.tokens_output, inserted, result.model,
            )

    try:
        batches = [
            all_chunks[start : start + chunks_per_batch]
            for start in range(0, len(all_chunks), chunks_per_batch)
        ]
        results = await asyncio.gather(
            *(_process_batch(i, b) for i, b in enumerate(batches)),
        )
        total_tokens_input = sum(r[0] for r in results)
        total_tokens_output = sum(r[1] for r in results)
        signals_count = sum(r[2] for r in results)
        last_model = results[-1][3] if results else settings.mistral_chat_model

    except Exception as exc:
        log.exception("synthesis.extractor.run_failed", run_id=str(run_id), error=str(exc))
        try:
            deleted = await signals_helper.delete_signals_by_run(run_id, pool=pool)
            if deleted:
                log.info(
                    "synthesis.extractor.signals_cleaned",
                    run_id=str(run_id),
                    deleted=deleted,
                )
        except Exception:
            log.exception("synthesis.extractor.cleanup_failed", run_id=str(run_id))
        await runs.mark_failed(run_id, str(exc), pool=pool)
        raise

    # 6. Cost calculation
    cost_usd = (
        total_tokens_input * settings.mistral_input_token_rate_usd
        + total_tokens_output * settings.mistral_output_token_rate_usd
    )

    log.info(
        "synthesis.extractor.run_completed",
        run_id=str(run_id),
        signals_total=signals_count,
        tokens_input=total_tokens_input,
        tokens_output=total_tokens_output,
        cost_usd=cost_usd,
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
