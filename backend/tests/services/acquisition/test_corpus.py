"""Tests d'intégration — services.acquisition.corpus (roles__get_corpus, §2.4).

Livraison incrémentale : refs docflow des items déposés à tout moment,
`only_new` par curseur (request_key, caller), `cursor` explicite stateless.
Critère §6 ligne 5 : deux pulls successifs / deux appelants indépendants.
"""

from __future__ import annotations

import asyncpg
import pytest

from role_builder.db_helpers import corpus_pull_cursors as cursors_helper
from role_builder.db_helpers import deposit_queue
from role_builder.services.acquisition.corpus import get_corpus
from role_builder.services.acquisition.errors import AcquisitionError
from tests.services.deposit.helpers import insert_item, seed_request_with_item

pytestmark = pytest.mark.asyncio


async def _deposit_next(pool: asyncpg.Pool, *, doc_id: str, slug: str) -> None:
    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)
    await deposit_queue.mark_deposited(claimed["id"], doc_id=doc_id, slug=slug, pool=pool)


async def test_get_corpus_returns_deposited_refs_and_metadata(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    await _deposit_next(pool, doc_id="doc-1", slug="transcript-interview-ux-a1")
    # Un second item sélectionné encore en vol : la requête n'est pas finie,
    # mais le premier dépôt est déjà livrable (livraison incrémentale).
    await insert_item(pool, source_id=seeded["source_id"], status="transcribing")

    result = await get_corpus(seeded["request_key"], caller="claude-web", pool=pool)

    assert result["request_key"] == seeded["request_key"]
    assert result["complete"] is False
    assert result["failed_items"] == []
    assert len(result["documents"]) == 1
    document = result["documents"][0]
    assert document["item_id"] == seeded["item_id"]
    assert document["docflow"] == {
        "doc_id": "doc-1",
        "slug": "transcript-interview-ux-a1",
        "title": "Interview UX : observer avant de questionner",
    }
    assert document["metadata"]["platform"] == "youtube"
    assert document["metadata"]["source_url"] == "https://youtube.com/@clea-ux"
    assert document["metadata"]["duration_s"] == 913
    assert document["metadata"]["published_at"] is not None


async def test_get_corpus_complete_when_all_selected_items_terminal(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    await _deposit_next(pool, doc_id="doc-1", slug="s-1")

    # L'unique item sélectionné est déposé → completed.
    result = await get_corpus(seeded["request_key"], caller="claude-web", pool=pool)
    assert result["complete"] is True

    # Un second item sélectionné encore en vol → plus complete.
    await insert_item(pool, source_id=seeded["source_id"], status="transcribing")
    result = await get_corpus(seeded["request_key"], caller="claude-web", pool=pool)
    assert result["complete"] is False


async def test_get_corpus_only_new_two_successive_pulls(pool: asyncpg.Pool) -> None:
    """§6 ligne 5 (première moitié) : le second pull only_new ne retourne que
    les items déposés entre-temps."""
    seeded = await seed_request_with_item(pool)
    await _deposit_next(pool, doc_id="doc-1", slug="s-1")

    first = await get_corpus(seeded["request_key"], caller="claude-web", only_new=True, pool=pool)
    assert [d["docflow"]["doc_id"] for d in first["documents"]] == ["doc-1"]

    second = await get_corpus(seeded["request_key"], caller="claude-web", only_new=True, pool=pool)
    assert second["documents"] == []  # rien de neuf

    await insert_item(pool, source_id=seeded["source_id"], status="transcribed")
    await _deposit_next(pool, doc_id="doc-2", slug="s-2")

    third = await get_corpus(seeded["request_key"], caller="claude-web", only_new=True, pool=pool)
    assert [d["docflow"]["doc_id"] for d in third["documents"]] == ["doc-2"]


async def test_get_corpus_cursors_are_independent_per_caller(pool: asyncpg.Pool) -> None:
    """§6 ligne 5 (seconde moitié) : deux appelants ont des curseurs indépendants."""
    seeded = await seed_request_with_item(pool)
    await _deposit_next(pool, doc_id="doc-1", slug="s-1")

    pulled_by_a = await get_corpus(
        seeded["request_key"], caller="claude-web", only_new=True, pool=pool
    )
    assert len(pulled_by_a["documents"]) == 1

    pulled_by_b = await get_corpus(
        seeded["request_key"], caller="agent-b", only_new=True, pool=pool
    )
    assert len(pulled_by_b["documents"]) == 1  # le curseur de A n'affecte pas B


async def test_get_corpus_full_pull_advances_the_callers_cursor(pool: asyncpg.Pool) -> None:
    """« Depuis le dernier get_corpus de cet appelant » : un pull complet
    (only_new=False) avance aussi le curseur."""
    seeded = await seed_request_with_item(pool)
    await _deposit_next(pool, doc_id="doc-1", slug="s-1")

    await get_corpus(seeded["request_key"], caller="claude-web", pool=pool)

    result = await get_corpus(seeded["request_key"], caller="claude-web", only_new=True, pool=pool)
    assert result["documents"] == []


async def test_get_corpus_explicit_cursor_is_stateless(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    await _deposit_next(pool, doc_id="doc-1", slug="s-1")

    first = await get_corpus(seeded["request_key"], caller="claude-web", pool=pool)
    next_cursor = first["next_cursor"]
    assert next_cursor is not None

    await insert_item(pool, source_id=seeded["source_id"], status="transcribed")
    await _deposit_next(pool, doc_id="doc-2", slug="s-2")

    result = await get_corpus(
        seeded["request_key"], caller="stateless-caller", cursor=next_cursor, pool=pool
    )
    assert [d["docflow"]["doc_id"] for d in result["documents"]] == ["doc-2"]
    # Mode stateless : le curseur stocké de cet appelant n'est pas touché.
    stored = await cursors_helper.get_last_pulled_at(
        seeded["request_id"], "stateless-caller", pool=pool
    )
    assert stored is None


async def test_get_corpus_lists_failed_items(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)
    await deposit_queue.mark_deposit_failed(claimed["id"], message="gateway down", pool=pool)

    result = await get_corpus(seeded["request_key"], caller="claude-web", pool=pool)

    assert result["documents"] == []
    assert len(result["failed_items"]) == 1
    failed = result["failed_items"][0]
    assert failed["item_id"] == seeded["item_id"]
    assert failed["title"] == "Interview UX : observer avant de questionner"
    assert "DOCFLOW_DEPOSIT_FAILED" in failed["error"]


async def test_get_corpus_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await get_corpus("nope", caller="claude-web", pool=pool)
    assert exc_info.value.code == "UNKNOWN_REQUEST"


async def test_get_corpus_invalid_cursor(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    with pytest.raises(AcquisitionError) as exc_info:
        await get_corpus(seeded["request_key"], caller="claude-web", cursor="pas-une-date", pool=pool)
    assert exc_info.value.code == "INVALID_CURSOR"
