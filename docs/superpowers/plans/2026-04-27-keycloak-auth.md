# Auth Keycloak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Authentification OIDC (Authorization Code + PKCE) via Keycloak `security.yoops.org/realms/yoops`. Frontend Next.js gère le flow login/callback/session via Auth.js v5. Backend FastAPI valide les access tokens JWT (RS256, JWKS) en middleware.

**Tech Stack:**
- Backend : `python-jose[cryptography]` ou `pyjwt[crypto]` + `httpx` (JWKS fetch & cache). Choix retenu : **PyJWT** (lib stable, intégrée à FastAPI patterns).
- Frontend : **Auth.js v5** (`next-auth@beta`) avec provider Keycloak natif.
- Endpoints OIDC découverts : issuer `https://security.yoops.org/realms/yoops`, JWKS `/protocol/openid-connect/certs`, RS256.

**Décisions actées :**
- Client OIDC `agflow-roles` (créé par user, secret = `IbwdjArNbnsOJd4wCCby8qMnASJRd11m` côté `.env` LXC, jamais commit).
- Audience attendue : `agflow-roles` (= client_id, par défaut Keycloak).
- `tenant_id` = constante `TENANT_ID_DEFAULT` (Sprint 1) pour MVP. `user_id` = sub JWT (UUID Keycloak). Multi-tenant via claim mapper Phase 2.
- Pas de refresh token rotation côté backend — Auth.js gère le refresh côté frontend, le backend valide juste l'access token à chaque requête.
- Routes protégées : toutes sauf `/health/`. WebSocket `/ws` lit le token depuis query param `?token=...` (pas de header pour WS browser).
- Mode dev sans Keycloak : flag `DISABLE_AUTH=true` (env var) bypass le middleware. Utile pour les tests pytest existants qui ne devraient pas tomber.

---

# Phase A — Backend FastAPI (~7 commits)

### Files
- Create: `backend/src/role_builder/auth/__init__.py`
- Create: `backend/src/role_builder/auth/keycloak.py`
- Create: `backend/src/role_builder/auth/dependencies.py`
- Create: `backend/src/role_builder/routes/me.py`
- Modify: `backend/src/role_builder/config.py` (ajout settings Keycloak + `disable_auth`)
- Modify: `backend/src/role_builder/main.py` (include router /me)
- Modify: `backend/src/role_builder/routes/{sources,scraping_jobs,websocket}.py` (protection)
- Modify: `backend/pyproject.toml` (ajout `pyjwt[crypto]`)
- Modify: `backend/tests/conftest.py` (`disable_auth=True` dans fixture client)
- Create: `backend/tests/test_auth_keycloak.py` (TDD validation JWT)
- Create: `backend/tests/test_auth_dependencies.py` (TDD get_current_user)
- Create: `backend/tests/test_me_route.py` (TDD endpoint /me)

### A1 : Settings + dépendance pyjwt (1 commit, TDD léger)

Ajouter à `Settings` :
```python
keycloak_issuer_url: str = ""           # ex: https://security.yoops.org/realms/yoops
keycloak_client_id: str = ""             # ex: agflow-roles
keycloak_audience: str = ""              # par défaut = client_id, peut être surchargé
disable_auth: bool = False               # bypass total pour tests/dev
```

Etendre `pyproject.toml` :
```toml
"pyjwt[crypto]>=2.8",
```

`uv sync --extra dev`. Test extension de `test_config.py` pour valider les defaults.

Commit : `feat(backend): config Keycloak (issuer + client_id + audience + disable_auth)`

### A2 : `auth/keycloak.py` — JWKS cache + JWT validation (1 commit, TDD)

Module qui :
1. Fetch et cache le JWKS depuis `{issuer}/protocol/openid-connect/certs` (cache simple en mémoire, TTL 1h).
2. Valide un JWT : signature RS256 avec la clé publique du JWKS (selon `kid` du header), `iss` match, `aud` match, `exp` non expiré.
3. Retourne le payload décodé ou raise `InvalidTokenError`.

Signature publique :
```python
class KeycloakValidator:
    def __init__(self, issuer_url: str, audience: str, jwks_ttl_s: int = 3600): ...
    async def validate(self, token: str) -> dict[str, Any]: ...  # raises InvalidTokenError
    async def get_signing_key(self, kid: str) -> Any: ...  # internal, lazy fetch JWKS

class InvalidTokenError(Exception): ...
```

Tests TDD (5-7) :
- Génère une paire RSA en test, simule un JWKS mock, signe un token valide, valide → OK
- Token expiré → InvalidTokenError
- Mauvaise audience → InvalidTokenError
- Mauvais issuer → InvalidTokenError
- Signature avec mauvaise clé → InvalidTokenError
- `kid` inconnu (force re-fetch JWKS) → ok après refresh
- JWKS HTTP error → InvalidTokenError clair

Mocks : patcher `httpx.AsyncClient.get` pour servir le JWKS de test. Génération RSA via `cryptography.hazmat`.

Commit : `feat(backend): auth/keycloak (JWKS cache + RS256 validation)`

### A3 : `auth/dependencies.py` — FastAPI deps (1 commit, TDD)

```python
async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
) -> CurrentUser:
    """Valide le token Bearer et retourne le user. 401 si absent/invalide.
    Bypass si settings.disable_auth=True → returns _DEFAULT_USER stub."""

async def get_optional_user(...) -> CurrentUser | None:
    """Comme get_current_user mais retourne None au lieu de raise."""

@dataclass
class CurrentUser:
    user_id: UUID         # depuis sub
    username: str         # depuis preferred_username
    email: str | None
    tenant_id: UUID       # depuis claim custom ou TENANT_ID_DEFAULT
    raw_token: dict[str, Any]
```

Tests :
- Header absent → 401
- Header `Bearer <invalid>` → 401
- Header `Bearer <valid>` → CurrentUser correct
- `disable_auth=True` → CurrentUser stub avec TENANT_ID_DEFAULT

Commit : `feat(backend): auth/dependencies (get_current_user FastAPI dep + bypass tests)`

### A4 : `routes/me.py` (1 commit, TDD)

Endpoint `GET /api/me` qui retourne le `CurrentUser` du token courant. Utile pour le frontend (vérifier session, afficher le nom).

```python
@router.get("/me")
async def get_me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
    return {
        "user_id": str(user.user_id),
        "username": user.username,
        "email": user.email,
        "tenant_id": str(user.tenant_id),
    }
```

Test : 401 sans token, 200 avec token valide.

Commit : `feat(backend): route /api/me (retourne user courant)`

### A5 : Protection des routes existantes (1 commit)

Ajouter `Depends(get_current_user)` à chaque endpoint **sauf** :
- `/health/` (toujours public)
- `/ws` (WebSocket — auth via query param `?token=...` avec `get_optional_user` pour MVP, full Keycloak token validation Phase 2)

Routes à protéger : `routes/sources.py`, `routes/scraping_jobs.py`. Ajouter en signature : `user: Annotated[CurrentUser, Depends(get_current_user)]`.

Tests existants : la fixture `client` dans `conftest.py` doit set `disable_auth=True` pour que les tests routes existants ne tombent pas. Si on veut tester l'auth elle-même, une nouvelle fixture `authenticated_client` qui injecte un Bearer token mockable.

Commit : `feat(backend): protection routes sources + scraping_jobs (Depends get_current_user)`

### A6 : conftest.py + tests existants (1 commit)

Modifier `conftest.py` :
- Fixture `client` : ajoute `monkeypatch.setattr(_settings, "disable_auth", True)`
- Tous les tests existants continuent de passer (~80+ tests verts).

Commit : `chore(backend): conftest disable_auth=True pour fixture client (tests existants intacts)`

### A7 : main.py + include router (1 commit)

`main.py` : `app.include_router(me.router, prefix="/api", tags=["auth"])`.

Test : `cd backend && uv run pytest -v && uv run ruff check src/ tests/` → tout vert.

Commit : `feat(backend): câblage route /api/me dans FastAPI app`

---

# Phase B — Frontend Next.js (~6 commits)

### Files
- Modify: `frontend/package.json` (ajout `next-auth@beta`)
- Create: `frontend/src/auth.ts`
- Create: `frontend/src/app/api/auth/[...nextauth]/route.ts`
- Create: `frontend/src/middleware.ts` (protection routes)
- Create: `frontend/src/app/login/page.tsx`
- Modify: `frontend/src/app/page.tsx` (afficher session + bouton logout)
- Modify: `frontend/src/lib/api/client.ts` (injection Authorization Bearer)
- Modify: `frontend/.env.example` (variables NEXTAUTH_*, KEYCLOAK_*)
- Create: `frontend/src/__tests__/auth-helper.test.ts`

### B1 : npm install next-auth@beta + types (1 commit)

```bash
cd frontend && npm install next-auth@beta @auth/core
```

Sur Windows + IDE locks : si échec → renommer `node_modules`, retry. Pattern Sprint 1 Phase E.

Commit : `chore(frontend): ajout next-auth@beta (Auth.js v5)`

### B2 : auth.ts config Auth.js (1 commit)

```typescript
// frontend/src/auth.ts
import NextAuth from 'next-auth';
import Keycloak from 'next-auth/providers/keycloak';

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Keycloak({
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      issuer: process.env.KEYCLOAK_ISSUER_URL!,
    }),
  ],
  session: { strategy: 'jwt' },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.access_token) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string;
      return session;
    },
  },
  pages: {
    signIn: '/login',
  },
});
```

Plus déclaration de types augmentée pour `Session` étendue avec `accessToken`.

Commit : `feat(frontend): Auth.js v5 config (provider Keycloak + JWT session + accessToken propagation)`

### B3 : route handler /api/auth/[...nextauth] (1 commit)

```typescript
// frontend/src/app/api/auth/[...nextauth]/route.ts
export { GET, POST } from '@/auth';
```

Wait, en Auth.js v5, c'est :
```typescript
import { handlers } from '@/auth';
export const { GET, POST } = handlers;
```

Commit : `feat(frontend): handler routes Auth.js (/api/auth/[...nextauth])`

### B4 : middleware.ts protection routes (1 commit)

```typescript
// frontend/src/middleware.ts
import { auth } from '@/auth';

export default auth((req) => {
  if (!req.auth && !req.nextUrl.pathname.startsWith('/login')) {
    return Response.redirect(new URL('/login', req.url));
  }
});

export const config = {
  matcher: ['/((?!_next|api/auth|favicon.ico).*)'],
};
```

Commit : `feat(frontend): middleware Auth.js (redirige vers /login si pas de session)`

### B5 : page /login (1 commit)

```tsx
// frontend/src/app/login/page.tsx
import { signIn } from '@/auth';

export default function LoginPage() {
  return (
    <main style={{ padding: '2rem', maxWidth: 480, margin: '4rem auto' }}>
      <h1>Connexion à Role Builder</h1>
      <form action={async () => {
        'use server';
        await signIn('keycloak', { redirectTo: '/' });
      }}>
        <button type="submit" style={{ /* ... */ }}>
          Se connecter avec Keycloak
        </button>
      </form>
    </main>
  );
}
```

Commit : `feat(frontend): page /login avec bouton Keycloak`

### B6 : page accueil + lib/api/client.ts (1 commit)

`app/page.tsx` (modify) :
- Récupérer la session via `auth()`
- Afficher username + bouton "Déconnexion" qui appelle `signOut`
- Le fetchHealth utilise toujours BACKEND_INTERNAL_URL (pas besoin de Bearer pour /health/)

`lib/api/client.ts` (modify) :
- Helper `apiFetch` qui inject `Authorization: Bearer ${session.accessToken}` en mode SSR (depuis `auth()`) ou en client (depuis `useSession()`)
- Pour MVP : juste un wrapper côté client. Le SSR de la page accueil n'a pas besoin d'appels protégés.

Test : `frontend/src/__tests__/auth-helper.test.ts` mock fetch + vérifie injection header.

Commit : `feat(frontend): home page session + helper apiFetch injecte Bearer`

---

# Phase C — Configuration env + redéploiement (~2 commits + manuel)

### C1 : .env.example étendu (1 commit)

Ajouter à `.env.example` :
```env
# === Auth Keycloak ===
KEYCLOAK_ISSUER_URL=https://security.yoops.org/realms/yoops
KEYCLOAK_CLIENT_ID=agflow-roles
KEYCLOAK_CLIENT_SECRET=
KEYCLOAK_AUDIENCE=agflow-roles

# Auth.js (frontend)
NEXTAUTH_SECRET=                           # secret HMAC pour le JWT session, à générer (openssl rand -hex 32)
NEXTAUTH_URL=https://role-agflow.yoops.org # URL publique du site

# Bypass auth (MVP/dev only — DOIT être False en prod)
DISABLE_AUTH=false
```

Étendre aussi `docker-compose.yml` pour injecter ces vars dans backend ET frontend.

Commit : `feat(infra): config Keycloak dans .env.example + docker-compose (backend+frontend)`

### C2 : MAJ open-decisions.md (1 commit)

Acter dans `12-open-decisions.md` :
- Auth Keycloak Phase 2 implémentée (Authorization Code + PKCE via Auth.js + PyJWT backend)
- Reste : multi-tenant via claim mapper, refresh token rotation côté backend (pas implémenté MVP)

Commit : `docs(specs): décisions auth Keycloak actées (Phase 2 livrée)`

### C3 : Déploiement LXC 220 (action humaine + scripts)

1. `git push origin main` → déclenche CI build-app (backend + frontend nouvelles images)
2. Sur LXC 220 :
   - Editer `.env` : ajouter `KEYCLOAK_CLIENT_SECRET=IbwdjArNbnsOJd4wCCby8qMnASJRd11m`
   - Générer `NEXTAUTH_SECRET=$(openssl rand -hex 32)` et l'ajouter
   - `git pull` (récupérer le nouveau code dans le LXC) — ou re-tar transfer si pas push
   - `docker compose build backend frontend && docker compose up -d`
3. Test :
   - Ouvrir `https://role-agflow.yoops.org` → redirect vers `/login` → bouton Keycloak → redirect vers Keycloak login form → callback → page accueil avec session
   - Backend `/api/me` testé avec le token retourné

---

## Récapitulatif des commits

~15 commits cumulés (7 backend + 6 frontend + 2 infra/docs).

Tag final visé : `v0.4.0-keycloak-auth`.

## Garde-fous

- `KEYCLOAK_CLIENT_SECRET` jamais commit (présent dans `.gitignore` via `.env`)
- Tests existants (~127) doivent tous rester verts (fixture `disable_auth=True`)
- Multi-tenant non câblé : `tenant_id` = constante MVP. À reprendre quand on aura plus d'un user.
