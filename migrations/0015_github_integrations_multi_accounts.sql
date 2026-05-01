-- Migration 0015 : multi-comptes GitHub par user.
-- Phase 2 sous-projet D.
--
-- Permet à un user de connecter plusieurs comptes GitHub (perso + orga
-- typiquement). La contrainte UNIQUE(user_id) est remplacée par
-- UNIQUE(user_id, github_user_id) — l'unicité est désormais sur le
-- couple (qui se connecte, quel compte GitHub) au lieu de juste qui se
-- connecte.

ALTER TABLE github_integrations
    DROP CONSTRAINT IF EXISTS github_integrations_user_id_key;

ALTER TABLE github_integrations
    ADD CONSTRAINT github_integrations_user_id_github_user_id_key
        UNIQUE (user_id, github_user_id);
