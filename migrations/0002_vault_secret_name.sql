-- Migration 0002 : renomme openbao_path → vault_secret_name dans user_transcription_keys.
-- Les clés de transcription sont désormais stockées dans Harpocrate avec un chemin
-- hiérarchique (users/{email_slug}/transcription/{provider}/{key_id}).

ALTER TABLE user_transcription_keys
    RENAME COLUMN openbao_path TO vault_secret_name;
