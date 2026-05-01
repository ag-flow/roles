-- Migration 0016 : sections custom par projet.
-- Phase 2 sous-projet G.
--
-- Tableau JSON de noms de sections, en plus des 3 standards (Role,
-- Missions, Skills). Le decomposer prompt étend son plan de documents à
-- ces sections supplémentaires. Bornage côté API : 0 à 5 sections.
--
-- Format : ["Outils", "Style-redactionnel"]

ALTER TABLE role_projects
    ADD COLUMN custom_sections jsonb NOT NULL DEFAULT '[]'::jsonb;
