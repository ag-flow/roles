-- Migration 0011 : retrait du concept `role_projects` (V1 abandonné en V2).
--
-- Référence : docs/specs/v2/00-fondations-v2.md, docs/specs/OBSOLETE.md.
-- En V2 les sources sont rattachées à une `acquisition_request` (façade MCP,
-- migration 0007), plus à un role_project. La colonne `sources.role_project_id`
-- (rendue nullable par 0007, NULL pour toutes les sources V2) et la table
-- `role_projects` deviennent du résidu V1.
--
-- ⚠️ Destructif. Après 0006 (drop synthèse) et 0011, plus aucune table ne
-- référence `role_projects`. Sur les bases déjà migrées, les éventuelles
-- sources V1 rétro-rattachées à une acquisition_request (0005 §4) survivent :
-- seul le lien vers role_projects disparaît.

-- Le DROP COLUMN retire la FK et l'index sources_role_project_idx associés.
ALTER TABLE sources DROP COLUMN IF EXISTS role_project_id;

DROP TABLE IF EXISTS role_projects;
