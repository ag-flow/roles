# Remove OpenBao — Migration complète vers Harpocrate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supprimer totalement OpenBao du codebase et migrer les 3 zones restantes (credentials scraping, GitHub tokens, credit_monitor) vers Harpocrate / UserVaultService.

**Architecture:** Les secrets utilisateur (cookies, tokens GitHub) sont stockés via `UserVaultService` — même service déjà utilisé pour les clés de transcription. Les chemins vault suivent le pattern `users/{email_slug}/{type}/{id}`. Le `credit_monitor` reçoit `UserVaultService` en paramètre au lieu d'`OpenBaoClient`.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, Harpocrate SDK (local path dep), pytest

---

## Fichiers modifiés/créés

| Action | Fichier |
|---|---|
| Créer | `migrations/0003_vault_user_credentials.sql` |
| Créer | `migrations/0004_vault_github_integrations.sql` |
| Modifier | `backend/src/role_builder/services/user_vault.py` |
| Modifier | `backend/src/role_builder/db_helpers/credentials.py` |
| Modifier | `backend/src/role_builder/db_helpers/github_integrations.py` |
| Modifier | `backend/src/role_builder/routes/credentials.py` |
| Modifier | `backend/src/role_builder/routes/github_auth.py` |
| Modifier | `backend/src/role_builder/routes/github_publish.py` |
| Modifier | `backend/src/role_builder/services/credit_monitor.py` |
| Modifier | `backend/src/role_builder/config.py` |
| Modifier | `backend/src/role_builder/services/scheduler.py` |
| Supprimer | `backend/src/role_builder/services/openbao_client.py` |
| Modifier | `backend/tests/test_credentials_route.py` |
| Modifier | `backend/tests/test_github_auth_route.py` |
| Modifier | `backend/tests/test_github_publish_route.py` |
| Modifier | `backend/tests/test_credit_monitor.py` |
| Modifier | `backend/tests/test_config.py` |
| Modifier | `backend/tests/test_db_helpers_credentials.py` |
| Modifier | `backend/tests/test_db_helpers_github_integrations.py` |
| Modifier | `docker-compose.yml` |
| Modifier | `CLAUDE.md` (section "Secrets app") |

---

## Task 1 : Migrations SQL

**Files:**
- Create: `migrations/0003_vault_user_credentials.sql`
- Create: `migrations/0004_vault_github_integrations.sql`

- [ ] **Step 1 : Créer la migration credentials**

```sql
-- migrations/0003_vault_user_credentials.sql
ALTER TABLE user_credentials
    RENAME COLUMN openbao_path TO vault_secret_name;
```

- [ ] **Step 2 : Créer la migration github_integrations**

```sql
-- migrations/0004_vault_github_integrations.sql
ALTER TABLE github_integrations
    RENAME COLUMN openbao_path TO vault_secret_name;
```

- [ ] **Step 3 : Commit**

```bash
git add migrations/0003_vault_user_credentials.sql migrations/0004_vault_github_integrations.sql
git commit -m "chore(vault): migrations SQL — renommer openbao_path → vault_secret_name (credentials + github_integrations)"
```

---

## Task 2 : Étendre `user_vault.py` avec les builders credentials et GitHub

**Files:**
- Modify: `backend/src/role_builder/services/user_vault.py`
- Test: `backend/tests/services/test_user_vault.py`

- [ ] **Step 1 : Écrire les tests failing**

Ajouter à la fin de `backend/tests/services/test_user_vault.py` :

```python
# ---------------------------------------------------------------------------
# build_credentials_vault_name
# ---------------------------------------------------------------------------


def test_build_credentials_vault_name_normal_email() -> None:
    """Email standard → chemin hiérarchique correct."""
    cred_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_credentials_vault_name("john@example.com", "youtube", cred_id)
    assert name == f"users/john_at_example.com/scraping/youtube/{cred_id}"


def test_build_credentials_vault_name_none_email() -> None:
    """Email None → slug 'no_email'."""
    cred_id = UUID("12345678-1234-5678-1234-567812345678")
    name = build_credentials_vault_name(None, "instagram", cred_id)
    assert name.startswith("users/no_email/scraping/instagram/")


def test_build_credentials_vault_name_cred_id_in_path() -> None:
    """Le cred_id doit apparaître en fin de chemin."""
    cred_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    name = build_credentials_vault_name("a@b.com", "tiktok", cred_id)
    assert str(cred_id) in name


# ---------------------------------------------------------------------------
# build_github_vault_name
# ---------------------------------------------------------------------------


def test_build_github_vault_name_normal() -> None:
    """user_id UUID → chemin github correct."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    tenant_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    name = build_github_vault_name(user_id, tenant_id)
    assert name == f"github/{tenant_id}/{user_id}"
```

Et ajouter les imports manquants en haut du fichier de test :
```python
from role_builder.services.user_vault import (
    UserVaultService,
    build_credentials_vault_name,
    build_github_vault_name,
    build_vault_secret_name,
    get_service,
    init_service,
)
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
cd backend && uv run pytest tests/services/test_user_vault.py -v -k "build_credentials or build_github"
```

Expected: FAIL avec `ImportError: cannot import name 'build_credentials_vault_name'`

- [ ] **Step 3 : Implémenter dans `user_vault.py`**

Ajouter après la fonction `build_vault_secret_name` existante :

```python
def build_credentials_vault_name(email: str | None, platform: str, cred_id: UUID) -> str:
    """Chemin vault pour les cookies de scraping : users/{slug}/scraping/{platform}/{cred_id}."""
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/scraping/{platform}/{cred_id}"


def build_github_vault_name(user_id: UUID, tenant_id: UUID) -> str:
    """Chemin vault pour les tokens GitHub : github/{tenant_id}/{user_id}."""
    return f"github/{tenant_id}/{user_id}"
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/services/test_user_vault.py -v
```

Expected: tous verts (14+ tests)

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/services/user_vault.py backend/tests/services/test_user_vault.py
git commit -m "feat(vault): ajouter build_credentials_vault_name et build_github_vault_name dans UserVaultService"
```

---

## Task 3 : Migrer `db_helpers/credentials.py`

**Files:**
- Modify: `backend/src/role_builder/db_helpers/credentials.py`
- Test: `backend/tests/test_db_helpers_credentials.py`

- [ ] **Step 1 : Mettre à jour le test existant**

Dans `test_db_helpers_credentials.py`, changer la ligne 123 et autour :

```python
# Avant
result = await credentials.insert_user_credential(
    tenant_id=tenant_id,
    user_id=user_id,
    platform="youtube",
    label="Mon compte YT",
    openbao_path="secret/scraping-credentials/t1/youtube/abc",
    pool=stub_pool,
)
# ...
assert args[4] == "secret/scraping-credentials/t1/youtube/abc"
```

```python
# Après
result = await credentials.insert_user_credential(
    tenant_id=tenant_id,
    user_id=user_id,
    platform="youtube",
    label="Mon compte YT",
    vault_secret_name="users/test_at_example.com/scraping/youtube/abc",
    pool=stub_pool,
)
# ...
assert args[4] == "users/test_at_example.com/scraping/youtube/abc"
```

- [ ] **Step 2 : Vérifier que le test échoue**

```
cd backend && uv run pytest tests/test_db_helpers_credentials.py -v -k "insert"
```

Expected: FAIL avec `TypeError: insert_user_credential() got an unexpected keyword argument 'vault_secret_name'`

- [ ] **Step 3 : Modifier `db_helpers/credentials.py`**

Changer le paramètre et la requête SQL dans `insert_user_credential` :

```python
async def insert_user_credential(
    *,
    tenant_id: UUID,
    user_id: UUID,
    platform: str,
    label: str | None,
    vault_secret_name: str,
    status: str = "active",
    last_validated_at: datetime | None = None,
    expires_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT INTO user_credentials RETURNING id."""
    query = (
        "INSERT INTO user_credentials "
        "(tenant_id, user_id, platform, label, vault_secret_name, status, "
        "last_validated_at, expires_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
        "RETURNING id"
    )
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            query,
            tenant_id,
            user_id,
            platform,
            label,
            vault_secret_name,
            status,
            last_validated_at,
            expires_at,
        )
    return row_id  # type: ignore[return-value]
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/test_db_helpers_credentials.py -v
```

Expected: tous verts

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/db_helpers/credentials.py backend/tests/test_db_helpers_credentials.py
git commit -m "feat(vault): db_helpers/credentials — openbao_path → vault_secret_name"
```

---

## Task 4 : Migrer `db_helpers/github_integrations.py`

**Files:**
- Modify: `backend/src/role_builder/db_helpers/github_integrations.py`
- Test: `backend/tests/test_db_helpers_github_integrations.py`

- [ ] **Step 1 : Mettre à jour les tests**

Dans `test_db_helpers_github_integrations.py`, remplacer toutes les occurrences de `openbao_path` par `vault_secret_name` (5 occurrences : args[4] dans upsert, et dans les fetchrow_return des tests get/list). Remplacer aussi le kwarg `openbao_path=` dans l'appel à `upsert`.

```python
# test_upsert_uses_on_conflict_user_id_github_user_id — ligne 75
await github_integrations.upsert(
    user_id=user_id,
    tenant_id=tenant_id,
    github_login="alice",
    github_user_id=12345,
    vault_secret_name=f"github/{tenant_id}/{user_id}",
    scope="public_repo",
    pool=stub_pool,
)

# Dans stub_conn.fetchrow_return (test_get_by_user_id_returns_primary_when_present, ligne 105)
"vault_secret_name": "github-tokens/x/y",

# Dans stub_conn.fetch_return (test_list_by_user_id_returns_all_integrations, lignes 159, 164)
"vault_secret_name": "p1",
"vault_secret_name": "p2",

# Dans stub_conn.fetchrow_return (test_get_by_id_returns_dict, ligne 185)
"vault_secret_name": "p",
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
cd backend && uv run pytest tests/test_db_helpers_github_integrations.py -v
```

Expected: FAIL sur le test upsert (`unexpected keyword argument 'vault_secret_name'`)

- [ ] **Step 3 : Modifier `db_helpers/github_integrations.py`**

Remplacer toutes les occurrences de `openbao_path` par `vault_secret_name` dans tout le fichier :

```python
_UPSERT_SQL = """
    INSERT INTO github_integrations
        (tenant_id, user_id, github_login, github_user_id,
         vault_secret_name, scope, last_validated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (user_id, github_user_id) DO UPDATE SET
        tenant_id = EXCLUDED.tenant_id,
        github_login = EXCLUDED.github_login,
        vault_secret_name = EXCLUDED.vault_secret_name,
        scope = EXCLUDED.scope,
        last_validated_at = EXCLUDED.last_validated_at
"""

_GET_PRIMARY_BY_USER_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           vault_secret_name, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE user_id = $1
    ORDER BY last_validated_at DESC NULLS LAST, created_at DESC
    LIMIT 1
"""

_LIST_BY_USER_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           vault_secret_name, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE user_id = $1
    ORDER BY created_at ASC
"""

_GET_BY_ID_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           vault_secret_name, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE id = $1
"""
```

Aussi renommer le paramètre dans `upsert()` :

```python
async def upsert(
    *,
    user_id: UUID,
    tenant_id: UUID,
    github_login: str,
    github_user_id: int,
    vault_secret_name: str,
    scope: str,
    pool: asyncpg.Pool,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _UPSERT_SQL,
            tenant_id,
            user_id,
            github_login,
            github_user_id,
            vault_secret_name,
            scope,
            datetime.now(tz=UTC),
        )
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/test_db_helpers_github_integrations.py -v
```

Expected: tous verts

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/db_helpers/github_integrations.py backend/tests/test_db_helpers_github_integrations.py
git commit -m "feat(vault): db_helpers/github_integrations — openbao_path → vault_secret_name"
```

---

## Task 5 : Migrer `routes/credentials.py`

**Files:**
- Modify: `backend/src/role_builder/routes/credentials.py`
- Test: `backend/tests/test_credentials_route.py`

- [ ] **Step 1 : Mettre à jour les tests**

Dans `test_credentials_route.py` :

1. Remplacer `"openbao_path": f"scraping-credentials/..."` dans `_make_cred_row` :
```python
"vault_secret_name": f"users/tenant_at_example.com/scraping/youtube/{uuid4()}",
```

2. Remplacer `_FakeOpenBao` par `_FakeUserVaultService` :
```python
class _FakeUserVaultService:
    """Stub UserVaultService pour les tests (write/read/try_delete no-op)."""

    def __init__(self, cookies_b64: str | None = None) -> None:
        self._cookies_b64 = cookies_b64

    async def write(self, secret_name: str, value: str) -> None:
        pass

    async def read(self, secret_name: str) -> str | None:
        return self._cookies_b64

    async def try_delete(self, secret_name: str) -> None:
        pass
```

3. T3 — `fake_insert` : renommer `openbao_path` → `vault_secret_name` dans la signature :
```python
async def fake_insert(
    *,
    tenant_id: UUID,
    user_id: UUID,
    platform: str,
    label: str | None,
    vault_secret_name: str,
    status: str,
    last_validated_at: Any,
    expires_at: Any,
    pool: Any,
) -> UUID:
    return cred_id
```
Et remplacer `monkeypatch.setattr(route, "OpenBaoClient", lambda: _FakeOpenBao())` par :
```python
monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeUserVaultService())
```

4. T5 — Remplacer :
```python
monkeypatch.setattr(
    route,
    "OpenBaoClient",
    lambda: _FakeOpenBao(secret_data={"cookies_b64": "dGVzdA=="}),
)
```
par :
```python
monkeypatch.setattr(
    route,
    "_get_vault_service",
    lambda: _FakeUserVaultService(cookies_b64="dGVzdA=="),
)
```

5. T7 — Remplacer `monkeypatch.setattr(route, "OpenBaoClient", lambda: _FakeOpenBao())` par :
```python
monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeUserVaultService())
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
cd backend && uv run pytest tests/test_credentials_route.py -v
```

Expected: FAIL sur T3, T5, T7 (AttributeError sur `_get_vault_service`)

- [ ] **Step 3 : Modifier `routes/credentials.py`**

```python
"""Endpoints REST pour la gestion des credentials (comptes réseaux sociaux).

Routes :
- GET  /api/credentials
- POST /api/credentials
- POST /api/credentials/{cred_id}/test
- DELETE /api/credentials/{cred_id}

Tous protégés par ``Depends(get_current_user)``.
Les cookies sont stockés dans Harpocrate sous le chemin :
  users/{email_slug}/scraping/{platform}/{cred_id}
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import credentials as creds_helper
from role_builder.schemas.credentials import (
    CreateCredentialRequest,
    TestCredentialResponse,
    UserCredentialOut,
)
from role_builder.services import credentials_validator
from role_builder.services.user_vault import (
    UserVaultService,
    build_credentials_vault_name,
    get_service as _get_vault_service,
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/credentials", response_model=list[UserCredentialOut])
async def list_credentials_endpoint(
    platform: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[UserCredentialOut]:
    """Retourne les credentials de l'utilisateur courant, filtrés par plateforme si fourni."""
    rows = await creds_helper.list_credentials(
        user_id=user.user_id,
        platform=platform,
        pool=db_pool.pool,
    )
    return [UserCredentialOut(**r) for r in rows]


@router.post("/credentials", response_model=UserCredentialOut, status_code=201)
async def create_credential_endpoint(
    request: CreateCredentialRequest,
    user: CurrentUser = Depends(get_current_user),
) -> UserCredentialOut:
    """Crée un nouveau credential après validation des cookies."""
    result = await credentials_validator.validate_cookies(
        request.platform,
        request.cookies_b64,
    )
    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail=result["error"] or "invalid cookies",
        )

    cred_id = uuid4()
    secret_name = build_credentials_vault_name(user.email, request.platform, cred_id)

    await _get_vault_service().write(secret_name, request.cookies_b64)

    now = datetime.now(UTC)
    inserted_id = await creds_helper.insert_user_credential(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        platform=request.platform,
        label=request.label,
        vault_secret_name=secret_name,
        status="active",
        last_validated_at=now,
        expires_at=result.get("expires_at"),
        pool=db_pool.pool,
    )

    log.info(
        "credentials.created",
        credential_id=str(inserted_id),
        platform=request.platform,
        user_id=str(user.user_id),
    )

    row = await creds_helper.get_credential(
        inserted_id,
        user_id=user.user_id,
        pool=db_pool.pool,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to retrieve created credential")
    return UserCredentialOut(**row)


@router.post("/credentials/{cred_id}/test", response_model=TestCredentialResponse)
async def test_credential_endpoint(
    cred_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> TestCredentialResponse:
    """Revalide un credential existant en récupérant ses cookies depuis le vault."""
    cred = await creds_helper.get_credential(
        cred_id,
        user_id=user.user_id,
        pool=db_pool.pool,
    )
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")

    cookies_b64 = await _get_vault_service().read(cred["vault_secret_name"])

    if not cookies_b64:
        await creds_helper.update_credential_status(
            cred_id,
            status="invalid",
            pool=db_pool.pool,
        )
        return TestCredentialResponse(
            status="invalid",
            last_validated_at=None,
            error="cookies missing from vault",
        )

    result = await credentials_validator.validate_cookies(cred["platform"], cookies_b64)

    new_status = "active" if result["valid"] else "invalid"
    now = datetime.now(UTC)
    await creds_helper.update_credential_status(
        cred_id,
        status=new_status,
        last_validated_at=now,
        pool=db_pool.pool,
    )

    log.info("credentials.tested", credential_id=str(cred_id), result=new_status)
    return TestCredentialResponse(
        status=new_status,
        last_validated_at=now,
        error=result.get("error"),
    )


@router.delete("/credentials/{cred_id}", status_code=204)
async def delete_credential_endpoint(
    cred_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Supprime un credential : efface les cookies dans le vault puis la ligne en base."""
    cred = await creds_helper.get_credential(
        cred_id,
        user_id=user.user_id,
        pool=db_pool.pool,
    )
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")

    await _get_vault_service().try_delete(cred["vault_secret_name"])

    await creds_helper.delete_credential(cred_id, pool=db_pool.pool)
    log.info("credentials.deleted", credential_id=str(cred_id))
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/test_credentials_route.py -v
```

Expected: tous verts

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/routes/credentials.py backend/tests/test_credentials_route.py
git commit -m "feat(vault): routes/credentials — migrer vers UserVaultService, supprimer OpenBaoClient"
```

---

## Task 6 : Migrer `routes/github_auth.py`

**Files:**
- Modify: `backend/src/role_builder/routes/github_auth.py`
- Test: `backend/tests/test_github_auth_route.py`

- [ ] **Step 1 : Mettre à jour les tests**

Dans `test_github_auth_route.py` :

1. Supprimer tous les `from role_builder.services.openbao_client import OpenBaoClient` des tests.

2. `test_callback_full_flow_stores_token_and_returns_login` — remplacer le patch OpenBaoClient par un patch de `_get_vault_service` :
```python
def test_callback_full_flow_stores_token_and_returns_login(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    user_id = uuid4()
    tenant_id = uuid4()

    async def fake_consume(state: str, *, pool: Any) -> Any:
        return {"user_id": user_id, "tenant_id": tenant_id, "expires_at": None}

    async def fake_exchange(self: Any, code: str) -> str:
        return "ghp_secret"

    async def fake_user_info(self: Any, token: str) -> dict[str, Any]:
        return {"login": "alice", "id": 42}

    write_calls: list[tuple[str, str]] = []

    class _FakeVaultSvc:
        async def write(self, name: str, value: str) -> None:
            write_calls.append((name, value))

    upsert_calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs: Any) -> None:
        upsert_calls.append(kwargs)

    monkeypatch.setattr(route.oauth_states, "consume_state", fake_consume)
    monkeypatch.setattr(
        route.gh_oauth_module.gh_oauth.__class__, "exchange_code", fake_exchange,
    )
    monkeypatch.setattr(
        route.gh_oauth_module.gh_oauth.__class__, "get_user_info", fake_user_info,
    )
    monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeVaultSvc())
    monkeypatch.setattr(route.github_integrations, "upsert", fake_upsert)

    resp = client.get(
        "/api/auth/github/callback",
        params={"code": "github-code", "state": "good"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"status": "connected", "github_login": "alice"}

    # Token stocké dans Harpocrate
    assert len(write_calls) == 1
    assert "github" in write_calls[0][0]
    assert write_calls[0][1] == "ghp_secret"

    assert len(upsert_calls) == 1
    assert upsert_calls[0]["github_login"] == "alice"
    assert upsert_calls[0]["github_user_id"] == 42
```

3. `test_disconnect_removes_token_and_integration` — remplacer patch OpenBaoClient :
```python
def test_disconnect_removes_token_and_integration(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_list(user_id: UUID, *, pool: Any) -> list[dict[str, Any]]:
        return [
            {"vault_secret_name": "github/t/u-perso"},
            {"vault_secret_name": "github/t/u-org"},
        ]

    deleted_names: list[str] = []

    class _FakeVaultSvc:
        async def try_delete(self, name: str) -> None:
            deleted_names.append(name)

    deleted_users: list[UUID] = []

    async def fake_delete_integration(user_id: UUID, *, pool: Any) -> int:
        deleted_users.append(user_id)
        return 2

    monkeypatch.setattr(route.github_integrations, "list_by_user_id", fake_list)
    monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeVaultSvc())
    monkeypatch.setattr(
        route.github_integrations, "delete_by_user_id", fake_delete_integration,
    )

    resp = client.delete("/api/auth/github")
    assert resp.status_code == 200
    assert resp.json() == {"status": "disconnected"}
    assert deleted_names == ["github/t/u-perso", "github/t/u-org"]
    assert len(deleted_users) == 1
```

4. `test_delete_integration_removes_token_and_row` — remplacer patch OpenBaoClient :
```python
def test_delete_integration_removes_token_and_row(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    fixed_user_id = UUID("00000000-0000-0000-0000-000000000001")
    integration_id = uuid4()

    async def fake_get(iid: UUID, *, pool: Any) -> dict[str, Any]:
        return {
            "id": iid, "user_id": fixed_user_id,
            "vault_secret_name": "github/t/spec",
            "github_login": "alice",
        }

    deleted_names: list[str] = []

    class _FakeVaultSvc:
        async def try_delete(self, name: str) -> None:
            deleted_names.append(name)

    delete_calls: list[UUID] = []

    async def fake_delete_by_id(iid: UUID, *, pool: Any) -> int:
        delete_calls.append(iid)
        return 1

    monkeypatch.setattr(route.github_integrations, "get_by_id", fake_get)
    monkeypatch.setattr(route.github_integrations, "delete_by_id", fake_delete_by_id)
    monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeVaultSvc())

    resp = client.delete(f"/api/auth/github/integrations/{integration_id}")
    assert resp.status_code == 204, resp.text
    assert deleted_names == ["github/t/spec"]
    assert delete_calls == [integration_id]
```

5. `test_list_integrations_returns_all` — dans `fake_rows`, remplacer `"openbao_path": "p1"/"p2"` par `"vault_secret_name": "p1"/"p2"`.

- [ ] **Step 2 : Vérifier que les tests échouent**

```
cd backend && uv run pytest tests/test_github_auth_route.py -v
```

Expected: FAIL sur callback, disconnect, delete_integration

- [ ] **Step 3 : Modifier `routes/github_auth.py`**

```python
"""Routes Sprint 8 — flow OAuth GitHub."""

from __future__ import annotations

import secrets as py_secrets
from typing import Annotated
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.config import settings
from role_builder.db import db_pool
from role_builder.db_helpers import github_integrations, oauth_states
from role_builder.schemas.github import (
    CallbackResponse,
    GithubIntegrationItem,
    GithubIntegrationStatus,
    StartOAuthResponse,
)
from role_builder.services.github_publish import oauth as gh_oauth_module
from role_builder.services.user_vault import build_github_vault_name, get_service as _get_vault_service

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
    url = gh_oauth_module.gh_oauth.build_authorize_url(state)
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
        access_token = await gh_oauth_module.gh_oauth.exchange_code(code)
        gh_user = await gh_oauth_module.gh_oauth.get_user_info(access_token)
    except httpx.HTTPStatusError as exc:
        log.exception("github.oauth.upstream_error")
        raise HTTPException(status_code=502, detail=f"GitHub: {exc}") from exc

    vault_secret_name = build_github_vault_name(user_id, tenant_id)
    await _get_vault_service().write(vault_secret_name, access_token)

    await github_integrations.upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        github_login=str(gh_user["login"]),
        github_user_id=int(gh_user["id"]),
        vault_secret_name=vault_secret_name,
        scope=settings.github_oauth_scope,
        pool=db_pool.pool,
    )
    log.info(
        "github.oauth.connected",
        user_id=str(user_id),
        github_login=gh_user["login"],
    )
    return CallbackResponse(status="connected", github_login=str(gh_user["login"]))


@router.get("/auth/github/status", response_model=GithubIntegrationStatus)
async def status_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GithubIntegrationStatus:
    integration = await github_integrations.get_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
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
    """Déconnecte TOUTES les intégrations GitHub du user."""
    integrations = await github_integrations.list_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
    if not integrations:
        return {"status": "not-connected"}

    vault_svc = _get_vault_service()
    for integration in integrations:
        await vault_svc.try_delete(str(integration["vault_secret_name"]))

    await github_integrations.delete_by_user_id(user.user_id, pool=db_pool.pool)
    log.info(
        "github.oauth.disconnected",
        user_id=str(user.user_id),
        count=len(integrations),
    )
    return {"status": "disconnected"}


@router.get("/auth/github/integrations", response_model=list[GithubIntegrationItem])
async def list_integrations(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[GithubIntegrationItem]:
    """Liste toutes les intégrations GitHub du user (peut être vide)."""
    rows = await github_integrations.list_by_user_id(
        user.user_id, pool=db_pool.pool,
    )
    return [GithubIntegrationItem(**r) for r in rows]


@router.delete(
    "/auth/github/integrations/{integration_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def delete_integration(
    integration_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    """Supprime une intégration GitHub spécifique du user."""
    integration = await github_integrations.get_by_id(
        integration_id, pool=db_pool.pool,
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="integration not found")
    if integration["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="not the integration owner")

    await _get_vault_service().try_delete(str(integration["vault_secret_name"]))

    await github_integrations.delete_by_id(integration_id, pool=db_pool.pool)
    log.info(
        "github.oauth.integration_deleted",
        user_id=str(user.user_id),
        integration_id=str(integration_id),
        github_login=integration["github_login"],
    )
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/test_github_auth_route.py -v
```

Expected: tous verts

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/routes/github_auth.py backend/tests/test_github_auth_route.py
git commit -m "feat(vault): routes/github_auth — migrer vers UserVaultService, supprimer OpenBaoClient"
```

---

## Task 7 : Migrer `routes/github_publish.py`

**Files:**
- Modify: `backend/src/role_builder/routes/github_publish.py`
- Test: `backend/tests/test_github_publish_route.py`

- [ ] **Step 1 : Mettre à jour le test**

Dans `test_github_publish_route.py`, `test_list_repos_returns_subset_of_fields` :

```python
def test_list_repos_returns_subset_of_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_publish as route

    async def fake_get(user_id: UUID, *, pool: Any) -> Any:
        return {
            "vault_secret_name": "github/t/u",
            "github_login": "alice",
        }

    class _FakeVaultSvc:
        async def read(self, name: str) -> str | None:
            return "ghp_x"

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)
    monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeVaultSvc())

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
        def __init__(self, *, access_token: str) -> None:
            assert access_token == "ghp_x"

        async def list_repos(self) -> list[dict[str, Any]]:
            return repos_full

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(route, "GitHubApiClient", _StubApiClient)

    resp = client.get("/api/github/repos")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert set(body[0].keys()) == {
        "full_name", "private", "default_branch", "html_url",
    }
    assert body[0]["full_name"] == "alice/role-pack"
```

- [ ] **Step 2 : Vérifier que le test échoue**

```
cd backend && uv run pytest tests/test_github_publish_route.py::test_list_repos_returns_subset_of_fields -v
```

Expected: FAIL

- [ ] **Step 3 : Modifier `_api_for_user` dans `routes/github_publish.py`**

Remplacer l'import `from role_builder.services.openbao_client import OpenBaoClient` par :
```python
from role_builder.services.user_vault import get_service as _get_vault_service
```

Remplacer la fonction `_api_for_user` :

```python
async def _api_for_user(
    user: CurrentUser, *, integration_id: UUID | None = None,
) -> tuple[GitHubApiClient, str]:
    """Helper : récupère le token via Harpocrate et instancie un GitHubApiClient."""
    if integration_id is not None:
        integration = await github_integrations.get_by_id(
            integration_id, pool=db_pool.pool,
        )
        if integration is None:
            raise HTTPException(status_code=404, detail="integration not found")
        if integration["user_id"] != user.user_id:
            raise HTTPException(
                status_code=403, detail="not the integration owner",
            )
    else:
        integration = await github_integrations.get_by_user_id(
            user.user_id, pool=db_pool.pool,
        )
        if integration is None:
            raise HTTPException(status_code=400, detail="GitHub not connected")

    access_token = await _get_vault_service().read(str(integration["vault_secret_name"])) or ""
    if not access_token:
        raise HTTPException(
            status_code=502, detail="GitHub token missing in vault",
        )

    return (
        GitHubApiClient(access_token=access_token),
        str(integration["github_login"]),
    )
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/test_github_publish_route.py -v
```

Expected: tous verts

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/routes/github_publish.py backend/tests/test_github_publish_route.py
git commit -m "feat(vault): routes/github_publish — migrer vers UserVaultService, supprimer OpenBaoClient"
```

---

## Task 8 : Migrer `services/credit_monitor.py`

**Files:**
- Modify: `backend/src/role_builder/services/credit_monitor.py`
- Test: `backend/tests/test_credit_monitor.py`

- [ ] **Step 1 : Mettre à jour les tests**

Dans `test_credit_monitor.py`, supprimer `_StubOpenBao` et `_make_key(openbao_path=...)`. Remplacer par :

```python
class _StubUserVaultSvc:
    """UserVaultService stub configurable."""

    def __init__(self, secrets: dict[str, str | None]) -> None:
        self._secrets = secrets

    async def read(self, name: str) -> str | None:
        return self._secrets.get(name)


def _make_key(
    *,
    vault_secret_name: str = "users/test/transcription/deepgram/x",
    provider: str = "deepgram",
    monthly_cap_usd: float | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "provider": provider,
        "vault_secret_name": vault_secret_name,
        "monthly_cap_usd": monthly_cap_usd,
    }
```

Mettre à jour chaque test pour utiliser `_StubUserVaultSvc` et passer `user_vault_svc=svc` au lieu de `openbao=bao`. La valeur dans le dict devient une chaîne directe (ex: `{"path/1": "key1"}`) au lieu d'un dict `{"api_key": "key1"}`.

Test 1 (happy path) :
```python
svc = _StubUserVaultSvc({
    "users/path/1": "key1",
    "users/path/2": "key2",
})
counters = await credit_monitor.poll_all_balances(pool=_StubPool(), user_vault_svc=svc)
```
... et `key1 = _make_key(vault_secret_name="users/path/1")`, `key2 = _make_key(vault_secret_name="users/path/2")`.

Adapter tous les 6 tests sur ce pattern : remplacer `openbao_path` → `vault_secret_name` dans les `_make_key()`, les dicts `_StubUserVaultSvc`, et l'appel `poll_all_balances(openbao=bao)` → `poll_all_balances(user_vault_svc=svc)`.

- [ ] **Step 2 : Vérifier que les tests échouent**

```
cd backend && uv run pytest tests/test_credit_monitor.py -v
```

Expected: FAIL (TypeError sur `openbao` vs `user_vault_svc`)

- [ ] **Step 3 : Modifier `services/credit_monitor.py`**

```python
"""Polling périodique des balances de crédit pour les providers
qui exposent une API balance (Deepgram principalement)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import asyncpg
import structlog

from role_builder.db_helpers import transcription_keys as keys_helper
from role_builder.services import transcription_validator
from role_builder.services.user_vault import UserVaultService, get_service

log = structlog.get_logger(__name__)

_LOW_BALANCE_PCT_OF_CAP = 0.20
_LOW_BALANCE_DEFAULT_USD = 20.0


def _is_low_balance(balance: float, monthly_cap_usd: float | None) -> bool:
    threshold = (
        monthly_cap_usd * _LOW_BALANCE_PCT_OF_CAP
        if monthly_cap_usd is not None and monthly_cap_usd > 0
        else _LOW_BALANCE_DEFAULT_USD
    )
    return balance <= threshold


async def poll_all_balances(
    *,
    pool: asyncpg.Pool,
    user_vault_svc: UserVaultService | None = None,
) -> dict[str, int]:
    """Poll les balances des clés actives.
    Retourne {polled, updated, exhausted, errors}.
    """
    keys: list[dict[str, Any]] = await keys_helper.list_active_keys_for_balance_polling(pool=pool)
    counters = {"polled": 0, "updated": 0, "exhausted": 0, "errors": 0}

    svc = user_vault_svc if user_vault_svc is not None else get_service()

    for key in keys:
        counters["polled"] += 1
        try:
            api_key = await svc.read(key["vault_secret_name"])
            if not api_key:
                log.warning("credit_monitor.secret_missing", key_id=str(key["id"]))
                counters["errors"] += 1
                continue

            balance = await transcription_validator.fetch_balance(key["provider"], api_key)
            if balance is None:
                continue

            now = dt.datetime.now(dt.UTC)
            await keys_helper.update_key_balance(
                key["id"],
                balance_usd=balance,
                checked_at=now,
                pool=pool,
            )
            counters["updated"] += 1

            if balance <= 0:
                await keys_helper.mark_exhausted(key["id"], pool=pool)
                counters["exhausted"] += 1
                log.warning(
                    "credit_monitor.balance_exhausted",
                    key_id=str(key["id"]),
                    provider=key["provider"],
                )
            elif _is_low_balance(balance, key.get("monthly_cap_usd")):
                log.warning(
                    "credit_monitor.balance_low",
                    key_id=str(key["id"]),
                    provider=key["provider"],
                    balance_usd=balance,
                    monthly_cap_usd=key.get("monthly_cap_usd"),
                )
        except Exception:
            counters["errors"] += 1
            log.exception("credit_monitor.poll_failed", key_id=str(key["id"]))

    log.info("credit_monitor.poll_completed", **counters)
    return counters
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
cd backend && uv run pytest tests/test_credit_monitor.py -v
```

Expected: tous verts

- [ ] **Step 5 : Commit**

```bash
git add backend/src/role_builder/services/credit_monitor.py backend/tests/test_credit_monitor.py
git commit -m "feat(vault): credit_monitor — migrer vers UserVaultService, supprimer OpenBaoClient"
```

---

## Task 9 : Supprimer `openbao_client.py` et nettoyer config + scheduler

**Files:**
- Delete: `backend/src/role_builder/services/openbao_client.py`
- Modify: `backend/src/role_builder/config.py`
- Modify: `backend/src/role_builder/services/scheduler.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1 : Mettre à jour `test_config.py`**

Dans `test_config.py`, supprimer toutes les lignes `monkeypatch.setenv("OPENBAO_URL", ...)` et `monkeypatch.setenv("OPENBAO_TOKEN", ...)`, et supprimer les assertions `s.openbao_url` et `s.openbao_token`. Le fichier a 2 fonctions de test à mettre à jour.

```python
def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads required values from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    # Plus d'OPENBAO_URL / OPENBAO_TOKEN

    from role_builder.config import Settings

    s = Settings()
    assert s.database_url == "postgresql://test:test@localhost/test"
    assert s.minio_endpoint == "http://minio:9000"
    assert s.minio_access_key == "key"
    assert s.minio_secret_key == "secret"
    assert s.log_level == "INFO"
    # ... reste identique, sans openbao_url / openbao_token
```

Idem pour `test_settings_sprint2_overrides`.

- [ ] **Step 2 : Vérifier que les tests config échouent**

```
cd backend && uv run pytest tests/test_config.py -v
```

Expected: FAIL (les Settings exigent encore `openbao_url` + `openbao_token`)

- [ ] **Step 3 : Supprimer les champs openbao de `config.py`**

Retirer de la classe `Settings` :
```python
openbao_url: str
openbao_token: str
```

- [ ] **Step 4 : Supprimer le commentaire openbao dans `scheduler.py`**

Dans `services/scheduler.py`, supprimer la ligne mentionnant OpenBao (commentaire sur Best-effort OpenBao, ligne ~87). Remplacer si nécessaire par un commentaire neutre sur Harpocrate.

- [ ] **Step 5 : Supprimer `openbao_client.py`**

```bash
rm backend/src/role_builder/services/openbao_client.py
```

- [ ] **Step 6 : Vérifier que les tests config passent**

```
cd backend && uv run pytest tests/test_config.py -v
```

Expected: tous verts

- [ ] **Step 7 : Vérifier qu'aucun import résiduel ne reste**

```bash
cd backend && uv run python -c "from role_builder.services import openbao_client" 2>&1
```

Expected: `ModuleNotFoundError` (confirmé supprimé)

```bash
cd backend && grep -r "openbao_client\|OpenBaoClient\|openbao_path\|openbao_url\|openbao_token" src/ tests/ --include="*.py"
```

Expected: 0 résultats

- [ ] **Step 8 : Commit**

```bash
git add backend/src/role_builder/config.py backend/src/role_builder/services/scheduler.py backend/tests/test_config.py
git rm backend/src/role_builder/services/openbao_client.py
git commit -m "feat(vault): supprimer openbao_client.py et les champs config openbao_url/openbao_token"
```

---

## Task 10 : Nettoyer `docker-compose.yml` et `CLAUDE.md`

**Files:**
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`

- [ ] **Step 1 : Modifier `docker-compose.yml`**

1. Supprimer le service `openbao` (lignes 35–50)
2. Supprimer `openbao: condition: service_healthy` du `depends_on` backend
3. Supprimer les variables `OPENBAO_URL` et `OPENBAO_TOKEN` du service backend
4. Supprimer les variables `OPENBAO_DEV_TOKEN` si elles ne servent plus (vérifier si référencées ailleurs)

- [ ] **Step 2 : Mettre à jour `CLAUDE.md`**

Dans la section "Stockage objets et secrets", remplacer :
```
- **Secrets app** : OpenBao KV v2 au path `secret/`. Sous-paths attendus :
  - `secret/scraping-credentials/{tenant_id}/{platform}/{credential_id}`
  - `secret/transcription-keys/{tenant_id}/{provider}/{key_id}`
  - `secret/github-tokens/{tenant_id}/{user_id}`
```

par :
```
- **Secrets app** : Harpocrate vault. Chemins vault :
  - `users/{email_slug}/scraping/{platform}/{cred_id}` — cookies de scraping
  - `users/{email_slug}/transcription/{provider}/{key_id}` — clés SaaS transcription
  - `github/{tenant_id}/{user_id}` — tokens GitHub OAuth
```

Et dans le stack technique, remplacer `OpenBao pour les secrets` par `Harpocrate`.

- [ ] **Step 3 : Commit**

```bash
git add docker-compose.yml CLAUDE.md
git commit -m "chore(vault): supprimer OpenBao de docker-compose et CLAUDE.md"
```

---

## Task 11 : Vérification finale — tests + lint + grep

**Files:** Aucun fichier nouveau

- [ ] **Step 1 : Lancer tous les tests Python**

```
cd backend && uv run pytest -v
```

Expected: tous verts (~552+ tests)

- [ ] **Step 2 : Lint ruff**

```
cd backend && uv run ruff check src/ tests/
```

Expected: aucune erreur

- [ ] **Step 3 : Grep résiduel openbao**

```bash
grep -r "openbao\|OpenBao\|OPENBAO" backend/src/ backend/tests/ --include="*.py" -l
```

Expected: 0 fichiers

- [ ] **Step 4 : Grep résiduel dans docker-compose et scripts**

```bash
grep -r "openbao\|OpenBao\|OPENBAO" docker-compose.yml scripts/ --include="*.sh" --include="*.yml"
```

Expected: 0 résultats (le fichier `scripts/init_openbao.sh` peut rester mais noter qu'il est désormais obsolète — il sera supprimé ou archivé selon décision)

- [ ] **Step 5 : Commit final si nécessaire**

Si des ajustements mineurs ont été faits :
```bash
git add -u
git commit -m "fix(vault): corrections post-migration OpenBao → Harpocrate"
```
