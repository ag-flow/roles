"""Tests TDD pour services/github_publish/publisher.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


def _make_project(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "display_name": "Agent",
        "description": "desc",
        "identity": "# Identity",
        "language": "fr",
        "service_types": ["claude-code"],
        "target_role_id": None,
    }
    base.update(overrides)
    return base


def _make_docs() -> dict[str, list[dict[str, Any]]]:
    return {
        "Role": [{"name": "doc1", "content": "## Doc1"}],
        "Missions": [{"name": "mission1", "content": "## M1"}],
    }


class _StubGithubApi:
    def __init__(self, *, access_token: str = "ghp_x") -> None:
        self.access_token = access_token
        self.put_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.existing_shas: dict[str, str] = {}

    async def get_content_sha(
        self, owner: str, repo: str, path: str, branch: str,
    ) -> str | None:
        return self.existing_shas.get(path)

    async def put_content(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        content_b64: str,
        message: str,
        existing_sha: str | None,
    ) -> str:
        self.put_calls.append({
            "path": path,
            "existing_sha": existing_sha,
            "message": message,
            "content_b64": content_b64,
        })
        return f"commit-for-{path}"

    async def delete_content(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        existing_sha: str,
        message: str,
    ) -> str:
        self.delete_calls.append({"path": path, "existing_sha": existing_sha})
        return "del-commit"

    async def aclose(self) -> None:
        return None


# ---------------------------------------------------------------------------
# build_publication_files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_publication_files_includes_all_required_paths(
    stubbed_env: None,
) -> None:
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    files = await publisher.build_publication_files(
        project=project,
        docs_by_section=docs,
        github_login="alice",
        license_choice="mit",
    )
    paths = set(files.keys())
    assert "README.md" in paths
    assert "role.json" in paths
    assert "identity.md" in paths
    assert "sections/role/doc1.md" in paths
    assert "sections/missions/mission1.md" in paths
    assert "LICENSE" in paths
    role_json = json.loads(files["role.json"])
    assert role_json["display_name"] == "Agent"
    assert len(role_json["sections"]) == 2


@pytest.mark.asyncio
async def test_build_publication_files_skips_license_when_none(
    stubbed_env: None,
) -> None:
    from role_builder.services.github_publish import publisher

    files = await publisher.build_publication_files(
        project=_make_project(),
        docs_by_section=_make_docs(),
        github_login="alice",
        license_choice="none",
    )
    assert "LICENSE" not in files


# ---------------------------------------------------------------------------
# push_publication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_publication_pushes_all_files_and_records(
    stubbed_env: None,
) -> None:
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "mit",
    }
    api = _StubGithubApi()
    insert_calls: list[dict[str, Any]] = []

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        insert_calls.append(kwargs)
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()

    result = await publisher.push_publication(
        project=project,
        docs_by_section=docs,
        config=config,
        github_login="alice",
        user_id=uuid4(),
        tenant_id=project["tenant_id"],
        api=api,
        insert_publication=fake_insert,
        pool=pool,
    )

    # Tous les fichiers sont publiés (5 docs + LICENSE = 6)
    assert len(api.put_calls) == 6
    pushed_paths = [c["path"] for c in api.put_calls]
    assert all(p.startswith("ux-clea/") for p in pushed_paths)
    # Aucun n'a de existing_sha (fichiers neufs)
    assert all(c["existing_sha"] is None for c in api.put_calls)
    # 1 record en DB
    assert len(insert_calls) == 1
    assert insert_calls[0]["files_count"] == 6
    assert "alice/roles" in insert_calls[0]["summary"]
    # Commit message templaté
    assert "Update Agent" in api.put_calls[0]["message"]
    # Result exposé proprement
    assert result["files_count"] == 6
    assert "alice/roles" in result["url"]


@pytest.mark.asyncio
async def test_push_publication_uses_existing_sha_for_existing_files(
    stubbed_env: None,
) -> None:
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "none",
    }
    api = _StubGithubApi()
    api.existing_shas["ux-clea/README.md"] = "old-sha"

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    await publisher.push_publication(
        project=project,
        docs_by_section=docs,
        config=config,
        github_login="alice",
        user_id=uuid4(),
        tenant_id=project["tenant_id"],
        api=api,
        insert_publication=fake_insert,
        pool=pool,
    )
    readme_call = next(c for c in api.put_calls if c["path"] == "ux-clea/README.md")
    assert readme_call["existing_sha"] == "old-sha"


# ---------------------------------------------------------------------------
# delete_publication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_publication_iterates_existing_files_only(
    stubbed_env: None,
) -> None:
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "mit",
    }
    api = _StubGithubApi()
    # Seuls 4 fichiers existent (README, role.json, identity, LICENSE)
    api.existing_shas = {
        "ux-clea/README.md": "s1",
        "ux-clea/role.json": "s2",
        "ux-clea/identity.md": "s3",
        "ux-clea/LICENSE": "s4",
    }

    deleted = await publisher.delete_publication(
        project=project,
        docs_by_section=docs,
        config=config,
        github_login="alice",
        api=api,
    )
    # 4 fichiers existaient, 4 suppressions
    assert deleted == 4
    assert len(api.delete_calls) == 4
    assert all(c["existing_sha"] in {"s1", "s2", "s3", "s4"} for c in api.delete_calls)
