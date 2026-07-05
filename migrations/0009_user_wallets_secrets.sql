-- Migration 0009 : wallets Harpocrate self-service + secrets utilisateur.
-- Chantier « clés Harpocrate self-service » (cadré 2026-07-05).
--
-- Nouveau modèle : plus de token Harpocrate global au boot. L'utilisateur
-- enregistre ses propres wallets (token hrpv_* chiffré en base via
-- SECRET_ENCRYPTION_KEY), puis saisit ses secrets typés avec un choix de
-- destination :
--   - storage='local'  : valeur chiffrée (Fernet) dans value_encrypted ;
--   - storage='wallet' : valeur écrite dans le wallet Harpocrate choisi,
--     seul le chemin (wallet_path) est persisté en base.
-- Les définitions de service (user_transcription_keys, user_credentials)
-- ne portent plus le secret : elles référencent un user_secrets via
-- secret_id.
--
-- Cette migration est purement additive. La bascule des routes (suppression
-- de vault_secret_name, invalidation des lignes legacy pointant vers le
-- wallet global désormais inaccessible) arrive dans la migration suivante,
-- une fois les nouvelles routes en place.

CREATE TABLE user_wallets (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    user_id             uuid NOT NULL,
    label               text NOT NULL,
    -- Token hrpv_* chiffré (Fernet, clé SECRET_ENCRYPTION_KEY de l'instance).
    api_token_encrypted bytea NOT NULL,
    api_url             text NOT NULL DEFAULT 'https://vault.yoops.org',
    status              text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'invalid')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Le tri chronologique sert la présélection UI (« premier wallet »).
CREATE INDEX user_wallets_user_idx ON user_wallets (user_id, created_at);

CREATE TABLE user_secrets (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    user_id         uuid NOT NULL,
    secret_type     text NOT NULL CHECK (secret_type IN (
                        'openai-whisper', 'deepgram', 'assemblyai',
                        'speechmatics', 'youtube-cookies',
                        'instagram-cookies', 'tiktok-cookies'
                    )),
    label           text NOT NULL,
    storage         text NOT NULL CHECK (storage IN ('local', 'wallet')),
    value_encrypted bytea,
    wallet_id       uuid REFERENCES user_wallets (id) ON DELETE RESTRICT,
    wallet_path     text,
    status          text NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'invalid')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    -- Exactement l'une des deux formes : locale (valeur chiffrée, pas de
    -- wallet) ou wallet (référence complète, pas de valeur en base).
    CONSTRAINT user_secrets_storage_shape CHECK (
        (storage = 'local'
         AND value_encrypted IS NOT NULL
         AND wallet_id IS NULL
         AND wallet_path IS NULL)
        OR
        (storage = 'wallet'
         AND value_encrypted IS NULL
         AND wallet_id IS NOT NULL
         AND wallet_path IS NOT NULL)
    )
);

CREATE INDEX user_secrets_user_type_idx
    ON user_secrets (user_id, secret_type, status);

-- Les définitions de service sélectionnent un secret existant. RESTRICT :
-- un secret encore référencé par un service ne peut pas être supprimé.
ALTER TABLE user_transcription_keys
    ADD COLUMN secret_id uuid REFERENCES user_secrets (id) ON DELETE RESTRICT;

ALTER TABLE user_credentials
    ADD COLUMN secret_id uuid REFERENCES user_secrets (id) ON DELETE RESTRICT;
