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
