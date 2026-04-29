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
    """Stub GitHubApiClient couvrant à la fois /contents (legacy) et git data."""

    def __init__(self, *, access_token: str = "ghp_x") -> None:
        self.access_token = access_token
        # /contents (legacy)
        self.put_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.existing_shas: dict[str, str] = {}
        # git data API (Trees)
        self.blob_calls: list[dict[str, str]] = []
        self.tree_items: list[dict[str, str]] = []
        self.created_commit_msg: str | None = None
        self.head_commit_sha: str = "head-sha"
        self.base_tree_sha: str = "base-tree-sha"
        self.new_tree_sha: str = "new-tree-sha"
        self.new_commit_sha: str = "new-commit-sha"
        self.update_ref_calls: list[dict[str, Any]] = []
        self.create_tag_calls: list[dict[str, Any]] = []
        self.create_tag_ref_calls: list[dict[str, Any]] = []
        # Si non-None, create_tag lève cette exception (simule conflict 422)
        self.create_tag_raises: Exception | None = None

    # ---- /contents (legacy)
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

    # ---- git data API (Trees)
    async def get_ref_sha(self, owner: str, repo: str, branch: str) -> str:
        return self.head_commit_sha

    async def get_commit_tree_sha(
        self, owner: str, repo: str, commit_sha: str,
    ) -> str:
        return self.base_tree_sha

    async def create_blob(
        self, owner: str, repo: str, *, content: str, encoding: str = "utf-8",
    ) -> str:
        idx = len(self.blob_calls)
        sha = f"blob-{idx}"
        self.blob_calls.append({"content": content, "encoding": encoding, "sha": sha})
        return sha

    async def create_tree(
        self,
        owner: str,
        repo: str,
        *,
        base_tree_sha: str,
        items: list[dict[str, str]],
    ) -> str:
        self.tree_items = list(items)
        return self.new_tree_sha

    async def create_commit(
        self,
        owner: str,
        repo: str,
        *,
        message: str,
        tree_sha: str,
        parent_sha: str,
    ) -> str:
        self.created_commit_msg = message
        return self.new_commit_sha

    async def update_ref(
        self,
        owner: str,
        repo: str,
        branch: str,
        *,
        new_sha: str,
        force: bool = False,
    ) -> str:
        self.update_ref_calls.append(
            {"branch": branch, "new_sha": new_sha, "force": force},
        )
        return new_sha

    # ---- tags
    async def create_tag(
        self,
        owner: str,
        repo: str,
        *,
        tag: str,
        message: str,
        commit_sha: str,
        tagger_name: str = "Role Builder",
        tagger_email: str = "x@y.z",
    ) -> str:
        if self.create_tag_raises is not None:
            raise self.create_tag_raises
        self.create_tag_calls.append(
            {"tag": tag, "message": message, "commit_sha": commit_sha},
        )
        return f"tagobj-{tag}"

    async def create_tag_ref(
        self,
        owner: str,
        repo: str,
        *,
        tag: str,
        tag_sha: str,
    ) -> str:
        self.create_tag_ref_calls.append({"tag": tag, "tag_sha": tag_sha})
        return f"tagref-{tag}"

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
async def test_push_publication_uses_trees_api_atomic(
    stubbed_env: None,
) -> None:
    """push_publication utilise Git data API : 1 commit atomique pour N fichiers."""
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

    # 6 blobs créés (5 docs + LICENSE) — 1 par fichier, parallélisés
    assert len(api.blob_calls) == 6
    # Tree avec items = 6 entries préfixées par le subdir
    assert len(api.tree_items) == 6
    paths = [item["path"] for item in api.tree_items]
    assert all(p.startswith("ux-clea/") for p in paths)
    # Tous mode 100644 (file) et type blob
    assert all(item["mode"] == "100644" for item in api.tree_items)
    assert all(item["type"] == "blob" for item in api.tree_items)
    # 1 commit créé avec le bon message templaté
    assert api.created_commit_msg == "Update Agent"
    # Branche mise à jour avec le nouveau commit_sha
    assert api.update_ref_calls == [
        {"branch": "main", "new_sha": "new-commit-sha", "force": False},
    ]
    # Aucun PUT /contents (legacy) — c'est bien la nouvelle stratégie
    assert api.put_calls == []
    # 1 record DB avec le commit_sha atomique
    assert len(insert_calls) == 1
    assert insert_calls[0]["commit_sha"] == "new-commit-sha"
    assert insert_calls[0]["files_count"] == 6
    assert result["commit_sha"] == "new-commit-sha"
    assert "alice/roles" in result["url"]


@pytest.mark.asyncio
async def test_push_publication_handles_empty_subdirectory(
    stubbed_env: None,
) -> None:
    """Si target_subdirectory est vide, les paths du tree ne sont pas préfixés."""
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "none",
    }
    api = _StubGithubApi()

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    await publisher.push_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
    )
    paths = [item["path"] for item in api.tree_items]
    # Pas de préfixe — README.md à la racine du repo, etc.
    assert "README.md" in paths
    assert "role.json" in paths
    assert "sections/role/doc1.md" in paths


@pytest.mark.asyncio
async def test_push_publication_legacy_n_put_still_works(
    stubbed_env: None,
) -> None:
    """L'ancienne implem N×PUT séquentielle reste fonctionnelle (fallback)."""
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
    api.existing_shas["ux-clea/README.md"] = "old-sha"

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    await publisher.push_publication_legacy_n_put(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
    )
    # 6 fichiers PUT, et le README utilise existing_sha
    assert len(api.put_calls) == 6
    readme_call = next(c for c in api.put_calls if c["path"] == "ux-clea/README.md")
    assert readme_call["existing_sha"] == "old-sha"
    # Pas d'appel git data API
    assert api.blob_calls == []
    assert api.update_ref_calls == []


# ---------------------------------------------------------------------------
# delete_publication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_publication_uses_trees_api_with_sha_null(
    stubbed_env: None,
) -> None:
    """delete_publication = 1 commit atomique avec items[].sha=None pour les
    fichiers existants. Pas de N×DELETE."""
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
    # 4 des 6 fichiers existent encore en repo
    api.existing_shas = {
        "ux-clea/README.md": "s1",
        "ux-clea/role.json": "s2",
        "ux-clea/identity.md": "s3",
        "ux-clea/LICENSE": "s4",
    }

    deleted = await publisher.delete_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", api=api,
    )
    assert deleted == 4
    # Aucun N×DELETE ni N×PUT
    assert api.delete_calls == []
    assert api.put_calls == []
    # 1 tree avec sha=None pour les 4 fichiers existants
    assert len(api.tree_items) == 4
    assert all(item["sha"] is None for item in api.tree_items)
    assert all(item["mode"] == "100644" for item in api.tree_items)
    paths = {item["path"] for item in api.tree_items}
    assert paths == {
        "ux-clea/README.md", "ux-clea/role.json",
        "ux-clea/identity.md", "ux-clea/LICENSE",
    }
    # 1 commit avec le bon message + branche update
    assert api.created_commit_msg == "Unpublish role Agent"
    assert api.update_ref_calls == [
        {"branch": "main", "new_sha": "new-commit-sha", "force": False},
    ]


@pytest.mark.asyncio
async def test_push_publication_creates_annotated_tag_when_version_provided(
    stubbed_env: None,
) -> None:
    """tag_version_number=N → crée le tag role-{slug}-v{N} après le commit."""
    from role_builder.services.github_publish import publisher

    project = _make_project(display_name="UX Designer Clea")
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "none",
    }
    api = _StubGithubApi()

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    result = await publisher.push_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
        tag_version_number=3,
    )

    assert len(api.create_tag_calls) == 1
    tag_call = api.create_tag_calls[0]
    assert tag_call["tag"] == "role-ux-designer-clea-v3"
    assert tag_call["commit_sha"] == "new-commit-sha"
    assert "v3" in tag_call["message"]
    # Tag ref créé après l'objet tag
    assert len(api.create_tag_ref_calls) == 1
    assert api.create_tag_ref_calls[0]["tag"] == "role-ux-designer-clea-v3"
    # Result expose tag_name + tag_url
    assert result["tag_name"] == "role-ux-designer-clea-v3"
    assert result["tag_url"] == (
        "https://github.com/alice/roles/releases/tag/role-ux-designer-clea-v3"
    )


@pytest.mark.asyncio
async def test_push_publication_no_tag_when_version_none(
    stubbed_env: None,
) -> None:
    """tag_version_number=None → aucun tag créé, result.tag_name=None."""
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

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    result = await publisher.push_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
    )
    assert api.create_tag_calls == []
    assert api.create_tag_ref_calls == []
    assert result["tag_name"] is None
    assert result["tag_url"] is None


@pytest.mark.asyncio
async def test_push_publication_tag_creation_failure_does_not_break_push(
    stubbed_env: None,
) -> None:
    """Si create_tag raise httpx.HTTPStatusError (ex: tag déjà existant 422),
    le push réussit quand même (best-effort sur le tag)."""
    import httpx

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
    api.create_tag_raises = httpx.HTTPStatusError(
        "422 Unprocessable Entity",
        request=httpx.Request("POST", "x"),
        response=httpx.Response(422, request=httpx.Request("POST", "x")),
    )

    async def fake_insert(**kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    result = await publisher.push_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
        tag_version_number=1,
    )
    # Push complet
    assert result["commit_sha"] == "new-commit-sha"
    # Mais tag absent
    assert result["tag_name"] is None
    assert api.create_tag_ref_calls == []


def test_slugify_handles_accents_and_punctuation() -> None:
    from role_builder.services.github_publish.publisher import _slugify

    assert _slugify("UX Designer Clea") == "ux-designer-clea"
    assert _slugify("Été à Paris !") == "ete-a-paris"
    assert _slugify("Multiple   Spaces") == "multiple-spaces"
    assert _slugify("") == "role"
    assert _slugify("---") == "role"


@pytest.mark.asyncio
async def test_delete_publication_no_op_when_nothing_exists(
    stubbed_env: None,
) -> None:
    """Si aucun fichier n'existe en repo, retourne 0 sans créer de commit."""
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
    # existing_shas vide

    deleted = await publisher.delete_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", api=api,
    )
    assert deleted == 0
    assert api.tree_items == []
    assert api.update_ref_calls == []
