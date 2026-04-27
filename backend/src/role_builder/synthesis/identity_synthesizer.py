"""Étage 5 du pipeline de synthèse : production de l'identity du rôle.

À partir des role_documents is_current=True (toutes sections), produit
un texte markdown libre qui synthétise l'identité de l'agent.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import asyncpg
import structlog

from role_builder.config import settings
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.db_helpers import role_documents as role_documents_helper
from role_builder.db_helpers import role_projects, runs
from role_builder.services.agflow_client import get_agflow_client

log = structlog.get_logger(__name__)

_PROMPT_NAME = "identity_synthesizer"
_SECTION_ORDER = ("Role", "Missions", "Skills")


# ---------------------------------------------------------------------------
# Helper de formatage
# ---------------------------------------------------------------------------


def _format_documents_by_section(docs: list[dict]) -> str:
    """Groupe les docs par section et produit du markdown ordonné."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        grouped[d["section"]].append(d)

    parts: list[str] = []
    for section in _SECTION_ORDER:
        section_docs = grouped.get(section, [])
        if not section_docs:
            continue
        parts.append(f"## {section}\n")
        for d in section_docs:
            parts.append(f"### {d['name']}\n\n{d['content']}\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------


async def synthesize_identity(
    role_project_id: UUID,
    *,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """Produit l'identity du rôle à partir des documents is_current=True.

    Steps :
      1. Resolve prompt_version (system_default "identity_synthesizer").
      2. Get role_project. Si None → RuntimeError.
      3. List documents current via role_documents.list_current_by_project.
         Si vide → RuntimeError.
      4. Create run, mark_running.
      5. Format prompt (display_name, description, global_directives, documents).
      6. messages [system + optionnel user instruction_override].
      7. invoke_chat (markdown libre, PAS de response_format).
      8. role_projects.update_identity.
      9. mark_done.
     10. Sur exception : log.exception + mark_failed + raise.
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
    display_name: str = project.get("display_name") or ""
    description: str = project.get("description") or ""
    global_directives: str = project.get("global_directives") or ""

    # 3. List current documents
    docs = await role_documents_helper.list_current_by_project(role_project_id, pool=pool)
    if not docs:
        raise RuntimeError("promote at least one document to current before synthesizing identity")

    # 4. Create run
    run_id = await runs.create_run(
        role_project_id=role_project_id,
        tenant_id=tenant_id,
        prompt_version_id=resolved_prompt_version_id,
        input_summary={"docs_count": len(docs)},
        instruction_override=instruction_override,
        pool=pool,
    )
    await runs.mark_running(run_id, pool=pool)

    log.info(
        "synthesis.identity_synthesizer.run_started",
        run_id=str(run_id),
        docs_count=len(docs),
    )

    try:
        # 5. Format prompt
        documents_text = _format_documents_by_section(docs)
        prompt_text = template.format(
            display_name=display_name,
            description=description,
            global_directives=global_directives,
            documents=documents_text,
        )

        # 6. Messages
        messages: list[dict] = [{"role": "system", "content": prompt_text}]
        if instruction_override:
            messages.append({"role": "user", "content": instruction_override})

        # 7. invoke_chat (markdown libre, pas de response_format)
        agflow_client = get_agflow_client()
        result = await agflow_client.invoke_chat(messages)
        identity_markdown: str = result.content
        llm_model = result.model
        tokens_input = result.tokens_input
        tokens_output = result.tokens_output

        # 8. Update identity on role_project
        await role_projects.update_identity(role_project_id, identity_markdown, pool=pool)

    except Exception as exc:
        log.exception(
            "synthesis.identity_synthesizer.run_failed",
            run_id=str(run_id),
            error=str(exc),
        )
        await runs.mark_failed(run_id, str(exc), pool=pool)
        raise

    # 9. Mark done
    cost_usd = (
        tokens_input * settings.mistral_input_token_rate_usd
        + tokens_output * settings.mistral_output_token_rate_usd
    )

    log.info(
        "synthesis.identity_synthesizer.run_completed",
        run_id=str(run_id),
        identity_length=len(identity_markdown),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )

    await runs.mark_done(
        run_id,
        output=identity_markdown[:1000],
        llm_model=llm_model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        pool=pool,
    )

    return run_id
