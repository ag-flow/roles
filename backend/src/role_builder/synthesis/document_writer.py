"""Étage 4 du pipeline de synthèse : rédaction de documents atomiques.

Le pipeline lit le plan d'un document (section + name + brief + supporting_signals),
récupère les signaux et chunks RAG, envoie au LLM et insère le résultat en base.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

import asyncpg
import structlog

from role_builder.config import settings
from role_builder.db_helpers import document_plans, role_projects, runs
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.db_helpers import role_documents as role_documents_helper
from role_builder.db_helpers import signals as signals_helper
from role_builder.services import corpus_search
from role_builder.services.agflow_client import get_agflow_client

log = structlog.get_logger(__name__)

_PROMPT_NAME = "document_writer"


# ---------------------------------------------------------------------------
# Helpers de formatage
# ---------------------------------------------------------------------------


def _format_rag_chunks(chunks: list[dict]) -> str:
    """Formate les chunks RAG retournés par corpus_search.find_relevant_chunks."""
    parts = []
    for c in chunks:
        parts.append(f"[score={c.get('similarity', 0):.2f}] {c.get('text', '')}")
    return "\n\n".join(parts)


def _format_signals_for_writer(signals_list: list[dict]) -> str:
    """JSON sérialisé des signaux supportants."""
    payload = [
        {"id": str(s["id"]), "type": s["type"], "content": s["content"]} for s in signals_list
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Pipeline principal : 1 document atomique
# ---------------------------------------------------------------------------


async def write_document(
    role_project_id: UUID,
    section: str,
    doc_plan: dict,
    *,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    rag_top_k: int = 8,
    rag_min_similarity: float = 0.5,
    pool: asyncpg.Pool,
) -> UUID:
    """Écrit UN document atomique. Retourne run_id.

    Le doc inséré a is_current=False — l'utilisateur promeut manuellement.

    Steps :
      1. Resolve prompt_version (system_default "document_writer").
      2. Get role_project (global_directives).
      3. Get supporting signals via signals.get_signals_by_ids.
         (Liste vide → continue, mais log warning.)
      4. Get RAG chunks via corpus_search.find_relevant_chunks.
         (Si vide, continue avec juste les signaux.)
      5. Create run, mark_running.
      6. Format prompt avec section, doc_name, doc_brief, global_directives, signals, chunks.
      7. messages [system + optionnel user instruction_override].
      8. invoke_chat (PAS de response_format JSON — markdown libre attendu).
      9. Insert role_document (is_current=False, source_run_id=run_id).
     10. mark_done.
     11. Sur exception : log.exception + delete_documents_by_run + mark_failed + raise.
    """
    doc_name: str = doc_plan["name"]
    doc_brief: str = doc_plan["brief"]
    raw_signal_ids: list = doc_plan.get("supporting_signals") or []
    signal_ids = [UUID(str(sid)) for sid in raw_signal_ids]

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

    # 3. Get supporting signals
    if signal_ids:
        supporting_signals = await signals_helper.get_signals_by_ids(signal_ids, pool=pool)
    else:
        supporting_signals = []
        log.warning(
            "synthesis.document_writer.no_supporting_signals",
            role_project_id=str(role_project_id),
            section=section,
            doc_name=doc_name,
        )

    # 4. Get RAG chunks
    rag_chunks = await corpus_search.find_relevant_chunks(
        role_project_id,
        doc_brief,
        top_k=rag_top_k,
        min_similarity=rag_min_similarity,
        pool=pool,
    )
    if not rag_chunks:
        log.warning(
            "synthesis.document_writer.no_rag_chunks",
            role_project_id=str(role_project_id),
            section=section,
            doc_name=doc_name,
        )

    # 5. Create run
    run_id = await runs.create_run(
        role_project_id=role_project_id,
        tenant_id=tenant_id,
        prompt_version_id=resolved_prompt_version_id,
        input_summary={
            "section": section,
            "doc_name": doc_name,
            "signals_count": len(supporting_signals),
            "rag_count": len(rag_chunks),
        },
        instruction_override=instruction_override,
        pool=pool,
    )
    await runs.mark_running(run_id, pool=pool)

    log.info(
        "synthesis.document_writer.run_started",
        run_id=str(run_id),
        section=section,
        name=doc_name,
        signals_count=len(supporting_signals),
        rag_count=len(rag_chunks),
    )

    try:
        # 6. Format prompt
        signals_text = _format_signals_for_writer(supporting_signals)
        chunks_text = _format_rag_chunks(rag_chunks)
        prompt_text = template.format(
            section=section,
            doc_name=doc_name,
            doc_brief=doc_brief,
            global_directives=global_directives,
            signals=signals_text,
            chunks=chunks_text,
        )

        # 7. Messages
        messages: list[dict] = [{"role": "system", "content": prompt_text}]
        if instruction_override:
            messages.append({"role": "user", "content": instruction_override})

        # 8. invoke_chat (markdown libre, pas de response_format)
        agflow_client = get_agflow_client()
        result = await agflow_client.invoke_chat(messages)
        markdown_content: str = result.content
        llm_model = result.model
        tokens_input = result.tokens_input
        tokens_output = result.tokens_output

        # 9. Insert role_document
        await role_documents_helper.insert_role_document(
            role_project_id=role_project_id,
            tenant_id=tenant_id,
            section=section,
            name=doc_name,
            content=markdown_content,
            source_run_id=run_id,
            is_current=False,
            pool=pool,
        )

    except Exception as exc:
        log.exception(
            "synthesis.document_writer.run_failed",
            run_id=str(run_id),
            section=section,
            doc_name=doc_name,
            error=str(exc),
        )
        try:
            deleted = await role_documents_helper.delete_documents_by_run(run_id, pool=pool)
            log.info(
                "synthesis.document_writer.documents_cleaned",
                run_id=str(run_id),
                deleted=deleted,
            )
        except Exception:
            log.exception("synthesis.document_writer.cleanup_failed", run_id=str(run_id))
        await runs.mark_failed(run_id, str(exc), pool=pool)
        raise

    # 10. Mark done
    cost_usd = (
        tokens_input * settings.mistral_input_token_rate_usd
        + tokens_output * settings.mistral_output_token_rate_usd
    )

    log.info(
        "synthesis.document_writer.run_completed",
        run_id=str(run_id),
        section=section,
        name=doc_name,
        content_length=len(markdown_content),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )

    await runs.mark_done(
        run_id,
        output=markdown_content[:1000],
        llm_model=llm_model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        pool=pool,
    )

    return run_id


# ---------------------------------------------------------------------------
# Pipeline batch : tous les documents d'un plan (parallélisme borné)
# ---------------------------------------------------------------------------


async def write_all_documents_for_plan(
    role_project_id: UUID,
    plan_id: UUID,
    *,
    parallelism: int = 3,
    pool: asyncpg.Pool,
) -> list[UUID]:
    """Lance write_document en parallèle borné (asyncio.Semaphore) pour
    tous les documents du plan donné. Retourne la liste des run_ids créés.

    Si write_document échoue pour un doc particulier, log error mais continue
    sur les autres (chaque doc est indépendant). Lève RuntimeError si TOUS échouent.
    """
    plan = await document_plans.get_by_id(plan_id, pool=pool)
    if plan is None:
        raise RuntimeError("plan not found")

    section: str = plan["section"]
    raw_planned = plan["planned_documents"]
    planned: list[dict] = raw_planned if isinstance(raw_planned, list) else json.loads(raw_planned)

    semaphore = asyncio.Semaphore(parallelism)

    async def _write_one(doc_plan: dict) -> UUID | None:
        async with semaphore:
            try:
                return await write_document(role_project_id, section, doc_plan, pool=pool)
            except Exception:
                log.exception(
                    "synthesis.document_writer.batch.doc_failed",
                    section=section,
                    name=doc_plan.get("name"),
                )
                return None

    results = await asyncio.gather(*[_write_one(d) for d in planned])
    successful = [r for r in results if r is not None]
    if not successful:
        raise RuntimeError("all documents failed to write")
    return successful
