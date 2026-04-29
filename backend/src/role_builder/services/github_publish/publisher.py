"""Construction et push des fichiers d'un rôle vers GitHub.

Compose les 4-N fichiers (README.md + role.json + identity.md + LICENSE
optionnel + sections/<sec>/<doc>.md), puis pousse chacun via PUT contents/.
Les fichiers existants sont mis à jour avec leur sha (~30 fichiers max
typique → 60 appels GET+PUT, ~10-20s par publication).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.services.github_publish.api_client import GitHubApiClient
from role_builder.services.github_publish.readme_builder import (
    render_license_file,
    render_readme,
)

log = structlog.get_logger(__name__)


def _build_role_json(
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    sections = [
        {"name": s, "documents": [d["name"] for d in docs]}
        for s, docs in docs_by_section.items()
    ]
    return {
        "display_name": project["display_name"],
        "description": project.get("description") or "",
        "identity": project.get("identity") or "",
        "language": project.get("language") or "fr",
        "service_types": project.get("service_types") or ["claude-code"],
        "sections": sections,
    }


async def build_publication_files(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    github_login: str,
    license_choice: str,
) -> dict[str, str]:
    """Compose tous les fichiers à publier (relpath → contenu texte)."""
    files: dict[str, str] = {}

    files["README.md"] = render_readme(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
    )
    files["role.json"] = json.dumps(
        _build_role_json(project, docs_by_section),
        indent=2,
        ensure_ascii=False,
    )
    files["identity.md"] = str(project.get("identity") or "")
    for section, docs in docs_by_section.items():
        for doc in docs:
            relpath = f"sections/{section.lower()}/{doc['name']}.md"
            files[relpath] = str(doc.get("content") or "")

    license_text = render_license_file(license_choice, author_login=github_login)
    if license_text is not None:
        files["LICENSE"] = license_text

    return files


def _format_message(template: str, project: dict[str, Any]) -> str:
    return template.format(role_name=str(project["display_name"]))


async def push_publication(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    github_login: str,
    user_id: UUID,
    tenant_id: UUID,
    api: GitHubApiClient,
    insert_publication: Callable[..., Awaitable[dict[str, Any]]],
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Push tous les fichiers d'un rôle vers GitHub.

    1. Build files (README + role.json + identity + sections + LICENSE)
    2. Pour chaque file : GET sha existant → PUT (avec sha si update)
    3. Insert role_publications row avec le commit_sha du dernier PUT
    """
    files = await build_publication_files(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=str(config.get("license_choice") or "none"),
    )

    owner, repo = str(config["repo_full_name"]).split("/", 1)
    base_path = str(config["target_subdirectory"]).strip("/")
    branch = str(config["branch"])
    commit_msg = _format_message(str(config["commit_message_template"]), project)

    last_commit_sha: str | None = None
    for relpath, content in files.items():
        full_path = f"{base_path}/{relpath}" if base_path else relpath
        existing_sha = await api.get_content_sha(owner, repo, full_path, branch)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        last_commit_sha = await api.put_content(
            owner=owner,
            repo=repo,
            path=full_path,
            branch=branch,
            content_b64=content_b64,
            message=commit_msg,
            existing_sha=existing_sha,
        )

    summary = f"Pushed to {config['repo_full_name']}/{base_path}"
    await insert_publication(
        role_project_id=project["id"],
        tenant_id=tenant_id,
        user_id=user_id,
        commit_sha=str(last_commit_sha or ""),
        files_count=len(files),
        summary=summary,
        pool=pool,
    )

    log.info(
        "github.publish.completed",
        project_id=str(project["id"]),
        files_count=len(files),
        commit_sha=last_commit_sha,
    )
    return {
        "commit_sha": last_commit_sha,
        "url": f"https://github.com/{owner}/{repo}/tree/{branch}/{base_path}",
        "files_count": len(files),
    }


async def delete_publication(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    github_login: str,
    api: GitHubApiClient,
) -> int:
    """Supprime les fichiers du sous-répertoire publié.

    Reconstruit la liste des fichiers attendus, récupère leur sha actuel,
    et envoie un DELETE pour chacun. Les fichiers déjà absents (404) sont
    skippés. Retourne le nombre de fichiers effectivement supprimés.
    """
    files = await build_publication_files(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=str(config.get("license_choice") or "none"),
    )
    owner, repo = str(config["repo_full_name"]).split("/", 1)
    base_path = str(config["target_subdirectory"]).strip("/")
    branch = str(config["branch"])
    msg = f"Unpublish role {project['display_name']}"

    deleted = 0
    for relpath in files:
        full_path = f"{base_path}/{relpath}" if base_path else relpath
        sha = await api.get_content_sha(owner, repo, full_path, branch)
        if sha is None:
            continue
        await api.delete_content(
            owner=owner,
            repo=repo,
            path=full_path,
            branch=branch,
            existing_sha=sha,
            message=msg,
        )
        deleted += 1
    return deleted
