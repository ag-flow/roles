-- Migration 0012 : table temporaire pour le state CSRF du flow OAuth GitHub.
-- Sprint 8.
--
-- Le state est généré au démarrage du flow (POST /auth/github/start), inséré
-- ici avec un expires_at (~10 min), puis consommé atomiquement (DELETE
-- ... RETURNING) au callback GitHub. Cleanup auto des entrées expirées via
-- helper `oauth_states.cleanup_expired` (pas de pg_cron — appelé à la
-- demande ou par un job de maintenance).

CREATE TABLE oauth_states (
    state text PRIMARY KEY,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    provider text NOT NULL DEFAULT 'github',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX oauth_states_expires_idx ON oauth_states (expires_at);
