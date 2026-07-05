"""Tests for mcp_server.server — enregistrement des tools roles__* (spec §2)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

EXPECTED_TOOL_NAMES = {
    "roles__submit_acquisition",
    "roles__list_discovered",
    "roles__select_items",
    "roles__create_upload_request",
    "roles__request_upload_slot",
    "roles__finalize_upload",
    "roles__close_upload_request",
    "roles__request_status",
    "roles__list_requests",
    "roles__get_corpus",
    "roles__cancel_request",
    "roles__retry_failed",
}


async def test_all_facade_tools_are_registered() -> None:
    from role_builder.mcp_server.server import mcp

    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}

    assert names == EXPECTED_TOOL_NAMES


async def test_submit_acquisition_tool_schema_requires_url_and_submitted_by() -> None:
    from role_builder.mcp_server.server import mcp

    tools = await mcp.list_tools()
    submit = next(t for t in tools if t.name == "roles__submit_acquisition")

    required = set(submit.inputSchema.get("required", []))
    assert {"url", "submitted_by"} <= required
