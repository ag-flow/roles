"""Réexporte la fixture `pool` (Postgres éphémère, migrations 0001..0007)
pour les tests de la façade MCP qui ont besoin d'un vrai pool asyncpg.
"""

from __future__ import annotations

from tests.services.acquisition.conftest import pool  # noqa: F401
