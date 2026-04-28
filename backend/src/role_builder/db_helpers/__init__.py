"""asyncpg helpers Sprint 2 — CRUD raw SQL pour sources/items/jobs/credentials.

Pas d'ORM. Une fonction = une opération. Pool injecté en argument keyword
pour faciliter les tests (stubs avec acquire/transaction).
"""

from __future__ import annotations
