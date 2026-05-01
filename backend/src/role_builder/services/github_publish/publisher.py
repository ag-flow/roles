"""Construction et push des fichiers d'un rôle vers GitHub.

Compose les 4-N fichiers (README.md + role.json + identity.md + LICENSE
optionnel + sections/<sec>/<doc>.md), puis pousse via Git data API
(create blobs → create tree → create commit → update ref) — atomique en
1 commit, ~5 appels HTTP indépendamment du nombre de fichiers.

L'ancienne implémentation N×PUT (`/contents`) reste disponible pour les
tests existants mais n'est plus appelée par les routes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import structlog

from role_builder.db_helpers.corpus_stats import get_corpus_stats
from role_builder.services.github_publish.api_client import GitHubApiClient
from role_builder.services.github_publish.readme_builder import (
    render_license_file,
    render_readme,
)

log = structlog.get_logger(__name__)


def _slugify(name: str) -> str:
    """Slug ASCII pour un nom de tag git : minuscules, [a-z0-9-], pas de doubles tirets.

    >>> _slugify("UX Designer Clea")
    'ux-designer-clea'
    >>> _slugify("Été à Paris !")
    'ete-a-paris'
    """
    # Normalisation accents (Café → Cafe)
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", ascii_only).strip("-").lower()
    slug = re.sub(r"-+", "-", slug)
    return slug or "role"


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
    stats: dict[str, int] | None = None,
) -> dict[str, str]:
    """Compose tous les fichiers à publier (relpath → contenu texte).

    ``stats`` optionnel (Phase 2 sous-projet B) injecte les compteurs
    sources/chunks dans le README.
    """
    files: dict[str, str] = {}

    files["README.md"] = render_readme(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=license_choice,
        stats=stats,
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
    tag_version_number: int | None = None,
) -> dict[str, Any]:
    """Push tous les fichiers d'un rôle vers GitHub via Git data API (atomique).

    1. Build files (README + role.json + identity + sections + LICENSE)
    2. GET ref → sha du commit HEAD de la branche
    3. GET commit/{sha} → sha du tree racine
    4. POST blobs en parallèle (1 par fichier) → sha de chaque blob
    5. POST trees avec base_tree=<root_tree> et items=[{path, mode, type, sha}]
    6. POST commits avec parents=[<head_commit>]
    7. PATCH refs/heads/<branch> avec le nouveau commit sha
    8. (Optionnel) POST git/tags + POST git/refs avec ref=refs/tags/role-<slug>-v<N>
       si ``tag_version_number`` est fourni — best-effort, n'interrompt pas le
       push si échec (ex: tag déjà existant).
    9. Insert role_publications row

    ~5 appels HTTP + N create_blob (parallélisable) ≈ 2-3 s pour 30 fichiers,
    contre ~10-20 s avec l'ancienne stratégie N×PUT séquentielle. Et atomique :
    si une étape échoue, le repo n'est pas dans un état partiel — la branche
    pointe toujours sur HEAD.
    """
    stats = await get_corpus_stats(project["id"], pool=pool)
    files = await build_publication_files(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=str(config.get("license_choice") or "none"),
        stats=stats,
    )

    owner, repo = str(config["repo_full_name"]).split("/", 1)
    base_path = str(config["target_subdirectory"]).strip("/")
    branch = str(config["branch"])
    commit_msg = _format_message(str(config["commit_message_template"]), project)

    head_sha = await api.get_ref_sha(owner, repo, branch)
    base_tree_sha = await api.get_commit_tree_sha(owner, repo, head_sha)

    # Création des blobs en parallèle — 1 round-trip cumulé au lieu de N
    async def _make_blob(relpath: str, content: str) -> dict[str, str]:
        sha = await api.create_blob(owner, repo, content=content, encoding="utf-8")
        full_path = f"{base_path}/{relpath}" if base_path else relpath
        return {
            "path": full_path,
            "mode": "100644",
            "type": "blob",
            "sha": sha,
        }

    items = await asyncio.gather(
        *(_make_blob(relpath, content) for relpath, content in files.items()),
    )

    new_tree_sha = await api.create_tree(
        owner, repo, base_tree_sha=base_tree_sha, items=items,
    )
    new_commit_sha = await api.create_commit(
        owner, repo, message=commit_msg, tree_sha=new_tree_sha, parent_sha=head_sha,
    )
    await api.update_ref(owner, repo, branch, new_sha=new_commit_sha)

    tag_name: str | None = None
    tag_url: str | None = None
    if tag_version_number is not None:
        slug = _slugify(str(project["display_name"]))
        tag_name = f"role-{slug}-v{tag_version_number}"
        try:
            tag_obj_sha = await api.create_tag(
                owner, repo,
                tag=tag_name,
                message=f"Publication v{tag_version_number} : {project['display_name']}",
                commit_sha=new_commit_sha,
            )
            await api.create_tag_ref(
                owner, repo, tag=tag_name, tag_sha=tag_obj_sha,
            )
            tag_url = f"https://github.com/{owner}/{repo}/releases/tag/{tag_name}"
            log.info("github.publish.tag_created", tag=tag_name)
        except httpx.HTTPStatusError as exc:
            # Tag déjà existant ou autre erreur GitHub — best-effort, on log
            # mais on ne casse pas le push.
            log.warning(
                "github.publish.tag_create_failed",
                tag=tag_name,
                status=exc.response.status_code if exc.response else None,
            )
            tag_name = None

    summary = f"Pushed to {config['repo_full_name']}/{base_path}"
    await insert_publication(
        role_project_id=project["id"],
        tenant_id=tenant_id,
        user_id=user_id,
        commit_sha=new_commit_sha,
        files_count=len(files),
        summary=summary,
        pool=pool,
    )

    log.info(
        "github.publish.completed",
        project_id=str(project["id"]),
        files_count=len(files),
        commit_sha=new_commit_sha,
        tag_name=tag_name,
        strategy="trees-api",
    )
    return {
        "commit_sha": new_commit_sha,
        "url": f"https://github.com/{owner}/{repo}/tree/{branch}/{base_path}",
        "files_count": len(files),
        "tag_name": tag_name,
        "tag_url": tag_url,
    }


async def push_publication_legacy_n_put(
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
    """Ancienne implémentation N PUT séquentiels (1 commit par fichier).

    Conservée pour fallback en cas de souci avec la Trees API. Pas exposée
    par les routes — accessible uniquement par tests / appel programmatique.
    Voir ``push_publication`` pour la version atomique.
    """
    stats = await get_corpus_stats(project["id"], pool=pool)
    files = await build_publication_files(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=str(config.get("license_choice") or "none"),
        stats=stats,
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
    """Supprime les fichiers du sous-répertoire publié — 1 commit atomique.

    Reconstruit la liste des fichiers attendus, vérifie ceux qui existent
    encore (GET get_content_sha), puis envoie un seul commit Trees avec
    ``sha: None`` pour chaque fichier à supprimer. Retourne le count.

    Avantage vs N×DELETE : 1 commit unique au lieu de N, et atomique.
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

    full_paths: list[str] = []
    for relpath in files:
        full_path = f"{base_path}/{relpath}" if base_path else relpath
        sha = await api.get_content_sha(owner, repo, full_path, branch)
        if sha is not None:
            full_paths.append(full_path)

    if not full_paths:
        return 0

    head_sha = await api.get_ref_sha(owner, repo, branch)
    base_tree_sha = await api.get_commit_tree_sha(owner, repo, head_sha)

    # Trees items avec sha=None → suppression. mode/type doivent rester.
    items: list[dict[str, Any]] = [
        {"path": p, "mode": "100644", "type": "blob", "sha": None}
        for p in full_paths
    ]
    new_tree_sha = await api.create_tree(
        owner, repo, base_tree_sha=base_tree_sha, items=items,
    )
    msg = f"Unpublish role {project['display_name']}"
    new_commit_sha = await api.create_commit(
        owner, repo, message=msg, tree_sha=new_tree_sha, parent_sha=head_sha,
    )
    await api.update_ref(owner, repo, branch, new_sha=new_commit_sha)

    log.info(
        "github.unpublish.completed",
        project_id=str(project["id"]),
        deleted_count=len(full_paths),
        commit_sha=new_commit_sha,
        strategy="trees-api",
    )
    return len(full_paths)
