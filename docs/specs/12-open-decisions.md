# 12 — Décisions ouvertes (TODO consolidé)

> Ce document agrège tous les TODO disséminés dans les autres blocs. Il
> sert de checklist unique pour suivre les décisions à trancher pendant
> l'implémentation. À mettre à jour au fil des sprints quand une décision
> est prise (cocher la case + ajouter la décision en commentaire).

## Méta

- À chaque fin de sprint, mettre à jour ce fichier :
  - Cocher les cases tranchées
  - Ajouter `→ Décision : ...` sous l'item
  - Ajouter les nouvelles questions émergées dans la section appropriée

---

## Pipeline de synthèse (§ 06)

- [ ] **Mécanisme exact d'invocation Mistral via ag.flow**
      Endpoint, format de requête, gestion du streaming. Lire l'OpenAPI
      réel `https://docker-agflow.yoops.org/openapi.json` au début du
      sprint 5.

- [ ] **Format JSON exact en sortie du decomposer**
      Définir un JSON Schema strict à valider avant de stocker. Test sur
      un corpus réel avant de figer.

- [ ] **Taxonomie des signaux**
      La liste actuelle (heuristique/anecdote/vocab/cadre/opinion) est-elle
      suffisante ? Tester sur un corpus réel (Clea UX) avant de figer.

- [ ] **Stratégie de chunking pour l'extractor**
      Taille de chunks à envoyer à l'extractor : on envoie 5 chunks à la
      fois ? 10 ? Selon la taille du contexte Mistral et la qualité de
      l'extraction.

- [ ] **Map-reduce pour les gros corpus**
      Si un projet a 500 chunks, l'extractor ne peut pas tout passer d'un
      coup. Stratégie batch déjà prévue, mais à régler la taille de batch
      selon les retours qualité.

- [ ] **Pipeline complet en une commande ?**
      Faut-il un endpoint `/runs/full-pipeline` qui enchaîne tout, ou
      laisser l'utilisateur contrôler chaque étape ?

- [ ] **Stratégie de cache automatique**
      Si l'utilisateur modifie les directives globales, les anciens runs
      sont-ils marqués "obsolètes" ? Pour le MVP, rien d'automatique,
      mais à ajouter en Phase 2.

- [x] **Diff visuel des role_documents (versions)**
      → **Décision (sprint 7) :** `react-diff-viewer-continued` en split
      view (cf. section Sprint 7).

- [x] **Edition manuelle d'un role_document après génération**
      → **Décision (sprint 7) :** `PATCH /role-documents/{id}` édite
      in-place. Lock/unlock pour empêcher l'écrasement par régénération.
      UI : bouton "Éditer" désactivé si locked (cf. section Sprint 7).

---

## Sections custom (§ 02, § 06)

- [ ] **UX d'ajout d'une section custom**
      Libre, ou suggestion par l'IA basée sur le corpus ?

- [ ] **Limite de nombre de sections custom**
      Plafond technique à fixer (3 ? 5 ? illimité ?).

---

## Comparaison de runs (§ 06)

- [ ] **Diff side-by-side dans l'UI ou simple historique ?**
      MVP : historique seul. Side-by-side en Phase 2 si demandé.

- [ ] **Métriques de comparaison automatiques**
      Longueur, lisibilité (Flesch), couverture des signaux ? Pas pour le
      MVP.

---

## Stockage des credentials (§ 02, § 05, § 07)

- [ ] **Finaliser l'intégration OpenBao**
      En attente de la stabilisation OIDC chez Beard. Mode AppRole en
      attendant.

- [x] **Mode dégradé en attendant l'OIDC**
      Tokens AppRole : on génère un token de rôle pour le backend, on
      le stocke dans une variable d'env.
      → **Décision (sprint 1) :** mode `dev` d'OpenBao avec token
      statique `OPENBAO_DEV_TOKEN` en env var (`docker-compose.yml`).
      AppRole / OIDC viendront avec l'effort d'auth utilisateur.

- [ ] **UX d'upload des cookies**
      Drag-drop d'un fichier `cookies.txt` (MVP simple). Plus tard :
      extension navigateur dédiée pour automatiser ?

---

## Sessions ag.flow (§ 00, § 08)

- [ ] **Test du rôle directement depuis l'app**
      Possible via `/api/admin/agents/{agent_slug}/task` d'ag.flow. Quand
      l'ajouter ? Pas pour le MVP, mais utile en Phase 2 pour itérer plus
      vite sur les prompts.

---

## Découverte avancée (§ 03)

- [ ] **Exploration sémantique pour suggérer du contenu**
      Suggérer d'autres contenus pertinents en fonction du corpus existant
      (Phase 2+). Out of scope MVP.

---

## Test du rôle généré (§ 08)

- [ ] **Smoke test automatique après push**
      Invoquer l'agent ag.flow avec quelques questions canoniques pour
      vérifier la qualité ? Pas pour le MVP, mais à designer.

---

## Authentification de l'app elle-même (§ 02, § 10)

- [x] **Multi-utilisateur : SSO OIDC ou auth basique MVP ?**
      Pour le MVP mono-user (Beard) : auth basique suffisante. Multi-user
      via Keycloak homelab en Phase 2.
      → **Décision (sprint 1) :** **aucune auth** dans le squelette
      (CORS ouvert), à reprendre dès qu'une UI nécessite des actions
      utilisateur (Sprint 6 "Ma stack" probablement). Keycloak homelab
      pour Phase 2.

- [ ] **Composant `<AuthGuard>` au layout root**
      Implémentation à confirmer selon le choix d'auth. Reporté au sprint
      qui introduira l'auth.

---

## Versioning des Dockerfiles scrapers (§ 03, § 10 phasage)

- [ ] **Stratégie de canaux à formaliser**
      Qui décide qu'un `:latest` devient `:stable` ? Tests automatiques ?
      Validation manuelle ?

- [ ] **CI corrective sur les nouvelles releases yt-dlp**
      Watcher CI sur les releases upstream, rebuild auto, push registry
      privé. Phase 2.

---

## Providers de transcription (§ 04, § 07)

- [ ] **Stratégie de garde-fou coût quand un cap est atteint**
      Job mis en pause, bascule shared, échec, notification ? Décision
      MVP : pause + bascule shared + notification.

- [ ] **Diarization : nécessaire pour le use case ?**
      Pour des interviews à plusieurs voix, oui. À évaluer selon les
      premiers retours utilisateurs.

- [ ] **Tests de qualité comparatifs entre providers**
      Process pour comparer la qualité sur un set de référence (audio
      étalon). Pas MVP, mais utile pour piloter le choix de provider.

- [ ] **Détection automatique de la langue : auto-detect ou override ?**
      Pour le MVP, auto-detect par faster-whisper. Override possible au
      niveau du projet.

- [ ] **Stratégie de retry sur erreur transitoire**
      Exponential backoff, combien de tentatives ? Décision MVP : 3
      tentatives, backoff x2.

- [ ] **Gestion des audios longs (> 25 MB pour OpenAI)**
      OpenAI Whisper a une limite de 25 MB par fichier. Découper côté
      worker ou refuser ces audios ?

---

## GitHub publication (§ 09)

- [ ] **Modération et vitrine officielle**
      Phase ultérieure, à designer séparément.

- [ ] **Format final du README**
      Ajouter des badges (shields.io) ? Stats du corpus ? Pour le MVP, le
      template simple proposé.

- [ ] **Licence par défaut suggérée**
      CC-BY ? MIT ? Apache 2.0 ? À discuter avec Beard.

- [ ] **Tag/release par version au lieu de commits simples ?**
      Pour le MVP, juste commits. Tags en Phase 2 si pertinent.

- [ ] **Optimisation push : API Trees pour 1 commit unique**
      Pour le MVP, N PUT séquentiels. Pour la Phase 2, utiliser l'API
      `git_data` pour faire un seul commit avec tous les fichiers.

- [ ] **Multi-comptes GitHub par user**
      Pour le MVP, 1 seul compte par user. À étendre en Phase 2 si besoin.

- [ ] **State CSRF en mémoire vs persistant**
      In-memory pour le MVP (mono-instance). Pour la prod multi-instance,
      migrer vers Redis ou table PG temporaire.

---

## Monitoring de crédit SaaS (§ 04, § 07)

- [ ] **Implémentation polling Deepgram**
      Premier provider à instrumenter (le seul qui expose la balance API).

- [ ] **Stratégie fallback de classification d'erreurs**
      Si l'erreur n'est pas reconnue, considère-t-on comme transitoire ou
      permanente ? Décision MVP : transitoire (retry), max_attempts gère
      la cap.

- [ ] **Format précis des `error_history` sur transcription_jobs**
      On garde combien d'entrées max ? 10 dernières, ou rotation FIFO ?

---

## Modèle de données (§ 01)

- [x] **Dimension exacte des embeddings Mistral**
      À confirmer selon le modèle utilisé (probablement 1024). Adapter
      `corpus_chunks.embedding vector(N)` en conséquence.
      → **Décision provisoire (sprint 1) :** `vector(1024)` posé dans
      migration `0004_corpus_chunks.sql`. À reconfirmer Sprint 4 à la
      lecture de l'OpenAPI ag.flow `/api/admin/llm/embeddings`. Si le
      modèle Mistral retenu renvoie une autre dimension, ajouter une
      migration `00XX_resize_chunks_vector.sql`.

- [x] **Soft-deletes vs hard-deletes**
      Tables où ajouter `deleted_at` (sources, role_projects) ? Pour le
      MVP, hard-delete avec CASCADE.
      → **Décision (sprint 1) :** hard-delete avec CASCADE comme dans la
      spec. Soft-deletes considérés en Phase 2 selon retours utilisateur.

- [ ] **Politiques de rétention**
      Combien de temps garde-t-on les `runs` archivés, transcripts,
      audios bruts ? À décider selon usage et coût stockage MinIO.

- [ ] **Seed des prompts système**
      Migration SQL `0012_seed_prompts.sql` ou commande Python séparée ?
      Recommandation : commande Python pour pouvoir versionner les
      prompts dans des fichiers `.md`. À trancher Sprint 5.

- [ ] **Politique CORS en prod**
      Domaines autorisés à appeler l'API. CORS ouvert (`*`) pour le MVP
      Sprint 1, à restreindre avant prod.

- [x] **Image pgvector exacte**
      `pgvector/pgvector:pg16` recommandée vs `ankane/pgvector`.
      → **Décision (sprint 1) :** `pgvector/pgvector:pg16` retenu dans
      `docker-compose.yml`. Image officielle, à jour, taggable.

---

## Frontend (§ 10)

- [ ] **Choix précis de la library UI**
      Tailwind seul, shadcn/ui, autre ?

- [x] **Choix entre SWR et TanStack Query**
      SWR plus léger, TanStack plus complet. SWR recommandé pour le MVP.
      → **Décision (sprint 1) :** **SWR** retenu (pas encore installé en
      Sprint 1 — le squelette n'a qu'un fetch direct côté server component
      `app/page.tsx`). À ajouter en deps quand le premier appel client-side
      arrivera (Sprint 2 — onglet Sources).

- [ ] **Génération auto des types TypeScript depuis l'OpenAPI ?**
      Via `openapi-typescript` : recommandé. Économise du temps de sync
      backend ↔ frontend.

- [ ] **Stratégie ErrorBoundary**
      Par page, par tab, ou global ?

- [ ] **Pagination ou virtualisation pour grandes listes**
      Pour les chunks d'un corpus (potentiellement 1000+) : virtualisation
      via `react-virtuoso` ou pagination simple ?

---

## Scrapers (§ 03)

- [x] **Stratégie pour Instagram**
      yt-dlp seul ou gallery-dl en complément ? Tester sur des reels
      publics réels.
      → **Décision (sprint 2) :** yt-dlp seul pour MVP, container Instagram
      livré comme stub contractuel. Câblage réel + évaluation gallery-dl
      reportés Phase 2 selon retours qualité.

- [x] **Format de stockage des thumbnails**
      Récupérer + uploader vers MinIO ou juste stocker l'URL d'origine ?
      MVP : URL d'origine (gain de coût/complexité).
      → **Décision (sprint 2) :** URL d'origine stockée dans
      `source_items.thumbnail_url` (champ déjà existant). Pas d'upload MinIO.

- [ ] **Stratégie de retry sur item failed**
      Combien de tentatives ? `max_attempts=3` dans le schéma, mais la
      logique de retry reste à coder. Reportée — Sprint 2 ne fait pas de
      retry automatique. À implémenter quand le retry sera nécessaire
      (probablement après les premiers retours utilisateur réels).

- [x] **Distinction "expired" vs "geo-restricted" vs "private"**
      Pour le MVP, traiter pareil. Plus tard, distinguer pour de meilleurs
      messages utilisateurs.
      → **Décision (sprint 2) :** tout échec → `failed` avec message
      texte. Distinction repoussée Phase 2.

- [x] **Cap à 5 containers simultanés : où configurable ?**
      Env var (recommandé) ou paramètre du tenant ?
      → **Décision (sprint 2) :** env var `MAX_CONCURRENT_SCRAPERS=5`
      (Pydantic Settings). Sémaphore asyncio dans `ScraperOrchestrator`.

---

## Service email (§ 07)

- [ ] **SMTP local, SendGrid, Mailgun, Postmark ?**
      Choix à faire selon ce que Beard a en homelab.

---

## Internationalisation (§ 10)

- [ ] **Étendre à l'anglais en Phase 2 ?**
      MVP : français only. Anglais si traction.

---

## Sprint 6 — Décisions actées et observations

- [x] **Composant `StatusIndicator` partagé**
      → **Décision (sprint 6) :** un seul composant `StatusIndicator`
      dans `frontend/src/components/` qui gère 8 statuts via maps :
      `active|configured` (vert), `low|expired|not-configured` (orange),
      `invalid|revoked|exhausted` (rouge). Inline styles (pas de Tailwind),
      cercle coloré + label français. Réutilisé dans tous les sous-onglets
      Ma stack.

- [x] **Validation cookies = parse format Netscape (pas appel scraper)**
      → **Décision (sprint 6) :** `services/credentials_validator.py`
      parse le format Netscape `cookies.txt` (7 champs tab-séparés) et vérifie
      la présence d'au moins un cookie clé par plateforme :
      - YouTube : `SID` ou `SAPISID` ou `__Secure-3PSID`
      - Instagram : `sessionid`
      - TikTok : `sessionid` ou `sid_tt`
      Le test "Tester maintenant" via container scraper réel est reporté
      Phase 2 (coût compute, complexité). MVP : si parse OK + cookie clé
      présent → status='active'.

- [x] **`check_mistral_secret_exists` = noop MVP**
      → **Décision (sprint 6) :** `routes/mistral_config.py` calcule
      le statut localement : `configured` si `secret_ref` non-vide, sinon
      `not-configured`. Pas d'appel `GET /api/admin/secrets` ag.flow car
      l'endpoint admin n'est pas encore disponible. À câbler quand ag.flow
      exposera l'API admin (Phase 2).

- [x] **Mistral config par projet (UX liste projets)**
      → **Décision (sprint 6) :** la spec 07 dit que `mistral_secret_ref`
      est par-`role_project` (multi-projet possible avec secrets différents).
      L'onglet Ma stack étant cross-project, l'UX liste tous les projets
      du user (`GET /api/role-projects` ajouté en Phase J) avec leur statut
      Mistral et un bouton "Configurer" par projet qui ouvre une modal.

- [x] **APScheduler pour les jobs périodiques**
      → **Décision (sprint 6) :** dépendance `apscheduler>=3.10.4` ajoutée
      à `pyproject.toml`. Wrapper `RoleBuilderScheduler` dans
      `services/scheduler.py` instancie `AsyncIOScheduler` avec 3 jobs :
      `poll_credit_balances` (interval 1h), `reset_monthly_spend`
      (cron jour 1 minuit), `cleanup_revoked_secrets` (cron 3h00 quotidien,
      no-op MVP). Démarré dans le lifespan FastAPI (gardé par
      `DISABLE_SCHEDULER`).

- [x] **Email reporté Phase 2**
      → **Décision (sprint 6) :** pas d'envoi email MVP. Les notifications
      `credit_exhausted`, `quota_warning_50/80/95%`, `cookies_expiring`
      ne sont pas envoyées en email. Visibilité uniquement via UI
      (StatusIndicator + bandeaux warning) + WebSocket push via PG NOTIFY.
      Service email (SMTP/SendGrid/Mailgun) à câbler Phase 2 selon le
      homelab disponible.

- [x] **Worker provisioning/stop hooks stubbed dans routes transcription_keys**
      → **Décision (sprint 6) :** `routes/transcription_keys.py` appelle
      `_trigger_worker_provisioning` et `_trigger_worker_stop` qui sont
      no-ops MVP (logs uniquement). Le `WorkerManager` est un singleton
      démarré dans le lifespan FastAPI mais pas exposé via `app.state` ni
      `Depends`. Pour activer le triggering réel, il faudra refactor
      `main.py` pour exposer `app.state.worker_manager` + `Depends(get_worker_manager)`.
      Reporté Phase 2.

- [x] **Slider workers 1-5 (défaut 1) avec debounce 500ms**
      → **Décision (sprint 6) :** `KeySettings.tsx` utilise
      `setTimeout(persist, 500)` pour limiter les PATCH à un par 500ms
      pendant que l'utilisateur slide. Toggle primaire/fallback persist
      immédiatement (1 click = 1 PATCH).

- [x] **Détection low-balance = 20% du cap mensuel ou 20$ si pas de cap**
      → **Décision (sprint 6) :** `credit_monitor.poll_all_balances`
      log warning `balance_low` si `balance <= 0.20 * monthly_cap_usd`
      (ou `balance <= 20$` si pas de cap configuré). Pas de side-effect
      DB MVP (le UI affichera l'orange via le calcul côté frontend dans
      `BalanceBadge`). Status DB `low` est mis à jour uniquement par les
      providers qui retournent l'info eux-mêmes (cf. `mark_invalid` /
      `mark_exhausted` Sprint 3).

- [ ] **Détection auto-quota mensuel atteint**
      Reporté. Si `current_month_spend_usd >= monthly_cap_usd`, on devrait
      basculer la clé en `exhausted` automatiquement et router les jobs
      vers shared. MVP : on attend le `429 quota` du provider (mécanisme
      `error_classifier` existant).

- [ ] **Test cookies via container scraper**
      Reporté Phase 2. La spec prévoit un appel test trivial (vidéo "Me at
      the zoo" pour YouTube par exemple) au clic sur "Tester maintenant".
      MVP : le test ne fait que re-parser les cookies stockés dans OpenBao.

- [ ] **Vérification ag.flow `GET /api/admin/secrets`**
      Reporté. Quand ag.flow exposera l'API admin secrets, câbler
      `mistral_config._status_for` pour faire un vrai check (HTTP timeout
      court).

- [ ] **Alertes email à 50/80/95%**
      Reporté. Service email à mettre en place d'abord.

- [ ] **OAuth pour les providers de transcription**
      Reporté. Peu de providers le supportent côté API key. Reste API key
      pour MVP.

---

## Sprint 5 — Décisions actées et observations

- [x] **Modèle LLM par défaut pour la synthèse**
      → **Décision (sprint 5) :** `mistral-large-latest` via `settings.mistral_chat_model`.
      Rates hardcodés Mistral pour le cost tracking : `mistral_input_token_rate_usd=0.000002`,
      `mistral_output_token_rate_usd=0.000006` (à mettre à jour si pricing change).

- [x] **Validation des sorties LLM**
      → **Décision (sprint 5) :** schémas Pydantic internes par étage
      (`_ExtractorResponse`, `_ClustererResponse`, `_DecomposerResponse`)
      avec `model_validate_json` + `response_format={"type": "json_object"}`
      sur les 3 premiers étages. Document writer + identity synthesizer
      retournent du markdown libre (pas de validation stricte).

- [x] **Bibliothèque de prompts versionnée**
      → **Décision (sprint 5) :** 5 prompts système (`extractor`, `clusterer`,
      `decomposer`, `document_writer`, `identity_synthesizer`) seedés depuis
      des templates `.md` versionnés dans `backend/src/role_builder/synthesis/templates/`
      via `python -m scripts.seed_prompts` (idempotent). Index unique partial
      `prompt_versions_one_system_default` impose un seul `is_system_default=true`
      par prompt — géré dans une transaction côté `db_helpers/prompts.py`.

- [x] **Pas de pipeline auto MVP**
      → **Décision (sprint 5) :** déclenchement manuel par étage via
      `POST /api/role-projects/{id}/runs/{stage}`. Endpoint `/runs/full-pipeline`
      reporté Phase 2 — laisse l'utilisateur garder le contrôle (peut éditer
      les prompts entre étages, retraiter un sous-ensemble).

- [x] **Validation `version_id ∈ prompt_id` côté DB + transactions**
      → **Décision (sprint 5) :** `set_system_default` et `insert_prompt_version`
      avec `is_system_default=True` ouvrent une transaction asyncpg. La route
      `PUT /api/prompts/{prompt_id}/system-default/{version_id}` valide que
      `version_id` appartient bien au `prompt_id` via SQL `WHERE id=$1 AND prompt_id=$2 RETURNING id`,
      404 si la version n'appartient pas. Détecté en code review Phase A blockers.

- [x] **Cleanup signaux/clusters/plans/documents orphelins sur échec pipeline**
      → **Décision (sprint 5) :** chaque étage du pipeline appelle son
      `delete_<entity>_by_run` AVANT `mark_failed` quand une exception
      survient en milieu de boucle. Évite l'état incohérent
      "run failed avec entités orphelines en BDD". Les fonctions sont
      exposées comme helpers asyncpg séparés pour pouvoir être appelées
      manuellement (admin) si nécessaire.

- [x] **Régénération un doc à la fois (instruction_override propagé)**
      → **Décision (sprint 5) :** `POST /api/role-documents/{doc_id}/regenerate`
      reconstitue un `doc_plan` minimal (`{name, brief, supporting_signals=[]}`)
      depuis le doc actuel et appelle `write_document` avec `instruction_override`.
      Le RAG via `corpus_search.find_relevant_chunks` reste actif. Le nouveau
      doc est inséré avec `is_current=False` — l'utilisateur promeut manuellement.

- [x] **Diff visuel texte brut (pas de coloration)**
      → **Décision (sprint 5) :** `RunDiff.tsx` et `DiffViewer.tsx` affichent
      les `output` ou `template` côte à côte en `<pre>`. Pas de `diff-match-patch`
      ni `react-diff-view` — laissé pour Phase 2 si le besoin se fait sentir.

- [x] **WebSocket `runs_changes` pour live updates UI**
      → **Décision (sprint 5) :** la migration 0010 trigger PG NOTIFY sur
      `runs_changes` est déjà câblée Sprint 1, relayée par `ws_relay` Sprint 2.
      Frontend Analyses utilise `useWebSocketEvent('runs_changes', mutate)` +
      backup polling SWR `refreshInterval: 5000`.

- [x] **Pas d'i18n côté frontend Sprint 5**
      → **Observation (sprint 5) :** aucune lib i18n (`react-i18next`,
      `next-intl`) installée dans le projet. Strings inline en français
      cohérent avec le reste du codebase (ChunkCard, CorpusSearchClient).
      À documenter dans CLAUDE.md si décision de garder ce statu quo.

- [ ] **Cache obsolescence des runs**
      Reporté Phase 2. Si l'utilisateur édite `global_directives` ou
      remplace une version system_default, les anciens runs deviennent
      conceptuellement "obsolètes" sans changement de status. À ajouter :
      colonne `runs.is_obsolete` ou view `v_active_runs`.

- [ ] **Map-reduce pour gros corpus (> 500 chunks dans extractor)**
      Reporté. MVP : extractor envoie les chunks par batch séquentiel
      (`chunks_per_batch=5` par défaut). Si volume > 500 chunks, prévoir
      un map-reduce (extract par batch puis cluster intermediate).

- [ ] **Word-level confidence dans le RAG**
      Reporté. Le `corpus_search.find_relevant_chunks` retourne des chunks
      ordonnés par cosine similarity. Pour pondérer par qualité de
      transcription, exposer `avg_logprob` du transcript (déjà stocké en
      `source_items.transcript_metadata`) et le combiner au score.

- [ ] **Pipeline auto `/runs/full-pipeline`**
      Reporté Phase 2. Endpoint qui déclenche les 5 étages d'un coup
      (extract → cluster → decompose → write_all_documents_for_plan ×3
      → synthesize_identity). Prudence : éviter de marquer
      automatiquement les docs comme `is_current=true`.

- [ ] **Algo de diff coloré pour RunDiff/DiffViewer**
      Reporté Phase 2. `diff-match-patch` (Google) ou `react-diff-view`
      pour mettre en évidence les changements ligne par ligne.

---

## Sprint 4 — Décisions actées et observations

- [x] **Mistral via ag.flow vs direct API**
      → **Décision (sprint 4) :** abstraction `services/agflow_client.py` qui
      appelle directement `api.mistral.ai` pour MVP. Quand l'OpenAPI ag.flow
      sera figé, swap interne sans toucher aux callers (`embedder`,
      `corpus_search`, et le futur pipeline de synthèse Sprint 5).
      Méthodes : `invoke_embeddings(texts) → list[list[float]]` (auto-batch
      32) et `invoke_chat(messages, model, response_format, temperature)
      → ChatResult`.

- [x] **Modèle d'embeddings**
      → **Décision (sprint 4) :** `mistral-embed`, 1024 dim. La dimension
      `vector(1024)` posée provisoirement migration 0004 Sprint 1 est
      confirmée. Si Mistral change la dim plus tard, créer une migration
      `00XX_resize_chunks_vector.sql`.

- [x] **Worker chunking : container séparé ou interne backend**
      → **Décision (sprint 4) :** asyncio task interne au backend FastAPI
      (gardée par `DISABLE_CHUNKING_WORKER`). Pattern strict des Sprints
      2/3 (orchestrator, ws_relay, worker_manager). L'opération est
      CPU-bound léger (chunking string + appel Mistral réseau), pas la
      peine d'un container dédié. Si volume devient critique, extraire
      en container worker en Phase 2.

- [x] **Câblage Sprint 3 → Sprint 4**
      Le trou noté en Sprint 3 (`event_handlers ne crée pas
      transcription_jobs`... NON, c'est `transcription-worker ne crée pas
      chunking_job`) est comblé : le worker transcription insère un
      `chunking_job` après `mark_job_done` (récupération role_project_id
      + tenant_id via JOIN sources/source_items).

- [x] **Index pgvector ivfflat lists=100 vs HNSW**
      → **Décision (sprint 4) :** ivfflat retenu (déjà créé migration
      0004). HNSW sera évalué Phase 2 si volume > 100k chunks (HNSW plus
      rapide en query mais plus gourmand en RAM au build).

- [x] **Multi-tenant routes corpus**
      → **Décision (sprint 4) :** TODO commenté dans `routes/corpus.py`,
      pas de vérification `user.user_id == role_projects.user_id` pour
      MVP mono-tenant. À câbler quand on activera multi-tenant via claim
      mapper Keycloak (cf. décision Auth Keycloak ci-dessous).

- [ ] **Re-chunking d'un transcript existant (rebuild corpus)**
      Reporté Phase 2. Endpoint admin "rebuild corpus" qui dropperait
      `corpus_chunks` du projet et recréerait via les `chunking_jobs`.
      Utile si on change la stratégie de chunking ou la dim d'embeddings.

- [ ] **Déduplication de chunks similaires entre vidéos**
      Reporté. Pour MVP on indexe tout. Plus tard, détection de chunks
      très proches via similarity > seuil (ex: 0.95) et suppression.

- [ ] **Streaming d'indexation (progression chunk par chunk côté UI)**
      Reporté. Pour MVP, le PG NOTIFY `source_items_changes` (status →
      `indexed`) suffit pour rafraîchir la liste. Granularité chunk-par-
      chunk en Phase 2 si gros corpus.

---

## Auth Keycloak — Phase 2 livrée (post-Sprint 3)

- [x] **Authentification utilisateur via Keycloak**
      → **Décision (post-Sprint 3) :** Authorization Code + PKCE via Auth.js v5
      (frontend Next.js) + PyJWT côté backend (validation JWT RS256 avec
      JWKS cache 1h). Issuer : `https://security.yoops.org/realms/yoops`,
      client OIDC `agflow-roles` (client confidential, secret en env var
      docker-compose, jamais commit).
      Routes backend protégées : toutes sauf `/health/`. WS `/ws` non
      protégé Phase 2 (auth WS = Phase 3, query param token + validation
      identique).
      Bypass via `DISABLE_AUTH=true` env var (utilisé par les tests pytest
      via fixture `client` du conftest).

- [x] **Multi-tenant via claim mapper Keycloak**
      → **Décision (post-Sprint 3) :** Reporté Phase 2+. MVP utilise
      `TENANT_ID_DEFAULT` constante (Sprint 1) pour tous les users. Pour
      activer le multi-tenant, ajouter un User Attribute mapper Keycloak
      sur le client `agflow-roles-dedicated` qui inject un claim `tenant_id`
      dans l'access token, puis adapter `auth/dependencies.py` pour le lire.

- [ ] **Refresh token rotation côté backend**
      Reporté. Auth.js gère le refresh côté frontend (rotation par
      Keycloak), le backend valide juste l'access token. Si on veut
      étendre à des clients machine (CLI, agent), il faudra implémenter
      le flow refresh côté backend.

- [ ] **Auth WebSocket `/ws`**
      Reporté Phase 3. Pattern prévu : query param `?token=<access_token>`,
      validation via `KeycloakValidator.validate()` au moment du
      `websocket.accept()`. Le frontend passera `session.accessToken` au
      moment d'ouvrir la connexion WS.

---

## CI Docker — Bugs initiaux corrigés (post-Sprint 3)

Trois bugs introduits par Sprint 2 H + Sprint 3 H qui empêchaient les builds CI de fonctionner. Détectés à la relecture (Docker non disponible localement, donc bugs latents jusqu'au premier push).

- [x] **`Dockerfile.cuda` Python 3.12 absent d'Ubuntu 22.04**
      Sprint 3 H1 utilisait `nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04` puis `apt-get install python3.12`. Mais Ubuntu 22.04 (jammy) n'a pas python3.12 dans ses repos officiels.
      → **Fix** : bump à `nvidia/cuda:12.4.0-cudnn-runtime-ubuntu24.04` (noble, python3.12 par défaut). Cohérent avec le Dockerfile CPU sur `python:3.12-slim`.

- [x] **Chaîne base→platforms cassée avec buildx isolé**
      Sprint 2 H2 faisait `docker pull base:sha-XXX && docker tag agflow-scraper-base:latest` sur le runner, puis le Dockerfile platform faisait `FROM agflow-scraper-base:latest`. Mais `docker/build-push-action@v6` utilise un builder buildx isolé qui ne voit pas les tags du daemon Docker host.
      → **Fix** : `ARG BASE_IMAGE=agflow-scraper-base:latest` dans les 3 Dockerfiles platforms (préserve le build local, default OK). `build-scrapers.yml` job `build-base` expose son tag SHA en output ; job `build-platforms` passe ce tag via `build-args: BASE_IMAGE=ghcr.io/.../agflow-scraper-base:sha-XXX` + `pull: true`. Plus de docker pull/tag manuel.

- [x] **`Dockerfile.cuda` ne copiait pas `uv.lock`**
      Asymétrie avec le Dockerfile CPU. Build CUDA non reproductible.
      → **Fix** : ajout du `uv.lock` au `COPY` pour cohérence.

- [ ] **Validation runtime des images Docker**
      Aucun `docker build` n'a été exécuté localement (Docker mis de côté). Les bugs ci-dessus ont été détectés à la relecture, pas par un build réel. À confirmer dès le premier push remote (workflows GHCR tourneront sur GitHub Actions).

---

## Sprint 3 — Décisions actées et observations

- [x] **Providers MVP**
      → **Décision (sprint 3) :** OpenAI Whisper API (priorité 1) + faster-whisper local (priorité 2). Deepgram, AssemblyAI, Speechmatics : différés Phase 2 (à câbler quand un user en aura besoin réel).

- [x] **Clés API SaaS via env vars docker-compose**
      → **Décision (sprint 3) :** `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, etc. dans `.env`, lus par Pydantic Settings du backend, retransmis aux containers worker via `docker run -e ...`. Pas d'OpenBao Sprint 3, cohérent avec cookies Sprint 2. Rebranchage OpenBao au sprint "Ma stack".

- [x] **Pool shared faster-whisper sur pve2**
      → **Décision (sprint 3) :** docker-compose.pve2.yml dédié (image cuda variante). Worker toujours up via `restart: unless-stopped` + `runtime: nvidia`. Provisionné manuellement par sysadmin (pas par le backend). Pull image GHCR `agflow-transcription-worker-cuda:latest`.

- [x] **Pools user provisionnés à la demande**
      → **Décision (sprint 3) :** `WorkerManager` backend lance des containers Docker via `asyncio.create_subprocess_exec` (pattern Sprint 2 scraper_orchestrator). Slider 1-5 workers/user (workers_count). Image CPU générique `agflow-transcription-worker:latest` (les workers SaaS n'ont pas besoin de GPU).

- [x] **Auto-stop workers user idle**
      → **Décision (sprint 3) :** asyncio Task interne au backend (lifespan), period 60s, threshold 5 min. Pas d'APScheduler — simple boucle qui appelle `auto_stop_idle()`. Le pool shared est exclu (jamais auto-stoppé).

- [x] **Bascule sur épuisement de crédit**
      → **Décision (sprint 3) :** `credit_basculer.handle_key_exhausted` : stop des workers de la clé + reassign des `transcription_jobs` pending vers `shared_default`. Déclenché par le worker à la détection HTTP 402 (via error_classifier). Pour Sprint 3, le worker met juste la clé en `exhausted` côté DB ; la bascule effective est faite par le backend quand il consomme PG NOTIFY `keys_changes` (wiring complet Sprint 6 "Ma stack" — pour l'instant `handle_key_exhausted` est appelable manuellement).

- [x] **Image worker variante CUDA**
      → **Décision (sprint 3) :** `Dockerfile.cuda` avec base `nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04`. Buildée par CI GitHub Actions (`build-workers.yml` matrix). Variante CPU pour pve1 + variante CUDA pour pve2.

- [ ] **Polling crédit Deepgram**
      Reporté Phase 2. Impossible Sprint 3 sans clé Deepgram câblée et sans use case immédiat. À recoder quand le sprint "Ma stack" introduira le sous-onglet quota et qu'un user aura ajouté Deepgram.

- [ ] **Diarization (interviews à plusieurs voix)**
      Reportée Phase 2. À évaluer selon retours utilisateurs Sprint 5 (synthèse) sur la qualité d'extraction.

- [ ] **Retry exponential backoff**
      Reporté Phase 2. Sprint 3 incrémente `attempts` au claim mais ne re-met pas le job en `pending` après échec. À ajouter quand un cas réel de transient error sera observé en prod.

- [ ] **Audios > 25 MB OpenAI Whisper**
      Reporté Phase 2. OpenAI Whisper a une limite de 25 MB par fichier. Sprint 3 considère que les MP3 mono 16 kHz 32 kbps font ~14 MB pour 1h, donc seuls les contenus > 1h45 dépassent. Quand on rencontrera, on splittera côté worker via ffmpeg + concat des résultats.

- [ ] **`stop_workers_for_key` requête key_id → (user_id, provider)**
      `WorkerManager.stop_workers_for_key` fait un `fetchrow` sur `user_transcription_keys` pour résoudre la clé → workers. Pourrait être inlined avec un JOIN dans la requête de stop pour économiser un round-trip. Acceptable MVP.

- [ ] **`event_handlers.on_item_done` fait 3 round-trips DB**
      Pour résoudre `(source_id → role_project_id → user_id) + (user_id → primary_key) + insert_job`. Acceptable MVP, à fusionner si latence devient sensible.

- [ ] **`reassign_pending_to_shared` rowcount via parsing du tag**
      Le helper utilise `int(tag.split()[-1])` pour récupérer le nombre de rows updated. Sensible aux changements de format asyncpg. À remplacer par `RETURNING id` + `len(rows)` si on veut plus de robustesse.

- [ ] **Worker nécessite `worker.config.Settings()` instancié à l'import**
      Comme le backend Sprint 1 — un conftest avec `os.environ.setdefault` permet l'import en test. Lazy init ferait sens à terme (cohérent avec dette Sprint 1).

---

## Sprint 2 — Décisions actées et observations

- [x] **OpenBao reportée pour les credentials de scraping**
      → **Décision (sprint 2) :** cookies passés via env vars docker-compose
      (`YOUTUBE_COOKIES_B64`, `INSTAGRAM_COOKIES_B64`, `TIKTOK_COOKIES_B64`).
      Le backend lit ces env vars depuis Settings et les retransmet au
      container scraper via `docker run -e ...`. Pas de table
      `user_credentials` consultée Sprint 2. Rebranchage OpenBao prévu au
      sprint "Ma stack" (spec 07).

- [x] **Build images Docker hors local**
      → **Décision (sprint 2) :** pas de `docker build` sur la machine de
      dev Windows. Pipeline GitHub Actions construit les 4 images
      (`base`, `youtube`, `instagram`, `tiktok`) et les pousse sur GHCR
      (`ghcr.io/<owner>/agflow-scraper-{platform}`). Tags `:latest` /
      `:sha-<short>` / `:vX.Y.Z`. Workflows : `.github/workflows/{tests,build-scrapers}.yml`.

- [x] **Docker SDK : subprocess vs aiodocker**
      → **Décision (sprint 2) :** `asyncio.create_subprocess_exec("docker",
      ...)` conforme spec 03. `aiodocker` reste envisagé Phase 2 si la
      complexité justifie (typing, gestion d'erreurs plus riche).

- [ ] **`claim_next_pending_job` ne JOIN pas `sources`**
      L'orchestrator fait un second `get_source(source_id)` après le claim.
      2 round-trips au lieu d'1. Acceptable MVP, à fusionner via JOIN si
      la latence devient sensible (charge >100 jobs/min).

- [ ] **`docker_runner` ne draine pas stderr**
      Le subprocess Docker écrit stderr sur PIPE jamais lu. Risque de
      blocage du process si stderr volumineux (les scrapers émettent les
      erreurs en NDJSON sur stdout, donc cas marginal). À durcir
      ultérieurement avec lecture concurrente stderr → log warning.

- [ ] **`event_handlers` ne crée pas de `transcription_jobs` sur `item_done`**
      Comportement attendu : Sprint 3 (transcription) introduira ce
      câblage. Items resteront en `audio_ready` après Sprint 2.

- [ ] **Exit code `download.run` simplifié**
      L'impl renvoie systématiquement `3` dès qu'un item échoue (au lieu
      de `2` total / `3` partiel comme la spec). L'orchestrator lit
      `complete.failed` / `complete.downloaded` pour distinguer.

- [ ] **Pas de retry orchestrator sur job failed**
      `mark_job_failed` est terminal. `attempts` est incrémenté par le
      claim mais aucune logique ne re-met le job en `pending` après échec.
      À ajouter selon spec retry plus tard.

- [ ] **WebSocket heartbeat 30s**
      Le subagent a ajouté un heartbeat `{"type": "ping"}` toutes les 30s
      côté `ws_relay` (non spécifié, idiomatique FastAPI). À documenter
      côté frontend si on veut filtrer les pings dans les abonnés.

---

## Sprint 1 — Observations émergentes (à reprendre en Phase 2)

- [ ] **`Settings()` instancié au top-level dans `config.py`**
      Pattern dicté par la spec 02 mais qui force l'instanciation à
      l'import. Conséquence : `tests/conftest.py` doit faire un
      `os.environ.setdefault(...)` au top du module pour que la collection
      pytest n'explose pas (`ValidationError` sur les env vars manquantes).
      → **À refactorer :** lazy init via fonction `get_settings()` ou
      `@lru_cache` dès qu'on aura besoin de plus de flexibilité (Sprint 5
      probablement, quand on ajoutera des configs LLM).

- [ ] **TypeScript `5.4.0` introuvable sur npm**
      Le plan détaillé Sprint 1 indiquait `typescript@5.4.0` mais cette
      version n'existe pas (npm passe de `5.4.0-beta` à `5.4.2`). Pinné
      sur `5.4.5` (dernière patch de la série 5.4).
      → **Action :** mettre à jour le plan détaillé Sprint 1 si on le
      référence comme template pour des plans futurs.

- [ ] **Vulnérabilité Next.js 14.2.0**
      `npm install` reporte un CVE sur `next@14.2.0`. Pas bloquant pour
      Sprint 1 (squelette local), à patcher avant tout déploiement
      public.
      → **Action :** upgrade vers la dernière patch 14.2.x au début du
      Sprint 2 ou 3 selon les retours sécurité.

- [ ] **Vérification end-to-end Phase F8 partielle (pas de Docker)**
      Environnement de dev Windows actuel n'a pas Docker installé. Les
      vérifications passées : pytest backend (10/10), npm test (3/3),
      typecheck, ruff. Non vérifiées : `docker compose up`, application
      des migrations sur Postgres réel, création buckets MinIO,
      activation OpenBao KV v2, healthcheck HTTP backend, page frontend
      via navigateur.
      → **Action :** installer Docker Desktop ou exécuter le sprint sur
      la cible LXC pve1 pour valider la stack complète avant Sprint 2.

- [ ] **Lock fichiers Windows par watchers IDE**
      `npm install` initial a échoué sur ENOTEMPTY à cause de processes
      node/IDE qui tenaient des fichiers `node_modules/next/dist/...`.
      Workaround : renommer `node_modules` puis relancer (artefact
      `node_modules_locked_*` resté dans `frontend/` à nettoyer).
      → **Action :** ajouter `node_modules_locked_*/` au `.gitignore`
      ou nettoyer manuellement quand l'IDE relâche les locks.

---

## Sprint 7 — Décisions actées et observations

Sprint 7 = export ag.flow + onglet Rôle frontend. Backend Phase A/B (livré
avant pause) puis Phase D (ce commit) = page rôle complète + WebSocket de
progression du push.

- [x] **Push ag.flow : sync HTTP ou async WebSocket ?**
      → **Décision (sprint 7) :** **variante A — sync HTTP + WS pour
      progression**. L'endpoint `POST /role-projects/{id}/push-to-agflow`
      reste synchrone et renvoie le résultat final (2-10s typique). Le
      canal WS `agflow_push_events` sert uniquement à afficher les étapes
      intermédiaires en live (`zip_built` → `role_ready` → `zip_uploaded`
      → `prompts_generated` → `done` ou `failed`). Plus simple à coder, le
      client gère l'erreur HTTP comme d'habitude, le WS est purement
      visuel et peut se déconnecter sans casser la logique.

- [x] **Format du payload `agflow_push_events`**
      → **Décision (sprint 7) :** JSON
      `{tenant_id, project_id, step, status, detail?}` avec
      `step ∈ {zip_built, role_ready, zip_uploaded, prompts_generated,
      done, failed}` et `status ∈ {in_progress, done, failed}`. Filtrage
      par `tenant_id` côté `WSRelay` comme les autres canaux. Les
      émissions sont best-effort : un échec d'émission `pg_notify` est
      loggé en warning mais ne casse jamais le push.

- [x] **Échec partiel sur `prompts_generated` : couleur du banner ?**
      → **Décision (sprint 7) :** **rouge** (border-left `#dc2626`),
      conformément à la convention StatusIndicator (rouge = action
      requise). Texte explicite "Rôle uploadé sur ag.flow, mais la
      génération du prompt a échoué" + bouton "Réessayer la génération du
      prompt" qui appelle `/generate-prompts-on-agflow`. Pas d'orange
      malgré que ce soit un état "partiel" — le rouge match la sémantique
      "il faut faire quelque chose".

- [x] **Conflit 409 sur `display_name` côté ag.flow**
      → **Décision (sprint 7) :** **bloquant**, pas de rename inline.
      Modale d'erreur dédiée affichant "Le nom 'X' existe déjà sur
      ag.flow. Renommez votre projet (paramètres) avant de pousser." Le
      frontend détecte le 409 via `ApiError.status === 409`. Le rename se
      fait côté Role Builder, pas côté push-flow.

- [x] **Édition manuelle d'un role_document après génération (était open)**
      → **Décision (sprint 7) :** `PATCH /role-documents/{id}` édite le
      content **in-place** sur la version courante, sans créer de nouvelle
      version. Si l'utilisateur veut versionner ses éditions, il bascule
      le `locked` (avec `lock_document` / `unlock_document`) — un doc
      verrouillé n'est plus écrasable par régénération. UI : bouton
      "Éditer" désactivé si `locked`, bouton "Régénérer" désactivé si
      `locked`.

- [x] **Diff visuel des role_documents (était open)**
      → **Décision (sprint 7) :** `react-diff-viewer-continued` (MIT, 4.x)
      en split view, leftTitle/rightTitle dynamiques. Le package est typé
      comme une class component legacy → encapsulation en
      FunctionComponent typée minimaliste pour rester compatible TS
      strict + React 18.

- [x] **Auto-cleanup des tests Testing Library**
      → **Décision (sprint 7) :** `globals: false` côté Vitest désactive
      le cleanup implicite de RTL. Ajout de `afterEach(cleanup)` dans
      `src/test/setup.ts` pour éviter les fuites de DOM entre tests
      composants. Important pour les tests qui assertent l'absence d'un
      élément (`queryBy*().toBeNull()`).

- [x] **Cache SWR entre tests**
      → **Décision (sprint 7) :** SWR mémorise par clé entre tests. Pour
      les tests composants qui dépendent du cycle loading→loaded, wrap le
      composant dans `<SWRConfig value={{ provider: () => new Map() }}>`.
      Pattern interne (`FreshSWR` dans `VersionDiff.test.tsx`).

- [x] **Surcharges typées de `useWebSocketEvent`**
      → **Décision (sprint 7) :** signature de `useWebSocketEvent`
      surchargée par canal : `'agflow_push_events'` reçoit
      `PushEventPayload`, les 4 autres canaux reçoivent `WSEventPayload`.
      Les callers obtiennent le bon type sans cast. Implémentation
      interne : `Listener = (payload: unknown) => void` dans
      `connection.ts`.

- [ ] **Suppression d'un rôle ag.flow depuis Role Builder**
      Reporté Phase 2. Pour MVP, l'utilisateur supprime via l'admin
      ag.flow s'il le souhaite. Si on supprime un projet Role Builder, on
      garde le `target_role_id` historique mais on ne peut plus pousser.

- [ ] **Endpoint multipart streamé pour ZIP > 10 MB**
      Reporté. Pour un rôle typique (3 sections × 10 docs × ~500 mots),
      le ZIP fait ~100-200 KB. Largement sous les limites HTTP standard.
      Si on dépasse 10 MB un jour, prévoir un endpoint multipart streamé
      côté ag.flow + côté Role Builder.

- [ ] **Tests end-to-end du push réel**
      Reporté. Le push a été testé unitairement (build ZIP, NOTIFY,
      orchestration). Test E2E réel = pousser un rôle complet vers une
      instance ag.flow staging et valider l'apparition dans son admin.
      À faire dès qu'une instance ag.flow staging est dispo et que la
      Phase 8 (publication) est entamée.

---

## Sprint 8 — Décisions actées et observations

Sprint 8 = publication GitHub. Dernier sprint MVP planifié.

### Licence et OAuth

- [x] **Licence par défaut suggérée dans le README**
      → **Décision (sprint 8) :** **option C — sélecteur utilisateur**
      dans `PublishToGithubConfigDialog`. 5 choix : `none` /
      `polyform-nc` / `cc-by-nc-sa-4.0` / `cc-by-4.0` / `mit`. Persisté
      dans `role_publication_config.license_choice` (migration 0013).
      Le `readme_builder.render_license_file` retourne le contenu d'un
      fichier LICENSE selon le choix (ou None si 'none' → pas de fichier
      publié). Validation côté Pydantic via `Literal` (rejette
      ex. 'GPL-3.0' avec 422). La licence du logiciel reste
      PolyForm-NC (cf. fichier `LICENSE` au repo root, sprint 8 chore).

- [x] **State CSRF : in-memory ou table PG ?**
      → **Décision (sprint 8) :** **option B — table PG `oauth_states`**
      (migration 0012). `state` PRIMARY KEY, `expires_at` à 10 min.
      Helper `consume_state` utilise `DELETE...RETURNING` pour atomicité
      anti-replay. `cleanup_expired` à la demande (pas de pg_cron MVP).
      Marche en multi-instance et survit aux redémarrages. Plus safe que
      l'in-memory du spec original.

- [x] **Multi-comptes GitHub par user**
      → **Décision (sprint 8) :** **1 seul compte par user** pour MVP
      (UNIQUE constraint sur `user_id` déjà en place dans la table
      `github_integrations` migration 0006). Reportée Phase 2 si besoin.

- [x] **Indépendance push ag.flow ↔ publication GitHub**
      → **Décision (sprint 8) :** totalement indépendants. L'utilisateur
      peut publier sur GitHub un rôle qu'il n'a pas (encore) poussé sur
      ag.flow. Aucune dépendance entre `target_role_id` (ag.flow) et
      `role_publications` (GitHub) au niveau DB.

### Architecture publication

- [x] **N PUT séquentiels vs API Trees pour 1 commit**
      → **Décision (sprint 8) :** **N PUT séquentiels** pour MVP
      (~30 fichiers × 60 appels ≈ 10-20 s par publication). Acceptable.
      Optimisation Trees (1 commit pour N fichiers via `git_data` API)
      reportée Phase 2 quand le volume justifiera.

- [x] **Sha tracking pour update existing files**
      → **Décision (sprint 8) :** GET `/contents/{path}` avant PUT pour
      récupérer le sha si fichier existant (404 → création neuve, 200 →
      update). Implémenté dans `GitHubApiClient.get_content_sha` qui
      retourne `str | None`. Permet la republication propre sans
      recréer l'arborescence.

### Reportés Phase 2

- [ ] **Optimisation Trees API** (1 commit pour N fichiers)
      Quand le volume de publications devient significatif.

- [ ] **Tags / releases auto par version**
      Pas dans le scope MVP. Chaque republication = un nouveau commit,
      pas de tag git.

- [ ] **Modération + vitrine officielle**
      Phase ultérieure, à designer séparément (probablement un service
      ag.flow distinct).

- [ ] **Format final du README** : badges shields.io, stats
      Itération design ultérieure.

- [ ] **OAuth pour autres providers de transcription**
      Cf. spec 07 — OAuth Deepgram/AssemblyAI/etc. quand disponible.

- [ ] **Tests E2E du push réel vers une instance GitHub**
      Tests unitaires couvrent l'orchestration (httpx mocké). Test E2E =
      pousser un rôle complet vers un repo de test et valider que tous
      les fichiers apparaissent. À faire dès qu'un repo de test est
      configuré.

---

## Convention de naming

Pour cocher un item dans ce fichier, préférer le format :

```markdown
- [x] **Question initiale**
      Description originale.
      → **Décision (sprint X) :** [résumé en 1-2 phrases].
```

Cela permet de tracer l'historique des décisions sans perdre le contexte.

---

**Document précédent :** `11-sequence-diagrams.md`

**Fin de la spec.**
