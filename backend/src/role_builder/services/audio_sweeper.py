"""Balayeur d'orphelins audio et garde disque (relais audio volume local).

Le scraper écrit l'audio dans un volume monté sur le host, et le worker de
transcription le supprime après une transcription réussie (tâche 4). Ce
qu'il laisse derrière lui : un job abandonné, un worker mort en cours de
traitement, un item `failed` définitivement. MinIO portait un cycle de vie
explicite (`keep_audio`) ; un répertoire monté n'en a aucun. Sans ce
balayeur périodique, le disque de la VM dédiée se remplit et arrête tout
sans prévenir.

Un fichier est balayé si, et seulement si, il est À LA FOIS :
  1. plus vieux que `settings.audio_orphan_retention_h` ;
  2. absent de toute référence `audio_path` d'un transcription_job encore
     vivant (pending/claimed/processing).
La condition 2 est celle qui porte la valeur : un fichier vieux mais
attendu par un job `pending` doit survivre, sinon le balayeur casse
précisément les retries que le worker préserve en gardant l'audio après un
échec (tâche 4).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

import asyncpg
import structlog

from role_builder.config import settings

log = structlog.get_logger(__name__)

# Statuts dont l'audio doit SURVIVRE quel que soit son âge : un retry doit
# retrouver le fichier (cf. tâche 4, qui garde l'audio sur échec pour cette
# raison). `done`, `failed` et `cancelled` sont hors de cette liste
# délibérément — un job `failed` définitif est précisément un des cas que ce
# balayeur doit nettoyer (cf. en-tête de module).
_LIVE_JOB_STATUSES = ("pending", "claimed", "processing")

_FETCH_LIVE_AUDIO_PATHS_SQL = (
    "SELECT audio_path FROM transcription_jobs WHERE status = ANY($1::text[])"
)


async def _db_fetch_live_audio_paths(*, pool: asyncpg.Pool) -> set[str]:
    """Chemins audio référencés par un transcription_job encore vivant.

    Ne lit QUE transcription_jobs : c'est la seule table dont une ligne
    pilote encore une reprise sur ce fichier après le passage du scraper
    (source_items.audio_path reste pour l'historique, mais ne gouverne plus
    aucun retry).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(_FETCH_LIVE_AUDIO_PATHS_SQL, list(_LIVE_JOB_STATUSES))
    return {row["audio_path"] for row in rows}


def _file_sweep_orphans(*, audio_dir: Path, cutoff: dt.datetime, keep: set[str]) -> tuple[int, int]:
    """Parcours et suppression, bloquants par nature (os.walk + stat + unlink).

    DOIT être appelé via `asyncio.to_thread` par l'appelant : jamais en
    direct depuis une coroutine. Le linter ASYNC240 ne voit pas à travers cet
    appel de fonction — ce n'est pas lui qui détecterait l'oubli, d'où ce
    rappel explicite au lieu de compter sur l'outillage.
    """
    deleted = 0
    reclaimed_bytes = 0
    if not audio_dir.exists():
        return deleted, reclaimed_bytes
    for path in audio_dir.rglob("*"):
        if not path.is_file() or str(path) in keep:
            continue
        stat = path.stat()
        mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.UTC)
        if mtime >= cutoff:
            continue
        size = stat.st_size
        path.unlink()
        deleted += 1
        reclaimed_bytes += size
    return deleted, reclaimed_bytes


async def sweep_orphan_audio(*, now: dt.datetime, pool: asyncpg.Pool) -> int:
    """Supprime les fichiers audio orphelins du volume local.

    Retourne le nombre de fichiers supprimés. `now` est injecté par
    l'appelant (scheduler) plutôt que lu via `dt.datetime.now()` ici — un
    test qui dépend de l'horloge échoue un jour sur cent (skill tests).
    """
    cutoff = now - dt.timedelta(hours=settings.audio_orphan_retention_h)
    keep = await _db_fetch_live_audio_paths(pool=pool)
    audio_dir = Path(settings.audio_volume_dir)
    deleted, reclaimed_bytes = await asyncio.to_thread(
        _file_sweep_orphans, audio_dir=audio_dir, cutoff=cutoff, keep=keep
    )
    # Décision journalisée uniquement si elle a eu un effet : une ligne par
    # run à vide noierait la seule qui compte (skill observability-logs).
    if deleted:
        log.info(
            "audio_sweeper.orphans_removed",
            deleted=deleted,
            reclaimed_bytes=reclaimed_bytes,
            retention_h=settings.audio_orphan_retention_h,
        )
    return deleted
