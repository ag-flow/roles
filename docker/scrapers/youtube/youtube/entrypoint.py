"""YouTube scraper entrypoint.

Reads a task from stdin (JSON), dispatches to discover or download,
emits NDJSON events on stdout, exits with documented codes (cf. spec 03 § Codes de sortie).
"""
from __future__ import annotations

import asyncio
import json
import sys


async def main() -> int:
    """Read task from stdin and execute."""
    task_json = sys.stdin.read()
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"type": "error", "error": f"invalid JSON: {exc}"}), flush=True)
        return 1

    task_id = task.get("task_id", "unknown")
    print(json.dumps({"type": "started", "task_id": task_id}), flush=True)

    command = task.get("command")
    if command == "discover":
        from youtube import discover
        return await discover.run(task)
    elif command == "download":
        from youtube import download
        return await download.run(task)
    else:
        print(json.dumps({"type": "error", "error": f"unknown command: {command}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
