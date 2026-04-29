-- Migration 0013 : ajout du choix de licence par projet pour la publication
-- GitHub. Sprint 8.
--
-- Valeurs attendues : 'none' / 'polyform-nc' / 'cc-by-nc-sa-4.0' /
-- 'cc-by-4.0' / 'mit'. Pas de CHECK contrainte (validation côté Pydantic
-- via Literal — permet d'ajouter de nouveaux choix sans migration DB).

ALTER TABLE role_publication_config
    ADD COLUMN license_choice text DEFAULT 'none' NOT NULL;
