-- Migration 0011 : Vues utiles pour l'UI.
-- Référence : docs/specs/01-data-model.md § Section 7.

CREATE VIEW v_role_project_summary AS
SELECT
    rp.id,
    rp.tenant_id,
    rp.user_id,
    rp.display_name,
    rp.description,
    rp.is_public,
    rp.created_at,
    rp.updated_at,
    COUNT(DISTINCT s.id) AS sources_count,
    COUNT(DISTINCT si.id) FILTER (WHERE si.status = 'indexed') AS items_indexed,
    COUNT(DISTINCT si.id) AS items_total,
    COUNT(DISTINCT cc.id) AS chunks_count,
    COUNT(DISTINCT rd.id) FILTER (WHERE rd.is_current) AS documents_count,
    rp.target_role_id IS NOT NULL AS pushed_to_agflow
FROM role_projects rp
LEFT JOIN sources s ON s.role_project_id = rp.id
LEFT JOIN source_items si ON si.source_id = s.id
LEFT JOIN corpus_chunks cc ON cc.role_project_id = rp.id
LEFT JOIN role_documents rd ON rd.role_project_id = rp.id
GROUP BY rp.id;
