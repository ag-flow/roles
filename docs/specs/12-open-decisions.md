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

- [ ] **Diff visuel des role_documents (versions)**
      Algorithme à utiliser : diff-match-patch, jsdiff, autre ?

- [ ] **Edition manuelle d'un role_document après génération**
      Flag `locked=true` pour empêcher l'écrasement par régénération
      automatique. UI à designer pour le toggle.

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
