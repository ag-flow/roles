"""Discover command : enumerate videos in a channel/playlist via yt-dlp --flat-playlist."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from youtube.events import emit


def _format_published_at(upload_date: str | None) -> str | None:
    """Convert yt-dlp 'upload_date' (YYYYMMDD) to ISO8601 UTC."""
    if not upload_date or len(upload_date) != 8:
        return None
    return f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"


async def run(task: dict[str, Any]) -> int:
    """Discover items from a YouTube channel/playlist URL.

    Spec : docs/specs/03-scrapers.md § Format de tâche stdin (command: 'discover').
    """
    url = task["url"]
    options = task.get("options", {})
    max_items = options.get("max_items", 100)

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", str(max_items),
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await proc.communicate()

    if proc.returncode != 0:
        emit("error", error=f"yt-dlp exited {proc.returncode}")
        return 2

    items: list[dict[str, Any]] = []
    for raw in stdout.decode("utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "duration_s": item.get("duration"),
            "published_at": _format_published_at(item.get("upload_date")),
            "thumbnail_url": item.get("thumbnail"),
        })

    emit("discovered", total=len(items), items=items)
    emit("complete", discovered=len(items))
    return 0
