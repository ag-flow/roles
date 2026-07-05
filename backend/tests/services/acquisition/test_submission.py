"""Tests d'intégration — services.acquisition.submission.submit_acquisition.

Postgres réel éphémère (cf. conftest.pool) : cette fonction touche
sources, acquisition_requests et scraping_jobs dans une même transaction
logique, plus adaptée à un test d'intégration qu'à des stubs multiples.
"""

from __future__ import annotations

from datetime import date

import asyncpg
import pytest

from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.submission import submit_acquisition
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


async def test_submit_acquisition_discover_only_happy_path(pool: asyncpg.Pool) -> None:
    """Cas nominal : source + acquisition_request + job discover créés, statut discovering."""
    await insert_active_credential(pool, platform="youtube")

    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )

    assert result["status"] == "discovering"
    assert result["platform"] == "youtube"
    assert result["url"] == "https://youtube.com/@clea-ux"
    assert result["request_key"].startswith("yt-clea-ux-2026-07-05")

    from role_builder.db_helpers import acquisition_requests as ar

    request = await ar.get_by_key(result["request_key"], pool=pool)
    assert request is not None
    assert request["mode"] == "discover_only"
    assert request["status"] == "discovering"
    assert request["kind"] == "scrape"

    source = await sources_helper.get_source(request["source_id"], pool=pool)
    assert source is not None
    assert source["platform"] == "youtube"
    assert source["role_project_id"] is None

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    discover_jobs = [j for j in jobs if j["source_id"] == source["id"] and j["command"] == "discover"]
    assert len(discover_jobs) == 1


async def test_submit_acquisition_auto_mode_with_filters(pool: asyncpg.Pool) -> None:
    """mode=auto + filters sont persistés tels quels sur la requête (appliqués à la découverte)."""
    await insert_active_credential(pool, platform="youtube")

    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        mode="auto",
        filters={"max_items": 10, "min_duration_s": 300},
        today=date(2026, 7, 5),
        pool=pool,
    )

    from role_builder.db_helpers import acquisition_requests as ar

    request = await ar.get_by_key(result["request_key"], pool=pool)
    assert request["mode"] == "auto"
    import json

    assert json.loads(request["filters"]) == {"max_items": 10, "min_duration_s": 300}


async def test_submit_acquisition_raises_no_credentials(pool: asyncpg.Pool) -> None:
    """Aucune credential active pour la plateforme → NO_CREDENTIALS."""
    with pytest.raises(AcquisitionError) as exc_info:
        await submit_acquisition(
            url="https://youtube.com/@clea-ux",
            submitted_by="claude-web",
            tenant_id=TENANT_ID,
            today=date(2026, 7, 5),
            pool=pool,
        )
    assert exc_info.value.code == "NO_CREDENTIALS"


async def test_submit_acquisition_raises_unsupported_platform(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await submit_acquisition(
            url="https://vimeo.com/12345",
            submitted_by="claude-web",
            tenant_id=TENANT_ID,
            today=date(2026, 7, 5),
            pool=pool,
        )
    assert exc_info.value.code == "UNSUPPORTED_PLATFORM"


async def test_submit_acquisition_retries_request_key_on_collision(pool: asyncpg.Pool) -> None:
    """Deux soumissions le même jour sur la même chaîne → request_key différencié."""
    await insert_active_credential(pool, platform="youtube")

    first = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )
    second = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )

    assert first["request_key"] != second["request_key"]
    assert second["request_key"].startswith("yt-clea-ux-2026-07-05")
