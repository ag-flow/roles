"""Runner de migrations SQL embarquées dans l'image.

Appelé au démarrage FastAPI (lifespan) avant que l'app commence à servir.
Contrats :

- Fichiers `migrations/*.sql` triés lexicographiquement (pattern
  ``^\\d{3,}_.*\\.sql$``).
- Idempotent : `schema_migrations(version text PRIMARY KEY, applied_at timestamptz)`
  garde la trace des migrations déjà jouées. Rejouer ne fait rien.
- Multi-replica safe : `pg_advisory_lock` exclusif sur une clé int8 dérivée du
  namespace ``agflow_roles_migrations`` — différent du runner de `agflow.docker`
  pour ne pas bloquer mutuellement quand les deux modules partagent un cluster.
- Aucun ``CREATE EXTENSION`` dans les SQL : les extensions sont créées en amont
  par le côté provisioning (compte superuser).

Sur erreur : on relève l'exception. Le container redémarre en boucle, ce qui
est le comportement souhaité (visibilité immédiate du problème).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import asyncpg
import structlog

log = structlog.get_logger(__name__)

_MIGRATION_FILENAME_RE = re.compile(r"^\d{3,}_.*\.sql$")
_NAMESPACE = b"agflow_roles_migrations"


def _lock_key() -> int:
    """Clé int8 stable pour pg_advisory_lock, dérivée du namespace."""
    digest = hashlib.sha256(_NAMESPACE).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _list_migration_files(migrations_dir: Path) -> list[Path]:
    """Liste triée des fichiers de migration valides."""
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"migrations directory not found: {migrations_dir}")
    files = [
        p for p in migrations_dir.iterdir()
        if p.is_file() and _MIGRATION_FILENAME_RE.match(p.name)
    ]
    files.sort(key=lambda p: p.name)
    return files


_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version text PRIMARY KEY,
        applied_at timestamptz NOT NULL DEFAULT now()
    )
"""


def _is_blank_sql(sql: str) -> bool:
    """True si le SQL ne contient que des commentaires / espaces.

    On strippe les commentaires SQL ``-- ...`` ligne par ligne avant de tester.
    """
    stripped = "\n".join(
        line.split("--", 1)[0] for line in sql.splitlines()
    ).strip()
    return stripped == ""


async def run_migrations(
    migrations_dir: Path, *, pool: asyncpg.Pool,
) -> list[str]:
    """Applique les migrations manquantes. Retourne la liste des versions appliquées.

    Algorithme :
    1. Acquérir l'advisory lock (try → fallback bloquant)
    2. Garantir l'existence de schema_migrations
    3. Charger les versions déjà appliquées
    4. Pour chaque fichier *.sql trié, l'appliquer s'il manque, dans une
       transaction qui inclut l'INSERT dans schema_migrations
    5. Relâcher le lock
    """
    files = _list_migration_files(migrations_dir)
    log.info("migrations.start", count=len(files))

    key = _lock_key()
    applied_versions: list[str] = []

    async with pool.acquire() as conn:
        # Advisory lock — try non-bloquant d'abord pour visibilité,
        # puis fallback bloquant si une autre replica est en cours.
        got_lock = await conn.fetchval("SELECT pg_try_advisory_lock($1)", key)
        if not got_lock:
            log.info("migrations.waiting_for_lock", key=key)
            await conn.execute("SELECT pg_advisory_lock($1)", key)
        try:
            await conn.execute(_CREATE_TABLE_SQL)
            already = {
                r["version"]
                for r in await conn.fetch(
                    "SELECT version FROM schema_migrations",
                )
            }

            for path in files:
                version = path.name
                if version in already:
                    continue
                sql = path.read_text(encoding="utf-8")
                async with conn.transaction():
                    if not _is_blank_sql(sql):
                        await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
                applied_versions.append(version)
                log.info("migrations.applied", version=version)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", key)

    log.info(
        "migrations.complete",
        applied=len(applied_versions),
        skipped=len(files) - len(applied_versions),
    )
    return applied_versions
