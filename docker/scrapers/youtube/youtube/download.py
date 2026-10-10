"""Download command : extract audio of selected items via yt-dlp into the mounted output directory."""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from youtube.events import emit

# --- I/O de fichier bloquant dans les coroutines de ce module : exception
# VOLONTAIRE à la règle du dépôt (« jamais d'I/O bloquant dans un chemin
# asynchrone »), marquée d'un `noqa: ASYNC240` à chaque point d'application.
#
# Pourquoi elle est tenable ICI : ce module est le point d'entrée d'un
# conteneur one-shot (un `docker run` par job, cf. spec 03), dont la boucle
# asyncio n'héberge QUE ce téléchargement, traité séquentiellement item par
# item. Bloquer la boucle sur un `stat` ou un `mkdir` ne retarde donc rien
# d'autre : il n'y a rien d'autre à retarder.
#
# Ce que la règle protège, et qui ne s'applique pas ici : les services
# longue durée dont la boucle est PARTAGÉE entre requêtes ou jobs
# concurrents (le backend FastAPI, les boucles `run_loop` des workers), où
# un appel bloquant pénalise des traitements étrangers. Dans ces modules, la
# règle reste inconditionnelle — cf. `audio_sweeper._file_sweep_orphans`,
# déporté sur `asyncio.to_thread` pour exactement cette raison.
#
# L'alternative écartée : six `asyncio.to_thread` dans ce fichier. Elle
# aurait un coût de lisibilité réel pour un bénéfice nul (aucune contention
# à éviter). Le précédent de ce dépôt est `worker/main.py`
# (`audio_path.unlink(missing_ok=True)`, même marqueur).


class OutputConfigError(Exception):
    """Raised when output_cfg fails pre-flight validation (missing/unwritable dir)."""


def validate_output(output_cfg: Any) -> Path:
    """Validate output.dir before any download is attempted.

    SCRAPER_IMAGE_TAG (spec 03) lets scraper images be pinned to a tag
    independent from the backend, so a payload shaped by a mismatched
    contract version -- e.g. an 'output' block missing 'dir' -- is an
    expected failure mode, not a bug. Raise a typed error here so the caller
    can turn it into a readable 'error' event instead of an uncaught
    KeyError (missing key) or OSError (unwritable dir) surfacing mid-run.
    """
    # Under the same version skew, 'output' can be a string or a list, not a
    # dict -- .get() would then raise AttributeError, which escapes run()'s
    # `except OutputConfigError` exactly like the KeyError this guard exists
    # to forbid. Shape first, contents after.
    if not isinstance(output_cfg, dict):
        raise OutputConfigError(
            f"output doit être un objet, reçu {type(output_cfg).__name__} "
            "(contrat de payload incompatible)"
        )

    dir_value = output_cfg.get("dir")
    if not dir_value:
        raise OutputConfigError("output.dir manquant (contrat de payload incompatible)")

    output_dir = Path(dir_value)
    # is_dir + os.access : I/O bloquant assumé, cf. en-tête de module.
    if not output_dir.is_dir():  # noqa: ASYNC240
        raise OutputConfigError(f"output.dir introuvable ou n'est pas un répertoire : {output_dir}")
    if not os.access(output_dir, os.W_OK):  # noqa: ASYNC240
        raise OutputConfigError(f"output.dir non accessible en écriture : {output_dir}")
    return output_dir


def _build_yt_dlp_cmd(item_url: str, output_path: Path, options: dict[str, Any]) -> list[str]:
    audio_format = options.get("audio_format", "mp3")
    audio_quality = str(options.get("audio_quality", 9))
    audio_args = options.get("audio_args", "-ac 1 -ar 16000 -b:a 32k")
    sleep_min = str(options.get("sleep_interval_min", 3))
    sleep_max = str(options.get("sleep_interval_max", 10))
    return [
        "yt-dlp",
        "-x",
        "--audio-format", audio_format,
        "--audio-quality", audio_quality,
        "--postprocessor-args", f"ffmpeg:{audio_args}",
        "--sleep-interval", sleep_min,
        "--max-sleep-interval", sleep_max,
        "-o", str(output_path),
        item_url,
    ]


async def _download_one(
    item: dict[str, Any],
    output_dir: Path,
    prefix: str,
    options: dict[str, Any],
) -> bool:
    """Download one item straight into the mounted volume. Returns True on success."""
    item_id = item["id"]
    item_url = item["url"]
    # The extension comes from options.audio_format, not from output : that
    # field already drives yt-dlp's --audio-format below, and the actual
    # bytes written are whatever yt-dlp produced -- two fields naming the
    # same decision always drift apart, so output stays {dir, prefix} only.
    audio_format = options.get("audio_format", "mp3")
    final_path = output_dir / f"{prefix}{item_id}.{audio_format}"
    # prefix encodes {tenant_id}/v2/{source_id}/ : the subtree may not exist
    # yet for a brand new source on this volume.
    final_path.parent.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240

    # yt-dlp writes under a temp name in the SAME directory as final_path --
    # os.replace() is only atomic within one filesystem -- with a suffix
    # unique per attempt so a replay of this item_id can never collide with
    # (or clobber in place) a previous pass's file while writing.
    tmp_path = final_path.with_name(f"{final_path.name}.tmp-{uuid.uuid4().hex}")

    cmd = _build_yt_dlp_cmd(item_url, tmp_path, options)

    emit("progress", item_id=item_id, phase="downloading", percent=0)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode != 0 or not tmp_path.exists():
        # Drop the failed/partial temp file only -- never touch final_path,
        # which may still hold a valid file from an earlier successful pass.
        tmp_path.unlink(missing_ok=True)  # noqa: ASYNC240
        emit("item_failed", item_id=item_id, error=f"yt-dlp exited {proc.returncode}")
        return False

    size = tmp_path.stat().st_size  # noqa: ASYNC240
    os.replace(tmp_path, final_path)  # noqa: ASYNC240

    emit(
        "item_done",
        item_id=item_id,
        audio_path=str(final_path),
        metadata={"size_bytes": size, "format": audio_format},
    )
    return True


async def run(task: dict[str, Any]) -> int:
    """Download every item in task['items']. Returns exit code per spec § Codes de sortie."""
    items = task.get("items", [])
    options = task.get("options", {})
    # .get(), not task["output"] : under a SCRAPER_IMAGE_TAG version skew the
    # whole 'output' block can be absent, not just its 'dir' field -- that
    # must fall into the same validate_output error path, never a bare
    # KeyError from task["output"].
    output_cfg = task.get("output", {})

    try:
        output_dir = validate_output(output_cfg)
    except OutputConfigError as exc:
        emit("error", error=str(exc))
        return 1

    prefix = output_cfg.get("prefix", "")

    downloaded = 0
    failed = 0
    for item in items:
        ok = await _download_one(item, output_dir, prefix, options)
        if ok:
            downloaded += 1
        else:
            failed += 1

    emit("complete", downloaded=downloaded, failed=failed)

    if failed == 0:
        return 0
    return 3
