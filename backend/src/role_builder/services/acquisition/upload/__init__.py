"""Cycle upload direct de la façade MCP roles__* (spec v2/01-protocole-mcp.md §2.2).

Modules :
- `media_types` : liste blanche des media_type acceptés ;
- `intake` : create_upload_request / request_upload_slot / close_upload_request ;
- `finalize` : finalize_upload (vérification objet, extraction audio si vidéo,
  entrée dans le pipeline standard) ;
- `cleanup` : nettoyage périodique des slots expirés (§5.5) ;
- `audio_extraction` : extraction ffmpeg vidéo → mp3.

Hypothèse d'exposition réseau MinIO : voir README.md du module.
"""
