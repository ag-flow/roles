"""Tests d'intégration des migrations 0005/0006 (refonte V2 — acquisition_requests).

Contrairement aux tests de `role_builder.migrations` (qui exercent le runner
contre un asyncpg *stubbé*), ces tests appliquent le SQL réel des migrations
0001 → 0006 contre un Postgres réel, sur une base éphémère créée puis
détruite pour chaque test. Deux scénarios couverts (demande explicite) :

- base vierge : la chaîne complète 0001..0006 s'applique sans erreur et
  aboutit au schéma attendu ;
- base avec données de fixture V1 : la migration de données (rattachement
  sources.role_project_id → acquisition_requests rétro-créées) produit le
  résultat attendu, et le drop des tables archivées (0006) ne casse rien.

Nécessite un Postgres joignable via `TEST_DATABASE_ADMIN_URL` (par défaut
``postgresql://rb:changeme_in_real_env@localhost:5432/postgres``, cohérent
avec `.env.example`/`docker-compose.yml`). Skip proprement si absent — ces
tests ne tournent pas encore en CI (pas de service Postgres dans
`.github/workflows/test.yml`), à ajouter séparément si on veut les y
enforcer.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql://rb:changeme_in_real_env@localhost:5432/postgres",
)

# Tables créées par 0001-0004, listées ici pour l'assertion de survie post-0006.
SURVIVING_TABLES = {
    "role_projects",
    "sources",
    "source_items",
    "scraping_jobs",
    "transcription_jobs",
    "user_credentials",
    "user_transcription_keys",
    "transcription_workers",
    "acquisition_requests",
    "corpus_pull_cursors",
}

# Tables archivées par scripts/archive_v1_tables.sh puis droppées par 0006.
DROPPED_TABLES = {
    "corpus_chunks",
    "chunking_jobs",
    "prompts",
    "prompt_versions",
    "runs",
    "signals",
    "clusters",
    "document_plans",
    "role_documents",
    "role_publication_config",
    "role_publications",
    "github_integrations",
    "oauth_states",
}


async def _postgres_reachable() -> bool:
    try:
        conn = await asyncpg.connect(dsn=ADMIN_DSN, timeout=2)
    except (OSError, asyncpg.PostgresError):
        return False
    await conn.close()
    return True


def _migration_sql(filename: str) -> str:
    return (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")


async def _apply(conn: asyncpg.Connection, filename: str) -> None:
    await conn.execute(_migration_sql(filename))


@pytest.fixture
async def db(request: pytest.FixtureRequest) -> AsyncIterator[asyncpg.Connection]:
    """Connexion à une base éphémère fraîche, détruite en fin de test."""
    if not await _postgres_reachable():
        pytest.skip(f"Postgres non joignable via TEST_DATABASE_ADMIN_URL ({ADMIN_DSN})")

    db_name = f"rb_migtest_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    target_dsn = re.sub(r"/[^/]+$", f"/{db_name}", ADMIN_DSN)
    conn = await asyncpg.connect(dsn=target_dsn)
    try:
        yield conn
    finally:
        await conn.close()
        admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
        try:
            await admin_conn.execute(
                f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'
            )
        finally:
            await admin_conn.close()


async def _existing_tables(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    return {r["tablename"] for r in rows}


async def _apply_v1_baseline(conn: asyncpg.Connection) -> None:
    for filename in (
        "0001_initial_schema.sql",
        "0002_vault_secret_name.sql",
        "0003_vault_user_credentials.sql",
        "0004_vault_github_integrations.sql",
    ):
        await _apply(conn, filename)


async def test_full_chain_applies_cleanly_on_empty_database(
    db: asyncpg.Connection,
) -> None:
    """0001..0006 sur base vierge : pas d'erreur, schéma final attendu."""
    await _apply_v1_baseline(db)
    await _apply(db, "0005_acquisition_requests.sql")
    await _apply(db, "0006_drop_synthesis_tables.sql")

    tables = await _existing_tables(db)

    assert SURVIVING_TABLES <= tables
    assert tables.isdisjoint(DROPPED_TABLES)

    # Aucune requête rétro-créée : base vide de départ.
    count = await db.fetchval("SELECT count(*) FROM acquisition_requests")
    assert count == 0


TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def _insert_v1_fixture(conn: asyncpg.Connection) -> dict[str, uuid.UUID]:
    """Un role_project complet : sources/items + tables de synthèse peuplées."""
    role_project_id = uuid.uuid4()
    source_id = uuid.uuid4()
    item_indexed_id = uuid.uuid4()
    item_chunking_id = uuid.uuid4()
    prompt_id = uuid.uuid4()
    prompt_version_id = uuid.uuid4()
    run_id = uuid.uuid4()

    await conn.execute(
        """
        INSERT INTO role_projects (id, tenant_id, user_id, display_name, keep_audio)
        VALUES ($1, $2, $3, $4, true)
        """,
        role_project_id, TENANT_ID, USER_ID, "Designer UX Cléa",
    )
    await conn.execute(
        """
        INSERT INTO sources (id, role_project_id, tenant_id, platform, source_type, url, status)
        VALUES ($1, $2, $3, 'youtube', 'channel', 'https://youtube.com/@clea-ux', 'discovered')
        """,
        source_id, role_project_id, TENANT_ID,
    )
    await conn.execute(
        """
        INSERT INTO source_items
            (id, source_id, tenant_id, platform_item_id, title, duration_s, status, selected)
        VALUES
            ($1, $3, $4, 'yt-abc123', 'Interview UX 1', 913, 'indexed', true),
            ($2, $3, $4, 'yt-def456', 'Interview UX 2', 500, 'chunking', true)
        """,
        item_indexed_id, item_chunking_id, source_id, TENANT_ID,
    )
    await conn.execute(
        """
        INSERT INTO prompts (id, name, type) VALUES ($1, 'extractor-default', 'extractor')
        """,
        prompt_id,
    )
    await conn.execute(
        """
        INSERT INTO prompt_versions (id, prompt_id, version_number, template, is_system_default)
        VALUES ($1, $2, 1, 'template text', true)
        """,
        prompt_version_id, prompt_id,
    )
    await conn.execute(
        """
        INSERT INTO runs (id, role_project_id, tenant_id, prompt_version_id, status)
        VALUES ($1, $2, $3, $4, 'completed')
        """,
        run_id, role_project_id, TENANT_ID, prompt_version_id,
    )
    await conn.execute(
        """
        INSERT INTO signals (id, run_id, role_project_id, tenant_id, type, content)
        VALUES ($1, $2, $3, $4, 'signal_type', '{}'::jsonb)
        """,
        uuid.uuid4(), run_id, role_project_id, TENANT_ID,
    )

    return {
        "role_project_id": role_project_id,
        "source_id": source_id,
        "item_indexed_id": item_indexed_id,
        "item_chunking_id": item_chunking_id,
    }


async def test_migration_0005_backfills_acquisition_requests_from_v1_fixture(
    db: asyncpg.Connection,
) -> None:
    await _apply_v1_baseline(db)
    ids = await _insert_v1_fixture(db)

    await _apply(db, "0005_acquisition_requests.sql")

    rows = await db.fetch("SELECT * FROM acquisition_requests")
    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == ids["source_id"]
    assert row["tenant_id"] == TENANT_ID
    assert row["kind"] == "scrape"
    assert row["mode"] == "auto"
    assert row["status"] == "completed"
    assert row["submitted_by"] == "migration-v1"
    assert re.match(r"^legacy-.+-[0-9a-f]{8}$", row["request_key"])
    assert row["request_key"].endswith(str(ids["source_id"])[:8])

    indexed_status = await db.fetchval(
        "SELECT status FROM source_items WHERE id = $1", ids["item_indexed_id"]
    )
    chunking_status = await db.fetchval(
        "SELECT status FROM source_items WHERE id = $1", ids["item_chunking_id"]
    )
    assert indexed_status == "deposited"
    assert chunking_status == "depositing"

    # Colonnes de dépôt docflow présentes et nullables (pas encore déposé).
    doc_id = await db.fetchval(
        "SELECT docflow_doc_id FROM source_items WHERE id = $1", ids["item_indexed_id"]
    )
    assert doc_id is None


async def test_migration_0006_drops_archived_tables_without_breaking_survivors(
    db: asyncpg.Connection,
) -> None:
    await _apply_v1_baseline(db)
    ids = await _insert_v1_fixture(db)
    await _apply(db, "0005_acquisition_requests.sql")

    request_row_before = await db.fetchrow("SELECT id, request_key FROM acquisition_requests")

    await _apply(db, "0006_drop_synthesis_tables.sql")

    tables = await _existing_tables(db)
    assert tables.isdisjoint(DROPPED_TABLES)

    # La requête rétro-créée en 0005 n'est pas affectée par le drop de 0006.
    request_row_after = await db.fetchrow("SELECT id, request_key FROM acquisition_requests")
    assert request_row_after["id"] == request_row_before["id"]
    assert request_row_after["request_key"] == request_row_before["request_key"]

    # role_projects / sources / source_items survivent intacts.
    display_name = await db.fetchval(
        "SELECT display_name FROM role_projects WHERE id = $1", ids["role_project_id"]
    )
    assert display_name == "Designer UX Cléa"

    item_count = await db.fetchval(
        "SELECT count(*) FROM source_items WHERE source_id = $1", ids["source_id"]
    )
    assert item_count == 2
