-- Migration 0013 : retrait du cycle d'upload direct (undo partiel de 0008).
--
-- Référence : docs/specs/v2/01-protocole-mcp.md (cycle upload retiré du
-- périmètre, lot "relais audio volume local" — tâche 5/6). Le worker de
-- transcription n'a plus qu'une seule provenance d'audio (le volume monté,
-- tâches 1 à 4) : le second producteur (upload présigné MinIO) disparaît.
--
-- Ce que 0008_upload_intake.sql avait réellement ajouté (vérifié dans ce
-- fichier, pas supposé) :
--   1. sources.url DROP NOT NULL — conservé ici : une source scrape garde
--      son URL, rendre la colonne nullable ne nuit à rien et revenir en
--      arrière exigerait de garantir l'absence de toute ligne à url NULL
--      (hors périmètre de ce lot, qui porte sur le code applicatif upload,
--      pas sur un audit de données).
--   2. source_items.upload_media_type / upload_s3_key — supprimées ici :
--      plus aucun code ne les lit ni ne les écrit (vérifié : le répertoire
--      upload/, db_helpers/source_items_upload.py et mcp_server/tools/
--      upload.py qui les manipulaient sont retirés par ce même lot).
--   3. L'index partiel source_items_awaiting_upload_idx (nettoyage des
--      slots awaiting_upload) — supprimé ici : plus aucun item ne prend ce
--      statut, le job de nettoyage périodique (scheduler) est retiré.
--
-- upload_expires_at (source_items) N'EST PAS touchée par cette migration :
-- elle a été ajoutée par 0005_acquisition_requests.sql, pas par 0008 — hors
-- périmètre de l'undo ciblé ici, même si elle devient orpheline (plus aucun
-- code ne l'alimente). Un lot ultérieur statuera sur son sort si besoin.
--
-- DROP COLUMN IF EXISTS / DROP INDEX IF EXISTS : Postgres les supporte
-- nativement (pas besoin du bloc DO/PLPGSQL qu'exigeait le RENAME de la
-- migration 0012) — rejoue sans erreur qu'une base porte déjà ces objets
-- ou non.

DROP INDEX IF EXISTS source_items_awaiting_upload_idx;

ALTER TABLE source_items
    DROP COLUMN IF EXISTS upload_media_type,
    DROP COLUMN IF EXISTS upload_s3_key;
