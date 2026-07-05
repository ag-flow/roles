-- Migration 0007 : ajustements pour la façade MCP roles__* (lot scrape).
-- Référence : docs/specs/v2/01-protocole-mcp.md § 2.1, 2.3.
--
-- Deux changements, tous deux nécessaires pour que les acquisitions
-- soumises via roles__submit_acquisition fonctionnent sans rattachement
-- à un role_project (concept retiré comme point d'attache en V2) :
--
-- 1. sources.role_project_id devient nullable. Les sources V1 gardent leur
--    valeur ; les sources créées par la façade V2 n'ont plus de projet à
--    référencer (la requête d'acquisition est leur seul rattachement).
--    ON DELETE CASCADE reste en place pour les sources V1 encore liées à
--    un role_project ; il ne s'applique simplement pas aux lignes NULL.
--
-- 2. source_items gagne description_excerpt + tags, nécessaires à
--    roles__list_discovered (métadonnées riches, §2.1). Colonnes nullables
--    et non peuplées par les scrapers existants pour l'instant (contrat
--    stdin/NDJSON figé, non modifié par ce lot) : elles seront alimentées
--    quand les scrapers seront étendus, hors périmètre ici.

ALTER TABLE sources
    ALTER COLUMN role_project_id DROP NOT NULL;

ALTER TABLE source_items
    ADD COLUMN description_excerpt text,
    ADD COLUMN tags text[];
