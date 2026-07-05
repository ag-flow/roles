# Module upload — intake par URL présignée MinIO

Implémente le cycle upload de la façade MCP `roles__*`
(spec `docs/specs/v2/01-protocole-mcp.md` §2.2, §5.5) :

```
create_upload_request ─► open_for_upload
      └─ N × (request_upload_slot → PUT client → finalize_upload)
      └─ close_upload_request ─► acquiring ─► completed
```

- **intake.py** — ouverture de requête (`kind=upload`, source technique
  `platform='upload'` sans URL), création de slot (item `awaiting_upload`,
  URL présignée PUT sur `corpus-audio`, TTL 1 h, liste blanche
  `media_types.py`), fermeture de l'intake.
- **finalize.py** — vérification de l'objet, extraction audio ffmpeg si le
  média est une vidéo (`audio_extraction.py`), puis entrée dans le pipeline
  standard : `audio_ready` → job de transcription en queue partagée →
  `queued_transcription`. En aval, l'item est indiscernable d'un item
  scrapé (`platform=upload`, `source_url=null` dans le corpus).
- **cleanup.py** — job léger périodique (scheduler) : suppression des slots
  `awaiting_upload` expirés et de leur objet orphelin éventuel.

## Hypothèse : exposition réseau de MinIO (hors périmètre de ce lot)

L'URL présignée PUT retournée par `request_upload_slot` est signée pour
l'endpoint configuré (`settings.minio_endpoint`). **Le client qui uploade
(le poste de l'humain derrière le pilote) doit pouvoir joindre cet endpoint
directement** : le fichier ne transite ni par MCP ni par le backend.

Ce lot suppose donc que MinIO est joignable par le client à l'URL exacte
utilisée pour la signature (la signature S3 couvre le host : un simple
reverse-proxy sous un autre nom d'hôte invalide l'URL — il faut signer avec
le nom public, ou exposer MinIO sous ce nom). Le choix du mécanisme
d'exposition (Cloudflare Tunnel / ingress sur le host `usage=ressources`)
est explicitement renvoyé au déploiement, cf. spec v2/01 §7 (questions
ouvertes). En dev/test, l'endpoint local (`localhost:9000`) suffit.

## Limites assumées

- `roles__retry_failed` remet les items `failed` en `pending_download` :
  pertinent pour les échecs de dépôt docflow, pas pour un échec
  d'extraction audio (`AUDIO_EXTRACTION_FAILED`) — dans ce cas, re-demander
  un slot est le chemin de reprise.
- Taille max par objet : politique MinIO (défaut 2 GB), spec §5.5.
