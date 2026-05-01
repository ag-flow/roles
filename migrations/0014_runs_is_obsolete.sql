-- Migration 0014 : marqueur d'obsolescence des runs.
-- Phase 2 sous-projet C.
--
-- Un run devient obsolete (is_obsolete=true) quand un paramètre qui le
-- régit a été modifié après son exécution :
-- 1. role_projects.global_directives édité → tous les runs du projet
-- 2. prompt.set_system_default(prompt_id, new_version_id) → runs du
--    projet utilisant une autre version de ce prompt
--
-- Le drapeau est monotone (true → reste true). Le run reste lisible/
-- téléchargeable, l'obsolescence n'est pas une suppression.

ALTER TABLE runs ADD COLUMN is_obsolete boolean NOT NULL DEFAULT false;

-- Index partial : accélère le listing "runs actifs" si une UI filtre.
CREATE INDEX runs_obsolete_idx
    ON runs (role_project_id, is_obsolete)
    WHERE is_obsolete = false;
