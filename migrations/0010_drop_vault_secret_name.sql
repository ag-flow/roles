-- Migration 0010 : bascule des définitions de service sur user_secrets.
-- Chantier « clés Harpocrate self-service » — second temps, après la 0009
-- (additive) et la refonte des routes.
--
-- Les lignes legacy portent une référence vault (vault_secret_name) vers le
-- wallet Harpocrate global, dont le token d'instance disparaît avec ce
-- chantier : leurs secrets sont définitivement inaccessibles. Elles sont
-- marquées invalid (re-saisie nécessaire via /api/secrets) et la colonne
-- tombe. Aucune donnée de production n'existe à ce stade (pré-prod).

UPDATE user_transcription_keys
SET status = 'invalid', updated_at = now()
WHERE secret_id IS NULL AND status <> 'invalid';

UPDATE user_credentials
SET status = 'invalid', updated_at = now()
WHERE secret_id IS NULL AND status <> 'invalid';

ALTER TABLE user_transcription_keys DROP COLUMN vault_secret_name;
ALTER TABLE user_credentials DROP COLUMN vault_secret_name;
