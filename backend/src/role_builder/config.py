"""Application configuration via environment variables."""

from __future__ import annotations

from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

# UUID stable du tenant unique en MVP mono-user. À retirer quand le multi-tenant
# sera réel (auth + extraction depuis le JWT).
TENANT_ID_DEFAULT = UUID("00000000-0000-0000-0000-000000000001")


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

    log_level: str = "INFO"

    # Sprint 2 — Scrapers
    youtube_cookies_b64: str = ""
    instagram_cookies_b64: str = ""
    tiktok_cookies_b64: str = ""
    max_concurrent_scrapers: int = 5
    scraper_image_tag: str = "latest"
    disable_orchestrator: bool = False
    disable_ws_relay: bool = False

    # Sprint 3 — Transcription (clés API SaaS, vides = fallback shared)
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    assemblyai_api_key: str = ""
    speechmatics_api_key: str = ""
    # Workers user (provisioning + auto-stop loop interne backend)
    worker_auto_stop_threshold_s: int = 300
    worker_auto_stop_period_s: int = 60
    worker_image_tag: str = "latest"
    ghcr_owner: str = ""
    disable_worker_manager: bool = False

    # V2 lot 4 — Dépôt docflow (transcribed → depositing → deposited).
    # deposit_backend=stub (défaut) : fichiers JSON locaux + refs factices,
    # tant que la convention docflow_target et l'identité machine ne sont
    # pas tranchées (cf. services/deposit/gateway.py).
    deposit_backend: str = "stub"
    stub_deposit_dir: str = "./stub-deposits"
    deposit_max_attempts: int = 3
    deposit_backoff_base_s: float = 1.0
    deposit_poll_interval_s: float = 2.0
    disable_deposit_worker: bool = False

    # Phase A — Auth Keycloak
    keycloak_issuer_url: str = ""
    keycloak_client_id: str = ""
    keycloak_audience: str = ""
    disable_auth: bool = False

    # Sprint 6 — Scheduler périodique (poll balance, reset mensuel)
    disable_scheduler: bool = False

    # Harpocrate vault — désactiver pour les tests qui ne fournissent pas de token
    disable_vault: bool = False

    # Clé Fernet (base64 url-safe, 32 octets) chiffrant les secrets stockés
    # en base : tokens de wallets Harpocrate + secrets storage='local'.
    # Générée par dev-deploy.sh ; vide = les routes wallets/secrets refusent
    # de fonctionner (RuntimeError explicite à la première utilisation).
    secret_encryption_key: str = ""

    # Façade MCP roles__* — session_manager.run() est mono-usage par instance
    # (cf. mcp.server.streamable_http_manager) : désactivé dans les tests, qui
    # recréent un TestClient(app) par test contre le même process (donc le
    # même singleton `mcp`), ce qui violerait ce mono-usage hors production
    # (un seul cycle de lifespan par process réel).
    disable_mcp_server: bool = False

    # Phase 2 — Migrations DB embarquées dans l'image, exécutées au startup.
    # disable_migrations=True dans les tests pour éviter le run au boot.
    disable_migrations: bool = False
    # Override explicite du dossier migrations (sinon /app/migrations en docker
    # ou ../migrations en dev local, cf. main._resolve_migrations_dir).
    migrations_dir: str | None = None

    # Phase 2 — Menu hamburger d'apps cross-modules.
    # Path du apps.json (bind mount /app/apps.json:ro en docker, ../apps.json
    # en dev local). Si le fichier manque ou JSON invalide, la route retourne
    # une liste vide et le menu reste caché.
    apps_file: str | None = None

    # Phase 2 — Mode admin local (auth sans OIDC).
    # Activé via local_admin_enabled=true ET local_admin_password non vide.
    # Le frontend appelle POST /api/auth/local-login (user/pwd) → reçoit un
    # JWT HS256 signé avec local_admin_secret. Toutes les routes API
    # acceptent ce JWT en plus des JWT Keycloak (RS256/JWKS).
    # Pour la prod : laisser disabled. Pour dev/test : enabled + définir
    # local_admin_password ET local_admin_secret (min 32 chars).
    local_admin_enabled: bool = False
    local_admin_user: str = "admin"
    local_admin_password: str = ""
    local_admin_secret: str = ""
    local_admin_email: str = ""
    # Durée de vie du JWT local en secondes (défaut 12h).
    local_admin_token_ttl_s: int = 43200


settings = Settings()  # type: ignore[call-arg]
