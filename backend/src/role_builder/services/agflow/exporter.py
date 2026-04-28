"""Construction du ZIP ag.flow."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Any

from role_builder.services.agflow.role_json_builder import (
    build_role_json_dict,
    serialize_role_json,
)


@dataclass
class BuildResult:
    """Résultat d'un build ZIP."""

    zip_bytes: bytes
    role_json: dict[str, Any]
    documents_count: int


def build_role_zip(
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
) -> BuildResult:
    """Construit le ZIP complet pour un rôle.

    Lève ValueError si :
    - identity null/vide
    - aucune section avec docs current

    Layout ZIP :
      role.json
      section_role/{doc_name}.md
      section_missions/{doc_name}.md
      ...
    """
    identity = project.get("identity")
    if not identity or not str(identity).strip():
        raise ValueError("identity not generated yet")

    if not any(docs_by_section.get(s) for s in docs_by_section):
        raise ValueError("no current documents to export")

    role_json = build_role_json_dict(project, docs_by_section)
    documents_count = sum(len(docs) for docs in docs_by_section.values())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # role.json à la racine
        zf.writestr("role.json", serialize_role_json(role_json))
        # 1 dossier par section, lowercase, préfixe "section_"
        for section_name, docs in docs_by_section.items():
            folder = f"section_{section_name.lower()}"
            for doc in docs:
                doc_name = str(doc["name"])
                doc_content = str(doc.get("content", ""))
                zf.writestr(f"{folder}/{doc_name}.md", doc_content)

    return BuildResult(
        zip_bytes=buffer.getvalue(),
        role_json=role_json,
        documents_count=documents_count,
    )
