# 01-v2 — Protocole MCP `roles__*`

> Spec du protocole de consommation de la stack rôles via la passerelle MCP.
> Complète `00-fondations-v2.md`. Modèle : **ticket asynchrone** — soumettre,
> puller le statut, récupérer le corpus incrémentalement.
>
> **Statut :** v2.1 — 2026-07-04 (ajouts : `list_discovered` enrichi, intake
> par upload via URL présignée)

---

## 1. Principes

1. **Asynchrone par ticket.** Toute acquisition retourne une `request_key`
   immédiatement ; le travail se fait en queue partagée entre tous les
   acteurs. Aucun tool ne bloque.
2. **Livraison incrémentale.** Le corpus est consultable au fil de l'eau,
   item par item, sans attendre la complétion.
3. **Références, jamais de contenu.** Les tools retournent des refs
   docflow ; la lecture passe par `docflow__*`. Symétriquement, aucun
   contenu binaire ne transite par un tool : l'upload passe par une URL
   présignée MinIO.
4. **Lecture n'engage pas, acte engage** (aligné workflow v2).
5. **Le pilote maîtrise les coûts et la sélection.** La découverte retourne
   des métadonnées brutes riches (titre, description, tags, durée) ; la
   **thématisation est le travail du pilote** (aucun LLM dans la stack).
   Il présente la liste à l'humain, qui choisit ; la demande porte ensuite
   sur la liste retenue.

## 2. Tools

### 2.1 Soumission — sources en ligne

#### `roles__submit_acquisition(url, platform?, mode?, filters?, docflow_target?, note?)`
Soumet une acquisition (chaîne, playlist, compte ou vidéo unique).

- `platform` : `youtube|instagram|tiktok` (déduit de l'URL si omis).
- `mode` :
  - `"discover_only"` (**défaut**) : découvre **toute la source** (chaîne
    complète) et s'arrête — le pilote consulte `list_discovered`, présente
    les items à l'humain, puis appelle `select_items` sur la liste retenue.
  - `"auto"` : discover puis sélection automatique par `filters` puis
    download+transcription. Raccourci pour les cas simples.
- `filters` : `{max_items?, since?, until?, min_duration_s?, max_duration_s?,
  title_contains?}` — appliqués à la sélection auto.
- `docflow_target` : workspace/bloc docflow de dépôt (défaut : convention
  du tenant, cf. question ouverte fondations §9).
- `note` : intention libre, tracée (ex. « corpus UX pour rôle designer »).

→ `{request_key, status: "discovering", platform, url}`
Erreurs : `UNSUPPORTED_PLATFORM`, `INVALID_URL`, `NO_CREDENTIALS`
(pas de cookies actifs pour la plateforme).

`request_key` : slug lisible et stable (ex. `yt-clea-ux-2026-07-04-a3f2`) —
clé de reprise conversationnelle, au même titre que les noms d'instances
workflow.

#### `roles__list_discovered(request_key, cursor?, limit?)`
Liste **enrichie** des items découverts — la matière du choix humain.
Disponible dès `discovered` (et pendant `discovering`, partielle).

→
```jsonc
{
  "request_key": "...",
  "discovery_complete": true,
  "items": [
    {
      "item_id": "...",
      "title": "Interview UX : observer avant de questionner",
      "description_excerpt": "Dans cette vidéo je partage ma méthode…",  // ~300 chars
      "tags": ["ux", "user research", "interview"],
      "duration_s": 913,
      "published_at": "2025-11-02T…",
      "thumbnail_url": "https://…",
      "already_selected": false
    }
  ],
  "next_cursor": "…"
}
```

La stack ne calcule **pas** de thème : titre + extrait + tags suffisent au
pilote pour thématiser et présenter la liste à l'utilisateur.

#### `roles__select_items(request_key, item_ids | filters)`
Sélectionne les items à télécharger/transcrire. Accepte une liste explicite
d'`item_ids` (chemin nominal : la liste retenue par l'humain) ou des
`filters`. Idempotent, cumulable (sélections successives possibles tant que
la requête n'est pas close).
→ `{selected_count, queued_count}`

### 2.2 Soumission — upload direct

Pour les médias hors plateformes (enregistrements perso, conférences,
podcasts fournis en fichier). Le fichier ne transite jamais par MCP :
**URL présignée MinIO**, PUT direct par le client.

#### `roles__create_upload_request(title, docflow_target?, note?)`
Ouvre une requête d'acquisition de type upload.
→ `{request_key, status: "open_for_upload"}`

#### `roles__request_upload_slot(request_key, filename, media_type, title?, published_at?, duration_s?)`
Crée un item et un slot d'upload.
- `media_type` : `audio/mpeg | audio/wav | audio/mp4 | video/mp4 | …`
  (liste blanche ; vidéo → extraction audio ffmpeg côté stack, comme les
  items scrapés).
→ `{item_id, upload_url, expires_at}` — `upload_url` = PUT présigné MinIO
(bucket `corpus-audio`), TTL 1 h.
Erreurs : `UNSUPPORTED_MEDIA`, `UNKNOWN_REQUEST`, `REQUEST_CLOSED`.

#### `roles__finalize_upload(request_key, item_id)`
Après le PUT réussi : vérifie la présence de l'objet MinIO, passe l'item en
`audio_ready` → pipeline standard (transcription → dépôt docflow),
strictement identique aux items scrapés.
Erreurs : `UPLOAD_NOT_FOUND` (PUT absent ou expiré), `UPLOAD_EXPIRED`.

#### `roles__close_upload_request(request_key)`
Ferme l'intake (plus de nouveaux slots) ; la complétion suit les items en
cours. Une requête upload sans close reste ouverte (corpus au fil de l'eau).

### 2.3 Suivi

#### `roles__request_status(request_key)`
→
```jsonc
{
  "request_key": "yt-clea-ux-2026-07-04-a3f2",
  "kind": "scrape | upload",
  "status": "discovering | discovered | open_for_upload | acquiring |
             completed | partially_failed | failed | cancelled",
  "submitted_by": "...", "submitted_at": "...",
  "counts": {
    "discovered": 200, "selected": 30,
    "downloaded": 22, "transcribed": 18, "deposited": 18,
    "failed": 2, "pending": 10
  },
  "items": [                        // résumé paginé ; détail riche → list_discovered
    {"item_id": "...", "title": "...", "duration_s": 913,
     "status": "pending_download | ... | deposited | failed",
     "error": null}
  ],
  "cost": {"transcription_usd": 1.84},
  "queue_position": 3               // si des jobs attendent (ressource partagée)
}
```
`status=completed` quand tous les items sélectionnés/uploadés sont
`deposited` ou `failed` (avec ≥1 failed → `partially_failed`).

#### `roles__list_requests(status?, submitted_by?)`
Reprise conversationnelle et vue multi-acteurs.
→ `[{request_key, kind, status, url?, counts_summary, submitted_by, submitted_at}]`

### 2.4 Récupération du corpus

#### `roles__get_corpus(request_key, only_new?, cursor?)`
Retourne les références docflow des transcripts **déjà déposés** — à tout
moment, sans attendre la complétion.

- `only_new: true` : uniquement les items déposés depuis le dernier
  `get_corpus` de cet appelant (curseur géré côté stack par
  `(request_key, caller)` ; `cursor` explicite en alternative stateless).

→
```jsonc
{
  "request_key": "...",
  "complete": false,
  "documents": [
    {
      "item_id": "...",
      "docflow": {"doc_id": "...", "slug": "transcript-...", "title": "..."},
      "metadata": {"platform": "youtube|instagram|tiktok|upload",
                    "source_url": "...",           // null si upload
                    "duration_s": 913, "published_at": "...",
                    "provider": "faster-whisper"}
    }
  ],
  "failed_items": [{"item_id": "...", "title": "...", "error": "..."}]
}
```

La lecture du texte : `docflow__get_document(doc_id)`. La stack ne proxifie
jamais le contenu.

### 2.5 Administration

#### `roles__cancel_request(request_key, note?)`
Annule les jobs pending/claimed de la requête ; les items déjà déposés
restent dans docflow. → `{cancelled_jobs, deposited_kept}`

#### `roles__retry_failed(request_key, item_ids?)`
Re-queue les items `failed` (tous, ou une sélection). Réutilise
`attempts`/`max_attempts` existants.

## 3. Cycle de vie d'une requête

```
Scrape :
  submit(discover_only) ─► discovering ─► discovered
        └─ le pilote : list_discovered → choix humain → select_items
                                          └──────────────► acquiring ─► completed
  submit(auto) ─────────► discovering ─► acquiring ─► completed
                                                          └─ partially_failed
Upload :
  create_upload_request ─► open_for_upload
        └─ N × (request_upload_slot → PUT client → finalize_upload)
        └─ close_upload_request ─► acquiring ─► completed

(à tout moment) cancel ─► cancelled
```

Pipeline interne par item (inchangé vs V1 jusqu'à `transcribed`, puis) :
`transcribed → depositing → deposited` — l'étape `depositing` remplace
`chunking/indexed` : dépôt du texte + métadonnées dans docflow via la
passerelle (retry avec backoff ; échec de dépôt = item `failed` avec
`error.code=DOCFLOW_DEPOSIT_FAILED`, transcript conservé dans MinIO pour
retry). Les items upload entrent au stade `audio_ready`.

## 4. Modèle de données — deltas vs V1

### Nouvelle table `acquisition_requests`
```sql
CREATE TABLE acquisition_requests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_key     text NOT NULL UNIQUE,      -- slug lisible
    tenant_id       uuid NOT NULL,
    submitted_by    text NOT NULL,             -- identité passerelle déclarée
    kind            text NOT NULL CHECK (kind IN ('scrape','upload')),
    source_id       uuid REFERENCES sources(id),  -- null si kind=upload pur
    mode            text CHECK (mode IN ('auto','discover_only')),
    filters         jsonb,
    docflow_target  jsonb,                     -- {workspace, block} ou null=convention
    note            text,
    status          text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
```
`role_projects` disparaît comme concept central : la **requête** remplace le
« projet de rôle » (le rôle, lui, vit chez le pilote/docflow). Migration :
`sources.role_project_id` → rattachement à la requête ; tables de synthèse
droppées (voir §5). Pour `kind=upload`, les items sont rattachés à une
source technique `platform='upload'` (déjà prévue au schéma V1).

### `source_items` — statuts et colonnes révisés
`chunking|indexed` → `depositing|deposited` ; nouvelles colonnes
`docflow_doc_id text`, `docflow_slug text`, `deposited_at timestamptz`.
Pour l'upload : `upload_expires_at timestamptz` (TTL du slot présigné),
statut initial `awaiting_upload` avant `audio_ready`.

### Nouvelle table `corpus_pull_cursors`
```sql
CREATE TABLE corpus_pull_cursors (
    request_id   uuid NOT NULL REFERENCES acquisition_requests(id),
    caller       text NOT NULL,
    last_pulled_at timestamptz NOT NULL,
    PRIMARY KEY (request_id, caller)
);
```

### Supprimées
`corpus_chunks`, `chunking_jobs`, `prompts`, `prompt_versions`, `runs`,
`signals`, `clusters`, `document_plans`, `role_documents`,
`role_publication_config`, `role_publications`, `github_integrations`,
`oauth_states`, colonnes `mistral_secret_ref`/`identity`/
`global_directives`/`custom_sections`/`is_public` de l'ex-`role_projects`.

### Conservées telles quelles
`sources`, `scraping_jobs`, `transcription_jobs`, `user_credentials`,
`user_transcription_keys`, `transcription_workers`, triggers PG NOTIFY
(pour la vue admin éventuelle).

## 5. Règles de comportement

1. **Queue partagée, FIFO** : les jobs de toutes les requêtes/acteurs
   partagent les mêmes queues (`priority` et `tenant_id` = hooks V3).
   `queue_position` exposé dans `request_status` pour la transparence.
2. **Dépôt docflow = étape du pipeline**, avec retry/backoff comme les
   autres. La stack utilise son identité machine passerelle.
3. **Identité déclarée** : `submitted_by` est requis à la soumission
   (déclaratif, comme `validated_by` côté workflow) — croisable plus tard
   avec l'identité de session passerelle.
4. **Aucune synthèse, aucun rôle, aucun thème** : la stack livre des
   métadonnées brutes et du corpus référencé. Toute analyse de contenu
   (thématisation incluse) appartient au pilote.
5. **Upload** : liste blanche de `media_type`, TTL des slots présignés,
   nettoyage périodique des items `awaiting_upload` expirés (job léger).
   Taille max par objet : politique MinIO (défaut 2 GB), pas de streaming
   par MCP.
6. **Erreurs** : format uniforme `{code, message, details}`. Codes :
   `UNKNOWN_REQUEST`, `UNSUPPORTED_PLATFORM`, `INVALID_URL`,
   `NO_CREDENTIALS`, `NOT_IN_DISCOVERED_STATE`, `DOCFLOW_DEPOSIT_FAILED`,
   `ALREADY_CANCELLED`, `UNSUPPORTED_MEDIA`, `REQUEST_CLOSED`,
   `UPLOAD_NOT_FOUND`, `UPLOAD_EXPIRED`.

## 6. Critères d'acceptation

- [ ] Cycle nominal deux temps : `submit(discover_only)` sur une chaîne
      complète → `list_discovered` retourne titres/extraits/tags/durées
      paginés → `select_items(liste retenue)` → seuls ces items passent
      en transcription.
- [ ] Cycle raccourci : `submit(url, mode=auto, filters)` → pulls
      `request_status` → `get_corpus` incrémental → `complete=true`.
- [ ] Cycle upload : `create_upload_request` → `request_upload_slot` →
      PUT présigné → `finalize_upload` → item transcrit et déposé dans
      docflow, indiscernable d'un item scrapé côté corpus
      (`platform=upload`, `source_url=null`).
- [ ] Slot expiré : `finalize_upload` → `UPLOAD_EXPIRED` ; item nettoyé.
- [ ] `only_new` : deux pulls successifs, le second ne retourne que les
      items déposés entre-temps ; deux appelants ont des curseurs
      indépendants.
- [ ] Multi-acteurs : deux requêtes simultanées de deux `submitted_by`
      différents partagent la queue sans se corrompre ; `queue_position`
      cohérent.
- [ ] Échec de dépôt docflow : item `failed` avec code dédié, transcript
      conservé, `retry_failed` le récupère.
- [ ] `cancel_request` : jobs pending annulés, items déposés préservés.
- [ ] Traçabilité : depuis un document docflow, remonter request_key →
      source → URL d'origine (ou origine upload).
- [ ] Aucun contenu (texte ou binaire) ne transite par un tool `roles__*`.

## 7. Questions ouvertes

- Convention `docflow_target` par défaut (workspace/bloc par tenant ?
  par requête ?) — à aligner avec la spec docflow.
- Notification push vers le pilote à la complétion (webhook/catch-up
  docflow ?) — V2 = pull uniquement.
- Quotas/équité multi-acteurs (V2 = FIFO).
- `roles__estimate_cost(request_key)` avant sélection (durées découvertes
  × tarif provider) — probablement oui, aligné « le pilote maîtrise les
  coûts » ; à confirmer.
- URL présignée MinIO : exposition réseau (MinIO doit être joignable par
  le client qui uploade — via Cloudflare Tunnel/ingress ?) — à trancher
  au déploiement sur le host ressources.
