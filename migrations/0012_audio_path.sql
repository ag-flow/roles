-- Migration 0012 : audio_s3_key -> audio_path (transcription_jobs, source_items).
--
-- Référence : docs/specs/v3/00-cadrage-service-de-transcription.md.
-- L'audio ne passe plus par MinIO (lot "relais audio volume local") : il est
-- écrit par le scraper dans un volume monté sur le host, et le worker de
-- transcription le lit sur disque. La colonne qui portait la clef S3 porte
-- maintenant un chemin de fichier — une colonne nommée `audio_s3_key`
-- contenant un chemin induirait en erreur pendant des années.
--
-- RENAME COLUMN conserve les données, la contrainte NOT NULL (transcription_jobs)
-- et les index existants : aucun n'est défini sur cette colonne (vérifié
-- dans 0001_initial_schema.sql et les migrations suivantes).
--
-- Idempotent : RENAME COLUMN n'a pas de clause IF EXISTS portant sur le nom de
-- colonne (seulement sur le nom de table) — on la simule via un bloc DO/PLPGSQL
-- qui vérifie l'ancien nom avant de renommer, pour que la migration ne lève pas
-- sur une base où elle aurait déjà été appliquée.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'source_items' AND column_name = 'audio_s3_key'
    ) THEN
        ALTER TABLE source_items RENAME COLUMN audio_s3_key TO audio_path;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'transcription_jobs' AND column_name = 'audio_s3_key'
    ) THEN
        ALTER TABLE transcription_jobs RENAME COLUMN audio_s3_key TO audio_path;
    END IF;
END $$;
