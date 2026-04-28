"""Construit le payload role.json pour l'import ag.flow.

Format hypothétique (à valider avec OpenAPI ag.flow réel) :
  {
    "display_name": str,
    "description": str,
    "identity": str,
    "language": str,                    # défaut "fr" si null en BDD
    "service_types": list[str],         # défaut ["claude-code"] (pas en BDD)
    "sections": [{"name": str, "documents": [doc_name, ...]}, ...]
  }
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_LANGUAGE = "fr"
DEFAULT_SERVICE_TYPES = ["claude-code"]
LOCKED_SECTIONS_ORDER = ["Role", "Missions", "Skills"]


def build_role_json_dict(
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Construit le dict role.json depuis project + docs groupés.

    Sections sont retournées dans l'ordre verrouillé Role/Missions/Skills,
    suivi de toute autre section qui apparaîtrait (custom Phase 2).
    """
    sections_meta: list[dict[str, Any]] = []
    seen_sections: set[str] = set()
    for section in LOCKED_SECTIONS_ORDER:
        docs = docs_by_section.get(section, [])
        if docs:
            sections_meta.append({
                "name": section,
                "documents": [str(d["name"]) for d in docs],
            })
            seen_sections.add(section)
    # Sections custom (au cas où) — ordre alphabétique
    for section in sorted(docs_by_section.keys()):
        if section not in seen_sections:
            docs = docs_by_section[section]
            if docs:
                sections_meta.append({
                    "name": section,
                    "documents": [str(d["name"]) for d in docs],
                })

    return {
        "display_name": str(project.get("display_name", "")),
        "description": str(project.get("description") or ""),
        "identity": str(project.get("identity") or ""),
        "language": str(project.get("language") or DEFAULT_LANGUAGE),
        "service_types": list(DEFAULT_SERVICE_TYPES),
        "sections": sections_meta,
    }


def serialize_role_json(role_json: dict[str, Any]) -> str:
    """Sérialise le dict en JSON UTF-8 indenté."""
    return json.dumps(role_json, indent=2, ensure_ascii=False)
