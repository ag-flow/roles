# Sprint 1 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser l'infrastructure de base de Role Builder. À la fin de ce sprint, `docker compose up -d` lance Postgres+pgvector / MinIO / OpenBao / backend FastAPI / frontend Next.js, toutes les tables des specs sont créées, les buckets MinIO existent, le KV v2 OpenBao est actif, et `http://localhost:3000` affiche "Backend status: ok".

**Architecture:** Stack docker-compose mono-machine pour le dev. Backend Python 3.12 + FastAPI + asyncpg sans ORM, structlog JSON, pyproject.toml managé par uv. Frontend Next.js 14 App Router en TypeScript strict. Migrations SQL versionnées à la main dans `migrations/` à la racine. Secrets applicatifs via OpenBao KV v2 (mode dev token statique pour Sprint 1). Stockage objets via MinIO (3 buckets prêts pour les corpus). Pas d'auth pour ce sprint — CORS ouvert.

**Tech Stack:**
- Backend : FastAPI 0.110+, asyncpg 0.29+, pydantic 2.5+, pydantic-settings 2.1+, structlog 24.1+, minio-py 7.2+, httpx 0.26+
- Frontend : Next.js 14.2, React 18.3, TypeScript 5.4, Vitest 1.4, @testing-library/react 14
- Infra : Postgres 16 (image `pgvector/pgvector:pg16`), MinIO latest, OpenBao latest (mode dev)
- Tooling : uv (Python), npm, ruff, ESLint, pytest 8 + pytest-asyncio 0.23

**Décisions actées en amont** (extraits de `docs/specs/12-open-decisions.md`) :
- Image pgvector : `pgvector/pgvector:pg16` (recommandée par spec 02)
- Dimension embeddings : `vector(1024)` (présumée Mistral Embed) — confirmation Sprint 4, migration adaptable
- Auth : hors scope Sprint 1, CORS ouvert
- Mode OpenBao : dev avec token statique en env var
- Service email : hors scope (Sprint 6)
- Seed prompts système : hors scope (Sprint 5)
- Soft-deletes : hard-delete avec CASCADE pour MVP

**Critères de fin** (cf. spec 02-foundations § Critères de fin de sprint) :
- `docker compose up -d` démarre tous les services sans erreur
- `curl http://localhost:8000/health/` → `{"status":"ok","db":true}`
- `mc ls rb-local/` affiche `corpus-audio`, `corpus-transcripts`, `corpus-thumbnails`
- `bao secrets list` montre `secret/` (KV v2)
- `http://localhost:3000` affiche "Backend status: ok"
- `psql ... -c "\dt"` liste les 23 tables des specs
- Aucun fichier Python ne dépasse 300 lignes
- Logs backend en JSON

---

## File Structure

```
agflow.roles/
├── .gitignore                              # créé Phase A
├── .editorconfig                           # créé Phase A
├── .env.example                            # créé Phase A
├── docker-compose.yml                      # créé Phase F
├── README.md                               # mis à jour Phase A
│
├── backend/
│   ├── Dockerfile                          # créé Phase F
│   ├── pyproject.toml                      # créé Phase B
│   ├── .python-version                     # créé Phase B (3.12)
│   ├── src/role_builder/
│   │   ├── __init__.py                     # créé Phase B
│   │   ├── main.py                         # créé Phase B (FastAPI app + lifespan)
│   │   ├── config.py                       # créé Phase B (Pydantic Settings)
│   │   ├── logging_setup.py                # créé Phase B (structlog JSON)
│   │   ├── db.py                           # créé Phase B (asyncpg pool)
│   │   ├── routes/
│   │   │   ├── __init__.py                 # créé Phase B
│   │   │   └── health.py                   # créé Phase B
│   │   └── services/
│   │       ├── __init__.py                 # créé Phase D
│   │       ├── minio_client.py             # créé Phase D
│   │       └── openbao_client.py           # créé Phase D
│   └── tests/
│       ├── __init__.py                     # créé Phase B
│       ├── conftest.py                     # créé Phase B (fixtures)
│       ├── test_health.py                  # créé Phase B
│       ├── test_config.py                  # créé Phase B
│       ├── test_db.py                      # créé Phase B
│       ├── test_minio_client.py            # créé Phase D
│       └── test_openbao_client.py          # créé Phase D
│
├── frontend/
│   ├── Dockerfile                          # créé Phase F
│   ├── package.json                        # créé Phase E
│   ├── tsconfig.json                       # créé Phase E
│   ├── next.config.js                      # créé Phase E
│   ├── vitest.config.ts                    # créé Phase E
│   ├── .eslintrc.json                      # créé Phase E
│   └── src/
│       ├── app/
│       │   ├── layout.tsx                  # créé Phase E
│       │   └── page.tsx                    # créé Phase E
│       └── lib/
│           └── api/
│               └── health.ts               # créé Phase E
│       └── __tests__/
│           └── health.test.ts              # créé Phase E
│
├── migrations/
│   ├── 0001_extensions.sql                 # créé Phase C
│   ├── 0002_role_projects.sql              # créé Phase C
│   ├── 0003_sources_items.sql              # créé Phase C
│   ├── 0004_corpus_chunks.sql              # créé Phase C
│   ├── 0005_queues.sql                     # créé Phase C
│   ├── 0006_credentials_keys.sql           # créé Phase C
│   ├── 0007_workers.sql                    # créé Phase C
│   ├── 0008_synthesis.sql                  # créé Phase C
│   ├── 0009_publication.sql                # créé Phase C
│   ├── 0010_triggers.sql                   # créé Phase C
│   └── 0011_views.sql                      # créé Phase C
│
└── scripts/
    ├── apply_migrations.sh                 # créé Phase F
    ├── reset_db.sh                         # créé Phase F
    ├── init_minio.sh                       # créé Phase F
    └── init_openbao.sh                     # créé Phase F
```

**Total** : ~45 fichiers à créer, dont 11 SQL purs (migrations).

---

# Phase A — Bootstrap repo

Objectif : poser les fichiers à la racine qui structurent le projet (gitignore, env, README court).

## Task A1 : `.gitignore`

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Créer `.gitignore`**

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Node
node_modules/
.next/
out/
dist/
*.log

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Env
.env
.env.local
!.env.example

# Docker volumes locaux
postgres_data/
minio_data/
openbao_data/

# Plans temporaires
.tmp/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ajout .gitignore racine (Python + Node + Docker volumes)"
```

## Task A2 : `.editorconfig`

**Files:**
- Create: `.editorconfig`

- [ ] **Step 1: Créer `.editorconfig`**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{ts,tsx,js,jsx,json,yml,yaml}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
```

- [ ] **Step 2: Commit**

```bash
git add .editorconfig
git commit -m "chore: ajout .editorconfig (4 esp Python, 2 esp JS/TS/YAML)"
```

## Task A3 : `.env.example`

**Files:**
- Create: `.env.example`

Conforme à la spec 02-foundations § `.env.example`, étendu pour inclure les variables qui seront utilisées dès le début par les clients.

- [ ] **Step 1: Créer `.env.example`**

```bash
# PostgreSQL
POSTGRES_USER=rb
POSTGRES_PASSWORD=changeme_in_real_env
POSTGRES_DB=role_builder
POSTGRES_PORT=5432

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=changeme_in_real_env
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

# OpenBao (mode dev pour bootstrap, à remplacer en prod)
OPENBAO_DEV_TOKEN=dev-only-token-change-me
OPENBAO_PORT=8200

# Backend
BACKEND_PORT=8000
LOG_LEVEL=INFO
DATABASE_URL=postgresql://rb:changeme_in_real_env@localhost:5432/role_builder
MINIO_ENDPOINT=http://localhost:9000
OPENBAO_URL=http://localhost:8200

# ag.flow (utilisé Sprint 4+)
AGFLOW_BASE_URL=https://docker-agflow.yoops.org

# Frontend
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: ajout .env.example (Postgres + MinIO + OpenBao + backend + frontend)"
```

## Task A4 : Mise à jour `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Lire le README actuel pour éviter une perte**

```bash
cat README.md
```

Expected: fichier vide ou très court.

- [ ] **Step 2: Écrire le nouveau README**

```markdown
# Role Builder

Webapp pour construire des rôles ag.flow à partir de corpus audio scrapés
(YouTube / Instagram / TikTok). Pipeline complet : scraping → transcription →
chunking + embeddings → synthèse Mistral en 4 étages → export vers ag.flow.

## Documentation

- **Spec produit complète** : `docs/specs/00-overview.md` (point d'entrée)
- **Modèle de données** : `docs/specs/01-data-model.md`
- **Plans d'implémentation** : `docs/superpowers/plans/`
- **Instructions Claude Code** : `CLAUDE.md`

## Démarrage rapide

```bash
cp .env.example .env                              # Adapter les valeurs si nécessaire
docker compose up -d                              # Lance toute la stack
./scripts/apply_migrations.sh                     # Applique les migrations SQL
./scripts/init_minio.sh                           # Crée les buckets
./scripts/init_openbao.sh                         # Active KV v2

curl http://localhost:8000/health/                # Health-check backend
open http://localhost:3000                        # Interface
```

## Stack

Backend FastAPI + asyncpg | Frontend Next.js 14 | PostgreSQL 16 + pgvector |
MinIO | OpenBao | Mistral via ag.flow.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README initial (description courte + démarrage rapide)"
```

---

# Phase B — Backend skeleton

Objectif : un backend FastAPI minimal qui expose `/health/` et qui se connecte à Postgres. Tests pytest couvrent config, db pool, et endpoint health.

## Task B1 : `pyproject.toml` et `.python-version`

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`

- [ ] **Step 1: Créer `backend/.python-version`**

```
3.12
```

- [ ] **Step 2: Créer `backend/pyproject.toml`**

```toml
[project]
name = "role-builder-backend"
version = "0.1.0"
description = "Role Builder backend (FastAPI + asyncpg)"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "asyncpg>=0.29",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "structlog>=24.1",
    "minio>=7.2",
    "httpx>=0.26",
    "python-multipart>=0.0.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.2",
    "mypy>=1.8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/role_builder"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "ASYNC"]
ignore = ["E501"]  # géré par formatter

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Initialiser uv**

Run: `cd backend && uv sync --extra dev`

Expected: `uv` télécharge les deps et crée `.venv/`. Pas d'erreur.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/.python-version backend/uv.lock
git commit -m "chore(backend): pyproject.toml + uv lock initial"
```

## Task B2 : Module skeleton (init files)

**Files:**
- Create: `backend/src/role_builder/__init__.py`
- Create: `backend/src/role_builder/routes/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Créer les 3 fichiers `__init__.py`**

`backend/src/role_builder/__init__.py` :
```python
"""Role Builder backend package."""
__version__ = "0.1.0"
```

`backend/src/role_builder/routes/__init__.py` :
```python
"""HTTP routers for FastAPI app."""
```

`backend/tests/__init__.py` :
```python
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/role_builder/__init__.py backend/src/role_builder/routes/__init__.py backend/tests/__init__.py
git commit -m "chore(backend): squelette des packages Python"
```

## Task B3 : `config.py` (Pydantic Settings) — TDD

**Files:**
- Create: `backend/tests/test_config.py`
- Create: `backend/src/role_builder/config.py`

- [ ] **Step 1: Écrire le test qui échoue**

`backend/tests/test_config.py` :
```python
"""Tests for the Settings module."""
from __future__ import annotations

import os

import pytest


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads required values from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("OPENBAO_URL", "http://bao:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "token")

    from role_builder.config import Settings

    s = Settings()
    assert s.database_url == "postgresql://test:test@localhost/test"
    assert s.minio_endpoint == "http://minio:9000"
    assert s.minio_access_key == "key"
    assert s.minio_secret_key == "secret"
    assert s.openbao_url == "http://bao:8200"
    assert s.openbao_token == "token"
    assert s.log_level == "INFO"  # default
    assert s.agflow_base_url == "https://docker-agflow.yoops.org"  # default
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd backend && uv run pytest tests/test_config.py -v`

Expected: FAIL avec `ModuleNotFoundError: No module named 'role_builder.config'`.

- [ ] **Step 3: Écrire l'implémentation**

`backend/src/role_builder/config.py` :
```python
"""Application configuration via environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    openbao_url: str
    openbao_token: str

    agflow_base_url: str = "https://docker-agflow.yoops.org"
    log_level: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
```

> Le `# type: ignore[call-arg]` est nécessaire parce que pydantic-settings
> charge les valeurs au runtime via env vars et que mypy ne le voit pas.

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd backend && uv run pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Lint**

Run: `cd backend && uv run ruff check src/ tests/`

Expected: pas d'erreur.

- [ ] **Step 6: Commit**

```bash
git add backend/src/role_builder/config.py backend/tests/test_config.py
git commit -m "feat(backend): config Pydantic Settings (DATABASE_URL, MinIO, OpenBao, ag.flow)"
```

## Task B4 : `logging_setup.py` (structlog JSON)

**Files:**
- Create: `backend/src/role_builder/logging_setup.py`

Pas de test unitaire pour structlog (couverture par les tests d'intégration de l'app), mais on vérifie le format JSON manuellement à la fin.

- [ ] **Step 1: Écrire l'implémentation**

`backend/src/role_builder/logging_setup.py` :
```python
"""Structlog JSON logging setup."""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit JSON on stdout."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 2: Lint**

Run: `cd backend && uv run ruff check src/role_builder/logging_setup.py`

Expected: pas d'erreur.

- [ ] **Step 3: Commit**

```bash
git add backend/src/role_builder/logging_setup.py
git commit -m "feat(backend): structlog JSON renderer (timestamp ISO UTC + log level)"
```

## Task B5 : `db.py` (asyncpg pool) — TDD

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_db.py`
- Create: `backend/src/role_builder/db.py`

> **Note** : ce test ne nécessite PAS de Postgres réel — on teste l'API du wrapper, pas la connectivité (couverte plus tard par le test d'intégration `test_health`).

- [ ] **Step 1: Écrire le test qui échoue**

`backend/tests/test_db.py` :
```python
"""Tests for the asyncpg pool wrapper."""
from __future__ import annotations

import pytest

from role_builder.db import DBPool


def test_db_pool_starts_disconnected() -> None:
    """A fresh DBPool has no active pool."""
    pool = DBPool()
    with pytest.raises(RuntimeError, match="not connected"):
        _ = pool.pool
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd backend && uv run pytest tests/test_db.py -v`

Expected: FAIL avec `ModuleNotFoundError: No module named 'role_builder.db'`.

- [ ] **Step 3: Écrire l'implémentation**

`backend/src/role_builder/db.py` :
```python
"""Async PostgreSQL connection pool."""
from __future__ import annotations

import asyncpg

from role_builder.config import settings


class DBPool:
    """Wrapper around asyncpg pool tied to the app lifespan."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create the pool. Called once at app startup."""
        self._pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Close the pool. Called once at app shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Return the active pool. Raises RuntimeError if disconnected."""
        if self._pool is None:
            raise RuntimeError("DB pool not connected")
        return self._pool


db_pool = DBPool()
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd backend && uv run pytest tests/test_db.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/db.py backend/tests/test_db.py
git commit -m "feat(backend): asyncpg pool wrapper (DBPool avec lifecycle connect/disconnect)"
```

## Task B6 : `routes/health.py` — TDD

**Files:**
- Create: `backend/tests/test_health.py`
- Create: `backend/src/role_builder/routes/health.py`
- Create: `backend/src/role_builder/main.py`

> Le test instancie l'app FastAPI complète et utilise un mock du pool DB
> pour ne pas dépendre d'une instance Postgres pendant les tests unitaires.

- [ ] **Step 1: Écrire le test qui échoue**

`backend/tests/test_health.py` :
```python
"""Tests for the /health endpoint."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


class _StubConn:
    async def fetchval(self, query: str) -> int:
        assert query == "SELECT 1"
        return 1


class _StubAcquireCtx:
    async def __aenter__(self) -> _StubConn:
        return _StubConn()

    async def __aexit__(self, *args: Any) -> None:
        return None


class _StubPool:
    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient with a stubbed DB pool."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://stub")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "stub")
    monkeypatch.setenv("MINIO_SECRET_KEY", "stub")
    monkeypatch.setenv("OPENBAO_URL", "http://stub")
    monkeypatch.setenv("OPENBAO_TOKEN", "stub")

    from role_builder import db as db_module
    from role_builder.main import app

    monkeypatch.setattr(db_module.db_pool, "_pool", _StubPool(), raising=False)
    return TestClient(app)


def test_health_returns_ok(client: TestClient) -> None:
    """/health/ returns ok when DB responds."""
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True}
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd backend && uv run pytest tests/test_health.py -v`

Expected: FAIL (modules `role_builder.routes.health` ou `role_builder.main` introuvables).

- [ ] **Step 3: Écrire `routes/health.py`**

`backend/src/role_builder/routes/health.py` :
```python
"""Health-check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from role_builder.db import db_pool

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, object]:
    """Return ok when the app and DB are reachable."""
    async with db_pool.pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    return {"status": "ok", "db": result == 1}
```

- [ ] **Step 4: Écrire `main.py`**

`backend/src/role_builder/main.py` :
```python
"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from role_builder.config import settings
from role_builder.db import db_pool
from role_builder.logging_setup import configure_logging
from role_builder.routes import health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    configure_logging(settings.log_level)
    if db_pool._pool is None:  # noqa: SLF001 — autorise injection en tests
        await db_pool.connect()
    try:
        yield
    finally:
        if db_pool._pool is not None:  # noqa: SLF001
            await db_pool.disconnect()


app = FastAPI(
    title="Role Builder API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # à restreindre en prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
```

- [ ] **Step 5: Vérifier que le test passe**

Run: `cd backend && uv run pytest tests/test_health.py -v`

Expected: PASS.

- [ ] **Step 6: Lint global**

Run: `cd backend && uv run ruff check src/ tests/`

Expected: pas d'erreur.

- [ ] **Step 7: Commit**

```bash
git add backend/src/role_builder/main.py backend/src/role_builder/routes/health.py backend/tests/test_health.py
git commit -m "feat(backend): app FastAPI + endpoint /health/ avec test stubbé"
```

## Task B7 : conftest commun

**Files:**
- Create: `backend/tests/conftest.py`

Mutualise la fixture `client` pour les tests à venir.

- [ ] **Step 1: Refactorer la fixture vers conftest**

`backend/tests/conftest.py` :
```python
"""Shared pytest fixtures."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


class _StubConn:
    async def fetchval(self, query: str) -> int:
        assert query == "SELECT 1"
        return 1


class _StubAcquireCtx:
    async def __aenter__(self) -> _StubConn:
        return _StubConn()

    async def __aexit__(self, *args: Any) -> None:
        return None


class _StubPool:
    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx()


@pytest.fixture()
def stubbed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the minimal env vars required by Settings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://stub")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "stub")
    monkeypatch.setenv("MINIO_SECRET_KEY", "stub")
    monkeypatch.setenv("OPENBAO_URL", "http://stub")
    monkeypatch.setenv("OPENBAO_TOKEN", "stub")


@pytest.fixture()
def client(stubbed_env: None, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient with a stubbed DB pool."""
    from role_builder import db as db_module
    from role_builder.main import app

    monkeypatch.setattr(db_module.db_pool, "_pool", _StubPool(), raising=False)
    return TestClient(app)
```

- [ ] **Step 2: Simplifier `tests/test_health.py`** pour réutiliser la fixture

Remplacer le contenu de `backend/tests/test_health.py` :
```python
"""Tests for the /health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """/health/ returns ok when DB responds."""
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True}
```

- [ ] **Step 3: Vérifier que tous les tests passent**

Run: `cd backend && uv run pytest -v`

Expected: PASS — `test_config.py`, `test_db.py`, `test_health.py`.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_health.py
git commit -m "refactor(backend): mutualisation fixture client dans conftest.py"
```

---

# Phase C — Migrations SQL

Objectif : 11 fichiers SQL versionnés qui matérialisent intégralement le schéma de `01-data-model.md`. Aucun test unitaire — la vérification se fait à la fin du sprint via `psql ... -c "\dt"` qui doit lister les 23 tables.

> **Convention** : un fichier = une zone fonctionnelle. Dépendances entre tables résolues en gardant l'ordre numérique. `gen_random_uuid()` provient de `pgcrypto`, donc 0001 doit s'appliquer avant tout INSERT/CREATE qui en dépend.

## Task C1 : `0001_extensions.sql`

**Files:**
- Create: `migrations/0001_extensions.sql`

- [ ] **Step 1: Créer `migrations/0001_extensions.sql`**

```sql
-- Migration 0001 : Extensions PostgreSQL requises.
-- Référence : docs/specs/01-data-model.md § Extensions PostgreSQL requises.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0001_extensions.sql
git commit -m "feat(db): migration 0001 extensions (uuid-ossp, pgcrypto, vector)"
```

## Task C2 : `0002_role_projects.sql`

**Files:**
- Create: `migrations/0002_role_projects.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0002 : Table role_projects.
-- Référence : docs/specs/01-data-model.md § role_projects.

CREATE TABLE role_projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    display_name text NOT NULL,
    description text,
    target_role_id text,
    identity text,
    global_directives text,
    language text,
    mistral_secret_ref text,
    is_public boolean DEFAULT false,
    keep_audio boolean DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX role_projects_tenant_user_idx ON role_projects (tenant_id, user_id);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0002_role_projects.sql
git commit -m "feat(db): migration 0002 table role_projects"
```

## Task C3 : `0003_sources_items.sql`

**Files:**
- Create: `migrations/0003_sources_items.sql`

> **Note** : la table `user_credentials` est référencée par `sources.credentials_id`,
> mais elle est créée plus tard (migration 0006). On déclare la FK sans contrainte
> ici, et on l'ajoute en 0006 via `ALTER TABLE`. Cela évite de réordonner les
> migrations.

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0003 : Tables sources et source_items.
-- Référence : docs/specs/01-data-model.md § sources, source_items.

CREATE TABLE sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    platform text NOT NULL,
    source_type text NOT NULL,
    url text NOT NULL,
    credentials_id uuid,  -- FK ajoutée en 0006 (user_credentials pas encore créée)
    status text NOT NULL DEFAULT 'pending_discovery',
    discovered_count integer,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sources_role_project_idx ON sources (role_project_id);

CREATE TABLE source_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    platform_item_id text NOT NULL,
    title text,
    duration_s integer,
    published_at timestamptz,
    thumbnail_url text,
    status text NOT NULL,
    audio_s3_key text,
    transcript_s3_key text,
    selected boolean DEFAULT false,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, platform_item_id)
);

CREATE INDEX source_items_source_status_idx ON source_items (source_id, status);
CREATE INDEX source_items_tenant_idx ON source_items (tenant_id);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0003_sources_items.sql
git commit -m "feat(db): migration 0003 tables sources + source_items"
```

## Task C4 : `0004_corpus_chunks.sql`

**Files:**
- Create: `migrations/0004_corpus_chunks.sql`

> Dimension du `vector` : 1024 (Mistral Embed présumée). Si Sprint 4 confirme
> une autre dimension, créer une nouvelle migration `00XX_resize_chunks_vector.sql`
> qui modifie la colonne ; les embeddings de test seront re-générés.

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0004 : Table corpus_chunks (chunks indexés via pgvector).
-- Référence : docs/specs/01-data-model.md § corpus_chunks.
-- Dimension vecteur 1024 = Mistral Embed (à confirmer Sprint 4).

CREATE TABLE corpus_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    start_s real,
    end_s real,
    text text NOT NULL,
    embedding vector(1024),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX corpus_chunks_role_project_idx ON corpus_chunks (role_project_id);

-- L'index ivfflat est inefficace tant qu'il y a peu de lignes.
-- À créer ou recréer (REINDEX) après ingestion d'un premier corpus.
CREATE INDEX corpus_chunks_embedding_idx
    ON corpus_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0004_corpus_chunks.sql
git commit -m "feat(db): migration 0004 corpus_chunks (vector(1024) + index ivfflat)"
```

## Task C5 : `0005_queues.sql`

**Files:**
- Create: `migrations/0005_queues.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0005 : Tables des queues (scraping, transcription, chunking).
-- Référence : docs/specs/01-data-model.md § Section 2.

CREATE TABLE scraping_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_item_id uuid REFERENCES source_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    credentials_id uuid,  -- FK ajoutée en 0006
    command text NOT NULL,
    status text NOT NULL,
    priority integer DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    max_attempts integer DEFAULT 3,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX scraping_jobs_status_priority_idx
    ON scraping_jobs (status, priority DESC, created_at)
    WHERE status = 'pending';

CREATE TABLE transcription_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    audio_s3_key text NOT NULL,
    language text,
    worker_pool_id text NOT NULL,
    status text NOT NULL,
    priority integer DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    max_attempts integer DEFAULT 3,
    provider_used text,
    cost_estimate_usd real,
    cost_actual_usd real,
    error text,
    error_history jsonb DEFAULT '[]'::jsonb,
    result_s3_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX transcription_jobs_pool_status_idx
    ON transcription_jobs (worker_pool_id, status, created_at);

CREATE TABLE chunking_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id uuid NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    transcript_s3_key text NOT NULL,
    status text NOT NULL,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    attempts integer DEFAULT 0,
    error text,
    chunks_produced integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX chunking_jobs_status_idx
    ON chunking_jobs (status, created_at)
    WHERE status = 'pending';
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0005_queues.sql
git commit -m "feat(db): migration 0005 queues (scraping_jobs + transcription_jobs + chunking_jobs)"
```

## Task C6 : `0006_credentials_keys.sql`

**Files:**
- Create: `migrations/0006_credentials_keys.sql`

> Cette migration ajoute aussi les FK différées de `sources.credentials_id` et
> `scraping_jobs.credentials_id` qui pointent vers `user_credentials`.

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0006 : Tables des credentials et clés API.
-- Référence : docs/specs/01-data-model.md § Section 3.

CREATE TABLE user_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    platform text NOT NULL,
    label text,
    openbao_path text NOT NULL,
    status text NOT NULL,
    last_validated_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_credentials_user_platform_idx
    ON user_credentials (user_id, platform, status);

ALTER TABLE sources
    ADD CONSTRAINT sources_credentials_fk
    FOREIGN KEY (credentials_id) REFERENCES user_credentials(id);

ALTER TABLE scraping_jobs
    ADD CONSTRAINT scraping_jobs_credentials_fk
    FOREIGN KEY (credentials_id) REFERENCES user_credentials(id);

CREATE TABLE user_transcription_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    provider text NOT NULL,
    label text,
    openbao_path text NOT NULL,
    status text NOT NULL,
    is_primary boolean DEFAULT false,
    is_fallback boolean DEFAULT false,
    workers_count integer DEFAULT 1 CHECK (workers_count BETWEEN 1 AND 5),
    monthly_cap_usd real,
    current_month_spend_usd real DEFAULT 0,
    current_balance_usd real,
    last_balance_check_at timestamptz,
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX user_transcription_keys_one_primary_per_user
    ON user_transcription_keys (tenant_id, user_id)
    WHERE is_primary = true AND status = 'active';

CREATE INDEX user_transcription_keys_user_idx
    ON user_transcription_keys (user_id, status);

CREATE TABLE github_integrations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL UNIQUE,
    github_login text NOT NULL,
    github_user_id bigint NOT NULL,
    openbao_path text NOT NULL,
    scope text NOT NULL,
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0006_credentials_keys.sql
git commit -m "feat(db): migration 0006 credentials (user_credentials + transcription_keys + github_integrations)"
```

## Task C7 : `0007_workers.sql`

**Files:**
- Create: `migrations/0007_workers.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0007 : Table transcription_workers (gestion des containers workers).
-- Référence : docs/specs/01-data-model.md § Section 4.

CREATE TABLE transcription_workers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_pool_id text NOT NULL,
    container_id text,
    container_name text,
    provider text,
    status text NOT NULL,
    last_activity_at timestamptz,
    started_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz,
    host text
);

CREATE INDEX transcription_workers_pool_status_idx
    ON transcription_workers (worker_pool_id, status);

CREATE INDEX transcription_workers_idle_idx
    ON transcription_workers (last_activity_at)
    WHERE status = 'idle';
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0007_workers.sql
git commit -m "feat(db): migration 0007 transcription_workers"
```

## Task C8 : `0008_synthesis.sql`

**Files:**
- Create: `migrations/0008_synthesis.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0008 : Tables du pipeline de synthèse.
-- Référence : docs/specs/01-data-model.md § Section 5.

CREATE TABLE prompts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    type text NOT NULL,
    target_section text,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prompt_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id uuid NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    template text NOT NULL,
    parameters_schema jsonb,
    is_system_default boolean DEFAULT false,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (prompt_id, version_number)
);

CREATE UNIQUE INDEX prompt_versions_one_system_default
    ON prompt_versions (prompt_id)
    WHERE is_system_default = true;

CREATE TABLE runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    prompt_version_id uuid NOT NULL REFERENCES prompt_versions(id),
    input_summary jsonb,
    parameters jsonb,
    instruction_override text,
    status text NOT NULL,
    output text,
    llm_provider text,
    llm_model text,
    tokens_input integer,
    tokens_output integer,
    cost_usd real,
    started_at timestamptz,
    completed_at timestamptz,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX runs_project_status_idx
    ON runs (role_project_id, status, created_at DESC);

CREATE TABLE signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    source_item_id uuid REFERENCES source_items(id),
    source_chunks uuid[],
    type text NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX signals_project_type_idx ON signals (role_project_id, type);

CREATE TABLE clusters (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    signal_ids uuid[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX clusters_project_idx ON clusters (role_project_id);

CREATE TABLE document_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    section text NOT NULL,
    planned_documents jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX document_plans_project_section_idx
    ON document_plans (role_project_id, section);

CREATE TABLE role_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    section text NOT NULL,
    name text NOT NULL,
    content text NOT NULL,
    source_run_id uuid REFERENCES runs(id),
    version integer NOT NULL DEFAULT 1,
    is_current boolean DEFAULT false,
    locked boolean DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX role_documents_current_unique
    ON role_documents (role_project_id, section, name)
    WHERE is_current = true;

CREATE INDEX role_documents_project_idx ON role_documents (role_project_id);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0008_synthesis.sql
git commit -m "feat(db): migration 0008 synthèse (prompts + versions + runs + signals + clusters + document_plans + role_documents)"
```

## Task C9 : `0009_publication.sql`

**Files:**
- Create: `migrations/0009_publication.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0009 : Tables de publication GitHub.
-- Référence : docs/specs/01-data-model.md § role_publication_config, role_publications.

CREATE TABLE role_publication_config (
    role_project_id uuid PRIMARY KEY REFERENCES role_projects(id) ON DELETE CASCADE,
    repo_full_name text NOT NULL,
    target_subdirectory text NOT NULL,
    branch text DEFAULT 'main',
    commit_message_template text DEFAULT 'Update role {role_name}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE role_publications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_project_id uuid NOT NULL REFERENCES role_projects(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    commit_sha text NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    files_count integer,
    summary text
);

CREATE INDEX role_publications_project_idx
    ON role_publications (role_project_id, published_at DESC);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0009_publication.sql
git commit -m "feat(db): migration 0009 publication (role_publication_config + role_publications)"
```

## Task C10 : `0010_triggers.sql`

**Files:**
- Create: `migrations/0010_triggers.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0010 : Fonction notify_event + triggers PG NOTIFY.
-- Référence : docs/specs/01-data-model.md § Section 6.

CREATE OR REPLACE FUNCTION notify_event() RETURNS trigger AS $$
DECLARE
    channel text;
    payload jsonb;
BEGIN
    channel := TG_ARGV[0];
    payload := jsonb_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'tenant_id', NEW.tenant_id,
        'id', NEW.id,
        'status', NEW.status
    );
    PERFORM pg_notify(channel, payload::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER source_items_notify
    AFTER UPDATE OF status ON source_items
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('source_items_changes');

CREATE TRIGGER runs_notify
    AFTER INSERT OR UPDATE OF status ON runs
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('runs_changes');

CREATE TRIGGER workers_notify
    AFTER UPDATE OF status ON transcription_workers
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('workers_changes');

CREATE TRIGGER keys_notify
    AFTER UPDATE OF status ON user_transcription_keys
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('keys_changes');
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0010_triggers.sql
git commit -m "feat(db): migration 0010 fonction notify_event + 4 triggers PG NOTIFY"
```

## Task C11 : `0011_views.sql`

**Files:**
- Create: `migrations/0011_views.sql`

- [ ] **Step 1: Créer le fichier**

```sql
-- Migration 0011 : Vues utiles pour l'UI.
-- Référence : docs/specs/01-data-model.md § Section 7.

CREATE VIEW v_role_project_summary AS
SELECT
    rp.id,
    rp.tenant_id,
    rp.user_id,
    rp.display_name,
    rp.description,
    rp.is_public,
    rp.created_at,
    rp.updated_at,
    COUNT(DISTINCT s.id) AS sources_count,
    COUNT(DISTINCT si.id) FILTER (WHERE si.status = 'indexed') AS items_indexed,
    COUNT(DISTINCT si.id) AS items_total,
    COUNT(DISTINCT cc.id) AS chunks_count,
    COUNT(DISTINCT rd.id) FILTER (WHERE rd.is_current) AS documents_count,
    rp.target_role_id IS NOT NULL AS pushed_to_agflow
FROM role_projects rp
LEFT JOIN sources s ON s.role_project_id = rp.id
LEFT JOIN source_items si ON si.source_id = s.id
LEFT JOIN corpus_chunks cc ON cc.role_project_id = rp.id
LEFT JOIN role_documents rd ON rd.role_project_id = rp.id
GROUP BY rp.id;
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0011_views.sql
git commit -m "feat(db): migration 0011 vue v_role_project_summary"
```

---

# Phase D — Services backend (clients MinIO + OpenBao)

Objectif : deux clients minimalistes (`minio_client.py`, `openbao_client.py`) testés et prêts pour les sprints suivants.

## Task D1 : `services/__init__.py`

**Files:**
- Create: `backend/src/role_builder/services/__init__.py`

- [ ] **Step 1: Créer le fichier**

```python
"""Backend services (clients externes, workers, helpers métier)."""
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/role_builder/services/__init__.py
git commit -m "chore(backend): paquet services/"
```

## Task D2 : `openbao_client.py` — TDD

**Files:**
- Create: `backend/tests/test_openbao_client.py`
- Create: `backend/src/role_builder/services/openbao_client.py`

> On teste l'API du client en mockant `httpx.AsyncClient` via `respx`. Pour
> garder les deps minimales, on utilise `pytest-asyncio` et un stub maison.

- [ ] **Step 1: Écrire le test qui échoue**

`backend/tests/test_openbao_client.py` :
```python
"""Tests for the OpenBao client."""
from __future__ import annotations

from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int, json_body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._json = json_body or {}

    def json(self) -> dict[str, Any]:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class _StubHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.next_response: _StubResponse | None = None

    async def post(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append(("POST", url, kwargs))
        return self.next_response or _StubResponse(200)

    async def get(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append(("GET", url, kwargs))
        return self.next_response or _StubResponse(200, {"data": {"data": {"foo": "bar"}}})

    async def delete(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append(("DELETE", url, kwargs))
        return self.next_response or _StubResponse(204)

    async def aclose(self) -> None: ...


@pytest.mark.asyncio
async def test_put_calls_post_with_data_envelope(stubbed_env: None) -> None:
    """OpenBaoClient.put POSTs to /v1/secret/data/{path} with KV v2 envelope."""
    from role_builder.services.openbao_client import OpenBaoClient

    client = OpenBaoClient()
    stub = _StubHttp()
    client._http = stub  # type: ignore[assignment]

    await client.put("foo/bar", {"key": "value"})

    method, url, kwargs = stub.calls[0]
    assert method == "POST"
    assert url == "/v1/secret/data/foo/bar"
    assert kwargs["json"] == {"data": {"key": "value"}}


@pytest.mark.asyncio
async def test_get_returns_inner_data(stubbed_env: None) -> None:
    """OpenBaoClient.get returns the inner data dict."""
    from role_builder.services.openbao_client import OpenBaoClient

    client = OpenBaoClient()
    client._http = _StubHttp()  # type: ignore[assignment]
    result = await client.get("foo/bar")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_returns_none_on_404(stubbed_env: None) -> None:
    """OpenBaoClient.get returns None when the secret doesn't exist."""
    from role_builder.services.openbao_client import OpenBaoClient

    client = OpenBaoClient()
    stub = _StubHttp()
    stub.next_response = _StubResponse(404)
    client._http = stub  # type: ignore[assignment]
    result = await client.get("missing")
    assert result is None
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd backend && uv run pytest tests/test_openbao_client.py -v`

Expected: FAIL — module introuvable.

- [ ] **Step 3: Écrire l'implémentation**

`backend/src/role_builder/services/openbao_client.py` :
```python
"""Async client for OpenBao KV v2 secrets engine."""
from __future__ import annotations

import httpx

from role_builder.config import settings


class OpenBaoClient:
    """Minimal async wrapper around OpenBao KV v2 HTTP API."""

    def __init__(self) -> None:
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.openbao_url,
            headers={"X-Vault-Token": settings.openbao_token},
            timeout=10.0,
        )

    async def put(self, path: str, data: dict[str, object]) -> None:
        """Store a secret at `secret/data/{path}` using the KV v2 envelope."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.post(url, json={"data": data})
        resp.raise_for_status()

    async def get(self, path: str) -> dict[str, object] | None:
        """Read a secret. Returns None if it doesn't exist (404)."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.json()
        return body["data"]["data"]

    async def delete(self, path: str) -> None:
        """Soft-delete the latest version of a secret."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.delete(url)
        if resp.status_code not in (200, 204):
            resp.raise_for_status()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()


openbao = OpenBaoClient()
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd backend && uv run pytest tests/test_openbao_client.py -v`

Expected: PASS — 3 tests verts.

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/services/openbao_client.py backend/tests/test_openbao_client.py
git commit -m "feat(backend): client OpenBao KV v2 (put + get + delete)"
```

## Task D3 : `minio_client.py` — TDD

**Files:**
- Create: `backend/tests/test_minio_client.py`
- Create: `backend/src/role_builder/services/minio_client.py`

> On encapsule la lib `minio` dans un wrapper qui expose les opérations
> dont les sprints suivants auront besoin : upload bytes, download bytes,
> presigned URL, ensure bucket exists. Les tests stubent l'objet `Minio`
> sous-jacent.

- [ ] **Step 1: Écrire le test qui échoue**

`backend/tests/test_minio_client.py` :
```python
"""Tests for the MinIO client wrapper."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest


class _StubMinio:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.last_presigned: tuple[str, str, int] | None = None

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(
        self,
        bucket: str,
        key: str,
        data: BytesIO,
        length: int,
        content_type: str | None = None,
    ) -> None:
        self.objects[(bucket, key)] = data.read()

    def get_object(self, bucket: str, key: str) -> Any:
        class _Resp:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def close(self) -> None: ...
            def release_conn(self) -> None: ...

        return _Resp(self.objects[(bucket, key)])

    def presigned_get_object(self, bucket: str, key: str, expires: Any) -> str:
        self.last_presigned = (bucket, key, int(expires.total_seconds()))
        return f"http://stub/{bucket}/{key}?signed"


@pytest.fixture()
def stub_minio(stubbed_env: None) -> _StubMinio:
    return _StubMinio()


def test_ensure_bucket_creates_when_missing(stub_minio: _StubMinio) -> None:
    """ensure_bucket creates the bucket if it doesn't exist."""
    from role_builder.services.minio_client import MinioWrapper

    wrapper = MinioWrapper(client=stub_minio)
    wrapper.ensure_bucket("corpus-audio")
    assert "corpus-audio" in stub_minio.buckets


def test_ensure_bucket_noop_when_exists(stub_minio: _StubMinio) -> None:
    """ensure_bucket does nothing if the bucket already exists."""
    from role_builder.services.minio_client import MinioWrapper

    stub_minio.buckets.add("corpus-audio")
    wrapper = MinioWrapper(client=stub_minio)
    wrapper.ensure_bucket("corpus-audio")
    assert stub_minio.buckets == {"corpus-audio"}


def test_upload_bytes_round_trip(stub_minio: _StubMinio) -> None:
    """Upload then download returns the same bytes."""
    from role_builder.services.minio_client import MinioWrapper

    wrapper = MinioWrapper(client=stub_minio)
    stub_minio.buckets.add("corpus-audio")
    wrapper.upload_bytes("corpus-audio", "k.mp3", b"hello", "audio/mpeg")
    assert wrapper.download_bytes("corpus-audio", "k.mp3") == b"hello"


def test_presigned_get_url_uses_seconds(stub_minio: _StubMinio) -> None:
    """presigned_get_url passes expires as a timedelta."""
    from role_builder.services.minio_client import MinioWrapper

    wrapper = MinioWrapper(client=stub_minio)
    url = wrapper.presigned_get_url("corpus-audio", "k.mp3", expires_seconds=900)
    assert url == "http://stub/corpus-audio/k.mp3?signed"
    assert stub_minio.last_presigned == ("corpus-audio", "k.mp3", 900)
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd backend && uv run pytest tests/test_minio_client.py -v`

Expected: FAIL — module introuvable.

- [ ] **Step 3: Écrire l'implémentation**

`backend/src/role_builder/services/minio_client.py` :
```python
"""MinIO client wrapper for object storage operations."""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from typing import Protocol
from urllib.parse import urlparse

from minio import Minio

from role_builder.config import settings


class _MinioLike(Protocol):
    def bucket_exists(self, bucket: str) -> bool: ...
    def make_bucket(self, bucket: str) -> None: ...
    def put_object(
        self,
        bucket: str,
        key: str,
        data: BytesIO,
        length: int,
        content_type: str | None = ...,
    ) -> None: ...
    def get_object(self, bucket: str, key: str) -> object: ...
    def presigned_get_object(self, bucket: str, key: str, expires: timedelta) -> str: ...


def _build_minio_client() -> Minio:
    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


class MinioWrapper:
    """Thin wrapper around `minio.Minio` exposing the operations Role Builder needs."""

    def __init__(self, client: _MinioLike | None = None) -> None:
        self._client: _MinioLike = client or _build_minio_client()

    def ensure_bucket(self, bucket: str) -> None:
        """Create the bucket if it doesn't already exist."""
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        payload: bytes,
        content_type: str | None = None,
    ) -> None:
        """Upload a byte payload at `bucket/key`."""
        buf = BytesIO(payload)
        self._client.put_object(bucket, key, buf, len(payload), content_type=content_type)

    def download_bytes(self, bucket: str, key: str) -> bytes:
        """Download an object's bytes."""
        resp = self._client.get_object(bucket, key)
        try:
            return resp.read()  # type: ignore[no-any-return]
        finally:
            close = getattr(resp, "close", None)
            release = getattr(resp, "release_conn", None)
            if callable(close):
                close()
            if callable(release):
                release()

    def presigned_get_url(
        self,
        bucket: str,
        key: str,
        *,
        expires_seconds: int = 900,
    ) -> str:
        """Generate a presigned GET URL valid for `expires_seconds`."""
        return self._client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=expires_seconds)
        )


minio_client = MinioWrapper()
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd backend && uv run pytest tests/test_minio_client.py -v`

Expected: PASS — 4 tests verts.

- [ ] **Step 5: Lancer toute la suite**

Run: `cd backend && uv run pytest -v && uv run ruff check src/ tests/`

Expected: PASS sur l'intégralité, pas de warning ruff.

- [ ] **Step 6: Commit**

```bash
git add backend/src/role_builder/services/minio_client.py backend/tests/test_minio_client.py
git commit -m "feat(backend): wrapper MinIO (ensure_bucket + upload + download + presigned URL)"
```

---

# Phase E — Frontend skeleton

Objectif : Next.js 14 App Router minimal qui interroge `/health/` du backend et affiche le statut.

## Task E1 : `package.json`

**Files:**
- Create: `frontend/package.json`

- [ ] **Step 1: Créer le fichier**

```json
{
  "name": "role-builder-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "next": "14.2.0",
    "react": "18.3.0",
    "react-dom": "18.3.0"
  },
  "devDependencies": {
    "@testing-library/react": "14.2.1",
    "@testing-library/jest-dom": "6.4.2",
    "@types/node": "20.11.0",
    "@types/react": "18.3.0",
    "@types/react-dom": "18.3.0",
    "@vitejs/plugin-react": "4.2.1",
    "eslint": "8.57.0",
    "eslint-config-next": "14.2.0",
    "jsdom": "24.0.0",
    "typescript": "5.4.0",
    "vitest": "1.4.0"
  }
}
```

- [ ] **Step 2: Installer**

Run: `cd frontend && npm install`

Expected: `npm` génère `package-lock.json` et `node_modules/`.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): package.json initial (Next.js 14 + React 18 + Vitest 1.4)"
```

## Task E2 : `tsconfig.json`

**Files:**
- Create: `frontend/tsconfig.json`

- [ ] **Step 1: Créer le fichier**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/tsconfig.json
git commit -m "chore(frontend): tsconfig.json strict (noUncheckedIndexedAccess true)"
```

## Task E3 : `next.config.js` et `.eslintrc.json`

**Files:**
- Create: `frontend/next.config.js`
- Create: `frontend/.eslintrc.json`

- [ ] **Step 1: Créer `next.config.js`**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000'}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
```

- [ ] **Step 2: Créer `.eslintrc.json`**

```json
{
  "extends": "next/core-web-vitals"
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/next.config.js frontend/.eslintrc.json
git commit -m "chore(frontend): next.config.js (rewrites /api → backend) + eslint"
```

## Task E4 : `vitest.config.ts`

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`

- [ ] **Step 1: Créer `frontend/vitest.config.ts`**

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
```

- [ ] **Step 2: Créer `frontend/src/test/setup.ts`**

```typescript
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 3: Commit**

```bash
git add frontend/vitest.config.ts frontend/src/test/setup.ts
git commit -m "chore(frontend): config vitest (jsdom + jest-dom matchers)"
```

## Task E5 : Health API client + test

**Files:**
- Create: `frontend/src/__tests__/health.test.ts`
- Create: `frontend/src/lib/api/health.ts`

- [ ] **Step 1: Écrire le test qui échoue**

`frontend/src/__tests__/health.test.ts` :
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchHealth } from '@/lib/api/health';

describe('fetchHealth', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('renvoie le payload quand le backend répond ok', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', db: true }),
    } as Response));

    const result = await fetchHealth('http://api.test');
    expect(result).toEqual({ status: 'ok', db: true });
  });

  it('renvoie unreachable si le fetch échoue', async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error('connection refused');
    });

    const result = await fetchHealth('http://api.test');
    expect(result).toEqual({ status: 'unreachable', db: false });
  });

  it('renvoie unreachable si le backend renvoie 5xx', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'unavailable' }),
    } as Response));

    const result = await fetchHealth('http://api.test');
    expect(result).toEqual({ status: 'unreachable', db: false });
  });
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd frontend && npm test`

Expected: FAIL — module `@/lib/api/health` introuvable.

- [ ] **Step 3: Écrire l'implémentation**

`frontend/src/lib/api/health.ts` :
```typescript
export interface HealthPayload {
  status: 'ok' | 'unreachable';
  db: boolean;
}

export async function fetchHealth(apiUrl: string): Promise<HealthPayload> {
  try {
    const resp = await fetch(`${apiUrl}/health/`, { cache: 'no-store' });
    if (!resp.ok) {
      return { status: 'unreachable', db: false };
    }
    const body = await resp.json();
    return { status: body.status === 'ok' ? 'ok' : 'unreachable', db: Boolean(body.db) };
  } catch {
    return { status: 'unreachable', db: false };
  }
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd frontend && npm test`

Expected: PASS — 3 tests verts.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/health.ts frontend/src/__tests__/health.test.ts
git commit -m "feat(frontend): client API health avec gestion erreurs (3 tests Vitest)"
```

## Task E6 : Layout + page d'accueil

**Files:**
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`

- [ ] **Step 1: Créer `layout.tsx`**

```tsx
import type { ReactNode } from 'react';

export const metadata = {
  title: 'Role Builder',
  description: 'Construction de rôles ag.flow depuis des corpus audio scrapés',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif' }}>{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: Créer `page.tsx`**

```tsx
import { fetchHealth } from '@/lib/api/health';

export default async function HomePage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const health = await fetchHealth(apiUrl);

  const color = health.status === 'ok' ? '#1f883d' : '#cf222e';

  return (
    <main style={{ padding: '2rem', maxWidth: 720 }}>
      <h1>Role Builder</h1>
      <p>
        Backend status :{' '}
        <span style={{ color, fontWeight: 600 }}>{health.status}</span>
        {' · '}
        DB : <span style={{ color, fontWeight: 600 }}>{health.db ? 'connectée' : 'indisponible'}</span>
      </p>
    </main>
  );
}
```

- [ ] **Step 3: Vérifier le typecheck**

Run: `cd frontend && npm run typecheck`

Expected: pas d'erreur.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/layout.tsx frontend/src/app/page.tsx
git commit -m "feat(frontend): layout root + page d'accueil avec status backend"
```

---

# Phase F — Docker integration et scripts d'init

Objectif : `docker compose up -d` lance toute la stack, et les 3 scripts d'init la rendent opérationnelle.

## Task F1 : `backend/Dockerfile`

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Créer le fichier**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# uv pour installer les deps
RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/
RUN uv pip install --system --no-cache .

COPY src/ /app/src/

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "role_builder.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/Dockerfile
git commit -m "chore(backend): Dockerfile (python 3.12-slim + uv + uvicorn)"
```

## Task F2 : `frontend/Dockerfile`

**Files:**
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Créer le fichier**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . /app/

ENV NODE_ENV=development

EXPOSE 3000

CMD ["npm", "run", "dev"]
```

- [ ] **Step 2: Commit**

```bash
git add frontend/Dockerfile
git commit -m "chore(frontend): Dockerfile dev (node:20-alpine + npm ci + next dev)"
```

## Task F3 : `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Créer le fichier**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-rb}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-role_builder}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-rb} -d ${POSTGRES_DB:-role_builder}"]
      interval: 5s
      timeout: 3s
      retries: 10

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    ports:
      - "${MINIO_API_PORT:-9000}:9000"
      - "${MINIO_CONSOLE_PORT:-9001}:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  openbao:
    image: openbao/openbao:latest
    cap_add:
      - IPC_LOCK
    environment:
      BAO_DEV_ROOT_TOKEN_ID: ${OPENBAO_DEV_TOKEN}
      BAO_DEV_LISTEN_ADDRESS: "0.0.0.0:8200"
    ports:
      - "${OPENBAO_PORT:-8200}:8200"
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8200/v1/sys/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
      openbao:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-rb}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-role_builder}
      MINIO_ENDPOINT: http://minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
      OPENBAO_URL: http://openbao:8200
      OPENBAO_TOKEN: ${OPENBAO_DEV_TOKEN}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - ./backend/src:/app/src

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    depends_on:
      - backend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:${BACKEND_PORT:-8000}
      BACKEND_INTERNAL_URL: http://backend:8000
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/next.config.js:/app/next.config.js

volumes:
  postgres_data:
  minio_data:
```

- [ ] **Step 2: Smoke test : `config` est valide**

Run: `cp .env.example .env && docker compose config -q`

Expected: aucun output (config valide). Si erreur, lire le message et corriger.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(infra): docker-compose.yml (postgres+pgvector + minio + openbao + backend + frontend)"
```

## Task F4 : `scripts/apply_migrations.sh`

**Files:**
- Create: `scripts/apply_migrations.sh`

- [ ] **Step 1: Créer le fichier**

```bash
#!/usr/bin/env bash
# Applique toutes les migrations SQL du dossier migrations/ dans l'ordre numérique.
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
MIGRATIONS_DIR="$(dirname "$0")/../migrations"

if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "Migrations directory not found: $MIGRATIONS_DIR" >&2
    exit 1
fi

echo "Applying migrations from $MIGRATIONS_DIR"
for file in "$MIGRATIONS_DIR"/*.sql; do
    echo ">> $(basename "$file")"
    psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$file"
done

echo "All migrations applied."
```

- [ ] **Step 2: Rendre exécutable**

Run: `chmod +x scripts/apply_migrations.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/apply_migrations.sh
git commit -m "feat(infra): scripts/apply_migrations.sh (psql -v ON_ERROR_STOP=1)"
```

## Task F5 : `scripts/init_minio.sh`

**Files:**
- Create: `scripts/init_minio.sh`

- [ ] **Step 1: Créer le fichier**

```bash
#!/usr/bin/env bash
# Crée les 3 buckets MinIO requis par Role Builder.
set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changeme_in_real_env}"

if ! command -v mc >/dev/null 2>&1; then
    echo "MinIO client 'mc' not found. Install from https://min.io/docs/minio/linux/reference/minio-mc.html" >&2
    exit 1
fi

mc alias set rb-local "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

for bucket in corpus-audio corpus-transcripts corpus-thumbnails; do
    if ! mc ls "rb-local/$bucket" >/dev/null 2>&1; then
        mc mb "rb-local/$bucket"
        echo "Created bucket: $bucket"
    else
        echo "Bucket exists: $bucket"
    fi
done

echo "MinIO initialization complete."
```

- [ ] **Step 2: Rendre exécutable**

Run: `chmod +x scripts/init_minio.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/init_minio.sh
git commit -m "feat(infra): scripts/init_minio.sh (3 buckets idempotents)"
```

## Task F6 : `scripts/init_openbao.sh`

**Files:**
- Create: `scripts/init_openbao.sh`

- [ ] **Step 1: Créer le fichier**

```bash
#!/usr/bin/env bash
# Active le KV v2 engine au path secret/ dans OpenBao.
set -euo pipefail

OPENBAO_URL="${OPENBAO_URL:-http://localhost:8200}"
OPENBAO_TOKEN="${OPENBAO_TOKEN:-${OPENBAO_DEV_TOKEN:-dev-only-token-change-me}}"

export VAULT_ADDR="$OPENBAO_URL"
export VAULT_TOKEN="$OPENBAO_TOKEN"

if ! command -v bao >/dev/null 2>&1; then
    echo "OpenBao CLI 'bao' not found. Install from https://openbao.org/docs/install/" >&2
    exit 1
fi

if bao secrets list 2>/dev/null | grep -q "^secret/"; then
    echo "KV v2 engine already enabled at secret/"
else
    bao secrets enable -path=secret -version=2 kv
    echo "KV v2 engine enabled at secret/"
fi

echo ""
echo "Expected secret paths (created on demand by the app) :"
echo "  secret/scraping-credentials/{tenant_id}/{platform}/{credential_id}"
echo "  secret/transcription-keys/{tenant_id}/{provider}/{key_id}"
echo "  secret/github-tokens/{tenant_id}/{user_id}"
```

- [ ] **Step 2: Rendre exécutable**

Run: `chmod +x scripts/init_openbao.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/init_openbao.sh
git commit -m "feat(infra): scripts/init_openbao.sh (KV v2 idempotent + doc paths)"
```

## Task F7 : `scripts/reset_db.sh`

**Files:**
- Create: `scripts/reset_db.sh`

- [ ] **Step 1: Créer le fichier**

```bash
#!/usr/bin/env bash
# Drop + recrée la base, puis ré-applique toutes les migrations.
# DEV ONLY. À ne JAMAIS exécuter en prod.
set -euo pipefail

if [ "${ALLOW_RESET:-}" != "yes" ]; then
    echo "Refus : exporter ALLOW_RESET=yes pour confirmer le reset." >&2
    exit 1
fi

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
DB_NAME="$(echo "$DB_URL" | sed -E 's|.*/([^?]+).*|\1|')"
ADMIN_URL="$(echo "$DB_URL" | sed -E "s|/${DB_NAME}|/postgres|")"

echo "Dropping & recreating database '$DB_NAME'…"
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB_NAME\""
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$DB_NAME\""

"$(dirname "$0")/apply_migrations.sh"
```

- [ ] **Step 2: Rendre exécutable**

Run: `chmod +x scripts/reset_db.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/reset_db.sh
git commit -m "feat(infra): scripts/reset_db.sh (drop + recreate + migrate, gate ALLOW_RESET)"
```

## Task F8 : Vérification end-to-end

> **Aucune ligne de code à écrire dans cette tâche.** Elle valide les
> critères de fin de Sprint 1 listés en haut du plan. Si une vérification
> échoue, ne pas continuer : ouvrir un ticket / corriger avant de boucler.

- [ ] **Step 1: Préparer l'env**

Run: `cp .env.example .env`

Vérifier les valeurs si on veut autre chose que les défauts.

- [ ] **Step 2: Lancer la stack**

Run: `docker compose up -d`

Expected: après ~30 secondes, `docker compose ps` montre les 5 services
(postgres, minio, openbao, backend, frontend) en `running` / `healthy`.

- [ ] **Step 3: Appliquer les migrations**

Run: `./scripts/apply_migrations.sh`

Expected: les 11 fichiers s'appliquent successivement, pas d'erreur.

- [ ] **Step 4: Vérifier les tables**

Run: `psql "postgresql://rb:changeme_in_real_env@localhost:5432/role_builder" -c "\dt"`

Expected: 23 tables listées : `role_projects`, `sources`, `source_items`,
`corpus_chunks`, `scraping_jobs`, `transcription_jobs`, `chunking_jobs`,
`user_credentials`, `user_transcription_keys`, `github_integrations`,
`transcription_workers`, `prompts`, `prompt_versions`, `runs`, `signals`,
`clusters`, `document_plans`, `role_documents`, `role_publication_config`,
`role_publications` (20 tables) + 3 vues / tables système éventuelles.
Si décompte différent, comparer avec spec 01-data-model.

- [ ] **Step 5: Vérifier la vue**

Run: `psql ... -c "\dv"`

Expected: `v_role_project_summary` listée.

- [ ] **Step 6: Vérifier les extensions**

Run: `psql ... -c "\dx"`

Expected: `uuid-ossp`, `pgcrypto`, `vector` toutes installées.

- [ ] **Step 7: Initialiser MinIO**

Run: `./scripts/init_minio.sh`

Expected: 3 buckets créés ou déjà présents.

Vérification : `mc ls rb-local/`
Expected: les 3 buckets affichés.

- [ ] **Step 8: Initialiser OpenBao**

Run: `./scripts/init_openbao.sh`

Expected: KV v2 engine enabled.

Vérification : `bao secrets list | grep secret/`
Expected: ligne `secret/  kv  ...`.

- [ ] **Step 9: Healthcheck backend**

Run: `curl -s http://localhost:8000/health/`

Expected: `{"status":"ok","db":true}`.

- [ ] **Step 10: Vérifier les logs JSON**

Run: `docker compose logs backend --tail 5`

Expected: chaque ligne est un JSON valide avec `timestamp`, `level`, `event`.

- [ ] **Step 11: Frontend**

Ouvrir `http://localhost:3000` dans un navigateur.

Expected: page "Role Builder" avec "Backend status: ok" en vert + "DB: connectée" en vert.

- [ ] **Step 12: Suite de tests**

Run: `cd backend && uv run pytest -v && cd ../frontend && npm test && npm run typecheck`

Expected: tout vert, 0 warning.

- [ ] **Step 13: Tagger le sprint**

```bash
git tag -a v0.1.0-sprint-1 -m "Sprint 1 — Foundations terminé : stack docker-compose + migrations + healthcheck"
```

> **Pas de push automatique.** L'utilisateur (architecte) décide de pousser
> sur le remote quand il veut.

- [ ] **Step 14: Mettre à jour `12-open-decisions.md`**

Cocher les décisions tranchées dans le plan (image pgvector, dimension
embeddings provisoire, auth hors scope MVP, etc.) en suivant le format
prescrit par le fichier 12 :

```markdown
- [x] **Image pgvector exacte**
      → **Décision (sprint 1) :** `pgvector/pgvector:pg16`. Choix conforme à
      la recommandation de la spec 02.
```

```bash
git add docs/specs/12-open-decisions.md
git commit -m "docs(specs): décisions Sprint 1 actées dans 12-open-decisions.md"
```

---

## Récapitulatif des commits attendus

À la fin du Sprint 1, le `git log` doit contenir au minimum (dans l'ordre) :

1. `chore: ajout .gitignore racine`
2. `chore: ajout .editorconfig`
3. `chore: ajout .env.example`
4. `docs: README initial`
5. `chore(backend): pyproject.toml + uv lock initial`
6. `chore(backend): squelette des packages Python`
7. `feat(backend): config Pydantic Settings`
8. `feat(backend): structlog JSON renderer`
9. `feat(backend): asyncpg pool wrapper`
10. `feat(backend): app FastAPI + endpoint /health/`
11. `refactor(backend): mutualisation fixture client`
12. `feat(db): migration 0001 extensions`
13. `feat(db): migration 0002 table role_projects`
14. `feat(db): migration 0003 tables sources + source_items`
15. `feat(db): migration 0004 corpus_chunks`
16. `feat(db): migration 0005 queues`
17. `feat(db): migration 0006 credentials`
18. `feat(db): migration 0007 transcription_workers`
19. `feat(db): migration 0008 synthèse`
20. `feat(db): migration 0009 publication`
21. `feat(db): migration 0010 fonction notify_event + triggers`
22. `feat(db): migration 0011 vue v_role_project_summary`
23. `chore(backend): paquet services/`
24. `feat(backend): client OpenBao KV v2`
25. `feat(backend): wrapper MinIO`
26. `chore(frontend): package.json initial`
27. `chore(frontend): tsconfig.json strict`
28. `chore(frontend): next.config.js + eslint`
29. `chore(frontend): config vitest`
30. `feat(frontend): client API health`
31. `feat(frontend): layout root + page d'accueil`
32. `chore(backend): Dockerfile`
33. `chore(frontend): Dockerfile dev`
34. `feat(infra): docker-compose.yml`
35. `feat(infra): scripts/apply_migrations.sh`
36. `feat(infra): scripts/init_minio.sh`
37. `feat(infra): scripts/init_openbao.sh`
38. `feat(infra): scripts/reset_db.sh`
39. `docs(specs): décisions Sprint 1 actées`

Tag final : `v0.1.0-sprint-1`.

---

## Sortie du Sprint 1 — Décisions ouvertes pour Sprint 2

Le Sprint 2 (`docs/specs/03-scrapers.md`) attaquera le pipeline de scraping.
Décisions à trancher AVANT d'écrire le plan Sprint 2 :

- Stratégie Instagram : yt-dlp seul ou gallery-dl en complément ?
- Format de stockage des thumbnails : URL d'origine ou upload MinIO ?
- Cap simultané scrapers : 5 (env var) ?
- Distinction des erreurs : 'expired' / 'geo-restricted' / 'private' / pareil ?

Ces questions se résolvent en testant manuellement les comportements yt-dlp /
Instagram avant de figer le contrat. Pas de décision prématurée à acter ici.
