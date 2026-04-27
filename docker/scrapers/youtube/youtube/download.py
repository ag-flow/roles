"""Download command : extract audio of selected items via yt-dlp + upload to MinIO."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from youtube import minio_uploader
from youtube.events import emit


def _tmp_dir() -> Path:
    """Return the temp dir used for intermediate audio files (overridable in tests)."""
    return Path(tempfile.gettempdir())


def _build_yt_dlp_cmd(item_url: str, item_id: str, output_path: Path, options: dict[str, Any]) -> list[str]:
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


async def _download_one(item: dict[str, Any], output_cfg: dict[str, Any], options: dict[str, Any]) -> bool:
    """Download one item, upload, emit events. Returns True on success."""
    item_id = item["id"]
    item_url = item["url"]
    local_path = _tmp_dir() / f"{item_id}.mp3"

    cmd = _build_yt_dlp_cmd(item_url, item_id, local_path, options)

    emit("progress", item_id=item_id, phase="downloading", percent=0)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode != 0 or not local_path.exists():
        emit("item_failed", item_id=item_id, error=f"yt-dlp exited {proc.returncode}")
        return False

    s3_key = minio_uploader.upload_audio(local_path, output_cfg, item_id)
    size = local_path.stat().st_size
    local_path.unlink(missing_ok=True)

    emit(
        "item_done",
        item_id=item_id,
        audio_s3_key=s3_key,
        metadata={"size_bytes": size, "format": output_cfg.get("format", "mp3")},
    )
    return True


async def run(task: dict[str, Any]) -> int:
    """Download every item in task['items']. Returns exit code per spec § Codes de sortie."""
    items = task.get("items", [])
    options = task.get("options", {})
    output_cfg = task["output"]

    downloaded = 0
    failed = 0
    for item in items:
        ok = await _download_one(item, output_cfg, options)
        if ok:
            downloaded += 1
        else:
            failed += 1

    emit("complete", downloaded=downloaded, failed=failed)

    if failed == 0:
        return 0
    return 3
