> ℹ️ **Conservée avec adaptations V2 (2026-07-04).** Infra conservée ; cible = host usage=ressources du portail devpod ; extension pgvector plus requise.
> Voir `docs/specs/v2/00-fondations-v2.md` et `docs/specs/v2/01-protocole-mcp.md`.

# 02 — Foundations : infrastructure de base

> Sprint 1 : poser l'infrastructure. À l'issue de ce sprint, tous les services
> de base (PostgreSQL, MinIO, OpenBao) sont opérationnels et le squelette
> du backend FastAPI répond à un health-check.

## Objectif du sprint

Avoir un environnement local de développement complet :

- PostgreSQL 16 avec extensions et schéma initial
- MinIO opérationnel avec les 3 buckets créés
- OpenBao accessible avec authentification
- Backend FastAPI minimal (health-check, structure de routes)
- Frontend Next.js minimal (page d'accueil)
- `docker-compose up` lance tout

## Structure du repo

```
role-builder/
├── README.md
├── docker-compose.yml
├── docker-compose.override.yml.example
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/
│   │   └── role_builder/
│   │       ├── __init__.py
│   │       ├── main.py            # FastAPI app
│   │       ├── config.py          # settings via env vars
│   │       ├── db.py              # asyncpg pool
│   │       ├── logging_setup.py   # structlog config
│   │       ├── routes/
│   │       │   ├── __init__.py
│   │       │   └── health.py
│   │       └── services/
│   │           ├── __init__.py
│   │           ├── minio_client.py
│   │           └── openbao_client.py
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   └── src/
│       └── app/
│           └── page.tsx
├── migrations/
│   ├── 0001_extensions.sql
│   ├── 0002_role_projects.sql
│   ├── 0003_sources_items.sql
│   ├── 0004_corpus_chunks.sql
│   ├── 0005_queues.sql
│   ├── 0006_credentials_keys.sql
│   ├── 0007_workers.sql
│   ├── 0008_synthesis.sql
│   ├── 0009_publication.sql
│   ├── 0010_triggers.sql
│   └── 0011_views.sql
├── scripts/
│   ├── apply_migrations.sh
│   ├── reset_db.sh
│   ├── init_minio.sh
│   └── init_openbao.sh
└── docs/
    └── spec/                      # ce dossier de spec
```

## docker-compose.yml

Services à inclure :

```yaml
version: '3.9'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: rb
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: role_builder
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rb -d role_builder"]
      interval: 5s
      timeout: 3s
      retries: 10

  pgvector_init:
    image: postgres:16-alpine
    depends_on:
      postgres:
        condition: service_healthy
    # Note: pgvector doit être installé via une image custom ou
    # l'image pgvector/pgvector:pg16 (à confirmer en implémentation)
    # On peut aussi utiliser ankane/pgvector
    profiles: ["init"]

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
    # En dev: mode dev avec token statique
    # En prod: cluster propre avec OIDC (Beard travaille dessus)
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
      DATABASE_URL: postgresql://rb:${POSTGRES_PASSWORD}@postgres:5432/role_builder
      MINIO_ENDPOINT: http://minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
      OPENBAO_URL: http://openbao:8200
      OPENBAO_TOKEN: ${OPENBAO_DEV_TOKEN}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      # Pour dev: hot reload
      - ./backend/src:/app/src

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    depends_on:
      - backend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:${BACKEND_PORT:-8000}
    ports:
      - "${FRONTEND_PORT:-3000}:3000"

volumes:
  postgres_data:
  minio_data:
```

**Note sur pgvector :** utiliser l'image `pgvector/pgvector:pg16` ou
`ankane/pgvector` qui inclut l'extension pré-installée. La migration 0001
fait juste `CREATE EXTENSION IF NOT EXISTS vector`.

## Fichier .env.example

```bash
# PostgreSQL
POSTGRES_PASSWORD=changeme_in_real_env
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

# Frontend
FRONTEND_PORT=3000
```

## Backend FastAPI minimal

### `backend/pyproject.toml`

```toml
[project]
name = "role-builder-backend"
version = "0.1.0"
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
```

### `backend/src/role_builder/main.py`

```python
"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from role_builder.config import settings
from role_builder.db import db_pool
from role_builder.logging_setup import configure_logging
from role_builder.routes import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    configure_logging(settings.log_level)
    await db_pool.connect()
    yield
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

### `backend/src/role_builder/config.py`

```python
"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str

    # OpenBao
    openbao_url: str
    openbao_token: str

    # ag.flow
    agflow_base_url: str = "https://docker-agflow.yoops.org"

    # Logging
    log_level: str = "INFO"


settings = Settings()
```

### `backend/src/role_builder/db.py`

```python
"""Async PostgreSQL connection pool."""
import asyncpg
from typing import Optional

from role_builder.config import settings


class DBPool:
    """Wrapper around asyncpg pool for app lifecycle."""

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create the pool at startup."""
        self._pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Close the pool at shutdown."""
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        """Return the active pool, raise if not connected."""
        if self._pool is None:
            raise RuntimeError("DB pool not connected")
        return self._pool


db_pool = DBPool()
```

### `backend/src/role_builder/routes/health.py`

```python
"""Health check endpoints."""
from fastapi import APIRouter

from role_builder.db import db_pool

router = APIRouter()


@router.get("/")
async def health_check() -> dict:
    """Basic health check including DB connectivity."""
    async with db_pool.pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    return {"status": "ok", "db": result == 1}
```

## Migrations SQL

Référence : voir `01-data-model.md` pour les schémas complets. Découper en
fichiers numérotés :

- `0001_extensions.sql` — `CREATE EXTENSION` pour uuid-ossp, pgcrypto, vector
- `0002_role_projects.sql` — table `role_projects`
- `0003_sources_items.sql` — tables `sources`, `source_items`
- `0004_corpus_chunks.sql` — table `corpus_chunks`
- `0005_queues.sql` — tables `scraping_jobs`, `transcription_jobs`, `chunking_jobs`
- `0006_credentials_keys.sql` — tables `user_credentials`, `user_transcription_keys`, `github_integrations`
- `0007_workers.sql` — table `transcription_workers`
- `0008_synthesis.sql` — tables `prompts`, `prompt_versions`, `runs`, `signals`, `clusters`, `document_plans`, `role_documents`
- `0009_publication.sql` — tables `role_publication_config`, `role_publications`
- `0010_triggers.sql` — fonction `notify_event` + triggers
- `0011_views.sql` — vue `v_role_project_summary`

### Script `scripts/apply_migrations.sh`

```bash
#!/bin/bash
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://rb:changeme_in_real_env@localhost:5432/role_builder}"
MIGRATIONS_DIR="$(dirname "$0")/../migrations"

echo "Applying migrations from $MIGRATIONS_DIR"

for file in "$MIGRATIONS_DIR"/*.sql; do
    echo ">> $(basename "$file")"
    psql "$DB_URL" -f "$file"
done

echo "All migrations applied."
```

## Initialisation MinIO

### Script `scripts/init_minio.sh`

Crée les 3 buckets nécessaires + politique de rétention si pertinent.

```bash
#!/bin/bash
set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changeme_in_real_env}"

# Configurer alias mc
mc alias set rb-local "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

# Créer les buckets
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

### Organisation des buckets MinIO

```
corpus-audio/
└── {tenant_id}/{role_id}/{source_id}/{item_id}.mp3

corpus-transcripts/
└── {tenant_id}/{role_id}/{source_id}/{item_id}.json

corpus-thumbnails/  (optionnel, pour l'UI)
└── {tenant_id}/{role_id}/{source_id}/{item_id}.jpg
```

## Initialisation OpenBao

### Script `scripts/init_openbao.sh`

Active le KV v2 engine au path `secret/` (qui sera utilisé pour tous les
secrets de l'application) :

```bash
#!/bin/bash
set -euo pipefail

OPENBAO_URL="${OPENBAO_URL:-http://localhost:8200}"
OPENBAO_TOKEN="${OPENBAO_TOKEN:-dev-only-token-change-me}"

export VAULT_ADDR="$OPENBAO_URL"
export VAULT_TOKEN="$OPENBAO_TOKEN"

# Activer KV v2 si pas déjà actif
if ! bao secrets list | grep -q "^secret/"; then
    bao secrets enable -path=secret -version=2 kv
    echo "KV v2 engine enabled at secret/"
else
    echo "KV v2 engine already enabled at secret/"
fi

# Créer les sous-paths attendus
# (ils n'existent pas vraiment tant qu'on n'y met rien, mais on documente)
echo ""
echo "Expected secret paths:"
echo "  secret/scraping-credentials/{tenant_id}/{platform}/{credential_id}"
echo "  secret/transcription-keys/{tenant_id}/{provider}/{key_id}"
echo "  secret/github-tokens/{tenant_id}/{user_id}"
```

**Note :** en mode dev, on utilise un token statique. En prod, OIDC sera
configuré côté Beard (en cours).

### Client OpenBao côté backend

```python
# backend/src/role_builder/services/openbao_client.py
"""OpenBao client for secrets management."""
import httpx
from typing import Optional

from role_builder.config import settings


class OpenBaoClient:
    """Async client for OpenBao KV v2 API."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.openbao_url,
            headers={"X-Vault-Token": settings.openbao_token},
            timeout=10.0,
        )

    async def put(self, path: str, data: dict) -> None:
        """Store a secret at the given path."""
        url = f"/v1/secret/data/{path}"
        await self._http.post(url, json={"data": data})

    async def get(self, path: str) -> Optional[dict]:
        """Retrieve a secret. Returns None if not found."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()["data"]["data"]

    async def delete(self, path: str) -> None:
        """Soft-delete a secret (KV v2 keeps the version)."""
        url = f"/v1/secret/data/{path}"
        await self._http.delete(url)

    async def close(self) -> None:
        await self._http.aclose()


openbao = OpenBaoClient()
```

## Frontend Next.js minimal

### `frontend/package.json`

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
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "eslint": "^8",
    "eslint-config-next": "14.2.0"
  }
}
```

### `frontend/src/app/page.tsx`

Minimal landing page qui ping le backend pour afficher le statut.

```tsx
async function checkHealth() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  try {
    const res = await fetch(`${apiUrl}/health/`, { cache: 'no-store' });
    return await res.json();
  } catch {
    return { status: 'unreachable' };
  }
}

export default async function HomePage() {
  const health = await checkHealth();
  return (
    <main style={{ padding: '2rem', fontFamily: 'system-ui' }}>
      <h1>Role Builder</h1>
      <p>Backend status: {health.status}</p>
    </main>
  );
}
```

## Critères de fin de sprint

- [ ] `docker-compose up` démarre tous les services sans erreur
- [ ] `curl http://localhost:8000/health/` retourne `{"status":"ok","db":true}`
- [ ] `mc ls rb-local/` affiche les 3 buckets
- [ ] `bao secrets list` affiche `secret/`
- [ ] `http://localhost:3000` affiche la page d'accueil avec "Backend status: ok"
- [ ] `psql` permet de lister les tables : toutes celles définies dans
      `01-data-model.md` doivent être créées
- [ ] Aucun fichier Python ne dépasse 300 lignes
- [ ] Logs du backend sont en JSON (structlog)

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Confirmer l'image pgvector exacte à utiliser
      (`pgvector/pgvector:pg16` recommandée)
- [ ] Stratégie de seed des prompts système par défaut : script SQL en
      migration `0012_seed_prompts.sql` ou commande Python séparée ?
- [ ] Politique CORS en prod : domaines autorisés
- [ ] Authentification de l'app elle-même : OIDC via Keycloak ou simple
      auth basique pour le MVP ? (cf. § 12-open-decisions.md)

---

**Document précédent :** `01-data-model.md`
**Document suivant :** `03-scrapers.md`
