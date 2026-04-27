"""Instagram scraper entrypoint (stub).

Respecte le contrat stdin JSON / stdout NDJSON pour permettre à l'orchestrator
de tester le pipeline. Renvoie une erreur 'not_implemented' contrôlée plutôt
que de planter.
"""
from __future__ import annotations

import asyncio
import json
import sys


async def main() -> int:
    task_json = sys.stdin.read()
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"type": "error", "error": f"invalid JSON: {exc}"}), flush=True)
        return 1

    print(json.dumps({"type": "started", "task_id": task.get("task_id", "unknown")}), flush=True)
    print(json.dumps({
        "type": "error",
        "error": "instagram scraper not implemented (Sprint 2 stub) — yt-dlp Instagram à câbler Phase 2",
    }), flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
