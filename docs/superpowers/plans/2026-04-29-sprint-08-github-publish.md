# Sprint 8 — Publication GitHub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline avec checkpoints par commit). Patterns établis Sprints 1-7 (asyncpg helpers, structlog, fichiers ≤300 lignes, TDD strict, Pydantic schemas, SWR + clients API typés frontend, components inline-styled).

**Goal:** Permettre à l'utilisateur de connecter son compte GitHub via OAuth puis de publier un rôle (les fichiers d'export ag.flow + un README généré) sur un repo qu'il contrôle, avec un sous-répertoire de son choix, une licence sélectionnable, un historique des publications et un bouton "Dépublier".

**Architecture:**
- **Backend** : nouvelle migration `0012_oauth_states.sql` (table `oauth_states` pour CSRF state, expiration 10 min) ; `services/github_publish/{oauth, api_client, readme_builder, publisher}` ; routes `github_auth.py` (start/callback/disconnect) + `github_publish.py` (list-repos, config GET/PUT, publish, unpublish, list-publications) ; helpers `db_helpers/{github_integrations, oauth_states, role_publications}` ; nouveaux schemas Pydantic. La table `github_integrations` existe déjà (migration 0006). Les tables `role_publication_config` + `role_publications` existent déjà (migration 0009) — on ajoute juste un champ `license_choice` à `role_publication_config`.
- **Frontend** : `lib/api/github.ts` ; sous-onglet `my-stack/publication/` (statut OAuth, connect/disconnect) ; section Publication dans la page rôle (config repo + license selector + bouton Publier + historique) ; modale `PublishToGithubDialog` (sélecteur licence + preview + commit message). Bouton "Publier sur GitHub" sur la page rôle, badge "Modifications non publiées" si rôle modifié après dernière publication.
- **OpenBao** : token au path `secret/github-tokens/{tenant_id}/{user_id}`.
- **GitHub API** : OAuth Web Flow + REST API `contents/{path}` (GET/PUT/DELETE). N appels GET + N PUT par publication. ~30 fichiers max → ~10-20s par push, acceptable MVP.

**Tech Stack:** httpx (existant), asyncpg, OpenBao client (existant), pas de nouvelle dépendance Python ni frontend.

**Décisions actées avant démarrage (cf. memory project_current_status.md § Sprint 8) :**
- **Licence rôle publié** = sélecteur utilisateur dans `PublishToGithubDialog` (PolyForm-NC / CC-BY-NC-SA-4.0 / CC-BY-4.0 / MIT / Aucune). Persisté dans `role_publication_config.license_choice`.
- **Multi-comptes GitHub par user** = 1 seul compte (UNIQUE sur `user_id` déjà en place dans `github_integrations`).
- **State CSRF OAuth** = table Postgres `oauth_states` avec cleanup auto > 10 min.
- **Indépendance push ag.flow ↔ publication GitHub** = totalement indépendants. Aucune dépendance entre `target_role_id` et `role_publications`.
- **Texte de licence** dans le repo publié = un fichier `LICENSE` à côté du `README.md` selon le choix utilisateur (PolyForm-NC reproduit verbatim, CC-* avec lien, MIT avec template, "Aucune" → pas de fichier).

---

## File Structure

```
migrations/
└── 0012_oauth_states.sql                          # Tâche 1 (création table)

backend/
├── src/role_builder/
│   ├── config.py                                  # Tâche 2 (settings GitHub OAuth)
│   ├── main.py                                    # Tâche 4 + 8 + 9 (include routers)
│   ├── db_helpers/
│   │   ├── oauth_states.py                        # Tâche 3 (nouveau)
│   │   ├── github_integrations.py                 # Tâche 4 (nouveau)
│   │   └── role_publications.py                   # Tâche 9 (nouveau)
│   ├── services/
│   │   └── github_publish/
│   │       ├── __init__.py                        # Tâche 5
│   │       ├── oauth.py                           # Tâche 5 (build_authorize_url, exchange_code, get_user_info)
│   │       ├── api_client.py                      # Tâche 7 (list_repos, get_content, put_content, delete_content)
│   │       ├── readme_builder.py                  # Tâche 9 (render_readme + render_license_file)
│   │       └── publisher.py                       # Tâche 9 (build_publication_files + push_files_to_github + delete_publication)
│   ├── schemas/
│   │   └── github.py                              # Tâche 4 + 8 + 9 (DTOs Pydantic)
│   └── routes/
│       ├── github_auth.py                         # Tâche 4 (start, callback, disconnect)
│       └── github_publish.py                      # Tâche 8 + 9 (repos, config, publish, unpublish, history)
├── migrations/
│   └── 0013_add_license_to_publication_config.sql # Tâche 6 (ALTER TABLE)
└── tests/
    ├── test_db_helpers_oauth_states.py            # Tâche 3
    ├── test_db_helpers_github_integrations.py     # Tâche 4
    ├── test_db_helpers_role_publications.py       # Tâche 9
    ├── test_github_oauth.py                       # Tâche 5
    ├── test_github_auth_route.py                  # Tâche 4
    ├── test_github_api_client.py                  # Tâche 7
    ├── test_github_readme_builder.py              # Tâche 9
    ├── test_github_publisher.py                   # Tâche 9
    └── test_github_publish_route.py               # Tâche 8 + 9

frontend/
└── src/
    ├── lib/
    │   ├── types.ts                               # Tâche 10 (étendre)
    │   └── api/github.ts                          # Tâche 10 (nouveau)
    ├── app/
    │   ├── my-stack/
    │   │   ├── layout.tsx                         # Tâche 11 (ajouter onglet Publication)
    │   │   └── publication/
    │   │       ├── page.tsx                       # Tâche 11
    │   │       └── ConnectGithubButton.tsx        # Tâche 11
    │   └── projects/[id]/role/
    │       ├── page.tsx                           # Tâche 13 (ajouter PublishToGithubButton + PublicationHistory)
    │       ├── PublishToGithubButton.tsx          # Tâche 12
    │       ├── PublishToGithubDialog.tsx          # Tâche 12 (preview + license selector + commit msg)
    │       └── PublicationHistory.tsx             # Tâche 13
    └── __tests__/
        ├── github-api.test.ts                     # Tâche 10
        ├── ConnectGithubButton.test.tsx           # Tâche 11
        ├── PublishToGithubDialog.test.tsx         # Tâche 12
        └── PublicationHistory.test.tsx            # Tâche 13

docs/specs/
└── 12-open-decisions.md                           # Tâche 14 (Sprint 8 closure)
```

---

## Tâche 1 — Migration `oauth_states` (CSRF state PG)

**Files:**
- Create: `migrations/0012_oauth_states.sql`

- [ ] **Step 1: Créer le fichier de migration**

```sql
-- migrations/0012_oauth_states.sql
-- Sprint 8 : table temporaire pour le state CSRF du flow OAuth GitHub.
-- Cleanup auto des entrées > 10 min via le query helper (pas de pg_cron).

CREATE TABLE oauth_states (
    state text PRIMARY KEY,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    provider text NOT NULL DEFAULT 'github',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX oauth_states_expires_idx ON oauth_states (expires_at);
```

- [ ] **Step 2: Appliquer la migration**

Run: `cd /e/srcs/agflow.roles && ./scripts/apply_migrations.sh`
Expected: succès, 1 nouvelle table `oauth_states`.

- [ ] **Step 3: Commit**

```bash
git add migrations/0012_oauth_states.sql
git commit -m "feat(db): migration 0012 oauth_states (CSRF state PG, Sprint 8)"
```

---

## Tâche 2 — Settings GitHub OAuth

**Files:**
- Modify: `backend/src/role_builder/config.py` (ajouter 4 champs)

- [ ] **Step 1: Identifier le bloc Settings et y ajouter les champs**

Lire d'abord la classe `Settings` pour trouver l'emplacement (chercher après les settings agflow). Ajouter :

```python
# Sprint 8 — GitHub OAuth (cf. spec 09)
github_oauth_client_id: str = Field(default="", alias="GITHUB_OAUTH_CLIENT_ID")
github_oauth_client_secret: SecretStr = Field(default=SecretStr(""), alias="GITHUB_OAUTH_CLIENT_SECRET")
github_oauth_redirect_uri: str = Field(
    default="http://localhost:8000/api/auth/github/callback",
    alias="GITHUB_OAUTH_REDIRECT_URI",
)
github_oauth_scope: str = Field(default="public_repo", alias="GITHUB_OAUTH_SCOPE")
```

- [ ] **Step 2: Vérifier le typecheck**

Run: `cd backend && uv run ruff check src/role_builder/config.py`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/src/role_builder/config.py
git commit -m "feat(backend): settings GitHub OAuth (client_id, client_secret, redirect_uri, scope)"
```

---

## Tâche 3 — `db_helpers/oauth_states` (CRUD + cleanup)

**Files:**
- Create: `backend/src/role_builder/db_helpers/oauth_states.py`
- Create: `backend/tests/test_db_helpers_oauth_states.py`

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_db_helpers_oauth_states.py
"""Tests TDD pour db_helpers/oauth_states.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchrow_return: Any = None
        self.execute_return: str = "INSERT 0 1"

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


async def test_insert_state_inserts_with_expires_at(stub_conn, stub_pool):
    from role_builder.db_helpers import oauth_states

    user_id = uuid4()
    tenant_id = uuid4()
    state = "abc123"

    await oauth_states.insert_state(
        state=state,
        user_id=user_id,
        tenant_id=tenant_id,
        ttl_seconds=600,
        pool=stub_pool,
    )

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "INSERT INTO oauth_states" in query
    assert state in args
    assert user_id in args
    assert tenant_id in args
    # 5e arg = expires_at (datetime ~10min ahead)
    expires_at = args[4]
    assert isinstance(expires_at, datetime)
    delta = expires_at - datetime.now(tz=timezone.utc)
    assert 590 < delta.total_seconds() < 610


async def test_consume_state_returns_user_id_and_deletes(stub_conn, stub_pool):
    """consume_state retourne le user_id si valide, et delete la ligne (ATOMIC)."""
    from role_builder.db_helpers import oauth_states

    user_id = uuid4()
    tenant_id = uuid4()
    stub_conn.fetchrow_return = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
    }

    result = await oauth_states.consume_state("abc", pool=stub_pool)

    assert result is not None
    assert result["user_id"] == user_id
    assert result["tenant_id"] == tenant_id
    # 1 fetchrow (DELETE ... RETURNING)
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "DELETE FROM oauth_states" in query
    assert "RETURNING" in query
    assert "abc" in args


async def test_consume_state_returns_none_when_unknown(stub_conn, stub_pool):
    from role_builder.db_helpers import oauth_states

    stub_conn.fetchrow_return = None
    result = await oauth_states.consume_state("unknown", pool=stub_pool)
    assert result is None


async def test_consume_state_returns_none_when_expired(stub_conn, stub_pool):
    """Si la row existe mais expires_at est dans le passé, retourne None."""
    from role_builder.db_helpers import oauth_states

    stub_conn.fetchrow_return = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "expires_at": datetime.now(tz=timezone.utc) - timedelta(minutes=1),
    }
    result = await oauth_states.consume_state("expired", pool=stub_pool)
    assert result is None


async def test_cleanup_expired_returns_count(stub_conn, stub_pool):
    from role_builder.db_helpers import oauth_states

    stub_conn.execute_return = "DELETE 5"
    count = await oauth_states.cleanup_expired(pool=stub_pool)
    assert count == 5
    method, query, _ = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM oauth_states" in query
    assert "expires_at < now()" in query
```

- [ ] **Step 2: Run, vérifier FAIL (module absent)**

Run: `cd backend && uv run pytest tests/test_db_helpers_oauth_states.py -v`
Expected: FAIL `ModuleNotFoundError: role_builder.db_helpers.oauth_states`.

- [ ] **Step 3: Implémenter**

```python
# backend/src/role_builder/db_helpers/oauth_states.py
"""CRUD asyncpg pour la table oauth_states (CSRF state OAuth, Sprint 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO oauth_states (state, user_id, tenant_id, provider, expires_at)
    VALUES ($1, $2, $3, $4, $5)
"""

# DELETE ... RETURNING : atomique. Si la ligne n'existe pas, rien retourné.
_CONSUME_SQL = """
    DELETE FROM oauth_states
    WHERE state = $1
    RETURNING user_id, tenant_id, expires_at
"""

_CLEANUP_SQL = "DELETE FROM oauth_states WHERE expires_at < now()"


async def insert_state(
    *,
    state: str,
    user_id: UUID,
    tenant_id: UUID,
    ttl_seconds: int = 600,
    provider: str = "github",
    pool: asyncpg.Pool,
) -> None:
    """Stocke un state CSRF avec une TTL de ttl_seconds (défaut 10 min)."""
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
    async with pool.acquire() as conn:
        await conn.execute(_INSERT_SQL, state, user_id, tenant_id, provider, expires_at)


async def consume_state(state: str, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Récupère et supprime un state. Retourne None si absent ou expiré.

    DELETE ... RETURNING garantit qu'un même state ne peut être consommé
    qu'une fois (anti-replay).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_CONSUME_SQL, state)
    if row is None:
        return None
    data = dict(row) if not isinstance(row, dict) else row
    expires_at = data["expires_at"]
    if isinstance(expires_at, datetime):
        # asyncpg renvoie aware ; on garde une marge de sécurité
        if expires_at < datetime.now(tz=timezone.utc):
            return None
    return data


async def cleanup_expired(*, pool: asyncpg.Pool) -> int:
    """Supprime les states expirés. Retourne le nombre supprimé."""
    async with pool.acquire() as conn:
        result = await conn.execute(_CLEANUP_SQL)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
```

- [ ] **Step 4: Run, PASS**

Run: `cd backend && uv run pytest tests/test_db_helpers_oauth_states.py -v`
Expected: 5/5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/db_helpers/oauth_states.py backend/tests/test_db_helpers_oauth_states.py
git commit -m "feat(backend): db_helpers/oauth_states (CRUD CSRF state + cleanup_expired)"
```

---

## Tâche 4 — `db_helpers/github_integrations` + routes `/auth/github/*`

**Files:**
- Create: `backend/src/role_builder/db_helpers/github_integrations.py`
- Create: `backend/src/role_builder/schemas/github.py` (premier ajout)
- Create: `backend/src/role_builder/routes/github_auth.py`
- Modify: `backend/src/role_builder/main.py` (include router)
- Create: `backend/tests/test_db_helpers_github_integrations.py`
- Create: `backend/tests/test_github_auth_route.py`

### Tâche 4.1 — Helper db `github_integrations`

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_db_helpers_github_integrations.py
"""Tests TDD pour db_helpers/github_integrations.py."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

# (réutilise le pattern _StubConn / _StubPool des autres tests db_helpers)


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchrow_return: Any = None
        self.execute_return: str = "INSERT 0 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return self.execute_return


class _StubAcquireCtx:
    def __init__(self, conn): self._conn = conn
    async def __aenter__(self): return self._conn
    async def __aexit__(self, *_): return None


class _StubPool:
    def __init__(self, conn): self._conn = conn
    def acquire(self): return _StubAcquireCtx(self._conn)


@pytest.fixture()
def stub_conn(): return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn): return _StubPool(stub_conn)


async def test_upsert_inserts_or_updates_on_user_id_unique(stub_conn, stub_pool):
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    tenant_id = uuid4()
    await github_integrations.upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        github_login="alice",
        github_user_id=12345,
        openbao_path=f"github-tokens/{tenant_id}/{user_id}",
        scope="public_repo",
        pool=stub_pool,
    )
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "INSERT INTO github_integrations" in query
    assert "ON CONFLICT (user_id) DO UPDATE" in query
    assert "alice" in args
    assert 12345 in args


async def test_get_by_user_id_returns_dict_or_none(stub_conn, stub_pool):
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    stub_conn.fetchrow_return = {
        "id": uuid4(),
        "user_id": user_id,
        "tenant_id": uuid4(),
        "github_login": "alice",
        "github_user_id": 12345,
        "openbao_path": "github-tokens/x/y",
        "scope": "public_repo",
        "last_validated_at": datetime.now(tz=timezone.utc),
        "created_at": datetime.now(tz=timezone.utc),
    }
    result = await github_integrations.get_by_user_id(user_id, pool=stub_pool)
    assert result is not None
    assert result["github_login"] == "alice"


async def test_get_by_user_id_none_when_absent(stub_conn, stub_pool):
    from role_builder.db_helpers import github_integrations

    stub_conn.fetchrow_return = None
    result = await github_integrations.get_by_user_id(uuid4(), pool=stub_pool)
    assert result is None


async def test_delete_by_user_id_removes_row(stub_conn, stub_pool):
    from role_builder.db_helpers import github_integrations

    stub_conn.execute_return = "DELETE 1"
    count = await github_integrations.delete_by_user_id(uuid4(), pool=stub_pool)
    assert count == 1
    method, query, _ = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM github_integrations" in query
```

- [ ] **Step 2: Run, FAIL**

Run: `cd backend && uv run pytest tests/test_db_helpers_github_integrations.py -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter**

```python
# backend/src/role_builder/db_helpers/github_integrations.py
"""CRUD asyncpg pour la table github_integrations (Sprint 8)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

_UPSERT_SQL = """
    INSERT INTO github_integrations
        (tenant_id, user_id, github_login, github_user_id,
         openbao_path, scope, last_validated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (user_id) DO UPDATE SET
        tenant_id = EXCLUDED.tenant_id,
        github_login = EXCLUDED.github_login,
        github_user_id = EXCLUDED.github_user_id,
        openbao_path = EXCLUDED.openbao_path,
        scope = EXCLUDED.scope,
        last_validated_at = EXCLUDED.last_validated_at
"""

_GET_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           openbao_path, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE user_id = $1
"""

_DELETE_SQL = "DELETE FROM github_integrations WHERE user_id = $1"


async def upsert(
    *,
    user_id: UUID,
    tenant_id: UUID,
    github_login: str,
    github_user_id: int,
    openbao_path: str,
    scope: str,
    pool: asyncpg.Pool,
) -> None:
    """Insert ou update sur conflit user_id (1 seul GitHub par user)."""
    async with pool.acquire() as conn:
        await conn.execute(
            _UPSERT_SQL,
            tenant_id,
            user_id,
            github_login,
            github_user_id,
            openbao_path,
            scope,
            datetime.now(tz=timezone.utc),
        )


async def get_by_user_id(user_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_SQL, user_id)
    return dict(row) if row is not None and not isinstance(row, dict) else row


async def delete_by_user_id(user_id: UUID, *, pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_SQL, user_id)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
```

- [ ] **Step 4: Run, PASS**

Run: `cd backend && uv run pytest tests/test_db_helpers_github_integrations.py -v`
Expected: 4/4 passed.

### Tâche 4.2 — Schemas Pydantic GitHub (premier ajout)

- [ ] **Step 1: Créer le fichier**

```python
# backend/src/role_builder/schemas/github.py
"""DTOs Pydantic pour les endpoints GitHub (Sprint 8)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GithubIntegrationStatus(BaseModel):
    connected: bool
    github_login: str | None = None
    scope: str | None = None
    last_validated_at: datetime | None = None


class StartOAuthResponse(BaseModel):
    redirect_url: str


class CallbackResponse(BaseModel):
    status: str
    github_login: str
```

### Tâche 4.3 — Routes `/auth/github/*`

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_github_auth_route.py
"""Tests routes /auth/github/* — start, callback, disconnect."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def test_start_returns_authorize_url_and_stores_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/auth/github/start retourne une URL GitHub avec state."""
    from role_builder.routes import github_auth as route

    insert_calls: list[dict[str, Any]] = []

    async def fake_insert_state(*, state, user_id, tenant_id, ttl_seconds, pool, provider="github"):
        insert_calls.append({"state": state, "user_id": user_id, "ttl": ttl_seconds})

    monkeypatch.setattr(route.oauth_states, "insert_state", fake_insert_state)

    resp = client.get("/api/auth/github/start")
    assert resp.status_code == 200
    body = resp.json()
    assert "redirect_url" in body
    assert body["redirect_url"].startswith("https://github.com/login/oauth/authorize?")
    assert "state=" in body["redirect_url"]
    assert "client_id=" in body["redirect_url"]
    assert "scope=public_repo" in body["redirect_url"]
    # State a bien été inséré
    assert len(insert_calls) == 1
    assert insert_calls[0]["ttl"] == 600


def test_callback_with_invalid_state_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_consume(state, *, pool):
        return None

    monkeypatch.setattr(route.oauth_states, "consume_state", fake_consume)

    resp = client.get("/api/auth/github/callback", params={"code": "x", "state": "bad"})
    assert resp.status_code == 400


def test_callback_full_flow_stores_token_and_returns_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    user_id = uuid4()
    tenant_id = uuid4()

    async def fake_consume(state, *, pool):
        return {"user_id": user_id, "tenant_id": tenant_id, "expires_at": None}

    async def fake_exchange(code):
        assert code == "github-code"
        return "ghp_secret"

    async def fake_user_info(token):
        assert token == "ghp_secret"
        return {"login": "alice", "id": 42}

    openbao_calls: list[tuple[str, dict[str, str]]] = []

    async def fake_put(path, data):
        openbao_calls.append((path, data))

    upsert_calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs):
        upsert_calls.append(kwargs)

    monkeypatch.setattr(route.oauth_states, "consume_state", fake_consume)
    monkeypatch.setattr(route.gh_oauth, "exchange_code", fake_exchange)
    monkeypatch.setattr(route.gh_oauth, "get_user_info", fake_user_info)
    monkeypatch.setattr(route.openbao_client, "put", fake_put)
    monkeypatch.setattr(route.github_integrations, "upsert", fake_upsert)

    resp = client.get(
        "/api/auth/github/callback",
        params={"code": "github-code", "state": "good"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"status": "connected", "github_login": "alice"}

    # Token stocké en OpenBao
    assert len(openbao_calls) == 1
    assert "github-tokens" in openbao_calls[0][0]
    assert openbao_calls[0][1] == {"access_token": "ghp_secret"}

    # Integration upsertée
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["github_login"] == "alice"
    assert upsert_calls[0]["github_user_id"] == 42


def test_get_status_returns_connected_when_integration_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_get(user_id, *, pool):
        return {
            "github_login": "alice",
            "scope": "public_repo",
            "last_validated_at": None,
        }

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)

    resp = client.get("/api/auth/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["github_login"] == "alice"


def test_get_status_returns_not_connected_when_absent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_get(user_id, *, pool):
        return None

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)

    resp = client.get("/api/auth/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["github_login"] is None


def test_disconnect_removes_token_and_integration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_get(user_id, *, pool):
        return {"openbao_path": "github-tokens/t/u"}

    deleted_paths: list[str] = []
    deleted_users: list[UUID] = []

    async def fake_delete_token(path):
        deleted_paths.append(path)

    async def fake_delete_integration(user_id, *, pool):
        deleted_users.append(user_id)
        return 1

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)
    monkeypatch.setattr(route.openbao_client, "delete", fake_delete_token)
    monkeypatch.setattr(route.github_integrations, "delete_by_user_id", fake_delete_integration)

    resp = client.delete("/api/auth/github")
    assert resp.status_code == 200
    assert resp.json() == {"status": "disconnected"}
    assert deleted_paths == ["github-tokens/t/u"]
    assert len(deleted_users) == 1
```

- [ ] **Step 2: Run, FAIL**

Run: `cd backend && uv run pytest tests/test_github_auth_route.py -v`
Expected: FAIL (module/route absent).

- [ ] **Step 3: Implémenter `services/github_publish/__init__.py` + `oauth.py`**

```python
# backend/src/role_builder/services/github_publish/__init__.py
"""Sprint 8 — services GitHub OAuth + publication."""
```

```python
# backend/src/role_builder/services/github_publish/oauth.py
"""Client OAuth GitHub : exchange code, get user info.

Le state CSRF n'est pas géré ici (cf. db_helpers.oauth_states). Cette
classe encapsule uniquement les appels HTTP vers GitHub.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
import structlog

from role_builder.config import settings

log = structlog.get_logger(__name__)


class GitHubOAuthClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

    def build_authorize_url(self, state: str) -> str:
        params = {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": settings.github_oauth_scope,
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> str:
        """Exchange code → access_token. Lève httpx.HTTPStatusError sur erreur."""
        secret = settings.github_oauth_client_secret
        if hasattr(secret, "get_secret_value"):
            secret_str = secret.get_secret_value()
        else:
            secret_str = str(secret)

        resp = await self._http.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": secret_str,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()
        if "access_token" not in body:
            raise ValueError(f"GitHub returned no access_token: {body}")
        return str(body["access_token"])

    async def get_user_info(self, access_token: str) -> dict:
        resp = await self._http.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()


# Singleton
gh_oauth = GitHubOAuthClient()
```

- [ ] **Step 4: Implémenter `routes/github_auth.py`**

```python
# backend/src/role_builder/routes/github_auth.py
"""Routes Sprint 8 — flow OAuth GitHub.

- GET  /api/auth/github/start    — démarre OAuth, retourne URL GitHub
- GET  /api/auth/github/callback — callback GitHub, échange code → token
- GET  /api/auth/github/status   — statut de la connexion (UI Ma stack)
- DELETE /api/auth/github        — déconnexion (revoke + delete row)
"""

from __future__ import annotations

import secrets as py_secrets
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import github_integrations, oauth_states
from role_builder.schemas.github import (
    CallbackResponse,
    GithubIntegrationStatus,
    StartOAuthResponse,
)
from role_builder.services.github_publish.oauth import gh_oauth
from role_builder.services.openbao_client import openbao_client

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/auth/github/start", response_model=StartOAuthResponse)
async def start_oauth(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StartOAuthResponse:
    state = py_secrets.token_urlsafe(32)
    await oauth_states.insert_state(
        state=state,
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        ttl_seconds=600,
        pool=db_pool.pool,
    )
    url = gh_oauth.build_authorize_url(state)
    log.info("github.oauth.started", user_id=str(user.user_id))
    return StartOAuthResponse(redirect_url=url)


@router.get("/auth/github/callback", response_model=CallbackResponse)
async def oauth_callback(code: str, state: str) -> CallbackResponse:
    info = await oauth_states.consume_state(state, pool=db_pool.pool)
    if info is None:
        raise HTTPException(status_code=400, detail="invalid or expired state")

    user_id = info["user_id"]
    tenant_id = info["tenant_id"]

    try:
        access_token = await gh_oauth.exchange_code(code)
        gh_user = await gh_oauth.get_user_info(access_token)
    except httpx.HTTPStatusError as exc:
        log.exception("github.oauth.upstream_error")
        raise HTTPException(status_code=502, detail=f"GitHub: {exc}") from exc

    openbao_path = f"github-tokens/{tenant_id}/{user_id}"
    await openbao_client.put(openbao_path, {"access_token": access_token})

    from role_builder.config import settings as _s
    await github_integrations.upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        github_login=str(gh_user["login"]),
        github_user_id=int(gh_user["id"]),
        openbao_path=openbao_path,
        scope=_s.github_oauth_scope,
        pool=db_pool.pool,
    )
    log.info("github.oauth.connected", user_id=str(user_id), github_login=gh_user["login"])
    return CallbackResponse(status="connected", github_login=str(gh_user["login"]))


@router.get("/auth/github/status", response_model=GithubIntegrationStatus)
async def status(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GithubIntegrationStatus:
    integration = await github_integrations.get_by_user_id(user.user_id, pool=db_pool.pool)
    if integration is None:
        return GithubIntegrationStatus(connected=False)
    return GithubIntegrationStatus(
        connected=True,
        github_login=str(integration["github_login"]),
        scope=str(integration["scope"]),
        last_validated_at=integration.get("last_validated_at"),
    )


@router.delete("/auth/github")
async def disconnect(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    integration = await github_integrations.get_by_user_id(user.user_id, pool=db_pool.pool)
    if integration is None:
        return {"status": "not-connected"}
    await openbao_client.delete(str(integration["openbao_path"]))
    await github_integrations.delete_by_user_id(user.user_id, pool=db_pool.pool)
    log.info("github.oauth.disconnected", user_id=str(user.user_id))
    return {"status": "disconnected"}
```

- [ ] **Step 5: Inclure le router dans `main.py`**

Ajouter à la liste des `from role_builder.routes import (...)`:
```python
github_auth,
```

Et après `app.include_router(role_documents_route...)` :
```python
app.include_router(github_auth.router, prefix="/api", tags=["github-auth"])
```

- [ ] **Step 6: Run, PASS**

Run: `cd backend && uv run pytest tests/test_github_auth_route.py tests/test_db_helpers_github_integrations.py -v`
Expected: tous PASS.

- [ ] **Step 7: Vérifier qu'aucune régression**

Run: `cd backend && uv run pytest -q`
Expected: 380+/380+ passed (370 + nouveaux).

- [ ] **Step 8: Commit**

```bash
git add backend/src/role_builder/db_helpers/github_integrations.py \
        backend/src/role_builder/schemas/github.py \
        backend/src/role_builder/services/github_publish/__init__.py \
        backend/src/role_builder/services/github_publish/oauth.py \
        backend/src/role_builder/routes/github_auth.py \
        backend/src/role_builder/main.py \
        backend/tests/test_db_helpers_github_integrations.py \
        backend/tests/test_github_auth_route.py
git commit -m "feat(backend): OAuth GitHub flow (start + callback + status + disconnect)"
```

---

## Tâche 5 — Tests `services/github_publish/oauth.py` isolés

**Note :** la tâche 4 teste l'intégration via les routes en monkeypatchant `gh_oauth.exchange_code` et `gh_oauth.get_user_info`. Ici on ajoute des tests unitaires de `oauth.py` lui-même (avec httpx mock) pour s'assurer que les requêtes GitHub sont bien formées.

**Files:**
- Create: `backend/tests/test_github_oauth.py`

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_github_oauth.py
"""Tests unitaires de services/github_publish/oauth.py (Sprint 8)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_build_authorize_url_includes_required_params(stubbed_env):
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    url = client.build_authorize_url("my-state")
    assert "https://github.com/login/oauth/authorize?" in url
    assert "state=my-state" in url
    assert "scope=public_repo" in url
    assert "client_id=" in url
    assert "redirect_uri=" in url


@pytest.mark.asyncio
async def test_exchange_code_posts_form_with_secret_and_returns_token(stubbed_env):
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    fake_resp = httpx.Response(
        200,
        json={"access_token": "ghp_xxx", "token_type": "bearer"},
    )

    with patch.object(client._http, "post", new=AsyncMock(return_value=fake_resp)) as post_mock:
        token = await client.exchange_code("code-xyz")
    assert token == "ghp_xxx"
    call = post_mock.call_args
    # Endpoint
    assert call.args[0] == "https://github.com/login/oauth/access_token"
    # Form data
    data = call.kwargs["data"]
    assert data["code"] == "code-xyz"
    assert "client_id" in data
    assert "client_secret" in data
    # Accept JSON
    assert call.kwargs["headers"]["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_exchange_code_raises_when_no_token(stubbed_env):
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    fake_resp = httpx.Response(200, json={"error": "bad_verification_code"})
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(ValueError, match="no access_token"):
            await client.exchange_code("bad")


@pytest.mark.asyncio
async def test_get_user_info_passes_bearer_and_returns_login(stubbed_env):
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    fake_resp = httpx.Response(
        200,
        json={"login": "alice", "id": 42, "name": "Alice"},
    )
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake_resp)) as get_mock:
        info = await client.get_user_info("ghp_xxx")
    assert info["login"] == "alice"
    call = get_mock.call_args
    assert call.args[0] == "https://api.github.com/user"
    assert call.kwargs["headers"]["Authorization"] == "Bearer ghp_xxx"
```

- [ ] **Step 2: Run, FAIL puis PASS après import**

(Le module existe depuis la tâche 4, donc PASS direct.)
Run: `cd backend && uv run pytest tests/test_github_oauth.py -v`
Expected: 4/4 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_github_oauth.py
git commit -m "test(backend): unitaires github_publish/oauth (build URL, exchange code, get user info)"
```

---

## Tâche 6 — Migration `add_license_to_publication_config`

**Files:**
- Create: `migrations/0013_add_license_to_publication_config.sql`

- [ ] **Step 1: Créer la migration**

```sql
-- migrations/0013_add_license_to_publication_config.sql
-- Sprint 8 : ajout du choix de licence par projet pour la publication GitHub.

ALTER TABLE role_publication_config
    ADD COLUMN license_choice text DEFAULT 'none' NOT NULL;

-- Valeurs attendues : 'none' / 'polyform-nc' / 'cc-by-nc-sa-4.0' /
-- 'cc-by-4.0' / 'mit'. Pas de CHECK contraint (à valider côté Pydantic
-- pour pouvoir ajouter de nouveaux choix sans migration).
```

- [ ] **Step 2: Appliquer**

Run: `cd /e/srcs/agflow.roles && ./scripts/apply_migrations.sh`
Expected: succès, colonne ajoutée.

- [ ] **Step 3: Commit**

```bash
git add migrations/0013_add_license_to_publication_config.sql
git commit -m "feat(db): migration 0013 license_choice sur role_publication_config"
```

---

## Tâche 7 — `services/github_publish/api_client.py` (REST API GitHub)

**Files:**
- Create: `backend/src/role_builder/services/github_publish/api_client.py`
- Create: `backend/tests/test_github_api_client.py`

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_github_api_client.py
"""Tests unitaires GitHubApiClient — list_repos, get_content, put_content, delete_content."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_list_repos_paginates_until_empty(stubbed_env):
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    page1 = httpx.Response(200, json=[{"full_name": "a/r1", "private": False, "default_branch": "main", "html_url": "x"}])
    page2 = httpx.Response(200, json=[])

    with patch.object(client._http, "get", new=AsyncMock(side_effect=[page1, page2])) as get_mock:
        repos = await client.list_repos()

    assert len(repos) == 1
    assert repos[0]["full_name"] == "a/r1"
    assert get_mock.call_count == 2


@pytest.mark.asyncio
async def test_get_content_returns_sha_when_200(stubbed_env):
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = httpx.Response(200, json={"sha": "abc123", "content": "..."})
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake)):
        sha = await client.get_content_sha("a/r", "path/to/f.md", "main")
    assert sha == "abc123"


@pytest.mark.asyncio
async def test_get_content_returns_none_when_404(stubbed_env):
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = httpx.Response(404, text="Not Found", request=httpx.Request("GET", "x"))
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake)):
        sha = await client.get_content_sha("a/r", "path/to/f.md", "main")
    assert sha is None


@pytest.mark.asyncio
async def test_put_content_creates_with_no_sha(stubbed_env):
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = httpx.Response(201, json={"commit": {"sha": "deadbeef"}})
    with patch.object(client._http, "put", new=AsyncMock(return_value=fake)) as put_mock:
        commit_sha = await client.put_content(
            owner="a", repo="r", path="f.md", branch="main",
            content_b64="aGVsbG8=", message="msg", existing_sha=None,
        )
    assert commit_sha == "deadbeef"
    body = put_mock.call_args.kwargs["json"]
    assert "sha" not in body
    assert body["message"] == "msg"
    assert body["content"] == "aGVsbG8="


@pytest.mark.asyncio
async def test_put_content_updates_with_sha(stubbed_env):
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = httpx.Response(200, json={"commit": {"sha": "newsha"}})
    with patch.object(client._http, "put", new=AsyncMock(return_value=fake)) as put_mock:
        await client.put_content(
            owner="a", repo="r", path="f.md", branch="main",
            content_b64="x", message="m", existing_sha="oldsha",
        )
    body = put_mock.call_args.kwargs["json"]
    assert body["sha"] == "oldsha"


@pytest.mark.asyncio
async def test_delete_content_passes_sha_and_message(stubbed_env):
    from role_builder.services.github_publish.api_client import GitHubApiClient

    client = GitHubApiClient(access_token="ghp_xxx")
    fake = httpx.Response(200, json={"commit": {"sha": "delsha"}})
    with patch.object(client._http, "request", new=AsyncMock(return_value=fake)) as req_mock:
        await client.delete_content(
            owner="a", repo="r", path="f.md", branch="main",
            existing_sha="abc", message="del",
        )
    call = req_mock.call_args
    assert call.args[0] == "DELETE"
    body = call.kwargs["json"]
    assert body["sha"] == "abc"
    assert body["message"] == "del"
```

- [ ] **Step 2: Run, FAIL**

Run: `cd backend && uv run pytest tests/test_github_api_client.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter**

```python
# backend/src/role_builder/services/github_publish/api_client.py
"""Client REST GitHub : list repos, get/put/delete contents.

Le token bearer est passé au constructeur. Les erreurs HTTP sont remontées
via httpx (HTTPStatusError). Pagination de list_repos jusqu'à un page vide.
"""

from __future__ import annotations

from typing import Any

import httpx


class GitHubApiClient:
    def __init__(self, *, access_token: str) -> None:
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    async def list_repos(self) -> list[dict[str, Any]]:
        """Liste tous les repos accessibles (pagination par 100)."""
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = await self._http.get(
                "https://api.github.com/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos

    async def get_content_sha(
        self, owner: str, repo: str, path: str, branch: str,
    ) -> str | None:
        """Retourne le sha du fichier ou None si 404."""
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return str(resp.json()["sha"])

    async def put_content(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        content_b64: str,
        message: str,
        existing_sha: str | None,
    ) -> str:
        """PUT /contents/{path}. Retourne le commit_sha."""
        body: dict[str, Any] = {
            "message": message,
            "content": content_b64,
            "branch": branch,
        }
        if existing_sha is not None:
            body["sha"] = existing_sha
        resp = await self._http.put(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            json=body,
        )
        resp.raise_for_status()
        return str(resp.json()["commit"]["sha"])

    async def delete_content(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        existing_sha: str,
        message: str,
    ) -> str:
        """DELETE /contents/{path}. Retourne le commit_sha."""
        resp = await self._http.request(
            "DELETE",
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            json={"message": message, "branch": branch, "sha": existing_sha},
        )
        resp.raise_for_status()
        return str(resp.json()["commit"]["sha"])

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run, PASS**

Run: `cd backend && uv run pytest tests/test_github_api_client.py -v`
Expected: 6/6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/services/github_publish/api_client.py \
        backend/tests/test_github_api_client.py
git commit -m "feat(backend): GitHubApiClient (list repos + get/put/delete contents avec pagination + sha tracking)"
```

---

## Tâche 8 — Routes `/github/repos` + `/role-projects/{id}/publication-config`

**Files:**
- Modify: `backend/src/role_builder/schemas/github.py` (ajouter DTOs)
- Create: `backend/src/role_builder/db_helpers/role_publication_config.py` (helper config)
- Create: `backend/src/role_builder/routes/github_publish.py` (router)
- Modify: `backend/src/role_builder/main.py` (include)
- Create: `backend/tests/test_github_publish_route.py`

### Tâche 8.1 — Helper `role_publication_config`

- [ ] **Step 1: Créer le helper db**

```python
# backend/src/role_builder/db_helpers/role_publication_config.py
"""CRUD asyncpg pour role_publication_config (Sprint 8)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

_GET_SQL = """
    SELECT role_project_id, repo_full_name, target_subdirectory, branch,
           commit_message_template, license_choice, created_at, updated_at
    FROM role_publication_config
    WHERE role_project_id = $1
"""

_UPSERT_SQL = """
    INSERT INTO role_publication_config
        (role_project_id, repo_full_name, target_subdirectory, branch,
         commit_message_template, license_choice)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (role_project_id) DO UPDATE SET
        repo_full_name = EXCLUDED.repo_full_name,
        target_subdirectory = EXCLUDED.target_subdirectory,
        branch = EXCLUDED.branch,
        commit_message_template = EXCLUDED.commit_message_template,
        license_choice = EXCLUDED.license_choice,
        updated_at = now()
"""


async def get_by_project_id(
    project_id: UUID, *, pool: asyncpg.Pool,
) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_SQL, project_id)
    return dict(row) if row is not None and not isinstance(row, dict) else row


async def upsert(
    *,
    role_project_id: UUID,
    repo_full_name: str,
    target_subdirectory: str,
    branch: str,
    commit_message_template: str,
    license_choice: str,
    pool: asyncpg.Pool,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _UPSERT_SQL,
            role_project_id,
            repo_full_name,
            target_subdirectory,
            branch,
            commit_message_template,
            license_choice,
        )
```

### Tâche 8.2 — Schemas étendus

- [ ] **Step 1: Étendre `schemas/github.py`**

Append:
```python
from typing import Literal

LicenseChoice = Literal[
    "none", "polyform-nc", "cc-by-nc-sa-4.0", "cc-by-4.0", "mit",
]


class GithubRepo(BaseModel):
    full_name: str
    private: bool
    default_branch: str
    html_url: str


class PublicationConfigOut(BaseModel):
    role_project_id: UUID
    repo_full_name: str
    target_subdirectory: str
    branch: str
    commit_message_template: str
    license_choice: LicenseChoice


class PublicationConfigRequest(BaseModel):
    repo_full_name: str
    target_subdirectory: str
    branch: str = "main"
    commit_message_template: str = "Update role {role_name}"
    license_choice: LicenseChoice = "none"
```

### Tâche 8.3 — Routes config

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_github_publish_route.py
"""Tests routes Sprint 8 — GitHub publish (repos + config + publish)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def test_list_repos_400_when_not_connected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    async def fake_get(user_id, *, pool):
        return None

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)

    resp = client.get("/api/github/repos")
    assert resp.status_code == 400


def test_list_repos_returns_list_with_subset_of_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    async def fake_get(user_id, *, pool):
        return {"openbao_path": "github-tokens/t/u"}

    async def fake_token(path):
        return {"access_token": "ghp_x"}

    repos_full = [
        {
            "full_name": "alice/role-pack",
            "private": False,
            "default_branch": "main",
            "html_url": "https://github.com/alice/role-pack",
            "stargazers_count": 5,
            "ignored_field": "value",
        }
    ]

    class _StubApiClient:
        def __init__(self, *, access_token):
            assert access_token == "ghp_x"
        async def list_repos(self):
            return repos_full
        async def aclose(self):
            return None

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)
    monkeypatch.setattr(route.openbao_client, "get", fake_token)
    monkeypatch.setattr(route, "GitHubApiClient", _StubApiClient)

    resp = client.get("/api/github/repos")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    # Seuls les champs pertinents sont exposés
    assert set(body[0].keys()) == {"full_name", "private", "default_branch", "html_url"}
    assert body[0]["full_name"] == "alice/role-pack"


def test_get_publication_config_returns_404_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    async def fake_get(project_id, *, pool):
        return None

    monkeypatch.setattr(route.role_publication_config, "get_by_project_id", fake_get)

    resp = client.get(f"/api/role-projects/{uuid4()}/publication-config")
    assert resp.status_code == 404


def test_put_publication_config_upserts_with_license_choice(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    project_id = uuid4()
    upsert_calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs):
        upsert_calls.append(kwargs)

    monkeypatch.setattr(route.role_publication_config, "upsert", fake_upsert)

    resp = client.put(
        f"/api/role-projects/{project_id}/publication-config",
        json={
            "repo_full_name": "alice/roles",
            "target_subdirectory": "ux-clea",
            "branch": "main",
            "commit_message_template": "Update {role_name}",
            "license_choice": "cc-by-nc-sa-4.0",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "saved"}
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["license_choice"] == "cc-by-nc-sa-4.0"
    assert str(upsert_calls[0]["role_project_id"]) == str(project_id)


def test_put_publication_config_rejects_invalid_license(client: TestClient) -> None:
    """license_choice doit être dans le Literal, sinon 422."""
    resp = client.put(
        f"/api/role-projects/{uuid4()}/publication-config",
        json={
            "repo_full_name": "alice/roles",
            "target_subdirectory": "x",
            "license_choice": "GPL-3.0",
        },
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Créer `routes/github_publish.py`** avec un router FastAPI exposant pour l'instant uniquement `GET /github/repos`, `GET/PUT /role-projects/{id}/publication-config`. Les endpoints `/publish` `/unpublish` `/publications` arrivent en tâche 9.

```python
# backend/src/role_builder/routes/github_publish.py
"""Routes Sprint 8 — GitHub publish (repos + config + publish + history).

Endpoints :
- GET   /api/github/repos
- GET   /api/role-projects/{id}/publication-config
- PUT   /api/role-projects/{id}/publication-config
- POST  /api/role-projects/{id}/publish-to-github           (tâche 9)
- DELETE /api/role-projects/{id}/github-publication        (tâche 9)
- GET   /api/role-projects/{id}/publications               (tâche 9)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import (
    github_integrations,
    role_publication_config,
)
from role_builder.schemas.github import (
    GithubRepo,
    PublicationConfigOut,
    PublicationConfigRequest,
)
from role_builder.services.github_publish.api_client import GitHubApiClient
from role_builder.services.openbao_client import openbao_client

router = APIRouter()
log = structlog.get_logger(__name__)


def _bad_gateway(exc: httpx.HTTPStatusError) -> HTTPException:
    status_code = exc.response.status_code if exc.response is not None else None
    return HTTPException(
        status_code=502, detail=f"GitHub returned HTTP {status_code}: {exc}"
    )


@router.get("/github/repos", response_model=list[GithubRepo])
async def list_repos(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[GithubRepo]:
    integration = await github_integrations.get_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
    if integration is None:
        raise HTTPException(status_code=400, detail="GitHub not connected")
    token_data = await openbao_client.get(str(integration["openbao_path"]))
    access_token = str(token_data["access_token"]) if token_data else ""
    if not access_token:
        raise HTTPException(status_code=502, detail="GitHub token missing in OpenBao")

    api = GitHubApiClient(access_token=access_token)
    try:
        repos = await api.list_repos()
    except httpx.HTTPStatusError as exc:
        raise _bad_gateway(exc) from exc
    finally:
        await api.aclose()

    return [
        GithubRepo(
            full_name=str(r["full_name"]),
            private=bool(r["private"]),
            default_branch=str(r["default_branch"]),
            html_url=str(r["html_url"]),
        )
        for r in repos
    ]


@router.get(
    "/role-projects/{project_id}/publication-config",
    response_model=PublicationConfigOut,
)
async def get_publication_config(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> PublicationConfigOut:
    config = await role_publication_config.get_by_project_id(
        project_id, pool=db_pool.pool,
    )
    if config is None:
        raise HTTPException(
            status_code=404, detail="publication config not set for this project"
        )
    return PublicationConfigOut(**config)


@router.put("/role-projects/{project_id}/publication-config")
async def set_publication_config(
    project_id: UUID,
    body: PublicationConfigRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> dict[str, str]:
    await role_publication_config.upsert(
        role_project_id=project_id,
        repo_full_name=body.repo_full_name,
        target_subdirectory=body.target_subdirectory,
        branch=body.branch,
        commit_message_template=body.commit_message_template,
        license_choice=body.license_choice,
        pool=db_pool.pool,
    )
    log.info(
        "github.publication_config.saved",
        project_id=str(project_id),
        license=body.license_choice,
    )
    return {"status": "saved"}
```

- [ ] **Step 4: Inclure dans `main.py`**

Ajouter `github_publish,` dans l'import groupé, puis :
```python
app.include_router(github_publish.router, prefix="/api", tags=["github-publish"])
```

- [ ] **Step 5: Run, PASS**

Run: `cd backend && uv run pytest tests/test_github_publish_route.py -v`
Expected: 5/5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/role_builder/db_helpers/role_publication_config.py \
        backend/src/role_builder/schemas/github.py \
        backend/src/role_builder/routes/github_publish.py \
        backend/src/role_builder/main.py \
        backend/tests/test_github_publish_route.py
git commit -m "feat(backend): routes GitHub repos + publication-config (avec license_choice Pydantic Literal)"
```

---

## Tâche 9 — Builder README + publisher (push réel) + helper `role_publications`

**Files:**
- Create: `backend/src/role_builder/db_helpers/role_publications.py`
- Create: `backend/src/role_builder/services/github_publish/readme_builder.py`
- Create: `backend/src/role_builder/services/github_publish/publisher.py`
- Modify: `backend/src/role_builder/schemas/github.py` (DTOs publish)
- Modify: `backend/src/role_builder/routes/github_publish.py` (3 nouveaux endpoints)
- Create: `backend/tests/test_db_helpers_role_publications.py`
- Create: `backend/tests/test_github_readme_builder.py`
- Create: `backend/tests/test_github_publisher.py`
- Modify: `backend/tests/test_github_publish_route.py` (étendre avec publish/unpublish/history)

C'est la tâche la plus volumineuse — gros morceau métier.

### 9.1 — Helper `role_publications`

- [ ] **Step 1: Test + impl** (pattern identique aux autres helpers, simple INSERT + LIST + DELETE)

```python
# backend/src/role_builder/db_helpers/role_publications.py
"""CRUD asyncpg pour role_publications (Sprint 8)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO role_publications
        (role_project_id, tenant_id, user_id, commit_sha, files_count, summary)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id, published_at
"""

_LIST_SQL = """
    SELECT id, role_project_id, tenant_id, user_id, commit_sha,
           published_at, files_count, summary
    FROM role_publications
    WHERE role_project_id = $1
    ORDER BY published_at DESC
    LIMIT $2
"""

_LATEST_SQL = """
    SELECT published_at, commit_sha
    FROM role_publications
    WHERE role_project_id = $1
    ORDER BY published_at DESC
    LIMIT 1
"""


async def insert(
    *,
    role_project_id: UUID,
    tenant_id: UUID,
    user_id: UUID,
    commit_sha: str,
    files_count: int,
    summary: str,
    pool: asyncpg.Pool,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _INSERT_SQL,
            role_project_id, tenant_id, user_id, commit_sha, files_count, summary,
        )
    return dict(row) if not isinstance(row, dict) else row


async def list_by_project(
    project_id: UUID, *, limit: int = 50, pool: asyncpg.Pool,
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_SQL, project_id, limit)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_latest(project_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LATEST_SQL, project_id)
    return dict(row) if row is not None and not isinstance(row, dict) else row
```

Tests stub-pool standard (3 tests : insert capture les args, list_by_project query order, get_latest retourne None ou row).

### 9.2 — `readme_builder.py`

- [ ] **Step 1: Test rouge**

```python
# backend/tests/test_github_readme_builder.py
"""Tests TDD pour services/github_publish/readme_builder.py."""

from __future__ import annotations


def test_render_readme_includes_display_name_and_sections():
    from role_builder.services.github_publish.readme_builder import render_readme

    project = {
        "display_name": "UX Designer Clea",
        "description": "Agent expert en design UX",
        "language": "fr",
        "service_types": ["claude-code"],
    }
    docs = {
        "Role": [{"name": "principe-empathie"}],
        "Missions": [{"name": "audit-ux"}, {"name": "onboarding"}],
    }
    md = render_readme(project=project, docs_by_section=docs, github_login="alice")

    assert "# UX Designer Clea" in md
    assert "Agent expert en design UX" in md
    assert "[@alice]" in md
    assert "**Role** (1 documents)" in md
    assert "**Missions** (2 documents)" in md
    assert "claude-code" in md


def test_render_license_polyform_includes_full_text():
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("polyform-nc", author_login="alice")
    assert text is not None
    assert "PolyForm Noncommercial License 1.0.0" in text
    assert "Required Notice: Copyright" in text
    assert "alice" in text


def test_render_license_cc_by_nc_sa_includes_attribution():
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("cc-by-nc-sa-4.0", author_login="alice")
    assert text is not None
    assert "Creative Commons" in text
    assert "Attribution-NonCommercial-ShareAlike" in text
    assert "alice" in text
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/" in text


def test_render_license_cc_by_includes_attribution():
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("cc-by-4.0", author_login="alice")
    assert text is not None
    assert "Attribution 4.0" in text
    assert "https://creativecommons.org/licenses/by/4.0/" in text


def test_render_license_mit():
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("mit", author_login="alice")
    assert text is not None
    assert "MIT License" in text
    assert "alice" in text
    assert "WITHOUT WARRANTY" in text


def test_render_license_none_returns_none():
    from role_builder.services.github_publish.readme_builder import render_license_file

    assert render_license_file("none", author_login="alice") is None
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implémenter**

```python
# backend/src/role_builder/services/github_publish/readme_builder.py
"""Génération du README.md et du LICENSE pour un rôle publié sur GitHub."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def render_readme(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    github_login: str,
) -> str:
    """Compose le README.md à pousser dans le repo cible."""
    sections_summary = "\n".join(
        f"- **{section}** ({len(docs)} documents)"
        for section, docs in docs_by_section.items()
    )
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    description = project.get("description") or ""
    language = project.get("language") or "fr"
    service_types = project.get("service_types") or ["claude-code"]
    service_types_str = ", ".join(service_types)

    return f"""# {project["display_name"]}

> {description}

**Auteur :** [@{github_login}](https://github.com/{github_login})
**Langue :** {language}
**Dernière mise à jour :** {today}
**Service types ag.flow :** {service_types_str}

## Sections

{sections_summary}

## Importer dans ag.flow

1. Téléchargez ce répertoire en ZIP
2. Dans ag.flow, créez un rôle vide avec le `display_name` de votre choix
3. Utilisez `POST /api/admin/roles/{{id}}/import` avec le ZIP
4. Optionnel : déclenchez `POST /api/admin/roles/{{id}}/generate-prompts`
   pour régénérer le prompt orchestrateur

## Structure

```
.
├── README.md          (ce fichier)
├── LICENSE            (la licence choisie pour ce rôle)
├── role.json          (métadonnées + structure des sections)
├── identity.md        (identité de l'agent)
└── sections/          (un sous-dossier par section)
```

---

Généré par Role Builder.
"""


_POLYFORM_NC = """Copyright (c) {year} {author_login}

This content is licensed under the PolyForm Noncommercial License 1.0.0.

Required Notice: Copyright (c) {year} {author_login} (https://github.com/{author_login})

# PolyForm Noncommercial License 1.0.0

<https://polyformproject.org/licenses/noncommercial/1.0.0>

The verbatim text of PolyForm Noncommercial 1.0.0 follows. See
<https://polyformproject.org/licenses/noncommercial/1.0.0> for the
full normative text. You may not modify the text of this license.
"""

_CC_BY_NC_SA = """Copyright (c) {year} {author_login} (https://github.com/{author_login})

This work is licensed under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International License.

To view a copy of this license, visit:
<https://creativecommons.org/licenses/by-nc-sa/4.0/>
"""

_CC_BY = """Copyright (c) {year} {author_login} (https://github.com/{author_login})

This work is licensed under the Creative Commons Attribution 4.0
International License (CC-BY 4.0).

To view a copy of this license, visit:
<https://creativecommons.org/licenses/by/4.0/>
"""

_MIT = """MIT License

Copyright (c) {year} {author_login}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"""


def render_license_file(license_choice: str, *, author_login: str) -> str | None:
    """Retourne le contenu d'un fichier LICENSE selon le choix utilisateur.

    Retourne None si license_choice == 'none' (pas de fichier à publier).
    """
    year = datetime.now(tz=timezone.utc).year
    fmt = {"year": year, "author_login": author_login}
    if license_choice == "polyform-nc":
        return _POLYFORM_NC.format(**fmt)
    if license_choice == "cc-by-nc-sa-4.0":
        return _CC_BY_NC_SA.format(**fmt)
    if license_choice == "cc-by-4.0":
        return _CC_BY.format(**fmt)
    if license_choice == "mit":
        return _MIT.format(**fmt)
    if license_choice == "none":
        return None
    raise ValueError(f"unknown license_choice: {license_choice}")
```

- [ ] **Step 4: Run, PASS**

Run: `cd backend && uv run pytest tests/test_github_readme_builder.py -v`
Expected: 6/6 passed.

### 9.3 — `publisher.py`

- [ ] **Step 1: Test rouge** — couvre `build_publication_files`, `push_publication`, `delete_publication`.

```python
# backend/tests/test_github_publisher.py
"""Tests TDD pour services/github_publish/publisher.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _make_project(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "display_name": "Agent",
        "description": "desc",
        "identity": "# Identity",
        "language": "fr",
        "service_types": ["claude-code"],
        "target_role_id": None,
    }
    base.update(overrides)
    return base


def _make_docs() -> dict[str, list[dict[str, Any]]]:
    return {
        "Role": [{"name": "doc1", "content": "## Doc1"}],
        "Missions": [{"name": "mission1", "content": "## M1"}],
    }


@pytest.mark.asyncio
async def test_build_publication_files_includes_readme_role_json_identity_and_sections(
    stubbed_env,
):
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    files = await publisher.build_publication_files(
        project=project, docs_by_section=docs, github_login="alice", license_choice="mit",
    )
    paths = set(files.keys())
    assert "README.md" in paths
    assert "role.json" in paths
    assert "identity.md" in paths
    assert "sections/role/doc1.md" in paths
    assert "sections/missions/mission1.md" in paths
    assert "LICENSE" in paths
    # role.json contient bien le display_name
    role_json = json.loads(files["role.json"])
    assert role_json["display_name"] == "Agent"


@pytest.mark.asyncio
async def test_build_publication_files_skips_license_when_none(stubbed_env):
    from role_builder.services.github_publish import publisher

    files = await publisher.build_publication_files(
        project=_make_project(), docs_by_section=_make_docs(),
        github_login="alice", license_choice="none",
    )
    assert "LICENSE" not in files


class _StubGithubApi:
    def __init__(self, *, access_token: str):
        self.access_token = access_token
        self.put_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.existing_shas: dict[str, str] = {}

    async def get_content_sha(self, owner, repo, path, branch):
        return self.existing_shas.get(path)

    async def put_content(self, *, owner, repo, path, branch,
                          content_b64, message, existing_sha):
        self.put_calls.append({
            "path": path, "existing_sha": existing_sha, "message": message,
        })
        return f"commit-for-{path}"

    async def delete_content(self, *, owner, repo, path, branch,
                             existing_sha, message):
        self.delete_calls.append({"path": path, "existing_sha": existing_sha})
        return "del-commit"

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_push_publication_pushes_all_files_and_records(stubbed_env):
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "mit",
    }
    api = _StubGithubApi(access_token="ghp_xxx")
    insert_calls: list[dict[str, Any]] = []

    async def fake_insert(**kwargs):
        insert_calls.append(kwargs)
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()

    result = await publisher.push_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
    )

    # Tous les fichiers sont publiés (5 fichiers + LICENSE = 6)
    assert len(api.put_calls) == 6
    pushed_paths = [c["path"] for c in api.put_calls]
    # Tous sont préfixés par le subdir
    assert all(p.startswith("ux-clea/") for p in pushed_paths)
    # Aucun n'a de existing_sha (fichiers neufs)
    assert all(c["existing_sha"] is None for c in api.put_calls)
    # 1 record en DB
    assert len(insert_calls) == 1
    assert insert_calls[0]["files_count"] == 6
    assert "alice/roles" in insert_calls[0]["summary"]
    # Commit message templaté
    assert "Update Agent" in api.put_calls[0]["message"]
    # Result exposé proprement
    assert result["files_count"] == 6
    assert "alice/roles" in result["url"]


@pytest.mark.asyncio
async def test_push_publication_uses_existing_sha_for_existing_files(stubbed_env):
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "none",
    }
    api = _StubGithubApi(access_token="ghp_x")
    api.existing_shas["ux-clea/README.md"] = "old-sha"

    async def fake_insert(**kwargs):
        return {"id": uuid4(), "published_at": None}

    pool = MagicMock()
    await publisher.push_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", user_id=uuid4(), tenant_id=project["tenant_id"],
        api=api, insert_publication=fake_insert, pool=pool,
    )
    readme_call = next(c for c in api.put_calls if c["path"] == "ux-clea/README.md")
    assert readme_call["existing_sha"] == "old-sha"


@pytest.mark.asyncio
async def test_delete_publication_iterates_files_and_deletes(stubbed_env):
    from role_builder.services.github_publish import publisher

    project = _make_project()
    docs = _make_docs()
    config = {
        "repo_full_name": "alice/roles",
        "target_subdirectory": "ux-clea",
        "branch": "main",
        "commit_message_template": "Update {role_name}",
        "license_choice": "mit",
    }
    api = _StubGithubApi(access_token="ghp_x")
    api.existing_shas = {
        "ux-clea/README.md": "s1",
        "ux-clea/role.json": "s2",
        "ux-clea/identity.md": "s3",
        "ux-clea/LICENSE": "s4",
        "ux-clea/sections/role/doc1.md": "s5",
        "ux-clea/sections/missions/mission1.md": "s6",
    }

    deleted = await publisher.delete_publication(
        project=project, docs_by_section=docs, config=config,
        github_login="alice", api=api,
    )
    assert deleted == 6
    assert len(api.delete_calls) == 6
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implémenter**

```python
# backend/src/role_builder/services/github_publish/publisher.py
"""Construction et push des fichiers vers GitHub."""

from __future__ import annotations

import base64
import json
from typing import Any, Awaitable, Callable
from uuid import UUID

import asyncpg
import structlog

from role_builder.services.github_publish.api_client import GitHubApiClient
from role_builder.services.github_publish.readme_builder import (
    render_license_file,
    render_readme,
)

log = structlog.get_logger(__name__)


def _build_role_json(
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    sections = [
        {"name": s, "documents": [d["name"] for d in docs]}
        for s, docs in docs_by_section.items()
    ]
    return {
        "display_name": project["display_name"],
        "description": project.get("description") or "",
        "identity": project.get("identity") or "",
        "language": project.get("language") or "fr",
        "service_types": project.get("service_types") or ["claude-code"],
        "sections": sections,
    }


async def build_publication_files(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    github_login: str,
    license_choice: str,
) -> dict[str, str]:
    """Compose tous les fichiers à publier (relpath → contenu texte).

    Inclut README.md, role.json, identity.md, sections/<sec>/<name>.md,
    et optionnellement LICENSE selon `license_choice`.
    """
    files: dict[str, str] = {}

    files["README.md"] = render_readme(
        project=project, docs_by_section=docs_by_section, github_login=github_login,
    )
    files["role.json"] = json.dumps(
        _build_role_json(project, docs_by_section),
        indent=2,
        ensure_ascii=False,
    )
    files["identity.md"] = str(project.get("identity") or "")
    for section, docs in docs_by_section.items():
        for doc in docs:
            relpath = f"sections/{section.lower()}/{doc['name']}.md"
            files[relpath] = str(doc.get("content") or "")

    license_text = render_license_file(license_choice, author_login=github_login)
    if license_text is not None:
        files["LICENSE"] = license_text

    return files


def _format_message(template: str, project: dict[str, Any]) -> str:
    return template.format(role_name=str(project["display_name"]))


async def push_publication(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    github_login: str,
    user_id: UUID,
    tenant_id: UUID,
    api: GitHubApiClient,
    insert_publication: Callable[..., Awaitable[dict[str, Any]]],
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Push tous les fichiers d'un rôle vers GitHub.

    1. Build files (README + role.json + identity + sections + LICENSE)
    2. Pour chaque file : GET sha existant → PUT
    3. Insert role_publications row
    """
    files = await build_publication_files(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=str(config.get("license_choice") or "none"),
    )

    owner, repo = str(config["repo_full_name"]).split("/", 1)
    base_path = str(config["target_subdirectory"]).strip("/")
    branch = str(config["branch"])
    commit_msg = _format_message(str(config["commit_message_template"]), project)

    last_commit_sha: str | None = None
    for relpath, content in files.items():
        full_path = f"{base_path}/{relpath}" if base_path else relpath
        existing_sha = await api.get_content_sha(owner, repo, full_path, branch)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        last_commit_sha = await api.put_content(
            owner=owner, repo=repo, path=full_path, branch=branch,
            content_b64=content_b64, message=commit_msg,
            existing_sha=existing_sha,
        )

    summary = f"Pushed to {config['repo_full_name']}/{base_path}"
    await insert_publication(
        role_project_id=project["id"],
        tenant_id=tenant_id,
        user_id=user_id,
        commit_sha=str(last_commit_sha or ""),
        files_count=len(files),
        summary=summary,
        pool=pool,
    )

    log.info(
        "github.publish.completed",
        project_id=str(project["id"]),
        files_count=len(files),
        commit_sha=last_commit_sha,
    )
    return {
        "commit_sha": last_commit_sha,
        "url": f"https://github.com/{owner}/{repo}/tree/{branch}/{base_path}",
        "files_count": len(files),
    }


async def delete_publication(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    github_login: str,
    api: GitHubApiClient,
) -> int:
    """Supprime tous les fichiers du sous-répertoire publié.

    Reconstruit la liste des fichiers attendus (déterministe), récupère
    leur sha actuel, et envoie un DELETE pour chacun. Retourne le nombre
    de fichiers effectivement supprimés.
    """
    files = await build_publication_files(
        project=project,
        docs_by_section=docs_by_section,
        github_login=github_login,
        license_choice=str(config.get("license_choice") or "none"),
    )
    owner, repo = str(config["repo_full_name"]).split("/", 1)
    base_path = str(config["target_subdirectory"]).strip("/")
    branch = str(config["branch"])
    msg = f"Unpublish role {project['display_name']}"

    deleted = 0
    for relpath in files:
        full_path = f"{base_path}/{relpath}" if base_path else relpath
        sha = await api.get_content_sha(owner, repo, full_path, branch)
        if sha is None:
            continue  # Already deleted ou jamais publié
        await api.delete_content(
            owner=owner, repo=repo, path=full_path, branch=branch,
            existing_sha=sha, message=msg,
        )
        deleted += 1
    return deleted
```

- [ ] **Step 4: Run, PASS**

### 9.4 — Routes `/publish`, `/unpublish`, `/publications`

- [ ] **Step 1: Étendre les schemas**

```python
# Append à schemas/github.py
class PublishResponse(BaseModel):
    commit_sha: str | None
    url: str
    files_count: int


class PublicationOut(BaseModel):
    id: UUID
    role_project_id: UUID
    user_id: UUID
    commit_sha: str
    published_at: datetime
    files_count: int | None = None
    summary: str | None = None
```

- [ ] **Step 2: Étendre `routes/github_publish.py`** avec les 3 endpoints

```python
# Append à routes/github_publish.py

from role_builder.db_helpers import role_documents, role_projects, role_publications
from role_builder.services.github_publish import publisher as gh_publisher
from role_builder.schemas.github import PublicationOut, PublishResponse


async def _api_for_user(user: CurrentUser) -> tuple[GitHubApiClient, str]:
    """Helper : retourne un GitHubApiClient + le github_login pour ``user``.
    Lève HTTPException 400 si non connecté.
    """
    integration = await github_integrations.get_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
    if integration is None:
        raise HTTPException(status_code=400, detail="GitHub not connected")
    token_data = await openbao_client.get(str(integration["openbao_path"]))
    if not token_data or not token_data.get("access_token"):
        raise HTTPException(status_code=502, detail="GitHub token missing in OpenBao")
    api = GitHubApiClient(access_token=str(token_data["access_token"]))
    return api, str(integration["github_login"])


@router.post(
    "/role-projects/{project_id}/publish-to-github",
    response_model=PublishResponse,
)
async def publish_to_github(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PublishResponse:
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")
    config = await role_publication_config.get_by_project_id(
        project_id, pool=db_pool.pool,
    )
    if config is None:
        raise HTTPException(
            status_code=400, detail="publication config not set for this project",
        )
    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id, pool=db_pool.pool,
    )

    api, github_login = await _api_for_user(user)
    try:
        result = await gh_publisher.push_publication(
            project=project,
            docs_by_section=docs_by_section,
            config=config,
            github_login=github_login,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            api=api,
            insert_publication=role_publications.insert,
            pool=db_pool.pool,
        )
    except httpx.HTTPStatusError as exc:
        raise _bad_gateway(exc) from exc
    finally:
        await api.aclose()

    return PublishResponse(**result)


@router.delete("/role-projects/{project_id}/github-publication")
async def unpublish_from_github(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, int]:
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")
    config = await role_publication_config.get_by_project_id(
        project_id, pool=db_pool.pool,
    )
    if config is None:
        raise HTTPException(
            status_code=400, detail="publication config not set for this project",
        )
    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id, pool=db_pool.pool,
    )

    api, github_login = await _api_for_user(user)
    try:
        deleted = await gh_publisher.delete_publication(
            project=project,
            docs_by_section=docs_by_section,
            config=config,
            github_login=github_login,
            api=api,
        )
    except httpx.HTTPStatusError as exc:
        raise _bad_gateway(exc) from exc
    finally:
        await api.aclose()

    return {"deleted_files": deleted}


@router.get(
    "/role-projects/{project_id}/publications",
    response_model=list[PublicationOut],
)
async def list_publications(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> list[PublicationOut]:
    rows = await role_publications.list_by_project(
        project_id, pool=db_pool.pool,
    )
    return [PublicationOut(**r) for r in rows]
```

- [ ] **Step 3: Étendre les tests `test_github_publish_route.py`**

```python
def test_publish_404_when_project_unknown(client, monkeypatch):
    from role_builder.routes import github_publish as route

    async def fake_get(pid, *, pool):
        return None

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get)
    resp = client.post(f"/api/role-projects/{uuid4()}/publish-to-github")
    assert resp.status_code == 404


def test_publish_400_when_config_missing(client, monkeypatch):
    from role_builder.routes import github_publish as route

    async def fake_get_project(pid, *, pool):
        return {"id": pid, "tenant_id": uuid4(), "display_name": "X"}

    async def fake_get_config(pid, *, pool):
        return None

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(route.role_publication_config, "get_by_project_id", fake_get_config)
    resp = client.post(f"/api/role-projects/{uuid4()}/publish-to-github")
    assert resp.status_code == 400


def test_list_publications_returns_history(client, monkeypatch):
    from datetime import datetime, timezone
    from role_builder.routes import github_publish as route

    project_id = uuid4()
    rows = [
        {
            "id": uuid4(), "role_project_id": project_id, "tenant_id": uuid4(),
            "user_id": uuid4(), "commit_sha": "abc", "published_at": datetime.now(tz=timezone.utc),
            "files_count": 5, "summary": "Pushed",
        }
    ]

    async def fake_list(pid, *, limit, pool):
        return rows

    monkeypatch.setattr(route.role_publications, "list_by_project", fake_list)
    resp = client.get(f"/api/role-projects/{project_id}/publications")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["commit_sha"] == "abc"
```

- [ ] **Step 4: Run full backend, PASS, regression check**

Run: `cd backend && uv run pytest -q`
Expected: 400+ passed (370 + ~30 nouveaux Sprint 8).

- [ ] **Step 5: Commit**

```bash
git add backend/src/role_builder/db_helpers/role_publications.py \
        backend/src/role_builder/services/github_publish/readme_builder.py \
        backend/src/role_builder/services/github_publish/publisher.py \
        backend/src/role_builder/schemas/github.py \
        backend/src/role_builder/routes/github_publish.py \
        backend/tests/test_db_helpers_role_publications.py \
        backend/tests/test_github_readme_builder.py \
        backend/tests/test_github_publisher.py \
        backend/tests/test_github_publish_route.py
git commit -m "feat(backend): publisher GitHub (build files + push avec sha tracking + delete + history)"
```

---

## Tâche 10 — Frontend types + client API github

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api/github.ts`
- Create: `frontend/src/__tests__/github-api.test.ts`

- [ ] **Step 1: Étendre types.ts**

```typescript
// Sprint 8 — GitHub publication types
export type LicenseChoice =
  | 'none'
  | 'polyform-nc'
  | 'cc-by-nc-sa-4.0'
  | 'cc-by-4.0'
  | 'mit';

export interface GithubIntegrationStatus {
  connected: boolean;
  github_login: string | null;
  scope: string | null;
  last_validated_at: string | null;
}

export interface GithubRepo {
  full_name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
}

export interface PublicationConfig {
  role_project_id: string;
  repo_full_name: string;
  target_subdirectory: string;
  branch: string;
  commit_message_template: string;
  license_choice: LicenseChoice;
}

export interface PublicationConfigRequest {
  repo_full_name: string;
  target_subdirectory: string;
  branch?: string;
  commit_message_template?: string;
  license_choice?: LicenseChoice;
}

export interface PublishResponse {
  commit_sha: string | null;
  url: string;
  files_count: number;
}

export interface Publication {
  id: string;
  role_project_id: string;
  user_id: string;
  commit_sha: string;
  published_at: string;
  files_count: number | null;
  summary: string | null;
}
```

- [ ] **Step 2: Créer `lib/api/github.ts`**

```typescript
import { api } from './client';
import type {
  GithubIntegrationStatus,
  GithubRepo,
  Publication,
  PublicationConfig,
  PublicationConfigRequest,
  PublishResponse,
} from '../types';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function getStatus(): Promise<GithubIntegrationStatus> {
  return api<GithubIntegrationStatus>('/api/auth/github/status');
}

export function startOAuthUrl(): string {
  return `${API_BASE}/api/auth/github/start`;
}

export async function startOAuth(): Promise<{ redirect_url: string }> {
  return api<{ redirect_url: string }>('/api/auth/github/start');
}

export async function disconnect(): Promise<{ status: string }> {
  return api<{ status: string }>('/api/auth/github', { method: 'DELETE' });
}

export async function listRepos(): Promise<GithubRepo[]> {
  return api<GithubRepo[]>('/api/github/repos');
}

export async function getPublicationConfig(
  projectId: string,
): Promise<PublicationConfig | null> {
  try {
    return await api<PublicationConfig>(
      `/api/role-projects/${projectId}/publication-config`,
    );
  } catch (err) {
    // 404 = pas configuré, on retourne null pour l'UI
    if (err instanceof Error && err.message.includes('404')) {
      return null;
    }
    throw err;
  }
}

export async function setPublicationConfig(
  projectId: string,
  body: PublicationConfigRequest,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    `/api/role-projects/${projectId}/publication-config`,
    { method: 'PUT', body: JSON.stringify(body) },
  );
}

export async function publishToGithub(
  projectId: string,
): Promise<PublishResponse> {
  return api<PublishResponse>(
    `/api/role-projects/${projectId}/publish-to-github`,
    { method: 'POST' },
  );
}

export async function unpublishFromGithub(
  projectId: string,
): Promise<{ deleted_files: number }> {
  return api<{ deleted_files: number }>(
    `/api/role-projects/${projectId}/github-publication`,
    { method: 'DELETE' },
  );
}

export async function listPublications(
  projectId: string,
): Promise<Publication[]> {
  return api<Publication[]>(`/api/role-projects/${projectId}/publications`);
}
```

- [ ] **Step 3: Tests Vitest** (pattern identique aux tests `agflow-export-api.test.ts`, ~10 tests couvrant chaque fonction)

```typescript
// frontend/src/__tests__/github-api.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as github from '@/lib/api/github';

interface FetchCall { url: string; init: RequestInit; }

function mockFetch(
  response: Partial<Response> & { json?: () => Promise<unknown>; text?: () => Promise<string> },
): { calls: FetchCall[]; fn: typeof globalThis.fetch } {
  const calls: FetchCall[] = [];
  const fn = vi.fn(async (url, init = {}) => {
    calls.push({ url: String(url), init });
    return {
      ok: true, status: 200,
      json: async () => ({}), text: async () => '',
      ...response,
    } as Response;
  }) as unknown as typeof globalThis.fetch;
  return { calls, fn };
}

describe('github API client', () => {
  const origFetch = globalThis.fetch;
  beforeEach(() => { vi.restoreAllMocks(); });
  afterEach(() => { globalThis.fetch = origFetch; });

  it('getStatus GET /auth/github/status', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ connected: false, github_login: null, scope: null, last_validated_at: null }) });
    globalThis.fetch = fn;
    await github.getStatus();
    expect(calls[0]!.url).toBe('http://localhost:8000/api/auth/github/status');
  });

  it('disconnect DELETE /auth/github', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ status: 'disconnected' }) });
    globalThis.fetch = fn;
    await github.disconnect();
    expect(calls[0]!.url).toBe('http://localhost:8000/api/auth/github');
    expect(calls[0]!.init.method).toBe('DELETE');
  });

  it('listRepos GET /github/repos', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;
    await github.listRepos();
    expect(calls[0]!.url).toBe('http://localhost:8000/api/github/repos');
  });

  it('setPublicationConfig PUT avec body', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ status: 'saved' }) });
    globalThis.fetch = fn;
    await github.setPublicationConfig('rp-1', {
      repo_full_name: 'a/r', target_subdirectory: 'x', license_choice: 'mit',
    });
    expect(calls[0]!.url).toBe('http://localhost:8000/api/role-projects/rp-1/publication-config');
    expect(calls[0]!.init.method).toBe('PUT');
  });

  it('publishToGithub POST /publish-to-github', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ commit_sha: 'x', url: 'y', files_count: 5 }) });
    globalThis.fetch = fn;
    await github.publishToGithub('rp-1');
    expect(calls[0]!.url).toBe('http://localhost:8000/api/role-projects/rp-1/publish-to-github');
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('unpublishFromGithub DELETE /github-publication', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ deleted_files: 3 }) });
    globalThis.fetch = fn;
    await github.unpublishFromGithub('rp-1');
    expect(calls[0]!.url).toBe('http://localhost:8000/api/role-projects/rp-1/github-publication');
    expect(calls[0]!.init.method).toBe('DELETE');
  });

  it('listPublications GET /publications', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;
    await github.listPublications('rp-1');
    expect(calls[0]!.url).toBe('http://localhost:8000/api/role-projects/rp-1/publications');
  });
});
```

- [ ] **Step 4: Run, PASS**

Run: `cd frontend && npm test -- --run github-api && npm run typecheck`
Expected: 7+ tests passed, typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts \
        frontend/src/lib/api/github.ts \
        frontend/src/__tests__/github-api.test.ts
git commit -m "feat(frontend): types + client API github (status, oauth, repos, config, publish, history)"
```

---

## Tâche 11 — Frontend onglet "Ma stack" → "Publication"

**Files:**
- Modify: `frontend/src/app/my-stack/layout.tsx` (ajouter onglet)
- Create: `frontend/src/app/my-stack/publication/page.tsx`
- Create: `frontend/src/app/my-stack/publication/ConnectGithubButton.tsx`
- Create: `frontend/src/__tests__/ConnectGithubButton.test.tsx`

- [ ] **Step 1: Ajouter onglet Publication dans layout my-stack**

Dans `frontend/src/app/my-stack/layout.tsx`, étendre `TABS` :
```typescript
const TABS = [
  { href: '/my-stack/social-accounts', label: 'Comptes réseaux sociaux' },
  { href: '/my-stack/transcription-services', label: 'Services de transcription' },
  { href: '/my-stack/mistral-config', label: 'Mistral pour la synthèse' },
  { href: '/my-stack/publication', label: 'Publication GitHub' },
  { href: '/my-stack/quotas', label: 'Quotas et garde-fous' },
];
```

- [ ] **Step 2: Test rouge ConnectGithubButton**

```tsx
// frontend/src/__tests__/ConnectGithubButton.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConnectGithubButton } from '@/app/my-stack/publication/ConnectGithubButton';
import * as gh from '@/lib/api/github';

describe('ConnectGithubButton', () => {
  it('non connecté : affiche bouton "Connecter GitHub"', () => {
    render(
      <ConnectGithubButton
        status={{ connected: false, github_login: null, scope: null, last_validated_at: null }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /connecter github/i })).toBeInTheDocument();
  });

  it('connecté : affiche login + bouton Déconnecter', () => {
    render(
      <ConnectGithubButton
        status={{ connected: true, github_login: 'alice', scope: 'public_repo', last_validated_at: null }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/@alice/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /déconnecter/i })).toBeInTheDocument();
  });

  it('clic Connecter appelle startOAuth et redirige', async () => {
    const startSpy = vi.spyOn(gh, 'startOAuth').mockResolvedValue({
      redirect_url: 'https://github.com/login/oauth/authorize?...',
    });
    // jsdom n'a pas window.location.assign par défaut, on stub
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true, value: { ...window.location, assign: assignSpy },
    });

    render(
      <ConnectGithubButton
        status={{ connected: false, github_login: null, scope: null, last_validated_at: null }}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /connecter github/i }));
    await waitFor(() => expect(startSpy).toHaveBeenCalled());
    await waitFor(() => expect(assignSpy).toHaveBeenCalledWith(
      'https://github.com/login/oauth/authorize?...',
    ));
  });

  it('clic Déconnecter appelle disconnect et onChange', async () => {
    const discSpy = vi.spyOn(gh, 'disconnect').mockResolvedValue({ status: 'disconnected' });
    const onChange = vi.fn();
    render(
      <ConnectGithubButton
        status={{ connected: true, github_login: 'alice', scope: 'public_repo', last_validated_at: null }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /déconnecter/i }));
    await waitFor(() => expect(discSpy).toHaveBeenCalled());
    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });
});
```

- [ ] **Step 3: Implémenter ConnectGithubButton**

```tsx
// frontend/src/app/my-stack/publication/ConnectGithubButton.tsx
'use client';

import { useState } from 'react';
import { disconnect, startOAuth } from '@/lib/api/github';
import type { GithubIntegrationStatus } from '@/lib/types';

interface Props {
  status: GithubIntegrationStatus;
  onChange: () => void;
}

export function ConnectGithubButton({ status, onChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    setBusy(true); setError(null);
    try {
      const { redirect_url } = await startOAuth();
      window.location.assign(redirect_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setBusy(true); setError(null);
    try {
      await disconnect();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally { setBusy(false); }
  }

  if (!status.connected) {
    return (
      <div>
        <button
          type="button"
          onClick={connect}
          disabled={busy}
          style={{
            padding: '0.5rem 1rem',
            background: '#24292f',
            color: 'white',
            border: 0,
            borderRadius: 4,
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy ? 0.6 : 1,
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          Connecter GitHub
        </button>
        {error && <p style={{ color: '#dc2626', fontSize: '0.8rem', marginTop: '0.5rem' }}>{error}</p>}
      </div>
    );
  }

  return (
    <div>
      <p style={{ margin: 0 }}>
        Connecté en tant que <strong>@{status.github_login}</strong>
        {status.scope && ` (scope: ${status.scope})`}
      </p>
      <button
        type="button"
        onClick={handleDisconnect}
        disabled={busy}
        style={{
          marginTop: '0.5rem',
          padding: '0.4rem 0.9rem',
          background: 'white',
          color: '#dc2626',
          border: '1px solid #dc2626',
          borderRadius: 4,
          cursor: busy ? 'not-allowed' : 'pointer',
          fontSize: '0.8rem',
        }}
      >
        Déconnecter
      </button>
      {error && <p style={{ color: '#dc2626', fontSize: '0.8rem', marginTop: '0.5rem' }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: page.tsx**

```tsx
// frontend/src/app/my-stack/publication/page.tsx
'use client';

import useSWR from 'swr';
import { getStatus } from '@/lib/api/github';
import { ConnectGithubButton } from './ConnectGithubButton';

export default function PublicationPage() {
  const { data, isLoading, error, mutate } = useSWR(
    'github-status',
    getStatus,
  );

  if (isLoading) return <p>Chargement…</p>;
  if (error || !data)
    return <p style={{ color: '#dc2626' }}>Erreur de chargement.</p>;

  return (
    <section>
      <h2 style={{ fontSize: '1.125rem', fontWeight: 600 }}>Publication GitHub</h2>
      <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>
        Connectez votre compte GitHub pour publier vos rôles construits sur un
        de vos repos. Le contenu source (transcriptions, audios, prompts) n&apos;est
        jamais publié.
      </p>
      <div style={{ marginTop: '1rem' }}>
        <ConnectGithubButton status={data} onChange={() => mutate()} />
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Run, PASS**

```
cd frontend && npm test -- --run ConnectGithubButton && npm run typecheck && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/my-stack/layout.tsx \
        frontend/src/app/my-stack/publication/page.tsx \
        frontend/src/app/my-stack/publication/ConnectGithubButton.tsx \
        frontend/src/__tests__/ConnectGithubButton.test.tsx
git commit -m "feat(frontend): onglet Ma stack > Publication (status OAuth + connect/disconnect)"
```

---

## Tâche 12 — `PublishToGithubDialog` (sélecteur licence + config + commit msg)

**Files:**
- Create: `frontend/src/app/projects/[id]/role/PublishToGithubButton.tsx`
- Create: `frontend/src/app/projects/[id]/role/PublishToGithubDialog.tsx`
- Create: `frontend/src/__tests__/PublishToGithubDialog.test.tsx`

Dialog modal avec :
- Sélecteur licence (5 choix : `none` / `polyform-nc` / `cc-by-nc-sa-4.0` / `cc-by-4.0` / `mit`)
- Repo + sous-répertoire (lecture seule, vient du config)
- Commit message templated (avec preview)
- Lien vers `/my-stack/publication` si pas connecté
- Lien vers une modale config si pas configuré

- [ ] **Step 1: Test rouge** (5-6 tests : sélecteur licence émet onChange, désactivé sans config, déclenche publishToGithub avec génération du commit msg, gestion 502)

(Tests détaillés rédigés au moment de l'implémentation. Pattern identique à `PushToAgflowButton.test.tsx` et `PostPushBanner.test.tsx`.)

- [ ] **Step 2: Implémenter** — pattern miroir de `PushToAgflowButton` mais avec :
  - state machine `idle / configure / confirm / pushing / done / error`
  - `configure` ouvre une modale qui propose un select de repos (depuis `listRepos`), un input subdirectory, un input commit message template, un radio pour la licence
  - `confirm` ouvre `PublishToGithubDialog` (preview + bouton Publier)
  - `pushing` montre un loader (pas de WS pour Sprint 8 — push ~10-20s, on attend simplement)
  - `done` → bandeau vert avec lien vers le commit GitHub
  - `error` → bandeau rouge avec retry

- [ ] **Step 3: Run, PASS**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/projects/\[id\]/role/PublishToGithubButton.tsx \
        frontend/src/app/projects/\[id\]/role/PublishToGithubDialog.tsx \
        frontend/src/__tests__/PublishToGithubDialog.test.tsx
git commit -m "feat(frontend): PublishToGithubButton + PublishToGithubDialog (sélecteur licence + config repo)"
```

---

## Tâche 13 — Intégration page rôle + `PublicationHistory`

**Files:**
- Modify: `frontend/src/app/projects/[id]/role/page.tsx` (ajouter sections Publication + History)
- Create: `frontend/src/app/projects/[id]/role/PublicationHistory.tsx`
- Create: `frontend/src/__tests__/PublicationHistory.test.tsx`

- [ ] **Step 1: Test rouge PublicationHistory**

```tsx
// frontend/src/__tests__/PublicationHistory.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { PublicationHistory } from '@/app/projects/[id]/role/PublicationHistory';
import * as gh from '@/lib/api/github';

describe('PublicationHistory', () => {
  it('liste les publications avec date + commit court + lien', async () => {
    vi.spyOn(gh, 'listPublications').mockResolvedValue([
      {
        id: 'p1', role_project_id: 'rp1', user_id: 'u',
        commit_sha: 'abcdef1234567890', published_at: '2026-04-29T10:00:00Z',
        files_count: 5, summary: 'Pushed to alice/roles/ux-clea',
      },
    ]);
    const { findByText } = render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <PublicationHistory projectId="rp1" repoFullName="alice/roles" />
      </SWRConfig>,
    );
    await findByText(/abcdef1/);
    expect(screen.getByText(/Pushed to alice\/roles\/ux-clea/)).toBeInTheDocument();
  });

  it('empty state quand aucune publication', async () => {
    vi.spyOn(gh, 'listPublications').mockResolvedValue([]);
    const { findByText } = render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <PublicationHistory projectId="rp1" repoFullName="alice/roles" />
      </SWRConfig>,
    );
    await findByText(/aucune publication/i);
  });
});
```

- [ ] **Step 2: Implémenter**

```tsx
// frontend/src/app/projects/[id]/role/PublicationHistory.tsx
'use client';

import useSWR from 'swr';
import { listPublications } from '@/lib/api/github';

interface Props {
  projectId: string;
  repoFullName: string;
}

export function PublicationHistory({ projectId, repoFullName }: Props) {
  const { data, isLoading } = useSWR(
    ['publications', projectId],
    () => listPublications(projectId),
  );
  if (isLoading) return <p style={{ color: '#6b7280' }}>Chargement…</p>;
  if (!data || data.length === 0)
    return (
      <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
        Aucune publication pour ce rôle.
      </p>
    );

  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
      {data.map((p) => (
        <li
          key={p.id}
          style={{
            padding: '0.5rem 0',
            borderBottom: '1px solid #f3f4f6',
            fontSize: '0.85rem',
          }}
        >
          <a
            href={`https://github.com/${repoFullName}/commit/${p.commit_sha}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontFamily: 'monospace' }}
          >
            {p.commit_sha.slice(0, 7)}
          </a>{' '}
          — {new Date(p.published_at).toLocaleString('fr-FR')}
          {' · '}
          {p.files_count ?? 0} fichier(s)
          <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>{p.summary}</div>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Modifier `page.tsx` pour ajouter une section Publication GitHub** (en-dessous du PushToAgflow)

```tsx
// Au début du return de RolePage, après <PushToAgflowButton />, ajouter :
<section style={{ marginTop: '2rem', borderTop: '1px solid #e5e7eb', paddingTop: '1rem' }}>
  <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
    Publication GitHub
  </h2>
  <PublishToGithubButton projectId={projectId} />
  <details style={{ marginTop: '0.75rem' }}>
    <summary style={{ cursor: 'pointer', fontSize: '0.85rem', color: '#6b7280' }}>
      Historique des publications
    </summary>
    <div style={{ marginTop: '0.5rem' }}>
      <PublicationHistory projectId={projectId} repoFullName={'…'} />
    </div>
  </details>
</section>
```

(Le `repoFullName` doit venir d'un SWR sur `getPublicationConfig` — détail à câbler à l'implémentation.)

- [ ] **Step 4: Run, PASS**

```
cd frontend && npm test -- --run && npm run typecheck && npm run lint
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/projects/\[id\]/role/page.tsx \
        frontend/src/app/projects/\[id\]/role/PublicationHistory.tsx \
        frontend/src/__tests__/PublicationHistory.test.tsx
git commit -m "feat(frontend): intégration page rôle + PublicationHistory (commit shorts + lien GitHub)"
```

---

## Tâche 14 — Closure Sprint 8

**Files:**
- Modify: `docs/specs/12-open-decisions.md`

- [ ] **Step 1: Ajouter section Sprint 8 dans 12-open-decisions** avec :
  - License choice = sélecteur user dans dialog (option C)
  - 1 seul compte GitHub par user (UNIQUE constraint sur user_id)
  - State CSRF en table PG `oauth_states` avec cleanup_expired (option B)
  - Indépendance push ag.flow ↔ publication GitHub
  - Reportés Phase 2 : optimisation Trees API (1 commit pour N fichiers), tags/releases, multi-comptes GitHub, badges shields.io, modération/vitrine, OAuth pour autres providers de transcription

- [ ] **Step 2: Tag annoté**

```bash
git tag -a v0.8.0-sprint-8 -m "Sprint 8 — Publication GitHub

Backend :
- Migrations 0012 (oauth_states) + 0013 (license_choice)
- db_helpers oauth_states + github_integrations + role_publication_config + role_publications
- services/github_publish/{oauth, api_client, readme_builder, publisher}
- routes /auth/github/{start, callback, status, disconnect}
- routes /github/repos + /role-projects/{id}/{publication-config, publish-to-github, github-publication, publications}

Frontend :
- types + lib/api/github.ts
- /my-stack/publication : ConnectGithubButton (status OAuth + connect/disconnect)
- /projects/[id]/role : PublishToGithubButton + PublishToGithubDialog (sélecteur licence)
- PublicationHistory (commit shorts + lien GitHub)

Décisions actées :
- Licence rôle = sélecteur user (none/polyform-nc/cc-by-nc-sa-4.0/cc-by-4.0/mit)
- 1 compte GitHub par user (UNIQUE user_id)
- State CSRF en table PG oauth_states (cleanup auto > 10 min)
- Publication GitHub indépendante du push ag.flow"
```

- [ ] **Step 3: Mettre à jour la mémoire** `project_current_status.md` : Sprint 8 ✅, Phase MVP terminée.

---

## Self-Review

### Spec coverage (vs `docs/specs/09-github-publish.md`)
- ✅ OAuth GitHub complet : tâches 4 + 5
- ✅ State CSRF (option B confirmée) : tâche 1 + 3 + 4
- ✅ Token stocké en OpenBao (pas en base) : tâche 4
- ✅ `GET /github/repos` : tâche 8
- ✅ Config publication par projet : tâche 8 + extension license_choice tâche 6
- ✅ Premier push : tâche 9 (push_publication)
- ✅ Republication via sha tracking : tâche 7 + 9
- ✅ README généré : tâche 9
- ✅ Historique publications : tâche 9
- ✅ Dépublication (DELETE) : tâche 9 (delete_publication)
- ✅ Déconnexion stoppe les publications : tâche 4 (DELETE /auth/github)
- ✅ UI Ma stack > Publication : tâche 11
- ✅ UI page rôle Publication + history : tâches 12 + 13
- ✅ Lien direct vers commit GitHub : tâche 13 (PublicationHistory)
- ✅ Sélecteur licence (décision Sprint 8 actée) : tâche 9 (readme_builder + LICENSE) + tâche 12 (UI)

### Placeholder scan
- Tâche 12 step 1 et step 2 : un peu high-level, j'écris "tests détaillés rédigés au moment de l'implémentation. Pattern identique à PushToAgflowButton". À préciser : 5-6 tests miroirs des tests Sprint 7. Acceptable parce que le pattern est connu et les tests Sprint 7 servent de référence vivante.
- Tâche 13 step 3 : `repoFullName={'…'}` — à câbler à l'implémentation via SWR sur publication-config. Précisé dans la note. Acceptable mais à finaliser.
- Tâche 14 : pas de placeholder.

### Type consistency
- `LicenseChoice` Literal : défini en tâche 8 (Pydantic) et tâche 10 (TypeScript) avec les 5 mêmes valeurs. ✓
- `GithubRepo` : 4 champs (full_name, private, default_branch, html_url) dans schemas backend (tâche 8) et types frontend (tâche 10). ✓
- `PublishResponse` : `commit_sha | null`, `url`, `files_count` cohérent backend/frontend.
- Endpoint paths cohérents :
  - `POST /publish-to-github` (tâche 9 + 10 + 12)
  - `DELETE /github-publication` (tâche 9 + 10)
  - `GET /publications` (tâche 9 + 10 + 13)
- `oauth_states.consume_state` retourne `dict | None` cohérent avec son usage dans `routes/github_auth.py:oauth_callback`.

---

## Estimation

- **Backend** : ~2 jours (tâches 1-9, ~9 commits, ~30 nouveaux tests)
- **Frontend** : ~1.5 jour (tâches 10-13, ~4 commits, ~20 nouveaux tests)
- **Closure** : ~30 min (tâche 14, 1 commit + tag)

**Total : ~14 commits, ~3.5 jours TDD soutenu.**

Plan complet et sauvegardé dans `docs/superpowers/plans/2026-04-29-sprint-08-github-publish.md`.
