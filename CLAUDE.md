# agflow.roles — Stack d'acquisition de corpus — Instructions Claude Code

## Projet

**Roles (ex-Role Builder)** est la **stack d'acquisition de corpus** de l'écosystème ag.flow V2 : elle scrape des sources vidéo (YouTube, Instagram, TikTok), transcrit l'audio, et **dépose les transcripts dans docflow**. C'est tout — la synthèse des rôles est faite par le pilote (Claude web), hors de cette stack.

Consommation via la passerelle MCP (`wrk.yoops.org`), namespace `roles__*` : modèle **ticket asynchrone** (submit → request_key → pull statut → get_corpus incrémental). Ressources d'exécution partagées entre tous les acteurs via queues PG.

> ⚠️ **Refonte V2 (2026-07-04)** : le pipeline de synthèse (5 étages, Mistral), l'export ag.flow, la publication GitHub et le chunking/pgvector sont **abandonnés**. Voir `docs/specs/OBSOLETE.md`.

**Documents fondateurs — à lire en premier sur toute nouvelle session de conception** :
1. `docs/specs/v2/00-fondations-v2.md` — vision V2, ce qui survit/tombe, architecture, frontière des données
2. `docs/specs/v2/01-protocole-mcp.md` — tools `roles__*`, cycle de vie des requêtes, deltas du modèle de données

Les specs V1 conservées (01, 02, 03, 04, 07) restent des références valides **avec les adaptations en bannière**. Les specs 05, 06, 08, 09, 10 sont obsolètes.

**Scope strict V2** : acquisition et livraison de corpus référencé. La stack ne fait **aucune synthèse**, ne connaît pas la notion de rôle, ne proxifie jamais le contenu des transcripts (lecture via `docflow__*`).

**Standard de qualité** : code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis, pas de "c'est pas grave", pas de "on simplifiera plus tard".

## Architecture V2

- **Façade MCP `roles__*`** derrière la passerelle : `submit_acquisition`, `select_items`, `request_status`, `list_requests`, `get_corpus`, `cancel_request`, `retry_failed`
- **Double posture MCP** : backend (`roles__*`) ET client (dépose dans docflow via la passerelle, avec identité machine propre)
- **Pipeline par item** : `pending_download → downloading → audio_ready → queued_transcription → transcribing → transcribed → depositing → deposited` (ou `failed`)
- **Sélection deux temps** : `discover_only` → examen par le pilote → `select_items` ; raccourci filtres (`max_items`, `since`, `min/max_duration_s`) avec sélection auto
- **Livraison incrémentale** : `get_corpus` retourne à tout moment les refs docflow des items déposés (`only_new`, curseurs par appelant)
- **Un document docflow par vidéo** (type `transcript`, métadonnées : plateforme, URL source, durée, date, request_key, provider)
- **Hébergement** : compose sur host `usage=ressources` (portail devpod) ; worker faster-whisper GPU épinglé pve2

## Stack technique

- **Backend** : Python 3.12 + FastAPI + asyncpg (**pas SQLAlchemy**) + structlog JSON + pytest
- **BDD** : PostgreSQL 16 (extensions `uuid-ossp`, `pgcrypto` — **pgvector plus requis en V2**)
- **Queues** : pattern `FOR UPDATE SKIP LOCKED` (cf. `docs/specs/01-data-model.md` §9), `tenant_id` partout, FIFO multi-acteurs (priority/quotas = hooks V3)
- **Stockage objets** : MinIO — `corpus-audio` (interne, `keep_audio`), `corpus-transcripts` (format pivot JSON interne). Le texte consommable vit dans **docflow**, jamais de binaire côté docflow.
- **Secrets** : coffre existant via `${vault://...}` (cookies scraping, clés SaaS transcription, identité machine passerelle)
- **Transcription** : faster-whisper local (GPU pve2) + SaaS (OpenAI Whisper prioritaire ; Deepgram/AssemblyAI/Speechmatics différés) ; format pivot JSON inchangé
- **Scraping** : containers Docker one-shot (yt-dlp + ffmpeg), contrat **stdin JSON / stdout NDJSON figé** — ne pas le modifier
- **Frontend** : l'interface primaire est conversationnelle (pilote + MCP). Le frontend Next.js existant est en sursis — vue admin minimale à cadrer, ne rien y développer de nouveau sans décision.

## Vocabulaire canonique V2

**Requête d'acquisition** (`acquisition_requests`, `request_key` = slug lisible, clé de reprise conversationnelle) · **Source** (URL : chaîne/playlist/compte/vidéo) · **Item** (une vidéo) · **Dépôt** (transcript → document docflow) · **Pilote** (Claude web — soumet, sélectionne, pull, synthétise ailleurs) · **Corpus** (ensemble des documents docflow d'une requête).

Vocabulaire V1 à **ne plus employer** : role_project, rôle ag.flow, signal/cluster/plan/run de synthèse, prompt orchestrateur, export ZIP, chunk/embedding.

## Commandes essentielles

```bash
docker compose up -d
./scripts/apply_migrations.sh
./scripts/init_minio.sh
cd backend && uv sync
cd backend && uv run uvicorn role_builder.main:app --reload    # :8000
cd backend && uv run pytest -v
cd backend && uv run ruff check src/ tests/
curl http://localhost:8000/health/
```

## Conventions de code

### Python (backend)
- Python 3.12+, async/await partout ; asyncpg direct (helpers `fetch_one`/`fetch_all`/`execute`)
- Pydantic v2 (DTOs + Settings) ; structlog — **jamais** `print()`
- Type hints partout, `from __future__ import annotations`
- Fichiers max 300 lignes ; classes SRP ; méthodes 5-15 lignes
- Règles détaillées : `@docs/python-dev-rules.md` · Tests : `@docs/tests-python.md`

### Base de données
- Migrations SQL numérotées dans `migrations/` à la racine ; pas d'ORM, pas d'Alembic
- IDs `uuid`, dates `timestamptz` UTC, `tenant_id` sur toutes les tables
- Deltas V2 (nouvelle table `acquisition_requests`, `corpus_pull_cursors`, drops synthèse/publication) : `docs/specs/v2/01-protocole-mcp.md` §4
- Toute nouvelle table → migration SQL + test de migration

### Tests
- pytest + pytest-asyncio ; fixture `client` (TestClient httpx) ; `DISABLE_AUTH=true` en test
- **TDD** : test rouge → impl → test vert → commit

## Règles de workflow

### Cycle de l'architecte
**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Livraison
- Ne livre **jamais** le code ni en test ni sur git sans demande explicite
- Ne modifie pas `.env` sauf si demandé
- Commit messages en français, format conventionnel (`feat:`, `fix:`, `chore:`, `docs:`, `test:`…)

### Vérification avant validation
1. Le code s'exécute sans erreur (lint + build)
2. Le cas nominal fonctionne (test unitaire ou manuel)
3. Les imports ajoutés existent réellement
4. Pas de régression sur les fichiers modifiés

### Discipline d'exécution
- Exécute directement, rapporte uniquement le résultat final
- Termine TOUTES les étapes d'un plan avant de faire un résumé
- Pas de raccourci "pour simplifier"
- Si tu rencontres un problème, signale-le et propose une solution

## Outils Claude Code

### Context7 — documentation live
Avant d'écrire du code utilisant FastAPI, Pydantic v2, asyncpg, MinIO Python, httpx, faster-whisper, yt-dlp. Les API évoluent, ne te fie pas à ta mémoire.

### Serena — navigation sémantique
Avant un refactor, pour comprendre les dépendances ou trouver les usages d'un symbole.

### Superpowers skills
`writing-plans` · `executing-plans` / `subagent-driven-development` · `systematic-debugging` · `test-driven-development` · `brainstorming` · `verification-before-completion`

### /review
Avant de présenter un changement multi-fichiers (>3 fichiers ou >100 lignes).

### /commit
Uniquement sur demande explicite. Format français conventionnel.

## Auto-amélioration

Quand tu fais une erreur ou que l'utilisateur te corrige :
- Ajoute une leçon dans `LESSONS.md` — format : `- [module] description courte`
- Relis `@LESSONS.md` en début de tâche touchant un module mentionné
- Max 50 lignes — consolide les leçons similaires

## Notifications de skills

Quand tu invoques une skill, affiche un marqueur visuel **avant** d'exécuter :

> **`🟢 SKILL`** → _nom-de-la-skill_ — raison en une phrase
