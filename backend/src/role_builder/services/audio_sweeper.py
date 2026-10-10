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

Ce module porte aussi `check_disk_guard` : « n'admettre un job que s'il
reste de la place sur le volume audio » est une responsabilité disque de ce
volume, au même titre que le balayage — pas une responsabilité de
`scraper_orchestrator.py`, qui construit et lance des conteneurs.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import shutil
from pathlib import Path
from typing import Any

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

_BYTES_PER_GB = 1024**3


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


def _free_disk_gb() -> float:
    """Go libres sur le volume audio. Bloquant (statvfs) : à appeler via
    `asyncio.to_thread`, jamais directement depuis une coroutine."""
    usage = shutil.disk_usage(settings.audio_volume_dir)
    return usage.free / _BYTES_PER_GB


async def check_disk_guard() -> tuple[str, dict[str, Any]] | None:
    """Garde disque avant d'admettre un nouveau job scraper (tâche 6).

    Retourne `(message_erreur, champs_a_journaliser)` si le job doit être
    refusé — répertoire inaccessible ou espace sous le seuil — sinon `None`.
    Ne journalise rien ici : l'appelant (`scraper_orchestrator`) décide seul
    du log et du marquage `failed`, pour n'avoir qu'une ligne de décision par
    refus plutôt que deux (une ici, une là) qui diraient la même chose.
    """
    try:
        free_gb = await asyncio.to_thread(_free_disk_gb)
    except OSError as exc:
        # audio_volume_dir illisible ou absent DEPUIS CE PROCESSUS (hors de
        # son contrôle : droits, montage manquant) — on ne sait donc pas
        # s'il reste de la place. Refuser plutôt que de laisser le job
        # avancer sur une garde qu'on ne peut pas vérifier (même discipline
        # fail closed que audio_volume_host_dir vide côté orchestrateur).
        err = (
            f"garde disque indisponible : {settings.audio_volume_dir} "
            f"inaccessible depuis l'orchestrateur ({exc}) — refus du job "
            "plutôt que de tourner sans visibilité sur l'espace restant"
        )
        return err, {"audio_volume_dir": settings.audio_volume_dir}
    if free_gb < settings.audio_min_free_gb:
        err = (
            f"espace disque insuffisant sur {settings.audio_volume_dir} : "
            f"{free_gb:.1f} Go libres < {settings.audio_min_free_gb} Go requis "
            "(fail closed : refus du job plutôt que de remplir le disque en silence)"
        )
        return err, {"free_gb": round(free_gb, 1), "min_free_gb": settings.audio_min_free_gb}
    return None
