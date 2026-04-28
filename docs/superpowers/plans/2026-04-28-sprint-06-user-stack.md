# Sprint 6 — Ma stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Patterns établis Sprint 5 (db_helpers stub asyncpg, structlog, ≤300 lignes, TDD strict).

**Goal:** Onglet "Ma stack" complet — CRUD credentials cookies, clés SaaS transcription (slider workers + toggles primaire/fallback), config Mistral ag.flow, quotas mensuels avec polling crédit. Cron jobs APScheduler.

**Architecture:**
- Backend : helpers étendus (`credentials`, `transcription_keys`), services `validators` (cookies + clés provider), `credit_monitor` (poll Deepgram), `scheduler` (APScheduler), 4 routers (credentials, transcription-keys, mistral-config, scheduler stats).
- Frontend : `app/my-stack/` avec 4 sous-onglets, composants réutilisables (`StatusIndicator` 🔴🟠🟢, `KeySettings`, `BalanceBadge`, `QuotaForm`).
- Storage : OpenBao paths déjà spécifiés (sub-paths `secret/scraping-credentials/...` et `secret/transcription-keys/...`).

**Tech Stack:** APScheduler (nouvelle dépendance), httpx (existant), OpenBaoClient (existant), pas de nouvelle dépendance frontend.

**Décisions actées :**
- Email reporté Phase 2 (notif WebSocket + UI uniquement MVP).
- Validation cookies = parse format Netscape côté backend (pas d'appel scraper réel pour MVP — reporté).
- Validation clés = appel API trivial par provider (cf. spec § 07 tableau).
- `check_mistral_secret_exists` = noop en MVP (return "configured" si secret_ref non vide). À câbler vraiment quand `GET /api/admin/secrets` ag.flow sera disponible.
- Endpoint test cookies via scraper container : reporté Phase 2.
- Multi-tenant : `TENANT_ID_DEFAULT` + `user.user_id` du JWT (déjà câblé Auth Keycloak).

---

## File Structure

```
backend/
├── src/role_builder/
│   ├── config.py                                 # Phase A : settings APScheduler + Deepgram
│   ├── main.py                                   # Phase E + F : include scheduler lifespan + routers
│   ├── db_helpers/
│   │   ├── credentials.py                        # Phase A : étendre (CRUD complet)
│   │   └── transcription_keys.py                 # Phase A : étendre (CRUD + quota)
│   ├── services/
│   │   ├── credentials_validator.py              # Phase B
│   │   ├── transcription_validator.py            # Phase B
│   │   ├── credit_monitor.py                     # Phase E
│   │   └── scheduler.py                          # Phase E
│   ├── schemas/
│   │   ├── credentials.py                        # Phase C
│   │   ├── transcription_keys.py                 # Phase D
│   │   └── mistral_config.py                     # Phase F
│   └── routes/
│       ├── credentials.py                        # Phase C
│       ├── transcription_keys.py                 # Phase D
│       └── mistral_config.py                     # Phase F
└── tests/
    ├── test_db_helpers_credentials.py            # Phase A (étendu)
    ├── test_db_helpers_transcription_keys.py     # Phase A (étendu)
    ├── test_credentials_validator.py             # Phase B
    ├── test_transcription_validator.py           # Phase B
    ├── test_credentials_route.py                 # Phase C
    ├── test_transcription_keys_route.py          # Phase D
    ├── test_credit_monitor.py                    # Phase E
    ├── test_scheduler.py                         # Phase E
    └── test_mistral_config_route.py              # Phase F

frontend/
└── src/
    ├── lib/
    │   ├── types.ts                              # Phase G : ajouter UserCredential, TranscriptionKey, etc.
    │   └── api/
    │       ├── credentials.ts                    # Phase G
    │       ├── transcription-keys.ts             # Phase G
    │       └── mistral-config.ts                 # Phase G
    ├── components/
    │   └── StatusIndicator.tsx                   # Phase H : 🔴🟠🟢
    └── app/my-stack/
        ├── page.tsx                              # Phase H : tabs container
        ├── social-accounts/
        │   ├── page.tsx                          # Phase H
        │   ├── AccountsList.tsx
        │   ├── AddAccountModal.tsx
        │   └── CookiesGuide.tsx
        ├── transcription-services/
        │   ├── page.tsx                          # Phase I
        │   ├── KeysList.tsx
        │   ├── AddKeyModal.tsx
        │   └── KeySettings.tsx
        ├── mistral-config/
        │   ├── page.tsx                          # Phase J
        │   └── ConfigForm.tsx
        └── quotas/
            ├── page.tsx                          # Phase J
            └── QuotaForm.tsx
```

---

## Phase A — DB helpers étendus

### A1 — `db_helpers/credentials.py` CRUD complet (TDD)

Le fichier existant ne contient que `get_cookies_b64` (settings env). À garder mais ajouter en plus :

```python
async def insert_user_credential(
    *, tenant_id: UUID, user_id: UUID, platform: str, label: str | None,
    openbao_path: str, status: str = "active",
    last_validated_at: datetime | None = None,
    expires_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> UUID: ...
# INSERT user_credentials RETURNING id

async def list_credentials(
    *, user_id: UUID, platform: str | None = None,
    pool: asyncpg.Pool,
) -> list[dict]: ...
# SELECT WHERE user_id=$1 [AND platform=$2] ORDER BY created_at DESC

async def get_credential(cred_id: UUID, *, user_id: UUID, pool) -> dict | None: ...
# SELECT WHERE id=$1 AND user_id=$2 (sécurité multi-user)

async def update_credential_status(
    cred_id: UUID, *, status: str,
    last_validated_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> None: ...

async def revoke_credential(cred_id: UUID, *, pool: asyncpg.Pool) -> None: ...
# UPDATE status='revoked', updated_at=now()

async def delete_credential(cred_id: UUID, *, pool: asyncpg.Pool) -> None: ...
# DELETE FROM user_credentials WHERE id=$1
```

Tests : 7 tests (insert, list sans filtre, list avec filtre platform, get, update_status, revoke, delete).

Commit : `feat(backend): db_helpers/credentials étendu (insert + CRUD complet par user)`

### A2 — `db_helpers/transcription_keys.py` CRUD complet (TDD)

Le fichier existant a 5 fonctions de read-only. Ajouter :

```python
async def insert_transcription_key(
    *, tenant_id: UUID, user_id: UUID, provider: str, label: str | None,
    openbao_path: str, workers_count: int = 1,
    is_primary: bool = False, is_fallback: bool = False,
    monthly_cap_usd: float | None = None,
    pool: asyncpg.Pool,
) -> UUID: ...
# Si is_primary=True : transaction qui passe les autres primary du user à False, puis INSERT.

async def list_keys_for_user(user_id: UUID, *, pool: asyncpg.Pool) -> list[dict]: ...
# Tous les status (pas juste active). ORDER BY created_at DESC.

async def get_key(key_id: UUID, *, user_id: UUID, pool: asyncpg.Pool) -> dict | None: ...

async def update_key_settings(
    key_id: UUID, *, workers_count: int | None = None,
    is_primary: bool | None = None,
    is_fallback: bool | None = None,
    monthly_cap_usd: float | None = None,
    pool: asyncpg.Pool,
) -> None: ...
# Build dynamic SET clause selon les non-None. Si is_primary=True : transaction.

async def update_key_balance(
    key_id: UUID, *, balance_usd: float | None,
    checked_at: datetime,
    pool: asyncpg.Pool,
) -> None: ...
# UPDATE current_balance_usd, last_balance_check_at

async def increment_spend(key_id: UUID, amount_usd: float, *, pool) -> float: ...
# UPDATE current_month_spend_usd = current_month_spend_usd + $2 RETURNING current_month_spend_usd

async def reset_monthly_spend_all(*, pool: asyncpg.Pool) -> int: ...
# UPDATE user_transcription_keys SET current_month_spend_usd=0 WHERE current_month_spend_usd > 0
# RETURNING count.

async def revoke_key(key_id: UUID, *, pool: asyncpg.Pool) -> None: ...

async def delete_key(key_id: UUID, *, pool: asyncpg.Pool) -> None: ...

async def list_active_keys_for_balance_polling(*, pool: asyncpg.Pool) -> list[dict]: ...
# SELECT WHERE status='active' AND provider IN ('deepgram') (providers avec balance API)
```

Tests : ~12 tests (insert simple, insert avec is_primary démote autres, list, get, update_settings (each field), update_balance, increment_spend retourne nouveau total, reset_monthly_spend, revoke, delete, list_for_balance_polling).

Commit : `feat(backend): db_helpers/transcription_keys étendu (CRUD + quota + balance polling)`

### A3 — `db_helpers/role_projects.update_mistral_secret_ref` + `get_mistral_secret_ref`

```python
async def update_mistral_secret_ref(
    role_project_id: UUID, secret_ref: str | None, *, pool: asyncpg.Pool,
) -> None: ...
# UPDATE role_projects SET mistral_secret_ref=$2, updated_at=now() WHERE id=$1
# Lève ValueError si rows=0.
```

Tests : 2 tests (envoie UPDATE, lève si rows=0).

Commit : `feat(backend): db_helpers/role_projects.update_mistral_secret_ref (config Mistral ag.flow)`

---

## Phase B — Validators (cookies + clés API)

### B1 — `services/credentials_validator.py` (TDD)

Validation cookies Netscape format (parse simple, pas appel scraper) :

```python
def parse_netscape_cookies(content: str) -> list[dict]:
    """Parse un fichier cookies.txt format Netscape.
    Format : domain<TAB>flag<TAB>path<TAB>secure<TAB>expiry<TAB>name<TAB>value
    Lignes commençant par # ou vides ignorées.
    Retourne list de dicts {domain, name, value, expiry, ...}.
    Lève ValueError si format invalide."""
    ...

async def validate_cookies(platform: str, cookies_b64: str) -> dict:
    """Valide format + extrait métadonnées.
    Retourne {valid: bool, expires_at: datetime|None, error: str|None}.
    Vérifie que des cookies clés sont présents par plateforme :
    - youtube: 'SID' ou 'SAPISID'
    - instagram: 'sessionid'
    - tiktok: 'sessionid' ou 'sid_tt'
    Si manquant → valid=False, error explicatif."""
    ...
```

Tests : 6 tests (parse OK, parse vide, parse comment-only, parse format invalide, validate_cookies platform OK, validate_cookies cookies clé manquant).

Commit : `feat(backend): credentials_validator (parse Netscape cookies + validation par plateforme)`

### B2 — `services/transcription_validator.py` (TDD)

```python
async def validate_transcription_key(provider: str, api_key: str) -> dict:
    """Appel API trivial selon provider :
    - openai-whisper: GET /v1/models (Authorization: Bearer key)
    - deepgram: GET /v1/projects (Authorization: Token key)
    - assemblyai: GET /v2/transcript?limit=1 (Authorization: key)
    - speechmatics: GET /v2/jobs (Authorization: Bearer key)
    Timeout 10s, retourne {valid: bool, error: str|None, balance_usd: float|None}.
    balance_usd renseigné uniquement si Deepgram (autres ne l'exposent pas trivialement)."""
    ...

async def fetch_balance(provider: str, api_key: str) -> float | None:
    """Récupère le crédit restant pour les providers qui l'exposent.
    - deepgram: GET /v1/projects/{project_id}/balance → list of balances, sum 'amount'
    - autres: return None.
    Timeout 10s. Retourne None sur erreur (logger warning)."""
    ...
```

Tests : ~8 tests avec httpx mock via `respx` ou `httpx.MockTransport`. Pour chaque provider : OK, 401, 5xx, timeout.

Commit : `feat(backend): transcription_validator (validate + balance polling Deepgram)`

---

## Phase C — Routes credentials

### C1 — Schemas + routes (TDD)

`schemas/credentials.py` :
```python
class UserCredentialOut(BaseModel):
    id: UUID
    platform: str
    label: str | None
    status: str
    last_validated_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

class CreateCredentialRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"]
    label: str | None = None
    cookies_b64: str  # base64 du cookies.txt
```

`routes/credentials.py` (sous `/api/credentials`) :
- `GET /api/credentials?platform=...` → `list[UserCredentialOut]` (filtrée par `user.user_id`)
- `POST /api/credentials` body `CreateCredentialRequest` → `UserCredentialOut` (validate cookies + put OpenBao + insert DB)
- `POST /api/credentials/{cred_id}/test` → `{status: str, last_validated_at: datetime}` (re-validate)
- `DELETE /api/credentials/{cred_id}` → 204 (revoke + delete OpenBao secret + delete DB)

Pour OpenBao : utiliser `services.openbao_client.OpenBaoClient` existant (cf. Sprint 1). Path : `scraping-credentials/{tenant_id}/{platform}/{credential_id}`.

Tests : ~6 tests (GET liste, POST OK, POST invalid cookies → 400, POST → check OpenBao put appelé, DELETE → check OpenBao delete + DB delete).

Commit : `feat(backend): routes credentials (CRUD + test + OpenBao integration)`

---

## Phase D — Routes transcription_keys

### D1 — Schemas + routes (TDD)

`schemas/transcription_keys.py` :
```python
class TranscriptionKeyOut(BaseModel):
    id: UUID
    provider: str
    label: str | None
    status: str
    is_primary: bool
    is_fallback: bool
    workers_count: int
    monthly_cap_usd: float | None
    current_month_spend_usd: float
    current_balance_usd: float | None
    last_balance_check_at: datetime | None
    last_validated_at: datetime | None
    created_at: datetime

class CreateTranscriptionKeyRequest(BaseModel):
    provider: Literal["openai-whisper", "deepgram", "assemblyai", "speechmatics"]
    label: str | None = None
    api_key: str
    workers_count: int = Field(default=1, ge=1, le=5)
    is_primary: bool = False
    is_fallback: bool = False

class UpdateTranscriptionKeyRequest(BaseModel):
    workers_count: int | None = Field(default=None, ge=1, le=5)
    is_primary: bool | None = None
    is_fallback: bool | None = None

class UpdateQuotaRequest(BaseModel):
    monthly_cap_usd: float | None = Field(default=None, ge=0)

class UsageResponse(BaseModel):
    current_month_spend_usd: float
    monthly_cap_usd: float | None
    pct_used: float | None
    last_balance_check_at: datetime | None
    current_balance_usd: float | None
```

`routes/transcription_keys.py` (sous `/api/transcription-keys`) :
- `GET /api/transcription-keys` → `list[TranscriptionKeyOut]` (filtrée par user)
- `POST /api/transcription-keys` body `CreateTranscriptionKeyRequest`
  - Valide via `transcription_validator.validate_transcription_key`
  - Si invalid → 400
  - Put OpenBao
  - Insert DB
  - Trigger `worker_manager.ensure_user_workers_running(user_id)` (best-effort, log si fail)
- `PATCH /api/transcription-keys/{key_id}` body `UpdateTranscriptionKeyRequest`
- `POST /api/transcription-keys/{key_id}/test` → re-validate + update status + balance
- `PATCH /api/transcription-keys/{key_id}/quota` body `UpdateQuotaRequest`
- `GET /api/transcription-keys/{key_id}/usage` → `UsageResponse`
- `DELETE /api/transcription-keys/{key_id}` → 204
  - Stop workers via `worker_manager.stop_workers_for_key(key_id)` (best-effort)
  - Delete OpenBao
  - Delete DB

Pour `worker_manager.ensure_user_workers_running` et `stop_workers_for_key` : si les méthodes n'existent pas dans `worker_manager.py`, créer des stubs minimaux qui logent un warning + ne font rien (worker_manager.py existe Sprint 3 mais sera enrichi quand on déploiera des workers user réels).

Tests : ~10 tests (GET, POST OK, POST invalid → 400, POST is_primary démote autres, PATCH settings, POST test, PATCH quota, GET usage, DELETE → check stop + cleanup).

Commit : `feat(backend): routes transcription_keys (CRUD + test + quota + usage + worker management)`

---

## Phase E — Credit monitor + scheduler APScheduler

### E1 — `services/credit_monitor.py` (TDD)

```python
async def poll_all_balances(*, pool: asyncpg.Pool, openbao: OpenBaoClient) -> dict[str, int]:
    """Poll les balances des clés actives pour les providers qui l'exposent.
    Retourne {polled: int, updated: int, errors: int}.

    Steps :
      1. list_active_keys_for_balance_polling(pool) → keys
      2. Pour chaque key : openbao.get(key.openbao_path) → api_key
         transcription_validator.fetch_balance(key.provider, api_key)
         Si balance is not None : update_key_balance(key_id, balance, now())
         Si balance < 0.20 * (monthly_cap_usd ou 100) : log warning "low balance"
         Si balance == 0 : mark_exhausted(key_id) + stop workers (best-effort)
    """
```

Tests : 4 tests avec mocks (happy path 2 keys, 1 fail openbao, balance 0 → mark_exhausted, balance None → no update).

### E2 — `services/scheduler.py` (TDD)

Ajouter dépendance `apscheduler>=3.10.4` au `pyproject.toml`.

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class RoleBuilderScheduler:
    def __init__(self, *, pool, openbao):
        self._scheduler = AsyncIOScheduler()
        self._pool = pool
        self._openbao = openbao

    def start(self) -> None:
        self._scheduler.add_job(
            self._poll_balances, "interval", hours=1,
            id="poll_credit_balances",
        )
        self._scheduler.add_job(
            self._reset_monthly_spend, "cron", day=1, hour=0, minute=0,
            id="reset_monthly_spend",
        )
        self._scheduler.add_job(
            self._cleanup_revoked_secrets, "cron", hour=3,
            id="cleanup_revoked_secrets",
        )
        self._scheduler.start()

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _poll_balances(self) -> None: ...
    async def _reset_monthly_spend(self) -> None: ...
    async def _cleanup_revoked_secrets(self) -> None: ...
```

Settings :
```python
disable_scheduler: bool = False
```

Lancement dans `main.py` lifespan :
```python
if not settings.disable_scheduler:
    scheduler = RoleBuilderScheduler(pool=db_pool, openbao=openbao)
    scheduler.start()
    app.state.scheduler = scheduler
yield
if hasattr(app.state, "scheduler"):
    await app.state.scheduler.shutdown()
```

Tests : 3 tests (instanciation OK, jobs schedulés, shutdown).

Commit : `feat(backend): credit_monitor + scheduler APScheduler (poll balance horaire + reset mensuel + cleanup)`

---

## Phase F — Routes mistral_config

### F1 — Schemas + routes (TDD)

`schemas/mistral_config.py` :
```python
class MistralConfigOut(BaseModel):
    secret_ref: str | None
    status: Literal["configured", "not-configured"]

class SetMistralConfigRequest(BaseModel):
    secret_ref: str | None = None
```

`routes/mistral_config.py` :
- `GET /api/role-projects/{project_id}/mistral-config` → `MistralConfigOut`
  - status = "configured" si secret_ref non None et non vide, sinon "not-configured"
  - (MVP : pas d'appel ag.flow `GET /api/admin/secrets`. Reporté Phase 2.)
- `PUT /api/role-projects/{project_id}/mistral-config` body `SetMistralConfigRequest`
  - Update via `db_helpers.role_projects.update_mistral_secret_ref`
  - 404 si project introuvable

Tests : 4 tests (GET configured, GET not-configured, PUT OK, PUT 404).

Commit : `feat(backend): routes mistral_config (GET/PUT secret_ref par projet)`

---

## Phase G — Frontend types + clients API

### G1 — Types + clients (TDD Vitest)

Modifier `frontend/src/lib/types.ts` :
```typescript
export interface UserCredential {
  id: string;
  platform: 'youtube' | 'instagram' | 'tiktok';
  label: string | null;
  status: 'active' | 'expired' | 'invalid' | 'revoked';
  last_validated_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface TranscriptionKey {
  id: string;
  provider: 'openai-whisper' | 'deepgram' | 'assemblyai' | 'speechmatics';
  label: string | null;
  status: 'active' | 'low' | 'exhausted' | 'invalid';
  is_primary: boolean;
  is_fallback: boolean;
  workers_count: number;
  monthly_cap_usd: number | null;
  current_month_spend_usd: number;
  current_balance_usd: number | null;
  last_balance_check_at: string | null;
  last_validated_at: string | null;
  created_at: string;
}

export interface MistralConfig {
  secret_ref: string | null;
  status: 'configured' | 'not-configured';
}

export interface KeyUsage {
  current_month_spend_usd: number;
  monthly_cap_usd: number | null;
  pct_used: number | null;
  last_balance_check_at: string | null;
  current_balance_usd: number | null;
}
```

Créer 3 clients dans `frontend/src/lib/api/` :
- `credentials.ts` : `listCredentials(platform?)`, `createCredential({platform, label, cookies_b64})`, `testCredential(id)`, `deleteCredential(id)`
- `transcription-keys.ts` : `listKeys()`, `createKey(...)`, `updateKey(id, settings)`, `testKey(id)`, `updateQuota(id, cap)`, `getUsage(id)`, `deleteKey(id)`
- `mistral-config.ts` : `getMistralConfig(projectId)`, `setMistralConfig(projectId, secret_ref)`

Tests Vitest pour chaque client (mock fetch). ~10 tests total.

Commit : `feat(frontend): clients API credentials + transcription-keys + mistral-config + types`

---

## Phase H — Frontend onglet Comptes réseaux sociaux

### H1 — Page tabs container + StatusIndicator + sous-onglet social-accounts

`components/StatusIndicator.tsx` :
```typescript
type StatusColor = 'red' | 'orange' | 'green';
interface Props { status: 'active' | 'expired' | 'invalid' | 'revoked' | 'low' | 'exhausted' | 'configured' | 'not-configured'; }

const STATUS_COLOR: Record<Props['status'], StatusColor> = {
  active: 'green', configured: 'green',
  low: 'orange', expired: 'orange', 'not-configured': 'orange',
  invalid: 'red', revoked: 'red', exhausted: 'red',
};

const STATUS_LABEL: Record<Props['status'], string> = {
  active: 'Actif', configured: 'Configuré',
  low: 'Crédit bas', expired: 'Expiré', 'not-configured': 'Non configuré',
  invalid: 'Invalide', revoked: 'Révoqué', exhausted: 'Épuisé',
};
```

Cercle coloré + label. Pas de modal, juste affichage compact.

`app/my-stack/page.tsx` (Client Component) :
- Container avec navigation entre 4 sous-onglets via `<Link>` Next.js (`/my-stack/social-accounts`, etc.)
- Default redirect vers `/my-stack/social-accounts`

`app/my-stack/social-accounts/page.tsx` :
- SWR `useSWR('credentials', listCredentials)`
- Liste groupée par platform (3 sections : YouTube, Instagram, TikTok)
- Bouton "Ajouter un compte YouTube/Instagram/TikTok" par section → ouvre `<AddAccountModal>`
- Pour chaque credential : label, `<StatusIndicator>`, last_validated_at, bouton "Tester", bouton "Révoquer"

`AccountsList.tsx` (présentation) :
- Props : `{ credentials: UserCredential[]; onTest: (id) => void; onDelete: (id) => void }`

`AddAccountModal.tsx` (présentation) :
- Sélecteur platform (preset si ouvert depuis bouton platform-specific)
- Input label
- Drag-drop `cookies.txt` → lit et encode base64 via FileReader → `cookies_b64`
- Mini-guide via `<CookiesGuide>` (section pliable avec instructions)
- Bouton "Ajouter" → POST + mutate

`CookiesGuide.tsx` :
- Section pliable avec instructions par plateforme : "Installer extension Get cookies.txt LOCALLY (Chrome/Firefox), se connecter sur YouTube, exporter, glisser ici."
- Liens vers store extension.

Tests Vitest (optionnels) : 1-2 sur AccountsList rendering.

Commit : `feat(frontend): my-stack/social-accounts (liste + ajout + test + révocation cookies)`

---

## Phase I — Frontend onglet Services de transcription

### I1 — Page transcription-services + composants

`app/my-stack/transcription-services/page.tsx` (Client) :
- SWR `useSWR('transcription-keys', listKeys)`
- Section "Pas de clé active" si liste vide → message + "Les transcriptions utiliseront le pool partagé (faster-whisper local)"
- Liste des clés (4 providers possibles : OpenAI Whisper, Deepgram, AssemblyAI, Speechmatics)
- Bouton "Ajouter une clé" → modal

`KeysList.tsx` :
- Props `{ keys: TranscriptionKey[]; onUpdate, onTest, onDelete }`
- Pour chaque clé : provider (icône), label, `<StatusIndicator>`, `<BalanceBadge>` si current_balance_usd, current_month_spend_usd / monthly_cap_usd, `<KeySettings>` (slider + toggles)

`KeySettings.tsx` :
- Slider 1-5 pour workers_count (avec debounce 500ms → PATCH)
- Toggle "Provider primaire" (radio : un seul actif globalement)
- Toggle "Activer en fallback"
- Section "Quota mensuel (USD)" : input number + bouton Save

`AddKeyModal.tsx` :
- Sélecteur provider
- Input label
- Input api_key (type=password)
- Slider workers_count (1-5)
- Toggles is_primary, is_fallback
- Bouton "Ajouter" → POST. Si erreur 400 → afficher l'erreur de validation.

`BalanceBadge.tsx` :
- Affichage `${balance.toFixed(2)} restants` avec couleur (vert > 50%, orange < 50%, rouge < 10% du cap mensuel ou 20$ si pas de cap)

Commit : `feat(frontend): my-stack/transcription-services (CRUD clés SaaS + slider workers + quotas)`

---

## Phase J — Frontend onglet Mistral + Quotas

### J1 — Mistral config

`app/my-stack/mistral-config/page.tsx` :
- SWR par projet courant (besoin d'un sélecteur de projet ou route paramétrée. Pour MVP : message "Configurez la clé Mistral par projet, ouvrez un projet pour configurer").
- **Décision MVP simplification** : la spec dit que `mistral_secret_ref` est par-`role_project`. Mais l'onglet "Ma stack" est cross-project. Solution : afficher la liste des projets + leur statut Mistral, bouton "Configurer" → ouvre `<ConfigForm>` pré-rempli.

`ConfigForm.tsx` :
- Input "Identifiant du secret Mistral dans ag.flow" (ex: `mistral-prod-key`)
- Bouton "Vérifier" (call GET endpoint)
- `<StatusIndicator status={config.status} />`
- Bouton "Sauvegarder" (PUT)
- Lien externe vers ag.flow admin (config dans settings frontend ou hardcodé)

### J2 — Quotas

`app/my-stack/quotas/page.tsx` :
- Liste des clés transcription (réutilise SWR `transcription-keys`)
- Pour chaque clé : `<QuotaForm>` (cap mensuel + bouton save) + jauge progression `current_spend / cap`
- Pas d'alertes email MVP (juste affichage UI)

`QuotaForm.tsx` :
- Input number "Cap mensuel (USD)" + bouton save → PATCH /quota
- Jauge visuelle : barre de progression colorée selon %, vert < 50, orange 50-95, rouge > 95

Commit : `feat(frontend): my-stack/mistral-config + quotas (config secret_ref + caps mensuels)`

---

## Phase K — Verification + tag

### K1 — MAJ `12-open-decisions.md` (Sprint 6)

Acter :
- Email reporté Phase 2 (notif WS uniquement MVP)
- Validation cookies = parse format Netscape (pas appel scraper)
- `check_mistral_secret_exists` = noop MVP
- APScheduler nouvelle dépendance Python
- Mistral config par projet (pas global) — UX simplifiée en liste de projets
- Slider workers 1-5 défaut 1
- StatusIndicator partagé (🔴🟠🟢)

Reportés Phase 2 :
- Email service (SMTP/SendGrid)
- Test cookies via container scraper
- Vérification ag.flow `/api/admin/secrets`
- Alertes email à 50/80/95%
- Détection auto-quota dépassé

Commit : `docs(specs): décisions Sprint 6 actées`

### K2 — Tag

```bash
cd backend && uv run pytest -v
cd backend && uv run ruff check src/ tests/
cd frontend && npm test && npm run typecheck && npm run lint

git tag -a v0.6.0-sprint-6 -m "Sprint 6 — Ma stack terminée

Onglet Ma stack avec 4 sous-onglets :
- Comptes réseaux sociaux (cookies CRUD + validation Netscape)
- Services de transcription (clés SaaS CRUD, slider workers 1-5,
  primaire/fallback, validation API)
- Mistral pour la synthèse (référence secret_ref ag.flow par projet)
- Quotas et garde-fous (cap mensuel, jauge spend, balance Deepgram)

Backend : 6 helpers étendus, 2 validators, credit_monitor + scheduler
APScheduler (poll horaire balance Deepgram + reset mensuel + cleanup
quotidien). 4 nouveaux routers.

Frontend : composant StatusIndicator partagé (🔴🟠🟢), 4 sous-onglets,
clients API typés.

Décisions actées :
- Email reporté Phase 2 (UI/WS only MVP)
- Validation cookies = parse Netscape format
- check_mistral_secret_exists = noop MVP
- Mistral config par projet (UX liste projets)
"
```

---

## Récapitulatif estimé : ~22 commits

- A : 3 (credentials + transcription_keys + mistral_secret_ref)
- B : 2 (credentials_validator + transcription_validator)
- C : 1 (routes credentials)
- D : 1 (routes transcription_keys)
- E : 1 (credit_monitor + scheduler)
- F : 1 (routes mistral_config)
- G : 1 (frontend types + 3 clients)
- H : 1 (social-accounts)
- I : 1 (transcription-services)
- J : 1 (mistral-config + quotas)
- K : 2 (open-decisions + tag)

Tag final : `v0.6.0-sprint-6`.
