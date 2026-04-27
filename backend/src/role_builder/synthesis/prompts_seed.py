"""Seed initial des 5 prompts système avec leur version v1.

Idempotent : à chaque exécution, vérifie si une version system_default existe
pour chaque prompt et n'en crée une nouvelle que si manquante ou si le
template a changé.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg

from role_builder.db_helpers import prompts as prompts_helper

SEED_DEFINITIONS: list[dict[str, object]] = [
    {
        "name": "extractor",
        "type": "extractor",
        "target_section": None,
        "description": "Extrait des signaux atomiques (heuristique/anecdote/vocab/cadre/opinion) depuis des chunks de corpus.",
        "template_file": "extractor_v1.md",
    },
    {
        "name": "clusterer",
        "type": "clusterer",
        "target_section": None,
        "description": "Regroupe des signaux en clusters thématiques cohérents.",
        "template_file": "clusterer_v1.md",
    },
    {
        "name": "decomposer",
        "type": "decomposer",
        "target_section": None,
        "description": "Produit un plan de documents par section (Role/Missions/Skills) à partir des clusters.",
        "template_file": "decomposer_v1.md",
    },
    {
        "name": "document_writer",
        "type": "writer",
        "target_section": None,
        "description": "Rédige un document atomique markdown à partir d'un brief, signaux supportants et chunks RAG.",
        "template_file": "document_writer_v1.md",
    },
    {
        "name": "identity_synthesizer",
        "type": "identity",
        "target_section": None,
        "description": "Produit l'identity du rôle à partir des documents current.",
        "template_file": "identity_synthesizer_v1.md",
    },
]


def _read_template(name: str) -> str:
    """Lit un template depuis le paquet synthesis/templates/."""
    path = Path(__file__).parent / "templates" / name
    return path.read_text(encoding="utf-8")


async def seed_system_prompts(pool: asyncpg.Pool) -> dict[str, str]:
    """Idempotent. Retourne un dict {prompt_name: action} avec action in
    {created, version_added, unchanged}."""
    actions: dict[str, str] = {}
    for definition in SEED_DEFINITIONS:
        name = str(definition["name"])
        template = _read_template(str(definition["template_file"]))

        prompt_id = await prompts_helper.upsert_prompt(
            name=name,
            type=str(definition["type"]),
            target_section=definition["target_section"],  # type: ignore[arg-type]
            description=str(definition["description"]),
            pool=pool,
        )

        existing = await prompts_helper.get_system_default_version(name, pool=pool)
        if existing is not None and existing["template"] == template:
            actions[name] = "unchanged"
            continue

        # Calcul du nouveau version_number = max + 1
        versions = await prompts_helper.list_versions(prompt_id, pool=pool)
        next_version = (max((v["version_number"] for v in versions), default=0)) + 1

        await prompts_helper.insert_prompt_version(
            prompt_id=prompt_id,
            version_number=next_version,
            template=template,
            is_system_default=True,
            pool=pool,
        )
        actions[name] = "created" if not versions else "version_added"

    return actions
