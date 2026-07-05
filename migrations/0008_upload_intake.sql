-- Migration 0008 : intake par upload direct (façade MCP roles__*, lot upload).
-- Référence : docs/specs/v2/01-protocole-mcp.md § 2.2, 5.5.
--
-- Trois changements :
--
-- 1. sources.url devient nullable. Les items upload sont rattachés à une
--    source technique platform='upload' (spec §4) qui n'a pas d'URL
--    d'origine — le champ source_url du corpus est null pour ces items
--    (spec §2.4). Les sources scrape continuent de fournir leur URL.
--
-- 2. source_items gagne deux colonnes propres au cycle upload :
--    - upload_media_type : media_type déclaré au slot (liste blanche §2.2),
--      détermine si une extraction audio ffmpeg est nécessaire au finalize
--      (vidéo) ou si l'objet uploadé est directement l'audio ;
--    - upload_s3_key : clé de l'objet visé par l'URL présignée PUT
--      (bucket corpus-audio). Distincte d'audio_s3_key : pour une vidéo,
--      audio_s3_key pointera vers l'audio extrait, pas l'objet brut.
--    upload_expires_at (TTL du slot) existe déjà depuis la migration 0005.
--
-- 3. Index partiel pour le nettoyage périodique des slots expirés
--    (spec §5.5) : le job ne scanne que les items 'awaiting_upload'.

ALTER TABLE sources
    ALTER COLUMN url DROP NOT NULL;

ALTER TABLE source_items
    ADD COLUMN upload_media_type text,
    ADD COLUMN upload_s3_key text;

CREATE INDEX source_items_awaiting_upload_idx
    ON source_items (upload_expires_at)
    WHERE status = 'awaiting_upload';
