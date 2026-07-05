"""Critères d'acceptation §6 de la spec (lignes 1, 2, 6, 8), adaptés au lot
scrape (sans dépôt docflow — lot 4, ni upload — lot 5) : exercés à travers
la façade MCP réelle (mcp_server.tools.*), pas les services internes
directement (déjà couverts par tests/services/acquisition/).

Adaptations assumées pour ce lot :
- Critère 2 : s'arrête à `request_status`/comptages une fois la sélection
  auto appliquée — `get_corpus` (dépôt docflow) est hors périmètre.
- Critère 8 : "items déposés" devient "items déjà avancés dans le
  pipeline" (transcribed) — le dépôt n'existe pas encore.
"""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest

from role_builder.db import db_pool as db_pool_singleton
from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.mcp_server.tools import admin as admin_tool
from role_builder.mcp_server.tools import discovery as discovery_tool
from role_builder.mcp_server.tools import status as status_tool
from role_builder.mcp_server.tools import submission as submission_tool
from role_builder.services import event_handlers
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _wire_real_pool(pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_pool_singleton, "_pool", pool, raising=False)


async def _simulate_discovered_event(source_id, *, items: list[dict], pool: asyncpg.Pool) -> None:
    """Simule ce que ferait l'orchestrator réel en recevant l'event 'discovered'."""
    job = {"id": uuid4(), "source_id": source_id, "tenant_id": TENANT_ID}
    await event_handlers.handle_scraper_event(
        {"type": "discovered", "total": len(items), "items": items}, job, pool=pool
    )


async def test_criterion_1_two_step_nominal_cycle(pool: asyncpg.Pool) -> None:
    """submit(discover_only) → list_discovered paginé → select_items → seuls ces
    items passent en téléchargement/transcription."""
    await insert_active_credential(pool, platform="youtube")

    submitted = await submission_tool.submit_acquisition(
        "https://youtube.com/@clea-ux", submitted_by="claude-web"
    )
    assert submitted["status"] == "discovering"
    request_key = submitted["request_key"]

    request = await ar.get_by_key(request_key, pool=pool)
    items = [
        {
            "id": f"vid-{i}",
            "title": f"Interview UX {i}",
            "duration_s": 900,
            "description_excerpt": "Dans cette vidéo…",
            "tags": ["ux"],
        }
        for i in range(3)
    ]
    await _simulate_discovered_event(request["source_id"], items=items, pool=pool)

    discovered = await discovery_tool.list_discovered(request_key, limit=50)
    assert discovered["discovery_complete"] is True
    assert len(discovered["items"]) == 3
    assert all(item["title"].startswith("Interview UX") for item in discovered["items"])

    chosen = [str(discovered["items"][0]["item_id"]), str(discovered["items"][1]["item_id"])]
    selection = await discovery_tool.select_items(request_key, item_ids=chosen)
    assert selection == {"selected_count": 2, "queued_count": 2}

    status = await status_tool.request_status(request_key)
    assert status["counts"]["selected"] == 2
    assert status["counts"]["pending"] == 2  # les 2 sélectionnés, pas le 3e

    # Le 3e item (non sélectionné) reste pending_download et non sélectionné.
    untouched_id = discovered["items"][2]["item_id"]
    untouched = await source_items_helper.get_by_id(untouched_id, pool=pool)
    assert untouched["selected"] is False
    assert untouched["status"] == "pending_download"


async def test_criterion_2_auto_mode_with_filters(pool: asyncpg.Pool) -> None:
    """submit(auto, filters) → pull request_status → sélection auto reflétée
    (adapté : s'arrête avant get_corpus, hors périmètre de ce lot)."""
    await insert_active_credential(pool, platform="youtube")

    submitted = await submission_tool.submit_acquisition(
        "https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        mode="auto",
        filters={"min_duration_s": 500},
    )
    request_key = submitted["request_key"]
    request = await ar.get_by_key(request_key, pool=pool)

    items = [
        {"id": "vid-short", "title": "Court", "duration_s": 100},
        {"id": "vid-long", "title": "Long", "duration_s": 900},
    ]
    await _simulate_discovered_event(request["source_id"], items=items, pool=pool)

    status = await status_tool.request_status(request_key)
    assert status["status"] == "acquiring"
    assert status["counts"]["selected"] == 1  # seul l'item >= 500s
    assert status["counts"]["discovered"] == 2


async def test_criterion_6_multi_actor_shared_queue(pool: asyncpg.Pool) -> None:
    """Deux requêtes simultanées de deux submitted_by différents partagent la
    queue sans se corrompre ; queue_position cohérent."""
    await insert_active_credential(pool, platform="youtube")

    first = await submission_tool.submit_acquisition(
        "https://youtube.com/@first", submitted_by="agent-a"
    )
    second = await submission_tool.submit_acquisition(
        "https://youtube.com/@second", submitted_by="agent-b"
    )

    status_first = await status_tool.request_status(first["request_key"])
    status_second = await status_tool.request_status(second["request_key"])
    assert status_first["queue_position"] == 1
    assert status_second["queue_position"] == 2

    only_a = await status_tool.list_requests(submitted_by="agent-a")
    only_b = await status_tool.list_requests(submitted_by="agent-b")
    assert {r["request_key"] for r in only_a} == {first["request_key"]}
    assert {r["request_key"] for r in only_b} == {second["request_key"]}


async def test_criterion_8_cancel_preserves_advanced_items(pool: asyncpg.Pool) -> None:
    """cancel_request : jobs pending annulés, items déjà avancés dans le pipeline
    (transcribed — l'équivalent 'déposé' de ce lot, le dépôt n'existe pas encore)
    préservés."""
    await insert_active_credential(pool, platform="youtube")

    submitted = await submission_tool.submit_acquisition(
        "https://youtube.com/@clea-ux", submitted_by="claude-web"
    )
    request_key = submitted["request_key"]
    request = await ar.get_by_key(request_key, pool=pool)
    source_id = request["source_id"]

    await _simulate_discovered_event(
        source_id,
        items=[
            {"id": "vid-1", "title": "T1", "duration_s": 100},
            {"id": "vid-2", "title": "T2", "duration_s": 100},
        ],
        pool=pool,
    )
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    await discovery_tool.select_items(
        request_key, item_ids=[str(r["id"]) for r in rows]
    )

    # vid-1 a déjà progressé (simule le pipeline réel) ; vid-2 reste pending.
    await source_items_helper.update_source_item_status(
        source_id, "vid-1", "transcribed", pool=pool
    )

    result = await admin_tool.cancel_request(request_key, note="plus besoin")

    assert result["cancelled_jobs"] >= 1  # au moins le download job de vid-2
    updated_request = await ar.get_by_key(request_key, pool=pool)
    assert updated_request["status"] == "cancelled"

    preserved = await source_items_helper.get_by_id(rows[0]["id"], pool=pool)
    assert preserved["status"] == "transcribed"  # inchangé par cancel_request
