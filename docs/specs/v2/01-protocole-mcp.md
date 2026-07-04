# 01-v2 — Protocole MCP `roles__*`

> Spec du protocole de consommation de la stack rôles via la passerelle MCP.
> Complète `00-fondations-v2.md`. Modèle : **ticket asynchrone** — soumettre,
> puller le statut, récupérer le corpus incrémentalement.
>
> **Statut :** v2.0 — 2026-07-04

---

## 1. Principes

1. **Asynchrone par ticket.** Toute acquisition retourne une `request_key`
   immédiatement ; le travail se fait en queue partagée entre tous les
   acteurs. Aucun tool ne bloque.
2. **Livraison incrémentale.** Le corpus est consultable au fil de l'eau,
   item par item, sans attendre la complétion.
3. **Références, jamais de contenu.** Les tools retournent des refs
   docflow ; la lecture passe par `docflow__*`.
4. **Lecture n'engage pas, acte engage** (aligné workflow v2).
5. **Le pilote maîtrise les coûts** : la sélection des items à transcrire
   lui appartient (mode deux temps), les filtres sont un raccourci.

## 2. Tools

### 2.1 Soumission

#### `roles__submit_acquisition(url, platform?, mode?, filters?, docflow_target?, note?)`
Soumet une acquisition (chaîne, playlist, compte ou vidéo unique).

- `platform` : `youtube|instagram|tiktok` (déduit de l'URL si omis).
- `mode` :
  - `"auto"` (défaut si `filters` fourni) : discover puis sélection
    automatique par filtres puis download+transcription.
  - `"discover_only"` : s'arrête après la découverte — le pilote examine
    puis appelle `select_items`.
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

#### `roles__select_items(request_key, item_ids | filters)`
Pour une requête en `discovered` (mode `discover_only`) : sélectionne les
items à télécharger/transcrire. Accepte une liste explicite d'`item_ids`
ou des `filters` (même schéma que le submit). Idempotent, cumulable
(sélections successives possibles tant que la requête n'est pas close).
→ `{selected_count, queued_count}`

### 2.2 Suivi

#### `roles__request_status(request_key)`
→
```jsonc
{
  "request_key": "yt-clea-ux-2026-07-04-a3f2",
  "status": "discovering | discovered | acquiring | completed |
             partially_failed | failed | cancelled",
  "submitted_by": "...", "submitted_at": "...",
  "counts": {
    "discovered": 200, "selected": 30,
    "downloaded": 22, "transcribed": 18, "deposited": 18,
    "failed": 2, "pending": 10
  },
  "items": [                        // paginé ; filtre ?status=
    {"item_id": "...", "title": "...", "duration_s": 913,
     "status": "pending_download | ... | deposited | failed",
     "error": null}
  ],
  "cost": {"transcription_usd": 1.84},
  "queue_position": 3               // si des jobs attendent (ressource partagée)
}
```
`status=completed` quand tous les items sélectionnés sont `deposited` ou
`failed` (avec ≥1 failed → `partially_failed`).

#### `roles__list_requests(status?, submitted_by?)`
Reprise conversationnelle et vue multi-acteurs.
→ `[{request_key, status, url, counts_summary, submitted_by, submitted_at}]`

### 2.3 Récupération du corpus

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
      "metadata": {"platform": "youtube", "source_url": "...",
                    "duration_s": 913, "published_at": "...",
                    "provider": "faster-whisper"}
    }
  ],
  "failed_items": [{"item_id": "...", "title": "...", "error": "..."}]
}
```

La lecture du texte : `docflow__get_document(doc_id)`. La stack ne proxifie
jamais le contenu.

### 2.4 Administration

#### `roles__cancel_request(request_key, note?)`
Annule les jobs pending/claimed de la requête ; les items déjà déposés
restent dans docflow. → `{cancelled_jobs, deposited_kept}`

#### `roles__retry_failed(request_key, item_ids?)`
Re-queue les items `failed` (tous, ou une sélection). Réutilise
`attempts`/`max_attempts` existants.

## 3. Cycle de vie d'une requête

```
submit(auto) ──► discovering ──► acquiring ──► completed
                                      │              └─ partially_failed
submit(discover_only) ─► discovering ─► discovered ─(select_items)─► acquiring
(à tout moment) cancel ─► cancelled
```

Pipeline interne par item (inchangé vs V1 jusqu'à `transcribed`, puis) :
`transcribed → depositing → deposited` — l'étape `depositing` remplace
`chunking/indexed` : dépôt du texte + métadonnées dans docflow via la
passerelle (retry avec backoff ; échec de dépôt = item `failed` avec
`error.code=DOCFLOW_DEPOSIT_FAILED`, transcript conservé dans MinIO pour
retry).

## 4. Modèle de données — deltas vs V1

### Nouvelle table `acquisition_requests`
```sql
CREATE TABLE acquisition_requests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_key     text NOT NULL UNIQUE,      -- slug lisible
    tenant_id       uuid NOT NULL,
    submitted_by    text NOT NULL,             -- identité passerelle déclarée
    source_id       uuid NOT NULL REFERENCES sources(id),
    mode            text NOT NULL CHECK (mode IN ('auto','discover_only')),
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
droppées (voir §5).

### `source_items` — statuts révisés
`chunking|indexed` → `depositing|deposited` ; nouvelle colonne
`docflow_doc_id text`, `docflow_slug text`, `deposited_at timestamptz`.

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
4. **Aucune synthèse, aucun rôle** : la stack refuse tout scope creep vers
   l'analyse du contenu. Elle livre du corpus référencé.
5. **Erreurs** : format uniforme `{code, message, details}`. Codes :
   `UNKNOWN_REQUEST`, `UNSUPPORTED_PLATFORM`, `INVALID_URL`,
   `NO_CREDENTIALS`, `NOT_IN_DISCOVERED_STATE`, `DOCFLOW_DEPOSIT_FAILED`,
   `ALREADY_CANCELLED`.

## 6. Critères d'acceptation

- [ ] Cycle nominal auto : `submit(url, filters)` → pulls `request_status`
      → `get_corpus` incrémental (docs partiels avant complétion) →
      `complete=true` ; transcripts lisibles via `docflow__get_document`.
- [ ] Cycle deux temps : `submit(discover_only)` → 200 items `discovered`
      → `select_items(30)` → seuls les 30 passent en transcription.
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
      source → URL d'origine (métadonnées présentes).
- [ ] Aucun contenu de transcript ne transite par un tool `roles__*`.

## 7. Questions ouvertes

- Convention `docflow_target` par défaut (workspace/bloc par tenant ?
  par requête ?) — à aligner avec la spec docflow.
- Notification push vers le pilote à la complétion (webhook/catch-up
  docflow ?) — V2 = pull uniquement.
- Quotas/équité multi-acteurs (V2 = FIFO).
- Faut-il exposer un `roles__estimate_cost(request_key)` avant
  sélection (durées découvertes × tarif provider) ? Probablement oui,
  peu coûteux et aligné « le pilote maîtrise les coûts » — à confirmer.
