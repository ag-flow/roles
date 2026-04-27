"""CLI : python -m scripts.seed_prompts (depuis le dossier backend/)."""

from __future__ import annotations

import asyncio

import asyncpg

from role_builder.config import settings
from role_builder.synthesis.prompts_seed import seed_system_prompts


async def main() -> None:
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        actions = await seed_system_prompts(pool)
        for name, action in actions.items():
            print(f"  {name}: {action}")  # noqa: T201 — CLI output intentionnel
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
