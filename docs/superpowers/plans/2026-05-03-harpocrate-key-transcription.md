# Harpocrate Key — Champ sur la création de clé de transcription

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un champ requis « Harpocrate key » au formulaire de création de clé de transcription : le secret API est stocké dans le coffre Harpocrate via le SDK, et la DB enregistre la référence vault `${vault://api1:<path>/<key>}`.

**Architecture:** Trois nouvelles fonctions pures dans `user_vault.py` (`build_transcription_vault_path`, `build_vault_ref`, `extract_vault_path`) permettent de construire les refs vault et de les lire en backward-compat (plain path legacy → idem). La route `create_key_endpoint` écrit le secret au path plain et stocke la ref en DB. Les endpoints `test` et `delete` extraient le path avant d'appeler le service vault.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, harpocrate SDK, pytest, Next.js 14 (App Router), TypeScript strict.

---

## Fichiers modifiés

| Fichier | Rôle |
|---|---|
| `backend/src/role_builder/services/user_vault.py` | +3 fonctions helpers |
| `backend/tests/services/test_user_vault.py` | +6 tests pour les helpers |
| `backend/src/role_builder/schemas/transcription_keys.py` | +champ `harpocrate_key` |
| `backend/src/role_builder/routes/transcription_keys.py` | mise à jour create/test/delete |
| `backend/tests/test_transcription_keys_route.py` | mise à jour T2/T3/T4/T13 + `_make_key_row` |
| `frontend/src/lib/api/transcription-keys.ts` | +`harpocrate_key` dans `createKey` |
| `frontend/src/app/my-stack/transcription-services/AddKeyModal.tsx` | +champ + validation |

---

## Task 1 — Helpers vault dans user_vault.py

**Files:**
- Modify: `backend/src/role_builder/services/user_vault.py`
- Test: `backend/tests/services/test_user_vault.py`

### Contexte

`user_vault.py` contient déjà `build_vault_secret_name(email, provider, key_id: UUID)` qui construit un path plain comme `users/john_at_example.com/transcription/deepgram/some-uuid`. Ici on ajoute :

1. `build_transcription_vault_path(email, provider, key_name: str) -> str` — même logique, leaf = string libre (pas UUID)
2. `build_vault_ref(path: str) -> str` — enveloppe un path en `${vault://api1:path}` (lit l'identifiant depuis l'env)
3. `extract_vault_path(ref: str) -> str` — extrait le path depuis une ref vault ; retourne la valeur brute si ce n'est pas une ref (compat backward)

- [ ] **Step 1 — Écrire les tests qui échouent**

Dans `backend/tests/services/test_user_vault.py`, ajouter en bas du fichier :

```python
import os

# ---------------------------------------------------------------------------
# build_transcription_vault_path
# ---------------------------------------------------------------------------


def test_build_transcription_vault_path_normal_email() -> None:
    from role_builder.services.user_vault import build_transcription_vault_path

    result = build_transcription_vault_path("john@example.com", "deepgram", "ma_cle")
    assert result == "users/john_at_example.com/transcription/deepgram/ma_cle"


def test_build_transcription_vault_path_none_email() -> None:
    from role_builder.services.user_vault import build_transcription_vault_path

    result = build_transcription_vault_path(None, "openai-whisper", "my_key")
    assert result == "users/no_email/transcription/openai-whisper/my_key"


# ---------------------------------------------------------------------------
# build_vault_ref
# ---------------------------------------------------------------------------


def test_build_vault_ref_wraps_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.services.user_vault import build_vault_ref

    monkeypatch.setenv("HARPOCRATE_API_TOKEN_API1", "hrpv_test")
    ref = build_vault_ref("users/john/transcription/deepgram/ma_cle")
    assert ref == "${vault://api1:users/john/transcription/deepgram/ma_cle}"


def test_build_vault_ref_fallback_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.services.user_vault import build_vault_ref

    for k in list(os.environ):
        if k.startswith("HARPOCRATE_API_TOKEN_"):
            monkeypatch.delenv(k, raising=False)
    ref = build_vault_ref("some/path")
    assert ref == "${vault://api1:some/path}"


# ---------------------------------------------------------------------------
# extract_vault_path
# ---------------------------------------------------------------------------


def test_extract_vault_path_from_vault_ref() -> None:
    from role_builder.services.user_vault import extract_vault_path

    ref = "${vault://api1:users/john/transcription/deepgram/ma_cle}"
    assert extract_vault_path(ref) == "users/john/transcription/deepgram/ma_cle"


def test_extract_vault_path_plain_path_passthrough() -> None:
    from role_builder.services.user_vault import extract_vault_path

    plain = "users/john/transcription/deepgram/some-uuid"
    assert extract_vault_path(plain) == plain
```

- [ ] **Step 2 — Vérifier que les tests échouent**

```
cd backend
uv run pytest tests/services/test_user_vault.py -k "transcription_vault_path or build_vault_ref or extract_vault_path" -v
```

Expected : FAIL × 6 avec `ImportError` ou `AttributeError`.

- [ ] **Step 3 — Implémenter les 3 fonctions dans user_vault.py**

Ajouter `import os` au bloc d'imports existant (ligne 13 environ), puis ajouter `_VAULT_REF_RE` et les 3 fonctions après `build_github_vault_name` (vers la ligne 51) :

```python
import os
```

```python
_VAULT_REF_RE = re.compile(r'^\$\{vault://[^:]+:(.+)\}$')


def build_transcription_vault_path(email: str | None, provider: str, key_name: str) -> str:
    """Path plain pour une clé de transcription avec nom personnalisé.

    Exemple : users/john_at_example.com/transcription/deepgram/ma_cle
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/transcription/{provider}/{key_name}"


def build_vault_ref(path: str) -> str:
    """Enveloppe un path dans une ref vault : ${vault://api1:path}.

    L'identifiant est déduit du premier HARPOCRATE_API_TOKEN_* configuré.
    """
    identifier = _primary_vault_identifier()
    return f"${{vault://{identifier}:{path}}}"


def extract_vault_path(vault_secret_name: str) -> str:
    """Extrait le path depuis une ref vault.

    Si ce n'est pas une ref (legacy plain path), retourne la valeur brute.
    Exemples :
      "${vault://api1:users/john/transcription/deepgram/ma_cle}" → "users/john/..."
      "users/john/transcription/deepgram/uuid"                  → "users/john/..."
    """
    m = _VAULT_REF_RE.match(vault_secret_name)
    return m.group(1) if m else vault_secret_name
```

Ajouter `_primary_vault_identifier` juste avant `build_vault_ref` :

```python
def _primary_vault_identifier() -> str:
    """Retourne le suffixe lowercase du premier HARPOCRATE_API_TOKEN_* configuré."""
    for key in os.environ:
        if key.startswith("HARPOCRATE_API_TOKEN_"):
            return key[len("HARPOCRATE_API_TOKEN_"):].lower()
    return "api1"
```

Le fichier complet de `user_vault.py` après modification :

```python
"""Gestion async des secrets utilisateurs dans le coffre Harpocrate.

Les clés utilisateur sont stockées avec un chemin hiérarchique :

    users/{email_slug}/transcription/{provider}/{key_name}  — clés de transcription
    users/{email_slug}/scraping/{platform}/{cred_id}        — cookies de scraping
    github/{tenant_id}/{user_id}                             — tokens GitHub OAuth

L'email/user_id sert de compartiment : les secrets de deux utilisateurs ne se mélangent pas.
"""
from __future__ import annotations

import asyncio
import os
import re
from uuid import UUID

import structlog
from harpocrate import SecretNotFound, VaultClient

log = structlog.get_logger(__name__)

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_VAULT_REF_RE = re.compile(r'^\$\{vault://[^:]+:(.+)\}$')


def build_vault_secret_name(email: str | None, provider: str, key_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour une clé de transcription (leaf = UUID).

    Exemple : users/john_at_example.com/transcription/openai/550e8400-e29b-...
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/transcription/{provider}/{key_id}"


def build_transcription_vault_path(email: str | None, provider: str, key_name: str) -> str:
    """Path plain pour une clé de transcription avec nom personnalisé.

    Exemple : users/john_at_example.com/transcription/deepgram/ma_cle
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/transcription/{provider}/{key_name}"


def build_credentials_vault_name(email: str | None, platform: str, cred_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour les cookies de scraping.

    Exemple : users/john_at_example.com/scraping/youtube/550e8400-...
    """
    raw = email or "no_email"
    slug = _UNSAFE_RE.sub("_", raw.replace("@", "_at_"))
    return f"users/{slug}/scraping/{platform}/{cred_id}"


def build_github_vault_name(user_id: UUID, tenant_id: UUID) -> str:
    """Retourne le nom de secret Harpocrate pour un token GitHub OAuth.

    Exemple : github/00000000-0000-0000-0000-000000000001/12345678-...
    """
    return f"github/{tenant_id}/{user_id}"


def _primary_vault_identifier() -> str:
    """Retourne le suffixe lowercase du premier HARPOCRATE_API_TOKEN_* configuré."""
    for key in os.environ:
        if key.startswith("HARPOCRATE_API_TOKEN_"):
            return key[len("HARPOCRATE_API_TOKEN_"):].lower()
    return "api1"


def build_vault_ref(path: str) -> str:
    """Enveloppe un path dans une ref vault : ${vault://api1:path}.

    L'identifiant est déduit du premier HARPOCRATE_API_TOKEN_* configuré.
    """
    identifier = _primary_vault_identifier()
    return f"${{vault://{identifier}:{path}}}"


def extract_vault_path(vault_secret_name: str) -> str:
    """Extrait le path depuis une ref vault, ou retourne le plain path (compat legacy).

    "${vault://api1:users/john/transcription/deepgram/ma_cle}" → "users/john/..."
    "users/john/transcription/deepgram/uuid"                  → "users/john/..."
    """
    m = _VAULT_REF_RE.match(vault_secret_name)
    return m.group(1) if m else vault_secret_name


class UserVaultService:
    """Wrapper async autour du VaultClient pour les secrets utilisateurs."""

    def __init__(self, client: VaultClient) -> None:
        self._client = client

    async def write(self, secret_name: str, value: str) -> None:
        """Crée ou met à jour un secret dans le coffre."""
        await asyncio.to_thread(
            self._client.secrets.populate, secret_name, False, value
        )
        log.info("user_vault.written", name=secret_name)

    async def read(self, secret_name: str) -> str | None:
        """Lit un secret ; retourne None s'il est absent."""
        try:
            return await asyncio.to_thread(self._client.secrets.get, secret_name)
        except SecretNotFound:
            return None

    async def try_delete(self, secret_name: str) -> None:
        """Best-effort : écrase le secret avec une valeur vide pour l'invalider."""
        try:
            await asyncio.to_thread(
                self._client.secrets.populate, secret_name, False, ""
            )
        except Exception:
            log.exception("user_vault.delete_failed", name=secret_name)


_service: UserVaultService | None = None


def init_service(client: VaultClient) -> None:
    """Initialise le singleton (appelé une fois dans le lifespan FastAPI)."""
    global _service
    _service = UserVaultService(client)


def get_service() -> UserVaultService:
    """Retourne le singleton ; lève RuntimeError si vault non initialisé."""
    if _service is None:
        raise RuntimeError(
            "UserVaultService non initialisé — vault désactivé ou lifespan non démarré"
        )
    return _service
```

- [ ] **Step 4 — Mettre à jour l'import dans test_user_vault.py**

En haut du fichier, modifier le bloc d'imports pour ajouter les 3 nouvelles fonctions :

```python
from role_builder.services.user_vault import (
    UserVaultService,
    build_credentials_vault_name,
    build_github_vault_name,
    build_transcription_vault_path,
    build_vault_ref,
    build_vault_secret_name,
    extract_vault_path,
    get_service,
    init_service,
)
```

Retirer les imports locaux dans les tests qu'on vient d'écrire (les `from role_builder.services.user_vault import ...` dans chaque test) puisqu'ils sont maintenant en tête de fichier. Remplacer :

```python
def test_build_transcription_vault_path_normal_email() -> None:
    from role_builder.services.user_vault import build_transcription_vault_path
    result = build_transcription_vault_path("john@example.com", "deepgram", "ma_cle")
    assert result == "users/john_at_example.com/transcription/deepgram/ma_cle"
```

par :

```python
def test_build_transcription_vault_path_normal_email() -> None:
    result = build_transcription_vault_path("john@example.com", "deepgram", "ma_cle")
    assert result == "users/john_at_example.com/transcription/deepgram/ma_cle"
```

Idem pour les 5 autres tests de cette tâche (supprimer le `from role_builder...` local de chacun).

- [ ] **Step 5 — Vérifier que les tests passent**

```
uv run pytest tests/services/test_user_vault.py -v
```

Expected : PASS × 22 (16 existants + 6 nouveaux).

- [ ] **Step 6 — Lint**

```
uv run ruff check src/role_builder/services/user_vault.py tests/services/test_user_vault.py --fix
```

Expected : `All checks passed!`

- [ ] **Step 7 — Commit**

```
git add backend/src/role_builder/services/user_vault.py backend/tests/services/test_user_vault.py
git commit -m "feat(vault): ajouter build_transcription_vault_path, build_vault_ref, extract_vault_path"
```

---

## Task 2 — Schema + route + tests backend

**Files:**
- Modify: `backend/src/role_builder/schemas/transcription_keys.py`
- Modify: `backend/src/role_builder/routes/transcription_keys.py`
- Modify: `backend/tests/test_transcription_keys_route.py`

### Contexte

Actuellement `CreateTranscriptionKeyRequest` n'a pas de champ `harpocrate_key`. La route `create_key_endpoint` génère un UUID comme leaf du path vault. Les endpoints `test` et `delete` passent `key["vault_secret_name"]` directement à `UserVaultService` sans extraire le path.

Après cette tâche :
- `CreateTranscriptionKeyRequest` a `harpocrate_key: str` (requis, min 1 char)
- `create_key_endpoint` utilise le nom fourni comme leaf, stocke la ref vault en DB
- `test_key_endpoint` et `delete_key_endpoint` extraient le path avant d'appeler le service

- [ ] **Step 1 — Mettre à jour les tests existants (ils doivent échouer après step 2)**

Dans `backend/tests/test_transcription_keys_route.py` :

**1a. Mettre à jour `_make_key_row`** — changer `vault_secret_name` pour utiliser le format ref vault :

```python
def _make_key_row(
    key_id: UUID | None = None,
    provider: str = "deepgram",
    status: str = "active",
    monthly_cap_usd: float | None = 100.0,
    current_month_spend_usd: float = 0.0,
    current_balance_usd: float | None = 50.0,
    is_primary: bool = False,
    is_fallback: bool = False,
    workers_count: int = 1,
) -> dict[str, Any]:
    """Construit un dict simulant une ligne de user_transcription_keys."""
    now = datetime.now(tz=UTC)
    kid = key_id or uuid4()
    return {
        "id": kid,
        "tenant_id": _FIXED_TENANT_ID,
        "user_id": _FIXED_USER_ID,
        "provider": provider,
        "label": "Ma clé Deepgram",
        "vault_secret_name": f"${{vault://api1:users/no_email/transcription/{provider}/test_key}}",
        "status": status,
        "is_primary": is_primary,
        "is_fallback": is_fallback,
        "workers_count": workers_count,
        "monthly_cap_usd": monthly_cap_usd,
        "current_month_spend_usd": current_month_spend_usd,
        "current_balance_usd": current_balance_usd,
        "last_balance_check_at": now,
        "last_validated_at": now,
        "created_at": now,
        "updated_at": now,
    }
```

**1b. Mettre à jour T2** (`test_create_key_returns_201_and_dto`) :

Ajouter `harpocrate_key` dans le POST body et capturer `vault_secret_name` dans `fake_insert` :

```python
    async def fake_insert(**kwargs: Any) -> UUID:
        calls["insert_vault_secret_name"] = kwargs.get("vault_secret_name", "")
        return key_id
```

Modifier la requête POST :

```python
    resp = client.post(
        "/api/transcription-keys",
        json={
            "provider": "deepgram",
            "label": "Ma clé Deepgram",
            "api_key": "dg_test_key_123",
            "harpocrate_key": "ma_cle_deepgram",
            "workers_count": 1,
            "is_primary": False,
            "is_fallback": False,
        },
    )
```

Ajouter des assertions sur le format vault ref :

```python
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(key_id)
    assert body["provider"] == "deepgram"
    assert "write_name" in calls
    assert calls["write_name"].startswith("users/")          # écrit le plain path dans vault
    assert "ma_cle_deepgram" in calls["write_name"]           # leaf = clé fournie
    assert calls.get("insert_vault_secret_name", "").startswith("${vault://")  # ref en DB
    assert "ma_cle_deepgram" in calls.get("insert_vault_secret_name", "")
    assert calls.get("update_balance_called") is None
```

**1c. Mettre à jour T3** (`test_create_key_invalid_returns_400`) — ajouter `harpocrate_key` :

```python
    resp = client.post(
        "/api/transcription-keys",
        json={"provider": "deepgram", "api_key": "bad_key", "harpocrate_key": "any_key"},
    )
```

**1d. Mettre à jour T4** (`test_create_key_with_balance_calls_update_balance`) — ajouter `harpocrate_key` :

```python
    resp = client.post(
        "/api/transcription-keys",
        json={"provider": "deepgram", "api_key": "dg_valid", "harpocrate_key": "ma_cle"},
    )
```

- [ ] **Step 2 — Vérifier que les tests échouent**

```
uv run pytest tests/test_transcription_keys_route.py::test_create_key_returns_201_and_dto tests/test_transcription_keys_route.py::test_create_key_invalid_returns_400 tests/test_transcription_keys_route.py::test_create_key_with_balance_calls_update_balance -v
```

Expected : T2 FAIL (manque assertion vault ref), T3 et T4 PASS (harpocrate_key ignoré pour l'instant — Pydantic ignore les champs extra par défaut). Cela confirme qu'on doit d'abord rendre le champ obligatoire.

- [ ] **Step 3 — Mettre à jour le schéma Pydantic**

Dans `backend/src/role_builder/schemas/transcription_keys.py`, modifier `CreateTranscriptionKeyRequest` :

```python
class CreateTranscriptionKeyRequest(BaseModel):
    provider: Literal["openai-whisper", "deepgram", "assemblyai", "speechmatics"]
    label: str | None = None
    api_key: str
    harpocrate_key: str = Field(min_length=1)
    workers_count: int = Field(default=1, ge=1, le=5)
    is_primary: bool = False
    is_fallback: bool = False
```

- [ ] **Step 4 — Mettre à jour la route transcription_keys.py**

Remplacer le bloc d'imports `user_vault` :

```python
# Avant :
from role_builder.services.user_vault import build_vault_secret_name
from role_builder.services.user_vault import get_service as _get_vault_service

# Après :
from role_builder.services.user_vault import (
    build_transcription_vault_path,
    build_vault_ref,
    extract_vault_path,
    get_service as _get_vault_service,
)
```

Retirer `uuid4` du bloc `from uuid import UUID, uuid4` → `from uuid import UUID`.

Modifier `create_key_endpoint` — remplacer les 3 lignes uuid4/build/write par :

```python
    path = build_transcription_vault_path(user.email, request.provider, request.harpocrate_key)
    vault_ref = build_vault_ref(path)

    await _get_vault_service().write(path, request.api_key)

    inserted_id = await keys_helper.insert_transcription_key(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        provider=request.provider,
        label=request.label,
        vault_secret_name=vault_ref,
        workers_count=request.workers_count,
        is_primary=request.is_primary,
        is_fallback=request.is_fallback,
        pool=db_pool.pool,
    )
```

Modifier `test_key_endpoint` — remplacer la lecture directe :

```python
    # Avant :
    raw_key = await _get_vault_service().read(key["vault_secret_name"])

    # Après :
    path = extract_vault_path(key["vault_secret_name"])
    raw_key = await _get_vault_service().read(path)
```

Modifier `delete_key_endpoint` — remplacer la suppression directe :

```python
    # Avant :
    await _get_vault_service().try_delete(key["vault_secret_name"])

    # Après :
    path = extract_vault_path(key["vault_secret_name"])
    await _get_vault_service().try_delete(path)
```

Le docstring du module ligne 14 est à mettre à jour :

```python
La clé API réelle est stockée dans Harpocrate sous le chemin :
  users/{email_slug}/transcription/{provider}/{harpocrate_key}
La DB enregistre la référence vault : ${vault://api1:<chemin>}
```

- [ ] **Step 5 — Vérifier que tous les tests passent**

```
uv run pytest tests/test_transcription_keys_route.py -v
```

Expected : PASS × 14 (tous les tests existants + les mises à jour).

- [ ] **Step 6 — Suite de tests complète**

```
uv run pytest -q
```

Expected : PASS × 553+.

- [ ] **Step 7 — Lint**

```
uv run ruff check src/ tests/ --fix
```

Expected : `All checks passed!`

- [ ] **Step 8 — Commit**

```
git add backend/src/role_builder/schemas/transcription_keys.py \
        backend/src/role_builder/routes/transcription_keys.py \
        backend/tests/test_transcription_keys_route.py
git commit -m "feat(transcription): champ harpocrate_key requis — stockage vault ref en DB"
```

---

## Task 3 — Frontend : API client + modal

**Files:**
- Modify: `frontend/src/lib/api/transcription-keys.ts`
- Modify: `frontend/src/app/my-stack/transcription-services/AddKeyModal.tsx`

### Contexte

`createKey` dans `transcription-keys.ts` n'a pas `harpocrate_key` dans son type. `AddKeyModal.tsx` n'a pas de champ pour ce nouvel input. Le backend renverra 422 si le champ est absent.

- [ ] **Step 1 — Mettre à jour le client API**

Dans `frontend/src/lib/api/transcription-keys.ts`, ajouter `harpocrate_key` au type de `createKey` :

```typescript
export async function createKey(body: {
  provider: TranscriptionProvider;
  label?: string | null;
  api_key: string;
  harpocrate_key: string;
  workers_count?: number;
  is_primary?: boolean;
  is_fallback?: boolean;
}): Promise<TranscriptionKey> {
  return api<TranscriptionKey>('/api/transcription-keys', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
```

- [ ] **Step 2 — Mettre à jour AddKeyModal.tsx**

Fichier complet après modification (`frontend/src/app/my-stack/transcription-services/AddKeyModal.tsx`) :

```tsx
'use client';

import { useState } from 'react';
import { createKey } from '@/lib/api/transcription-keys';
import type { TranscriptionProvider } from '@/lib/types';

interface Props {
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const PROVIDER_OPTIONS: { value: TranscriptionProvider; label: string }[] = [
  { value: 'openai-whisper', label: 'OpenAI Whisper' },
  { value: 'deepgram', label: 'Deepgram' },
  { value: 'assemblyai', label: 'AssemblyAI' },
  { value: 'speechmatics', label: 'Speechmatics' },
];

export function AddKeyModal({ onClose, onSaved }: Props) {
  const [provider, setProvider] = useState<TranscriptionProvider>('openai-whisper');
  const [label, setLabel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [harpocrateKey, setHarpocrateKey] = useState('');
  const [workersCount, setWorkersCount] = useState(1);
  const [isPrimary, setIsPrimary] = useState(false);
  const [isFallback, setIsFallback] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!apiKey.trim()) {
      setError('Renseigne la clé API');
      return;
    }
    if (!harpocrateKey.trim()) {
      setError('Renseigne la clé Harpocrate');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createKey({
        provider,
        label: label || null,
        api_key: apiKey,
        harpocrate_key: harpocrateKey,
        workers_count: workersCount,
        is_primary: isPrimary,
        is_fallback: isFallback,
      });
      await onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.5)',
    }}>
      <div style={{ width: '100%', maxWidth: 500, background: 'white', padding: 24, borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <h2 style={{ marginBottom: 16, fontSize: '1.125rem', fontWeight: 600 }}>Ajouter une clé de transcription</h2>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Provider</span>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as TranscriptionProvider)}
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}
          >
            {PROVIDER_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Libellé (optionnel)</span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ex: Compte perso"
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Clé API</span>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Clé Harpocrate</span>
          <input
            type="text"
            value={harpocrateKey}
            onChange={(e) => setHarpocrateKey(e.target.value)}
            placeholder="ma_cle_openai"
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Workers (1-5) : {workersCount}
          </span>
          <input
            type="range"
            min={1} max={5} step={1}
            value={workersCount}
            onChange={(e) => setWorkersCount(Number(e.target.value))}
            style={{ width: '100%' }}
          />
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input
            type="checkbox"
            checked={isPrimary}
            onChange={(e) => setIsPrimary(e.target.checked)}
          />
          <span>Provider primaire</span>
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <input
            type="checkbox"
            checked={isFallback}
            onChange={(e) => setIsFallback(e.target.checked)}
          />
          <span>Activer en fallback</span>
        </label>

        {error !== null && <p style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</p>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onClose}
            style={{ border: '1px solid #d1d5db', padding: '6px 14px', borderRadius: 4, background: 'white', cursor: 'pointer', fontSize: 13 }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !apiKey.trim() || !harpocrateKey.trim()}
            style={{
              background: '#2563eb', color: 'white', padding: '6px 14px', borderRadius: 4, border: 'none',
              cursor: 'pointer', fontSize: 13,
              opacity: submitting || !apiKey.trim() || !harpocrateKey.trim() ? 0.5 : 1,
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3 — Vérifier le typecheck**

```
cd frontend
npm run typecheck
```

Expected : zéro erreur TypeScript.

- [ ] **Step 4 — Commit**

```
git add frontend/src/lib/api/transcription-keys.ts \
        frontend/src/app/my-stack/transcription-services/AddKeyModal.tsx
git commit -m "feat(frontend): champ Harpocrate key requis dans le formulaire de transcription"
```
