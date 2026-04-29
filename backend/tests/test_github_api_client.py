"""Tests unitaires GitHubApiClient — list_repos, get_content, put_content, delete_content."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest


def _resp(status: int, json_body: Any = None) -> httpx.Response:
    """Helper qui construit une httpx.Response complète (avec request)."""
    return httpx.Response(
        status,
        json=json_body if json_body is not None else {},
        request=httpx.Request("GET", "https://api.github.com/x"),
    )


@pytest.mark.asyncio
async def test_list_repos_paginates_until_empty(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    page1 = _resp(
        200,
        [
            {
                "full_name": "a/r1",
                "private": False,
                "default_branch": "main",
                "html_url": "x",
            }
        ],
    )
    page2 = _resp(200, [])

    with patch.object(
        client._http,  # noqa: SLF001
        "get",
        new=AsyncMock(side_effect=[page1, page2]),
    ) as get_mock:
        repos = await client.list_repos()

    assert len(repos) == 1
    assert repos[0]["full_name"] == "a/r1"
    assert get_mock.call_count == 2


@pytest.mark.asyncio
async def test_get_content_returns_sha_when_200(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = _resp(200, {"sha": "abc123", "content": "..."})
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake)):  # noqa: SLF001
        sha = await client.get_content_sha("a", "r", "path/to/f.md", "main")
    assert sha == "abc123"


@pytest.mark.asyncio
async def test_get_content_returns_none_when_404(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = _resp(404, {"message": "Not Found"})
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake)):  # noqa: SLF001
        sha = await client.get_content_sha("a", "r", "path/to/f.md", "main")
    assert sha is None


@pytest.mark.asyncio
async def test_put_content_creates_with_no_sha(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = _resp(201, {"commit": {"sha": "deadbeef"}})
    with patch.object(client._http, "put", new=AsyncMock(return_value=fake)) as put_mock:  # noqa: SLF001
        commit_sha = await client.put_content(
            owner="a", repo="r", path="f.md", branch="main",
            content_b64="aGVsbG8=", message="msg", existing_sha=None,
        )
    assert commit_sha == "deadbeef"
    body = put_mock.call_args.kwargs["json"]
    assert "sha" not in body
    assert body["message"] == "msg"
    assert body["content"] == "aGVsbG8="
    assert body["branch"] == "main"


@pytest.mark.asyncio
async def test_put_content_updates_with_existing_sha(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = _resp(200, {"commit": {"sha": "newsha"}})
    with patch.object(client._http, "put", new=AsyncMock(return_value=fake)) as put_mock:  # noqa: SLF001
        await client.put_content(
            owner="a", repo="r", path="f.md", branch="main",
            content_b64="x", message="m", existing_sha="oldsha",
        )
    body = put_mock.call_args.kwargs["json"]
    assert body["sha"] == "oldsha"


@pytest.mark.asyncio
async def test_delete_content_passes_sha_and_message(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = _resp(200, {"commit": {"sha": "delsha"}})
    with patch.object(client._http, "request", new=AsyncMock(return_value=fake)) as req_mock:  # noqa: SLF001
        await client.delete_content(
            owner="a", repo="r", path="f.md", branch="main",
            existing_sha="abc", message="del",
        )
    call = req_mock.call_args
    assert call.args[0] == "DELETE"
    body = call.kwargs["json"]
    assert body["sha"] == "abc"
    assert body["message"] == "del"
    assert body["branch"] == "main"


# ---------------------------------------------------------------------------
# Git data API (Trees) — Phase 2.B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ref_sha_returns_object_sha(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(200, {"object": {"sha": "head-commit-sha", "type": "commit"}})
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake)) as get_mock:  # noqa: SLF001
        sha = await client.get_ref_sha("a", "r", "main")
    assert sha == "head-commit-sha"
    assert "git/ref/heads/main" in get_mock.call_args.args[0]


@pytest.mark.asyncio
async def test_get_commit_tree_sha_extracts_tree_sha(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(200, {"tree": {"sha": "tree-sha"}, "parents": []})
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake)):  # noqa: SLF001
        sha = await client.get_commit_tree_sha("a", "r", "commit-sha")
    assert sha == "tree-sha"


@pytest.mark.asyncio
async def test_create_blob_posts_content_and_encoding(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(201, {"sha": "blob-sha"})
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake)) as post_mock:  # noqa: SLF001
        sha = await client.create_blob("a", "r", content="hello", encoding="utf-8")
    assert sha == "blob-sha"
    body = post_mock.call_args.kwargs["json"]
    assert body == {"content": "hello", "encoding": "utf-8"}


@pytest.mark.asyncio
async def test_create_tree_passes_base_tree_and_items(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(201, {"sha": "new-tree-sha"})
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake)) as post_mock:  # noqa: SLF001
        items = [{"path": "x.md", "mode": "100644", "type": "blob", "sha": "blob-1"}]
        sha = await client.create_tree(
            "a", "r", base_tree_sha="base-tree", items=items,
        )
    assert sha == "new-tree-sha"
    body = post_mock.call_args.kwargs["json"]
    assert body["base_tree"] == "base-tree"
    assert body["tree"] == items


@pytest.mark.asyncio
async def test_create_commit_returns_sha(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(201, {"sha": "commit-sha"})
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake)) as post_mock:  # noqa: SLF001
        sha = await client.create_commit(
            "a", "r", message="msg", tree_sha="t", parent_sha="p",
        )
    assert sha == "commit-sha"
    body = post_mock.call_args.kwargs["json"]
    assert body["message"] == "msg"
    assert body["tree"] == "t"
    assert body["parents"] == ["p"]


@pytest.mark.asyncio
async def test_update_ref_returns_object_sha(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(200, {"object": {"sha": "new-head"}})
    with patch.object(client._http, "patch", new=AsyncMock(return_value=fake)) as patch_mock:  # noqa: SLF001
        sha = await client.update_ref("a", "r", "main", new_sha="new-head")
    assert sha == "new-head"
    body = patch_mock.call_args.kwargs["json"]
    assert body == {"sha": "new-head", "force": False}


@pytest.mark.asyncio
async def test_create_tag_posts_annotated_tag_object(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(201, {"sha": "tag-obj-sha"})
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake)) as post_mock:  # noqa: SLF001
        sha = await client.create_tag(
            "a", "r",
            tag="role-x-v1",
            message="Initial publication",
            commit_sha="commit-sha",
        )
    assert sha == "tag-obj-sha"
    body = post_mock.call_args.kwargs["json"]
    assert body["tag"] == "role-x-v1"
    assert body["message"] == "Initial publication"
    assert body["object"] == "commit-sha"
    assert body["type"] == "commit"
    assert body["tagger"]["name"] == "Role Builder"
    assert body["tagger"]["email"]


@pytest.mark.asyncio
async def test_create_tag_ref_posts_refs_tags(stubbed_env: None) -> None:
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_x")
    fake = _resp(201, {"object": {"sha": "tag-ref-sha"}})
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake)) as post_mock:  # noqa: SLF001
        sha = await client.create_tag_ref(
            "a", "r", tag="role-x-v1", tag_sha="tag-obj-sha",
        )
    assert sha == "tag-ref-sha"
    body = post_mock.call_args.kwargs["json"]
    assert body == {"ref": "refs/tags/role-x-v1", "sha": "tag-obj-sha"}
