# agflow.roles — Role Builder — Instructions Claude Code

## Projet

**Role Builder** est une webapp qui construit des **rôles ag.flow** à partir de corpus audio scrapés sur YouTube, Instagram et TikTok. Pipeline complet : scraping → transcription (faster-whisper local ou SaaS) → chunking + embeddings (pgvector) → synthèse en 4 étages (extractor → clusterer → decomposer → document_writer) → export ZIP vers ag.flow. Mistral via ag.flow pour la synthèse, Harpocrate pour les secrets, MinIO pour les corpus.

**Spec complète** : `docs/specs/00-overview.md` (point d'entrée). Lire d'abord ce fichier, puis le fichier du sprint courant + `01-data-model.md` (référence SQL transverse). 13 fichiers de spec figés (00 → 12), 8 sprints planifiés.

**Scope strict** : produire des rôles ag.flow et rien d'autre. Pas de gestion d'agents, pas de dockerfiles ag.flow, pas de génération d'avatars, pas de modération de contenu publié.

**Standard de qualité** : code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis, pas de "c'est pas grave", pas de "on simplifiera plus tard". Chaque tâche est faite correctement ou pas du tout.

## Stack technique

- **Backend** : Python 3.12 + FastAPI + asyncpg (**pas SQLAlchemy**) + structlog JSON + pytest
- **Frontend** : Next.js 14 (App Router) + React 18 + TypeScript strict + SWR + Vitest
- **BDD** : PostgreSQL 16 + **pgvector** (embeddings) + extensions `uuid-ossp` et `pgcrypto`
- **Temps réel** : WebSocket alimenté par `LISTEN/NOTIFY` PostgreSQL — pas de Redis, pas de message broker externe
- **Stockage objets** : MinIO — 3 buckets : `corpus-audio`, `corpus-transcripts`, `corpus-thumbnails`
- **Secrets** : **Harpocrate** (coffre end-to-end encrypted) — tous les secrets via `${vault://api1:SECRET_NAME}`
- **LLM synthèse** : Mistral via les ressources LLM d'**ag.flow** (la clé Mistral est dans le coffre ag.flow, jamais côté Role Builder)
- **Transcription** : faster-whisper en local (GPU) ou providers SaaS (OpenAI Whisper, Deepgram, AssemblyAI, Speechmatics) avec clés fournies par l'utilisateur
- **Scraping** : containers Docker one-shot (yt-dlp + ffmpeg) avec contrat stdin JSON / stdout NDJSON
- **Intégration ag.flow** : `https://docker-agflow.yoops.org` (OpenAPI à `/openapi.json`)

## Dev & cible

- **Développement** : local Windows (uv + node), `docker-compose up` lance Postgres + MinIO + backend + frontend
- **Cible homelab** :
  - **pve1** : backend FastAPI, scrapers (containers one-shot), workers de transcription SaaS (légers, sans GPU)
  - **pve2** : worker faster-whisper du pool shared (accès GPU RTX 4090)
- **Mono-utilisateur** en MVP (Beard), schéma multi-tenant ready dès le départ (`tenant_id` partout)
- **Phasage** : Phase 1 in-app (scrapers et worker dans ce repo) → Phase 2 repos séparés + CI corrective → Phase 3 délégation des scrapers à ag.flow (le worker de transcription reste géré par l'app). Voir `docs/specs/00-overview.md` § Stratégie de phasage.

## Commandes essentielles

```bash
# Stack complète (Postgres + MinIO + backend + frontend)
docker compose up -d
docker compose logs -f backend                            # Suivi des logs backend

# Init des dépendances (à lancer une fois après docker compose up)
./scripts/apply_migrations.sh                             # Applique les migrations SQL
./scripts/init_minio.sh                                   # Crée les 3 buckets
# Backend local (Windows, hot-reload)
cd backend && uv sync
cd backend && uv run uvicorn role_builder.main:app --reload    # :8000
cd backend && uv run pytest -v                                  # Tests Python
cd backend && uv run ruff check src/ tests/                     # Lint
cd backend && uv run ruff format src/ tests/                    # Format

# Frontend local (Windows)
cd frontend && npm install
cd frontend && npm run dev                                # :3000, proxy /api -> backend:8000
cd frontend && npm test                                   # Vitest
cd frontend && npm run typecheck                          # tsc --noEmit
cd frontend && npm run lint                               # ESLint

# Healthcheck end-to-end
curl http://localhost:8000/health/                        # {"status":"ok","db":true}
```

## Layout du code

```
agflow.roles/
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/role_builder/
│   │   ├── main.py              # FastAPI app + lifespan
│   │   ├── config.py            # Pydantic Settings (env vars)
│   │   ├── logging_setup.py     # structlog JSON
│   │   ├── db.py                # asyncpg pool
│   │   ├── routes/              # Routers FastAPI (health, sources, corpus, synthesis, agflow_export…)
│   │   ├── schemas/             # DTOs Pydantic
│   │   └── services/
│   │       ├── minio_client.py
│   │       ├── ws_relay.py              # Pont LISTEN/NOTIFY → WebSocket
│   │       ├── chunking_worker.py       # Sprint 4
│   │       ├── synthesis/               # Sprint 5 (extractor, clusterer, decomposer, document_writer, identity_synthesizer)
│   │       ├── agflow/                  # Sprint 7 (export ZIP + push)
│   │       └── github_publish/          # Sprint 8
│   └── tests/
├── frontend/                    # Next.js 14, App Router
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── app/                 # Pages App Router (projects, my-stack, …)
│       ├── components/          # Composants réutilisables (dont StatusIndicator)
│       ├── hooks/               # useWebSocket, etc.
│       └── lib/                 # Clients API typés (projects.ts, sources.ts, corpus.ts…)
├── migrations/                  # SQL numérotés à la racine (0001_extensions.sql … 0011_views.sql)
├── docker/
│   ├── scrapers/                # base + youtube + instagram + tiktok (containers one-shot)
│   └── transcription-worker/    # Worker configurable par provider (faster-whisper, OpenAI, Deepgram…)
├── docs/
│   ├── specs/                   # 13 fichiers figés (00-overview → 12-open-decisions)
│   ├── patterns/                # Design patterns (référence transverse)
│   ├── python-dev-rules.md
│   ├── tests-python.md
│   └── sonarQube.md
├── scripts/
│   ├── apply_migrations.sh
│   ├── reset_db.sh
│   └── init_minio.sh
├── docker-compose.yml           # Dev : postgres + minio + backend + frontend
└── docker-compose.prod.yml      # Prod : à finaliser quand MVP validé
```

## Conventions de code

### Python (backend)
- Python 3.12+, async/await partout
- **Pas de SQLAlchemy** — asyncpg direct avec helpers `fetch_one` / `fetch_all` / `execute` dans `db/pool.py`
- Pydantic v2 pour les DTOs, Pydantic Settings pour la config
- Logs structurés via `structlog.get_logger(__name__)` — **jamais** `print()`
- `type` hints partout, `from __future__ import annotations` en tête de fichier
- Fichiers max 300 lignes ; classes SRP ; méthodes 5-15 lignes
- Règles détaillées : `@docs/python-dev-rules.md`
- Règles tests : `@docs/tests-python.md`

### TypeScript (frontend)
- Next.js 14 **App Router** (pas Pages Router), composants serveur par défaut, `"use client"` au cas par cas
- `strict: true`, `noUncheckedIndexedAccess: true`
- Composants fonctionnels + hooks, pas de classes
- **SWR** pour tout appel API GET, pas de `useEffect + fetch` direct ; mutations via fonction async appelée depuis un handler
- WebSocket unique géré par un manager (`useWebSocket` hook ou contexte) qui dispatch par type d'event
- Clients API typés par domaine dans `src/lib/` (`projects.ts`, `sources.ts`, `corpus.ts`, `synthesis.ts`, `my-stack.ts`)
- Fichiers max 300 lignes
- Props typées via `interface`, exports nommés
- Langue de travail = français (UI, code comments, doc) ; pas d'i18n côté MVP

### Base de données
- Migrations = fichiers SQL numérotés dans `migrations/` à la racine (ex: `0001_extensions.sql` … `0011_views.sql`)
- Schéma géré en SQL brut, pas d'ORM, pas d'Alembic
- Extensions requises : `uuid-ossp`, `pgcrypto`, **`vector`** (pgvector)
- IDs en `uuid`, dates en `timestamptz` (UTC), `tenant_id` sur **toutes** les tables (multi-tenant ready)
- Pull de queue : pattern standard `FOR UPDATE SKIP LOCKED` (cf. `docs/specs/01-data-model.md` § 9)
- Triggers PG NOTIFY pour les événements temps réel (pattern dans 01-data-model § 6)
- Toute nouvelle table → migration SQL + test de migration

### Stockage objets et secrets
- **Secrets app** : Harpocrate vault. Chemins vault :
  - `users/{email_slug}/scraping/{platform}/{cred_id}` — cookies de scraping
  - `users/{email_slug}/transcription/{provider}/{key_id}` — clés SaaS transcription
  - `github/{tenant_id}/{user_id}` — tokens GitHub OAuth
- **Secret Mistral** : pas géré par Role Builder — référence stockée dans `role_projects.mistral_secret_ref`, le secret réel vit dans le coffre ag.flow
- **Buckets MinIO** : `corpus-audio/{tenant_id}/{role_id}/{source_id}/{item_id}.mp3`, `corpus-transcripts/.../{item_id}.json`, `corpus-thumbnails/...`
- **Format pivot transcript** : JSON normalisé indépendant du provider de transcription (cf. `docs/specs/04-transcription.md` § Format pivot). Tout provider est adapté vers ce format à la sortie.

### Tests
- **Backend** : pytest + pytest-asyncio ; fixture `client` (TestClient httpx)
- **Frontend** : Vitest + React Testing Library ; `describe`/`it`, pas de `test`
- **TDD** : test rouge → impl → test vert → commit
- Couverture minimale par zone : voir `docs/tests-python.md`

### Indicateurs visuels (convention spec)
Partout où on affiche le statut d'un credential (cookies de scraping, clé SaaS de transcription, secret Mistral ag.flow, token GitHub, clé d'embedding), utiliser le composant `StatusIndicator` :
- 🔴 Rouge : `invalid` / `revoked` / `expired` / `not-found` — action utilisateur requise
- 🟠 Orange : `low` (crédit < 20%) / `expiring soon` / `not-configured` — attention proche
- 🟢 Vert : `active` / `configured` — tout va bien

Domaine d'application principal : onglet "Ma stack" (`docs/specs/07-user-stack.md`) — sous-onglets Comptes réseaux sociaux, Services de transcription, Mistral pour la synthèse, Quotas et garde-fous.

## Règles de workflow

### Cycle de l'architecte
**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Livraison
- Ne livre **jamais** le code ni en test ni sur git sans demande explicite
- Ne modifie pas `.env` sauf si demandé
- Commit messages en français, format conventionnel (`feat:`, `fix:`, `chore:`, `docs:`, `test:`…)

### Vérification avant validation
Avant de déclarer une tâche terminée, **toutes** ces étapes sont obligatoires :
1. Le code s'exécute sans erreur (lint + build)
2. Le cas nominal fonctionne (test unitaire ou manuel)
3. Les imports ajoutés existent réellement
4. Pas de régression sur les fichiers modifiés
5. Si modification frontend : la page charge sans erreur console

### Discipline d'exécution
- Exécute directement, ne décris pas ce que tu vas faire — fais-le
- N'explique pas les étapes intermédiaires. Rapporte uniquement le résultat final
- Termine TOUTES les étapes d'un plan avant de faire un résumé
- Pas de raccourci "pour simplifier"
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas silencieusement

## Outils Claude Code

### Context7 — documentation live
**Quand** : avant d'écrire du code qui utilise FastAPI, Pydantic v2, asyncpg, pgvector, MinIO Python, httpx (ag.flow + GitHub), faster-whisper, yt-dlp, Next.js 14 App Router, SWR, etc. Les API évoluent, ne te fie pas à ta mémoire.

### Serena — navigation sémantique
**Quand** : avant un refactor, pour comprendre les dépendances entre modules, ou pour trouver tous les usages d'une fonction/classe.

### Superpowers skills
- `writing-plans` : rédiger un plan d'implémentation TDD avant de coder
- `executing-plans` / `subagent-driven-development` : exécuter un plan tâche par tâche
- `systematic-debugging` : méthode pour debug un bug ou test qui échoue
- `test-driven-development` : discipline TDD rigoureuse
- `brainstorming` : explorer le design avant d'écrire quoi que ce soit
- `verification-before-completion` : vérifier que le travail est réellement fini avant de le dire

### /review
**Quand** : avant de présenter un changement multi-fichiers (>3 fichiers ou >100 lignes).

### /commit
**Quand** : quand l'utilisateur demande explicitement de committer. Format français conventionnel.

## Auto-amélioration

Quand tu fais une erreur ou que l'utilisateur te corrige :
- Ajoute une leçon dans `LESSONS.md`
- Format : `- [module] description courte de l'erreur et de la bonne pratique`
- Relis `@LESSONS.md` en début de tâche qui touche un module mentionné
- Ne dépasse pas 50 lignes — consolide les leçons similaires

## Notifications de skills

Quand tu invoques une skill via l'outil Skill, affiche systématiquement un marqueur visuel **avant** d'exécuter :

> **`🟢 SKILL`** → _nom-de-la-skill_ — raison en une phrase
