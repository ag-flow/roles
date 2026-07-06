# BUG-18 — `retry_failed` sur un item upload fabrique un job scraper impossible

- **Zone** : acquisition / admin (confirmé par 2 agents)
- **Fichier(s)** : `backend/src/role_builder/services/acquisition/admin.py:70-90`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

Le chemin « pas de `transcript_s3_key` » suppose un item scrapé : il fait `reset_for_retry` (→ `pending_download`) et insère un scraping job `download`. Pour un item upload échoué à l'extraction audio (`AUDIO_EXTRACTION_FAILED`, posé par `finalize.py:118-124`), c'est faux : l'orchestrateur construit l'image `agflow-scraper-upload:<tag>` (`scraper_orchestrator.py:66`) qui n'existe pas → le job échoue, et l'item reste bloqué `pending_download` — état d'où ni `retry_failed` (plus `failed`) ni `finalize_upload` (plus `awaiting_upload`) ne peuvent le sortir. Item définitivement irrécupérable via la façade. Le fichier vidéo source est pourtant toujours dans MinIO.

## Scénario d'échec

Upload d'un `.mov` corrompu → ffmpeg échoue → item `failed` → `roles__retry_failed` → `{retried_count: 1}` mais l'item part en download scraping impossible → bloqué `pending_download` à vie.

## Piste de résolution

Dans `retry_failed`, brancher sur `request["kind"]` (ou présence d'`upload_s3_key`) : pour un item upload, re-tenter l'extraction/la mise en queue transcription (ré-appeler la logique de finalize) au lieu d'un download job ; sinon refuser avec un code explicite. La donnée nécessaire (`upload_s3_key`) est déjà sur la ligne.

## Pourquoi Opus

Nouveau chemin de retry upload, avec décision sur l'objet brut (supprimé après extraction réussie, conservé après échec) + tests.

## ✅ Résolu (2026-07-06)

retry_failed route les items upload via `_retry_upload_item` : vidéo → pending_extraction (re-extraction), audio → re-queue transcription. Plus jamais de job scraper impossible.

Vérifié : suite backend verte (481 passed).
