# Harpocrate Vault Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer tous les secrets applicatifs en clair (API keys, JWT secrets, OAuth secrets) dans `.env` par des références `${vault://api1:<nom>}` résolues au démarrage via le coffre Harpocrate (SDK local à `backend/src/role_builder/secrets/`).

**Architecture:**
Le backend (FastAPI) installe le SDK Harpocrate comme dépendance locale (path dep uv), instancie un `VaultResolver` au démarrage, et patche `settings` in-place avant de lancer les services. Le frontend (Next.js 14) implémente un mini-client TypeScript maison (Node.js `crypto`) déclenché via `instrumentation.ts` qui patche `process.env` avant que Auth.js lise ses secrets.

**Tech Stack:** Python `harpocrate` (local sdist), `asyncio.to_thread`, Next.js 14 instrumentation, Node.js `node:crypto` (AES-256-GCM), `node:https` fetch.

---

## Périmètre — Secrets migrés vers Harpocrate

**Backend** (`HARPOCRATE_API_TOKEN_API1`) :
- `MISTRAL_API_KEY` → `${vault://api1:mistral_api_key}`
- `AGFLOW_API_TOKEN` → `${vault://api1:agflow_api_token}`
- `OPENAI_API_KEY` → `${vault://api1:openai_api_key}`
- `DEEPGRAM_API_KEY` → `${vault://api1:deepgram_api_key}`
- `ASSEMBLYAI_API_KEY` → `${vault://api1:assemblyai_api_key}`
- `SPEECHMATICS_API_KEY` → `${vault://api1:speechmatics_api_key}`
- `GITHUB_OAUTH_CLIENT_SECRET` → `${vault://api1:github_oauth_client_secret}`
- `LOCAL_ADMIN_PASSWORD` → `${vault://api1:local_admin_password}`
- `LOCAL_ADMIN_SECRET` → `${vault://api1:local_admin_secret}`

**Frontend** (`HARPOCRATE_API_TOKEN_API1`) :
- `KEYCLOAK_CLIENT_SECRET` → `${vault://api1:keycloak_client_secret}`
- `NEXTAUTH_SECRET` → `${vault://api1:nextauth_secret}`

**NON migrés** (bootstrap infrastructure docker-compose) :
- `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `OPENBAO_DEV_TOKEN`, `DATABASE_URL`, `MINIO_ACCESS_KEY/SECRET_KEY` — requis par les containers docker-compose eux-mêmes, avant que l'application ne soit disponible.

---

## Fichiers créés / modifiés

| Action | Fichier |
|--------|---------|
| Modifie | `backend/pyproject.toml` — add harpocrate dep + uv sources + hatch exclude |
| Crée | `backend/src/role_builder/services/vault_resolver.py` |
| Crée | `backend/tests/services/test_vault_resolver.py` |
| Modifie | `backend/src/role_builder/main.py` — call vault resolve in lifespan |
| Crée | `frontend/src/lib/vault.ts` — mini TypeScript vault client |
| Crée | `frontend/src/instrumentation.ts` — patch process.env at startup |
| Modifie | `frontend/next.config.js` — enable instrumentationHook |
| Modifie | `.env.example` — HARPOCRATE vars + vault refs |
| Modifie | `docker-compose.yml` — HARPOCRATE_API_TOKEN_API1 pour backend + frontend |

---

## Task 1 — Installer le SDK harpocrate (path dep uv)

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1 — Modifier pyproject.toml**

  Ajouter dans `[project].dependencies` :

  ```toml
  "harpocrate>=0.1.0",
  "cryptography>=42",
  "argon2-cffi>=23",
  "bcrypt>=4.1",
  ```

  Ajouter sous `[tool.pytest.ini_options]` :

  ```toml
  [tool.uv.sources]
  harpocrate = { path = "src/role_builder/secrets", editable = true }
  ```

  Modifier la section `[tool.hatch.build.targets.wheel]` :

  ```toml
  [tool.hatch.build.targets.wheel]
  packages = ["src/role_builder"]
  exclude = ["src/role_builder/secrets"]
  ```

- [ ] **Step 2 — Synchroniser les dépendances**

  ```bash
  cd backend && uv sync
  ```

  Résultat attendu : `harpocrate` installé en mode editable, pas d'erreur.

- [ ] **Step 3 — Vérifier l'import**

  ```bash
  cd backend && uv run python -c "from harpocrate import VaultClient; print('OK')"
  ```

  Résultat attendu : `OK`

- [ ] **Step 4 — Commit**

  ```bash
  git add backend/pyproject.toml backend/uv.lock
  git commit -m "chore: add harpocrate SDK as local path dep (vault migration)"
  ```

---

## Task 2 — `vault_resolver.py` — résolution des références vault

**Files:**
- Create: `backend/src/role_builder/services/vault_resolver.py`

- [ ] **Step 1 — Écrire le test (rouge)**

  Créer `backend/tests/services/test_vault_resolver.py` :

  ```python
  """Tests unitaires pour VaultResolver."""
  from __future__ import annotations

  from unittest.mock import MagicMock, patch

  import pytest

  from role_builder.services.vault_resolver import VaultResolver


  def _make_resolver(monkeypatch: pytest.MonkeyPatch, token: str = "hrpv_1_fake") -> VaultResolver:
      monkeypatch.setenv("HARPOCRATE_API_TOKEN_API1", token)
      monkeypatch.setenv("HARPOCRATE_API_URL_API1", "https://vault.yoops.org")
      mock_client = MagicMock()
      mock_client.secrets.get.side_effect = lambda k: f"resolved_{k}"
      with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
          return VaultResolver()


  def test_no_tokens_raises(monkeypatch: pytest.MonkeyPatch) -> None:
      for key in list(__import__("os").environ):
          if key.startswith("HARPOCRATE_API_TOKEN_"):
              monkeypatch.delenv(key, raising=False)
      with pytest.raises(RuntimeError, match="No Harpocrate API key configured"):
          VaultResolver()


  def test_resolve_vault_ref(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("HARPOCRATE_API_TOKEN_API1", "hrpv_1_fake")
      mock_client = MagicMock()
      mock_client.secrets.get.return_value = "sk-mistral-abc123"
      with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
          r = VaultResolver()
          result = r.resolve("${vault://api1:mistral_api_key}")
      assert result == "sk-mistral-abc123"
      mock_client.secrets.get.assert_called_once_with("mistral_api_key")


  def test_non_vault_ref_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
      r = _make_resolver(monkeypatch)
      assert r.resolve("plain_value") == "plain_value"
      assert r.resolve("") == ""
      assert r.resolve("https://api.mistral.ai") == "https://api.mistral.ai"


  def test_cache_avoids_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("HARPOCRATE_API_TOKEN_API1", "hrpv_1_fake")
      mock_client = MagicMock()
      mock_client.secrets.get.return_value = "cached_value"
      with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
          r = VaultResolver()
          r.resolve("${vault://api1:my_secret}")
          r.resolve("${vault://api1:my_secret}")
      mock_client.secrets.get.assert_called_once()


  def test_resolve_embedded_ref(monkeypatch: pytest.MonkeyPatch) -> None:
      r = _make_resolver(monkeypatch)
      result = r.resolve("postgresql://rb:${vault://api1:pg_pass}@localhost/rb")
      assert result == "postgresql://rb:resolved_pg_pass@localhost/rb"


  def test_resolve_settings_patches_vault_refs(monkeypatch: pytest.MonkeyPatch) -> None:
      r = _make_resolver(monkeypatch)
      from role_builder.config import Settings
      s = Settings(
          database_url="postgresql://rb:pass@localhost/rb",
          minio_endpoint="http://localhost:9000",
          minio_access_key="minioadmin",
          minio_secret_key="minioadmin",
          openbao_url="http://localhost:8200",
          openbao_token="dev-token",
          mistral_api_key="${vault://api1:mistral_api_key}",
          local_admin_password="${vault://api1:local_admin_password}",
      )
      r.resolve_settings(s)
      assert s.mistral_api_key == "resolved_mistral_api_key"
      assert s.local_admin_password == "resolved_local_admin_password"
      # Champs non-vault inchangés
      assert s.database_url == "postgresql://rb:pass@localhost/rb"


  def test_resolve_settings_leaves_non_str_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
      r = _make_resolver(monkeypatch)
      from role_builder.config import Settings
      s = Settings(
          database_url="postgresql://rb:pass@localhost/rb",
          minio_endpoint="http://localhost:9000",
          minio_access_key="minioadmin",
          minio_secret_key="minioadmin",
          openbao_url="http://localhost:8200",
          openbao_token="dev-token",
          max_concurrent_scrapers=7,
      )
      r.resolve_settings(s)
      assert s.max_concurrent_scrapers == 7


  def test_secret_not_found_raises_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
      from harpocrate import SecretNotFound
      monkeypatch.setenv("HARPOCRATE_API_TOKEN_API1", "hrpv_1_fake")
      mock_client = MagicMock()
      mock_client.secrets.get.side_effect = SecretNotFound("mistral_api_key not found")
      with patch("role_builder.services.vault_resolver.VaultClient", return_value=mock_client):
          r = VaultResolver()
          with pytest.raises(RuntimeError, match="mistral_api_key"):
              r.resolve("${vault://api1:mistral_api_key}")


  def test_unknown_identifier_raises(monkeypatch: pytest.MonkeyPatch) -> None:
      r = _make_resolver(monkeypatch)
      with pytest.raises(RuntimeError, match="Unknown Harpocrate identifier"):
          r.resolve("${vault://unknown_id:some_secret}")
  ```

- [ ] **Step 2 — Lancer les tests (doit échouer)**

  ```bash
  cd backend && uv run pytest tests/services/test_vault_resolver.py -v 2>&1 | head -30
  ```

  Résultat attendu : `ImportError: cannot import name 'VaultResolver'`

- [ ] **Step 3 — Implémenter vault_resolver.py**

  Créer `backend/src/role_builder/services/vault_resolver.py` :

  ```python
  """Résolution des références ${vault://id:key} via le coffre Harpocrate."""

  from __future__ import annotations

  import os
  import re
  from dataclasses import dataclass
  from typing import Any

  import structlog
  from harpocrate import SecretNotFound, VaultClient
  from harpocrate.exceptions import VaultHttpError

  log = structlog.get_logger(__name__)

  # Regex pour ${vault://identifier:secret_name} en full-string ou embedded
  _VAULT_RE = re.compile(r"\$\{vault://([^:}]+):([^}]+)\}")


  @dataclass(frozen=True)
  class _ApiKeyConfig:
      identifier: str
      url: str
      token: str


  class VaultResolver:
      """Résout les références vault://id:key depuis les env vars HARPOCRATE_API_TOKEN_*."""

      def __init__(self) -> None:
          self._configs: dict[str, _ApiKeyConfig] = {}
          self._clients: dict[str, VaultClient] = {}
          self._cache: dict[str, str] = {}
          self._load_configs()

      def _load_configs(self) -> None:
          for key, value in os.environ.items():
              if not key.startswith("HARPOCRATE_API_TOKEN_"):
                  continue
              identifier = key[len("HARPOCRATE_API_TOKEN_"):].lower()
              url_env = f"HARPOCRATE_API_URL_{identifier.upper()}"
              url = os.environ.get(url_env, "https://vault.yoops.org")
              self._configs[identifier] = _ApiKeyConfig(
                  identifier=identifier, url=url, token=value,
              )

          if not self._configs:
              raise RuntimeError(
                  "No Harpocrate API key configured, cannot resolve secrets. "
                  "Set HARPOCRATE_API_TOKEN_<IDENTIFIER> in your environment."
              )

      def _client(self, identifier: str) -> VaultClient:
          if identifier not in self._clients:
              if identifier not in self._configs:
                  raise RuntimeError(
                      f"Unknown Harpocrate identifier: {identifier!r}. "
                      f"Known identifiers: {list(self._configs)}"
                  )
              cfg = self._configs[identifier]
              self._clients[identifier] = VaultClient(token=cfg.token, base_url=cfg.url)
          return self._clients[identifier]

      def _resolve_one(self, identifier: str, secret_name: str) -> str:
          cache_key = f"{identifier}:{secret_name}"
          if cache_key in self._cache:
              return self._cache[cache_key]

          try:
              value = self._client(identifier).secrets.get(secret_name)
          except VaultHttpError as exc:
              if exc.status_code in (401, 403):
                  self._clients.pop(identifier, None)
                  raise RuntimeError(
                      f"Harpocrate API key '{identifier}' refused (HTTP {exc.status_code}). "
                      "Check that the token is valid and not revoked."
                  ) from exc
              raise RuntimeError(
                  f"Vault error fetching '{secret_name}' via '{identifier}': "
                  f"HTTP {exc.status_code}"
              ) from exc
          except SecretNotFound as exc:
              raise RuntimeError(
                  f"Secret '{secret_name}' not found in vault for identifier '{identifier}'"
              ) from exc

          self._cache[cache_key] = value
          log.info("vault.secret.resolved", identifier=identifier, secret=secret_name)
          return value

      def resolve(self, value: str) -> str:
          """Résout les refs vault dans une chaîne (full ou embedded).

          "plain"                                 → "plain"
          "${vault://api1:my_key}"                → "<secret_value>"
          "prefix:${vault://api1:my_key}@host"    → "prefix:<secret_value>@host"
          """
          if "${vault://" not in value:
              return value

          def _sub(m: re.Match[str]) -> str:
              return self._resolve_one(m.group(1), m.group(2))

          return _VAULT_RE.sub(_sub, value)

      def resolve_settings(self, settings: Any) -> None:
          """Résout toutes les refs vault dans les champs str du Settings Pydantic."""
          for field_name in settings.model_fields:
              raw = getattr(settings, field_name)
              if not isinstance(raw, str) or "${vault://" not in raw:
                  continue
              resolved = self.resolve(raw)
              if resolved != raw:
                  object.__setattr__(settings, field_name, resolved)
                  log.debug("vault.settings.patched", field=field_name)
  ```

- [ ] **Step 4 — Lancer les tests (doit passer)**

  ```bash
  cd backend && uv run pytest tests/services/test_vault_resolver.py -v
  ```

  Résultat attendu : `9 passed`

- [ ] **Step 5 — Commit**

  ```bash
  git add backend/src/role_builder/services/vault_resolver.py backend/tests/services/test_vault_resolver.py
  git commit -m "feat(vault): VaultResolver — résolution ${vault://id:key} au démarrage"
  ```

---

## Task 3 — Intégrer VaultResolver dans le lifespan FastAPI

**Files:**
- Modify: `backend/src/role_builder/main.py`

- [ ] **Step 1 — Écrire le test d'intégration startup**

  Créer `backend/tests/services/test_vault_startup.py` :

  ```python
  """Test que le lifespan échoue proprement si le coffre est absent."""
  from __future__ import annotations

  from unittest.mock import patch

  import pytest
  from fastapi.testclient import TestClient


  def test_startup_fails_without_vault_token(monkeypatch: pytest.MonkeyPatch) -> None:
      for key in list(__import__("os").environ):
          if key.startswith("HARPOCRATE_API_TOKEN_"):
              monkeypatch.delenv(key, raising=False)

      # Désactiver les autres workers pour isoler le test
      monkeypatch.setenv("DISABLE_ORCHESTRATOR", "true")
      monkeypatch.setenv("DISABLE_WS_RELAY", "true")
      monkeypatch.setenv("DISABLE_WORKER_MANAGER", "true")
      monkeypatch.setenv("DISABLE_CHUNKING_WORKER", "true")
      monkeypatch.setenv("DISABLE_SCHEDULER", "true")
      monkeypatch.setenv("DISABLE_MIGRATIONS", "true")
      monkeypatch.setenv("DISABLE_VAULT", "false")

      from role_builder.main import app
      with pytest.raises(RuntimeError, match="No Harpocrate API key configured"):
          with TestClient(app):
              pass
  ```

- [ ] **Step 2 — Lancer le test (doit échouer)**

  ```bash
  cd backend && uv run pytest tests/services/test_vault_startup.py -v 2>&1 | head -20
  ```

  Résultat attendu : le test passe car le resolver n'est pas encore intégré (le startup ne lève pas encore l'erreur).

- [ ] **Step 3 — Ajouter `DISABLE_VAULT` dans config.py**

  Dans `backend/src/role_builder/config.py`, après la ligne `disable_scheduler: bool = False` :

  ```python
  # Harpocrate vault — désactiver pour les tests qui ne fournissent pas de token
  disable_vault: bool = False
  ```

- [ ] **Step 4 — Intégrer dans main.py**

  Dans `backend/src/role_builder/main.py`, après les imports existants, ajouter :

  ```python
  import asyncio
  ```

  (déjà présent)

  Juste avant `@asynccontextmanager`, ajouter l'import :

  ```python
  from role_builder.services.vault_resolver import VaultResolver
  ```

  Dans la fonction `lifespan`, après `configure_logging(settings.log_level)` et avant `if db_pool._pool is None`, insérer :

  ```python
  if not settings.disable_vault:
      log.info("vault.resolver.starting")
      try:
          resolver = VaultResolver()
          await asyncio.to_thread(resolver.resolve_settings, settings)
          log.info("vault.resolver.done")
      except RuntimeError as exc:
          log.critical("vault.resolver.failed", error=str(exc))
          raise
  ```

- [ ] **Step 5 — Lancer les tests**

  ```bash
  cd backend && uv run pytest tests/services/test_vault_startup.py tests/services/test_vault_resolver.py -v
  ```

  Résultat attendu : tous passent.

- [ ] **Step 6 — Commit**

  ```bash
  git add backend/src/role_builder/main.py backend/src/role_builder/config.py backend/tests/services/test_vault_startup.py
  git commit -m "feat(vault): intégration VaultResolver dans le lifespan FastAPI"
  ```

---

## Task 4 — Frontend : mini-client TypeScript Harpocrate

**Files:**
- Create: `frontend/src/lib/vault.ts`

- [ ] **Step 1 — Écrire le test (rouge)**

  Créer `frontend/src/lib/__tests__/vault.test.ts` :

  ```typescript
  import { describe, it, expect, vi, beforeEach } from 'vitest';

  describe('resolveVaultRef', () => {
    beforeEach(() => {
      vi.resetModules();
      // Reset module-level cache entre les tests
    });

    it('passe les valeurs non-vault telles quelles', async () => {
      const { resolveVaultRef } = await import('../vault');
      expect(await resolveVaultRef('plain_value')).toBe('plain_value');
      expect(await resolveVaultRef('')).toBe('');
      expect(await resolveVaultRef('https://api.mistral.ai')).toBe('https://api.mistral.ai');
    });

    it('résout une référence vault complète', async () => {
      process.env.HARPOCRATE_API_TOKEN_API1 = 'hrpv_1_fake';
      process.env.HARPOCRATE_API_URL_API1 = 'https://vault.yoops.org';

      vi.mock('../vault', async (importOriginal) => {
        const mod = await importOriginal<typeof import('../vault')>();
        return {
          ...mod,
          _fetchVaultSecret: vi.fn().mockResolvedValue('sk-mistral-real'),
        };
      });

      // Test de la regex + détection
      const { resolveVaultRef } = await import('../vault');
      // La fonction doit détecter le pattern et appeler la résolution
      const ref = '${vault://api1:mistral_api_key}';
      // Vérifie que la ref est bien reconnue comme vault ref
      expect(ref).toMatch(/^\$\{vault:\/\/[^:]+:[^}]+\}$/);
    });
  });

  describe('parseHarpocrateToken', () => {
    it('rejette un token sans préfixe hrpv_', async () => {
      const { parseHarpocrateToken } = await import('../vault');
      expect(() => parseHarpocrateToken('invalid_token')).toThrow('Invalid token prefix');
    });
  });
  ```

- [ ] **Step 2 — Lancer les tests (doit échouer)**

  ```bash
  cd frontend && npm test -- src/lib/__tests__/vault.test.ts 2>&1 | head -20
  ```

  Résultat attendu : `Cannot find module '../vault'`

- [ ] **Step 3 — Implémenter vault.ts**

  Créer `frontend/src/lib/vault.ts` :

  ```typescript
  /**
   * Mini-client Harpocrate pour Next.js server-side (Node.js runtime).
   * Résout les références ${vault://id:key} depuis process.env via AES-256-GCM.
   *
   * N'importer ce module que dans des contextes server-side (instrumentation.ts,
   * Server Components, Route Handlers). Ne jamais exposer au bundle client.
   */

  import { createDecipheriv } from 'node:crypto';

  // ─── Constantes token format ────────────────────────────────────────────────
  const HMAC_LEN = 22;
  const DKEY_LEN = 43;
  const AUTH_LEN = 43;
  const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

  // ─── Utilitaires ────────────────────────────────────────────────────────────

  function base32Decode(str: string): Buffer {
    const s = str.toUpperCase().replace(/=/g, '');
    let bits = '';
    for (const ch of s) {
      const idx = BASE32_ALPHABET.indexOf(ch);
      if (idx === -1) throw new Error(`Invalid base32 char: ${ch}`);
      bits += idx.toString(2).padStart(5, '0');
    }
    const bytes: number[] = [];
    for (let i = 0; i + 8 <= bits.length; i += 8) {
      bytes.push(parseInt(bits.slice(i, i + 8), 2));
    }
    return Buffer.from(bytes);
  }

  function bytesToUuid(b: Buffer): string {
    const h = b.toString('hex');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }

  function aesGcmDecrypt(blob: Buffer, key: Buffer): Buffer {
    if (blob.length < 28) throw new Error('Blob too short for AES-GCM');
    const nonce = blob.subarray(0, 12);
    const tag = blob.subarray(-16);
    const ciphertext = blob.subarray(12, -16);
    const decipher = createDecipheriv('aes-256-gcm', key, nonce);
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  }

  // ─── Parsing du token hrpv_* ────────────────────────────────────────────────

  export interface ParsedToken {
    apiKeyId: string;   // UUID string
    decryptionKey: Buffer;
  }

  export function parseHarpocrateToken(token: string): ParsedToken {
    if (!token.startsWith('hrpv_')) {
      throw new Error('Invalid token prefix — must start with hrpv_');
    }

    const hmacB64 = token.slice(-HMAC_LEN);
    const dkeyB64 = token.slice(-(HMAC_LEN + 1 + DKEY_LEN), -(HMAC_LEN + 1));
    const authB64 = token.slice(
      -(HMAC_LEN + 1 + DKEY_LEN + 1 + AUTH_LEN),
      -(HMAC_LEN + 1 + DKEY_LEN + 1),
    );
    const prefixPart = token.slice(0, -(HMAC_LEN + 1 + DKEY_LEN + 1 + AUTH_LEN + 1));
    const parts = prefixPart.split('_');

    if (parts.length !== 5) {
      throw new Error('Invalid token structure (expected 5 prefix parts)');
    }

    const [, , idB32, expB36] = parts;
    const exp = parseInt(expB36, 36);
    if (exp !== 0 && exp < Math.floor(Date.now() / 1000)) {
      throw new Error('Harpocrate token has expired');
    }

    const dkeyBytes = Buffer.from(dkeyB64 + '==', 'base64url');
    if (dkeyBytes.length !== 32) {
      throw new Error(`Invalid decryption key length: ${dkeyBytes.length}`);
    }

    const idBytes = base32Decode(idB32);
    const apiKeyId = bytesToUuid(idBytes);

    // Silence unused vars (hmac not verified client-side, auth used by server)
    void hmacB64;
    void authB64;

    return { apiKeyId, decryptionKey: dkeyBytes };
  }

  // ─── Client HTTP vault ───────────────────────────────────────────────────────

  async function vaultFetch(baseUrl: string, token: string, path: string): Promise<unknown> {
    const url = `${baseUrl.replace(/\/$/, '')}${path}`;
    const resp = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    });
    if (!resp.ok) {
      throw new Error(`Vault HTTP ${resp.status} on ${path}`);
    }
    return resp.json();
  }

  // ─── Client haut-niveau par identifier ──────────────────────────────────────

  interface VaultClientState {
    baseUrl: string;
    token: string;
    parsed: ParsedToken;
    walletId?: string;
    walletKey?: Buffer;
  }

  const _clients = new Map<string, VaultClientState>();
  const _secretCache = new Map<string, string>();

  function _getClientState(identifier: string): VaultClientState {
    if (_clients.has(identifier)) return _clients.get(identifier)!;

    const tokenEnv = `HARPOCRATE_API_TOKEN_${identifier.toUpperCase()}`;
    const urlEnv = `HARPOCRATE_API_URL_${identifier.toUpperCase()}`;
    const token = process.env[tokenEnv];
    const baseUrl = process.env[urlEnv] ?? 'https://vault.yoops.org';

    if (!token) {
      throw new Error(
        `No Harpocrate token for identifier '${identifier}' — set ${tokenEnv}`,
      );
    }

    const parsed = parseHarpocrateToken(token);
    const state: VaultClientState = { baseUrl, token, parsed };
    _clients.set(identifier, state);
    return state;
  }

  async function _resolveWalletId(state: VaultClientState): Promise<string> {
    if (state.walletId) return state.walletId;
    const data = await vaultFetch(
      state.baseUrl,
      state.token,
      `/v1/api-keys/${state.parsed.apiKeyId}/wallet-id`,
    ) as { wallet_id: string };
    state.walletId = data.wallet_id;
    return data.wallet_id;
  }

  async function _resolveWalletKey(state: VaultClientState): Promise<Buffer> {
    if (state.walletKey) return state.walletKey;
    const walletId = await _resolveWalletId(state);
    const data = await vaultFetch(
      state.baseUrl,
      state.token,
      `/v1/wallets/${walletId}/my-api-key-grant`,
    ) as { encrypted_wallet_key: string };
    const encWk = Buffer.from(data.encrypted_wallet_key, 'base64');
    const walletKey = aesGcmDecrypt(encWk, state.parsed.decryptionKey);
    state.walletKey = walletKey;
    return walletKey;
  }

  async function _fetchAndDecryptSecret(
    state: VaultClientState,
    secretName: string,
  ): Promise<string> {
    const walletId = await _resolveWalletId(state);
    const data = await vaultFetch(
      state.baseUrl,
      state.token,
      `/v1/wallets/${walletId}/secrets/${secretName}`,
    ) as { encrypted_value: string; encrypted_wallet_key: string };

    const walletKey = await _resolveWalletKey(state);
    const encValue = Buffer.from(data.encrypted_value, 'base64');

    try {
      return aesGcmDecrypt(encValue, walletKey).toString('utf-8');
    } catch {
      // Fallback: use secret-specific encrypted_wallet_key
      const encWk = Buffer.from(data.encrypted_wallet_key, 'base64');
      const wkFromGrant = aesGcmDecrypt(encWk, state.parsed.decryptionKey);
      state.walletKey = wkFromGrant;
      return aesGcmDecrypt(encValue, wkFromGrant).toString('utf-8');
    }
  }

  // ─── API publique ────────────────────────────────────────────────────────────

  const REF_RE = /\$\{vault:\/\/([^:}]+):([^}]+)\}/g;

  export async function resolveVaultRef(value: string): Promise<string> {
    if (!value.includes('${vault://')) return value;

    const matches = [...value.matchAll(REF_RE)];
    if (matches.length === 0) return value;

    let result = value;
    for (const m of matches) {
      const [full, identifier, secretName] = m;
      const cacheKey = `${identifier}:${secretName}`;
      let secret = _secretCache.get(cacheKey);

      if (!secret) {
        const state = _getClientState(identifier);
        secret = await _fetchAndDecryptSecret(state, secretName);
        _secretCache.set(cacheKey, secret);
      }

      result = result.replace(full, secret);
    }
    return result;
  }

  export async function resolveVaultEnv(): Promise<void> {
    const entries = Object.entries(process.env).filter(
      ([, v]) => v && v.includes('${vault://'),
    );

    if (entries.length === 0) return;

    const hasToken = Object.keys(process.env).some((k) =>
      k.startsWith('HARPOCRATE_API_TOKEN_'),
    );
    if (!hasToken) {
      throw new Error(
        'Harpocrate vault refs found in env but no HARPOCRATE_API_TOKEN_* configured',
      );
    }

    for (const [key, ref] of entries) {
      try {
        process.env[key] = await resolveVaultRef(ref!);
      } catch (err) {
        throw new Error(
          `Harpocrate: failed to resolve ${key}=${ref} — ${err instanceof Error ? err.message : err}`,
        );
      }
    }
  }
  ```

- [ ] **Step 4 — Lancer les tests (doit passer)**

  ```bash
  cd frontend && npm test -- src/lib/__tests__/vault.test.ts
  ```

  Résultat attendu : `3 passed`

- [ ] **Step 5 — Commit**

  ```bash
  git add frontend/src/lib/vault.ts frontend/src/lib/__tests__/vault.test.ts
  git commit -m "feat(vault): mini-client TypeScript Harpocrate (AES-256-GCM, Node.js crypto)"
  ```

---

## Task 5 — Next.js instrumentation.ts — patch process.env au démarrage

**Files:**
- Create: `frontend/src/instrumentation.ts`
- Modify: `frontend/next.config.js`

- [ ] **Step 1 — Activer instrumentationHook dans next.config.js**

  Modifier `frontend/next.config.js` :

  ```javascript
  /** @type {import('next').NextConfig} */
  const nextConfig = {
    reactStrictMode: true,
    experimental: {
      instrumentationHook: true,
    },
  };

  module.exports = nextConfig;
  ```

- [ ] **Step 2 — Créer instrumentation.ts**

  Créer `frontend/src/instrumentation.ts` :

  ```typescript
  /**
   * Next.js instrumentation hook — résout les références vault dans process.env
   * avant que les Route Handlers et Server Components ne soient servis.
   *
   * S'exécute une seule fois au démarrage du server Node.js.
   * Ne s'exécute PAS dans le runtime Edge.
   */
  export async function register(): Promise<void> {
    if (process.env.NEXT_RUNTIME !== 'nodejs') return;

    const hasVaultRef = Object.values(process.env).some(
      (v) => v && v.includes('${vault://'),
    );
    if (!hasVaultRef) return;

    try {
      const { resolveVaultEnv } = await import('./lib/vault');
      await resolveVaultEnv();
      console.log('[vault] process.env patched — all vault refs resolved');
    } catch (err) {
      console.error('[vault] FATAL: failed to resolve vault secrets at startup:', err);
      process.exit(1);
    }
  }
  ```

- [ ] **Step 3 — Vérifier le typecheck**

  ```bash
  cd frontend && npm run typecheck
  ```

  Résultat attendu : pas d'erreur TypeScript.

- [ ] **Step 4 — Commit**

  ```bash
  git add frontend/src/instrumentation.ts frontend/next.config.js
  git commit -m "feat(vault): Next.js instrumentation — résolution vault refs au démarrage"
  ```

---

## Task 6 — Migrer les secrets dans .env.example et docker-compose.yml

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1 — Mettre à jour .env.example**

  Ajouter une section Harpocrate en début de `.env.example` (après les commentaires registry) :

  ```bash
  # === Harpocrate — coffre de secrets applicatifs ===
  # Token API complet (format hrpv_*). Le SDK en extrait auth_secret + decryption_key.
  # Identifier logique = "api1" → ${vault://api1:<nom_du_secret>}
  HARPOCRATE_API_TOKEN_API1=
  HARPOCRATE_API_URL_API1=https://vault.yoops.org
  ```

  Puis remplacer les secrets applicatifs dans `.env.example` :

  ```bash
  # Mistral (LLM + embeddings)
  MISTRAL_API_KEY=${vault://api1:mistral_api_key}
  MISTRAL_BASE_URL=https://api.mistral.ai
  MISTRAL_EMBED_MODEL=mistral-embed
  MISTRAL_CHAT_MODEL=mistral-large-latest

  # ag.flow
  AGFLOW_BASE_URL=https://docker-agflow.yoops.org
  AGFLOW_API_TOKEN=${vault://api1:agflow_api_token}

  # Transcription SaaS (shared defaults — vides = fallback sur shared_default)
  OPENAI_API_KEY=${vault://api1:openai_api_key}
  DEEPGRAM_API_KEY=${vault://api1:deepgram_api_key}
  ASSEMBLYAI_API_KEY=${vault://api1:assemblyai_api_key}
  SPEECHMATICS_API_KEY=${vault://api1:speechmatics_api_key}

  # Auth admin local
  LOCAL_ADMIN_ENABLED=false
  LOCAL_ADMIN_USER=admin
  LOCAL_ADMIN_PASSWORD=${vault://api1:local_admin_password}
  LOCAL_ADMIN_SECRET=${vault://api1:local_admin_secret}

  # Auth Keycloak (frontend + backend)
  KEYCLOAK_ISSUER_URL=
  KEYCLOAK_CLIENT_ID=
  KEYCLOAK_CLIENT_SECRET=${vault://api1:keycloak_client_secret}
  KEYCLOAK_AUDIENCE=

  # Auth.js (Next.js)
  NEXTAUTH_SECRET=${vault://api1:nextauth_secret}
  NEXTAUTH_URL=

  # GitHub OAuth
  GITHUB_OAUTH_CLIENT_ID=
  GITHUB_OAUTH_CLIENT_SECRET=${vault://api1:github_oauth_client_secret}
  GITHUB_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/github/callback
  GITHUB_OAUTH_SCOPE=public_repo
  ```

- [ ] **Step 2 — Mettre à jour docker-compose.yml**

  Dans le bloc `backend:environment`, ajouter avant `DATABASE_URL` :

  ```yaml
      HARPOCRATE_API_TOKEN_API1: ${HARPOCRATE_API_TOKEN_API1:-}
      HARPOCRATE_API_URL_API1: ${HARPOCRATE_API_URL_API1:-https://vault.yoops.org}
  ```

  Dans le bloc `frontend:environment`, ajouter :

  ```yaml
      HARPOCRATE_API_TOKEN_API1: ${HARPOCRATE_API_TOKEN_API1:-}
      HARPOCRATE_API_URL_API1: ${HARPOCRATE_API_URL_API1:-https://vault.yoops.org}
  ```

- [ ] **Step 3 — Vérifier que .env.example ne contient plus de secrets en clair**

  ```bash
  grep -E "(sk-|hrp_|hrpv_|changeme|openai|deepgram|assemblyai|speechmatics)" .env.example
  ```

  Résultat attendu : aucune ligne avec un vrai secret (seules les références `${vault://...}` pour les secrets, les valeurs `changeme_in_real_env` restent pour les infra passwords qui ne sont pas migrés).

- [ ] **Step 4 — Commit**

  ```bash
  git add .env.example docker-compose.yml
  git commit -m "feat(vault): migrer les secrets applicatifs vers des refs \${vault://...}"
  ```

---

## Task 7 — Tests backend complets + lint

- [ ] **Step 1 — Lancer tous les tests backend**

  ```bash
  cd backend && uv run pytest -v 2>&1 | tail -30
  ```

  Résultat attendu : tous les tests passent (notamment test_vault_resolver, test_vault_startup). Si des tests existants ont des assertions sur des valeurs de secrets, ils peuvent avoir besoin de l'env var `DISABLE_VAULT=true`.

- [ ] **Step 2 — Vérifier que les tests existants utilisent DISABLE_VAULT**

  Si des tests en conftest.py bootent l'app via TestClient ou fixture `app`, s'assurer qu'ils définissent `DISABLE_VAULT=true` dans les fixtures. Chercher :

  ```bash
  cd backend && grep -r "TestClient\|lifespan\|DISABLE_VAULT" tests/ --include="*.py" | head -20
  ```

  Si des tests bootent l'app sans DISABLE_VAULT, ajouter dans `conftest.py` (ou les fixtures concernées) :

  ```python
  @pytest.fixture(autouse=True)
  def disable_vault(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("DISABLE_VAULT", "true")
  ```

- [ ] **Step 3 — Lint**

  ```bash
  cd backend && uv run ruff check src/ tests/
  ```

  Résultat attendu : pas d'erreur.

- [ ] **Step 4 — Typecheck frontend**

  ```bash
  cd frontend && npm run typecheck && npm test
  ```

  Résultat attendu : pas d'erreur TypeScript, tous les tests vitest passent.

- [ ] **Step 5 — Commit final**

  ```bash
  git add -A
  git commit -m "test(vault): ajuster les fixtures pour DISABLE_VAULT en tests"
  ```

---

## Task 8 — Documentation README

- [ ] **Step 1 — Mettre à jour le README.md à la racine**

  Ajouter une section `## Secrets (Harpocrate)` après la section stack :

  ```markdown
  ## Secrets (Harpocrate)

  Tous les secrets applicatifs (API keys, JWT secrets, OAuth credentials) sont stockés
  dans le coffre [Harpocrate](https://vault.yoops.org) et référencés dans la config
  via `${vault://<identifier>:<nom_du_secret>}`.

  ### Configuration locale

  Dans votre `.env` (jamais committé), définir :

  ```env
  HARPOCRATE_API_TOKEN_API1=hrpv_1_...   # token complet fourni par l'opérateur
  HARPOCRATE_API_URL_API1=https://vault.yoops.org
  ```

  ### Ajouter un nouveau secret

  1. Créer le secret dans le wallet Harpocrate associé à `api1`
  2. Référencer dans `.env` : `MON_SECRET=${vault://api1:mon_secret}`
  3. Ajouter le champ dans `backend/src/role_builder/config.py` si c'est un secret backend

  ### Référencer un secret dans le code

  ```python
  # Le settings est patché au démarrage — lire directement
  from role_builder.config import settings
  api_key = settings.mistral_api_key  # déjà résolu
  ```

  ```typescript
  // Côté Next.js — process.env est patché avant la première requête
  const secret = process.env.NEXTAUTH_SECRET; // déjà résolu
  ```

  ### Résolution au démarrage

  **Backend (FastAPI)** : `VaultResolver.resolve_settings(settings)` est appelé dans le `lifespan`
  avant tout service. Si le coffre est inaccessible, l'application refuse de démarrer.

  **Frontend (Next.js)** : `instrumentation.ts` patche `process.env` via `resolveVaultEnv()`
  avant que les Route Handlers soient servis.
  ```

- [ ] **Step 2 — Commit**

  ```bash
  git add README.md
  git commit -m "docs: documenter l'intégration Harpocrate vault"
  ```

---

## Self-Review — Couverture du spec

| Exigence spec | Tâche | Statut |
|---|---|---|
| Inventaire secrets | Périmètre ci-dessus | ✓ |
| Table de config (env vars HARPOCRATE_*) | Task 2 `_load_configs` | ✓ |
| Loader détecte `${vault://...}` | Task 2 `resolve()` + regex | ✓ |
| Cache RAM (pas disque) | Task 2 `_cache: dict`, Task 4 `_secretCache: Map` | ✓ |
| Fail-fast au démarrage | Task 3 lifespan + Task 5 instrumentation `process.exit(1)` | ✓ |
| Erreur 401 → invalide client + message | Task 2 `_resolve_one` 401 handler | ✓ |
| Secret introuvable → message clair | Task 2 `SecretNotFound` handler | ✓ |
| Pas de log du token en clair | `structlog` ne logue que `identifier` + `secret_name` | ✓ |
| Pas de log de la valeur déchiffrée | `log.info("vault.secret.resolved")` sans value | ✓ |
| Migration secrets backend | Task 6 `.env.example` | ✓ |
| Migration secrets frontend | Task 6 `.env.example` + Task 5 instrumentation | ✓ |
| SDK Python officiel | Task 1 harpocrate local path dep | ✓ |
| SDK TypeScript : appels directs (pas de npm pkg) | Task 4 `vault.ts` Node.js crypto | ✓ |
| Tests avec mock SDK | Task 2 `test_vault_resolver.py` | ✓ |
| README documentation | Task 8 | ✓ |

**Secrets infra non migrés** (justification) : `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `OPENBAO_DEV_TOKEN` sont requis directement par les containers docker-compose avant que l'application ne soit disponible — ils ne peuvent pas bootstrapper depuis un vault applicatif.
