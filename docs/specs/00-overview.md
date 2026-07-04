> ℹ️ **Conservée avec adaptations V2 (2026-07-04).** Vision et intégration ag.flow remplacées par v2/00-fondations-v2.md — la stack devient acquisition pure : scraping → transcription → dépôt docflow, consommée en MCP.
> Voir `docs/specs/v2/00-fondations-v2.md` et `docs/specs/v2/01-protocole-mcp.md`.

# 00 — Vue d'ensemble du projet

> Ce document est le point d'entrée de la spécification. Lis-le en premier
> avant tout autre fichier de cette spec.

## Le projet en une phrase

**Role Builder** est une application web qui permet de construire des rôles
ag.flow à partir de corpus audio scrapés sur YouTube, Instagram, TikTok et
autres plateformes vidéo, avec un pipeline IA qui transforme l'audio en
documents structurés prêts à être importés dans ag.flow.

## Statut et version

- Version de la spec : 1.0
- Statut : figée, prête pour implémentation
- Langue de travail : français (UI, code comments, doc)
- Cible primaire : déploiement homelab Beard, évolution SaaS multi-tenant

## Structure de cette spec

La spec est découpée en blocs cohérents pour permettre une implémentation
progressive. Lire dans l'ordre suggéré :

| Fichier | Contenu | Quand l'utiliser |
|---------|---------|------------------|
| `00-overview.md` | Ce fichier | Toujours, en premier |
| `01-data-model.md` | Schéma SQL complet (référence) | Référence transverse, lire avant de coder |
| `02-foundations.md` | docker-compose, MinIO, OpenBao, init PG | Sprint 1 : poser l'infra |
| `03-scrapers.md` | Containers de scraping + contrat | Sprint 2 : pipeline d'acquisition |
| `04-transcription.md` | Workers, pools, providers, format pivot | Sprint 3 : pipeline de transcription |
| `05-corpus-indexing.md` | Chunking, embeddings, pgvector | Sprint 4 : indexation |
| `06-synthesis.md` | Pipeline 4 étages + Mistral via ag.flow | Sprint 5 : synthèse |
| `07-user-stack.md` | Onglet "Ma stack" (clés, comptes, monitoring) | Sprint 6 : config user |
| `08-export-agflow.md` | ZIP + push vers ag.flow | Sprint 7 : livraison |
| `09-github-publish.md` | OAuth + push GitHub | Sprint 8 : publication publique |
| `10-frontend-ux.md` | Onglets, navigation, composants clés | Transverse front |
| `11-sequence-diagrams.md` | Tous les Mermaid groupés | Référence visuelle |
| `12-open-decisions.md` | TODO d'implémentation | Au fur et à mesure |

## Vision

### Objectif

Permettre à un utilisateur de construire un **rôle** ag.flow à partir du
contenu public (vidéo + audio) d'un expert ou influenceur, en automatisant :

1. La collecte du contenu via scraping multi-plateforme
2. La transformation en corpus textuel exploitable via transcription
3. La synthèse en documents structurés via une chaîne de prompts IA
4. L'export vers ag.flow au bon format
5. Optionnellement, la publication publique du rôle sur le GitHub de
   l'utilisateur

### Genèse

L'application industrialise la démarche manuelle utilisée pour construire le
profil UX à partir du corpus Clea (55 vidéos transcrites avec faster-whisper,
puis analyse manuelle pour extraire heuristiques, principes cognitifs et
mission protocols).

## Scope strict

### Ce que l'application FAIT

- Production de **rôles ag.flow** (et rien d'autre)
- Scraping multi-plateforme via cookies user
- Transcription locale (faster-whisper) ou SaaS (Deepgram, AssemblyAI,
  OpenAI Whisper, Speechmatics) avec clés user
- Pipeline de synthèse en 4 étages
- Export ZIP vers ag.flow via `POST /api/admin/roles/{id}/import`
- Publication GitHub optionnelle

### Ce que l'application NE FAIT PAS

- Pas de gestion d'agents, dockerfiles, ou orchestration runtime
- Pas de génération d'avatars ou d'images
- Pas de configuration d'infrastructure ag.flow
- Pas de tests d'agents intégrés (à terme possible via
  `/api/admin/agents/{agent_slug}/task` d'ag.flow, hors MVP)
- Pas de modération du contenu publié sur GitHub (phase ultérieure)
- Pas de gestion de clé Mistral côté app (déléguée à ag.flow)

## Hosts du déploiement homelab

- **pve1** : backend de l'app, PostgreSQL, scrapers (containers one-shot),
  workers de transcription user (containers SaaS, légers, sans GPU)
- **pve2** : worker de transcription du pool shared (faster-whisper, accès
  GPU RTX 4090)
- **Service séparé** : MinIO (stockage corpus), OpenBao (stockage des
  secrets : cookies réseaux sociaux + clés SaaS transcription)

## Stack technique imposée

- **Backend** : FastAPI (Python 3.12+)
- **DB driver** : asyncpg (pas SQLAlchemy)
- **Logging** : structlog (JSON)
- **Limite de taille** : aucun fichier ne doit dépasser 300 lignes
- **Migrations** : pas d'Alembic, scripts SQL versionnés à la main
- **Base de données** : PostgreSQL 16 + extension pgvector
- **Frontend** : Next.js 14, React, TypeScript strict
- **Communication temps réel** : WebSocket alimenté par PG NOTIFY
- **Containers** : Docker, docker-compose en Phase 1
- **Secrets app-level** : OpenBao (déjà déployé sur le homelab Beard)

## Intégration ag.flow

L'application interagit avec ag.flow via son API REST documentée à
`https://docker-agflow.yoops.org/openapi.json`.

### Endpoints utilisés

| Endpoint | Usage |
|----------|-------|
| `POST /api/admin/roles` | Créer le rôle (vide ou avec metadata) |
| `POST /api/admin/roles/{role_id}/import` | Upload du ZIP de contenu |
| `POST /api/admin/roles/{role_id}/generate-prompts` | Générer le `prompt_orchestrator_md` (étape optionnelle, déclenchée par l'utilisateur) |
| `GET /api/admin/roles/{role_id}` | Vérifier le rôle après import |
| `GET /api/admin/secrets` | Vérifier l'existence du secret Mistral user |

### Délégation LLM

**Important :** la synthèse LLM (extraction de signaux, clustering, écriture
de documents) **n'est pas faite par ag.flow** mais **passe par les services
LLM ag.flow** via le mécanisme d'invocation d'agents/dockerfiles.

L'utilisateur fournit sa propre clé Mistral, qui est stockée dans le coffre
de secrets d'ag.flow (`/api/admin/secrets`). L'application ne stocke pas la
clé Mistral elle-même, juste une référence au secret ag.flow.

Conséquence : si l'utilisateur n'a pas de clé Mistral configurée dans
ag.flow, il ne peut pas exécuter le pipeline de synthèse. L'application
doit afficher un message clair invitant à la configurer.

## Modèle conceptuel : un rôle ag.flow

Conformément au modèle ag.flow, un rôle est composé de :

- Un **identity** (markdown) au niveau du rôle
- Un **display_name** et une **description**
- Une liste de **service types** supportés (claude-code, aider, codex, etc.)
- Des **sections**, chacune contenant des **documents** Markdown atomiques

### Sections verrouillées + sections custom

Trois sections sont systématiquement présentes et verrouillées dans tout
rôle produit par l'application :

- **Role** — qui est l'agent, ses principes cognitifs, ses traits d'identité
- **Missions** — les missions types qu'il peut accomplir
- **Skills** — les compétences atomiques qu'il maîtrise

L'utilisateur peut ajouter des **sections custom** à la marge si son cas
d'usage déborde du cadre, mais c'est l'exception. Le verrouillage des trois
sections principales garantit la compatibilité inter-rôles et la
prévisibilité pour la composition de mission profiles côté ag.flow.

### Documents atomiques (décision structurante)

Chaque section contient **plusieurs documents atomiques** plutôt qu'un seul
gros document.

**Raison :** dans ag.flow, une mission profile sélectionne un sous-ensemble
de documents d'un rôle. Plus les documents sont atomiques, plus la
composition est fine.

**Exemple** pour un rôle "UX Designer" :

```
Skills/
├── user-research-interviews.md
├── heuristic-evaluation.md
├── journey-mapping.md
├── prototyping-figma.md
└── stakeholder-alignment.md

Missions/
├── audit-ux-application.md
├── conception-parcours-onboarding.md
└── facilitation-atelier-co-design.md

Role/
├── principe-empathie-utilisateur.md
├── biais-pragmatique-vs-perfection.md
└── cadre-mental-double-diamond.md
```

### Format d'export ag.flow

L'export final est un ZIP conforme à l'endpoint
`POST /api/admin/roles/{role_id}/import` :

```
role.json                # display_name, description, identity, sections
section_role/
├── document_1.md
└── document_2.md
section_missions/
├── document_1.md
└── ...
section_skills/
└── ...
```

Ag.flow se charge ensuite (sur déclenchement utilisateur) de générer le
`prompt_orchestrator_md` final via son endpoint `/generate-prompts`.

L'application n'a pas besoin de produire ce prompt orchestrateur — elle
produit la matière première structurée.

## Stratégie de phasage

### Phase 1 — In-app (MVP)

- Dockerfiles des scrapers et du worker de transcription dans le repo de
  l'application
- `docker-compose.yml` qui build et lance tout
- MinIO et OpenBao en parallèle, hébergés sur le homelab
- Mono-utilisateur (Beard) pour valider le concept
- Schéma de données déjà multi-tenant ready

### Phase 2 — Repos séparés + CI corrective

- Chaque scraper et le worker de transcription sortent dans leur propre
  repo
- CI watch les nouvelles releases yt-dlp / instaloader / faster-whisper
- Rebuild auto + tag versionné + push sur registry privé
- Stratégie de canaux : `:latest` (build auto), `:stable` (testé et promu)
- L'application pointe sur `:stable`

### Phase 3 — Délégation à ag.flow

- Les scrapers deviennent des **dockerfiles ag.flow** enregistrés via
  `POST /api/admin/dockerfiles/{id}/import`
- L'application les invoque via `POST /api/admin/dockerfiles/{id}/task`
- Stream NDJSON consommé comme aujourd'hui
- Le worker de transcription **reste géré par l'application** (long-running
  stateful, ag.flow n'est pas optimisé pour ce pattern)

### Conditions de migration indolore

Pour rendre le passage Phase 1 → Phase 3 indolore, **figer dès Phase 1** :

- Le format JSON stdin (la "tâche" envoyée aux containers)
- Le format NDJSON stdout (les "events" remontés)
- La structure des chemins dans MinIO
- Les variables d'environnement (credentials, options)

Si ce contrat est stable, sortir le code dans un repo séparé puis le
migrer dans ag.flow devient mécanique.

## Principes de design transversaux

Ces principes s'appliquent à toutes les sections de la spec :

1. **Conversation before code** : les décisions architecturales sont prises
   avant l'écriture du code, documentées, puis implémentées.
2. **Traçabilité** : chaque artefact produit (signal, cluster, document)
   doit pouvoir être tracé jusqu'à sa source (run → chunks → audio).
3. **Réversibilité** : on conserve les versions intermédiaires (audio brut,
   transcripts, runs) pour permettre la régénération sans tout refaire.
4. **Multi-tenant ready** : même en mono-user, le schéma porte un
   `tenant_id` partout.
5. **Async-first** : tous les jobs longs (scraping, transcription, synthèse)
   sont asynchrones avec livraison événementielle au front.
6. **FIFO + parallélisme contrôlé** : queue PG avec `FOR UPDATE SKIP LOCKED`,
   plusieurs workers possibles via segmentation par pool.

## Comment Claude Code doit utiliser cette spec

1. **Avant chaque sprint** : lire ce fichier (`00-overview.md`) + le fichier
   de référence du sprint + `01-data-model.md` (référence SQL transverse).
2. **Pendant l'implémentation** : implémenter strictement ce qui est
   spécifié dans le fichier du sprint. Les décisions ouvertes (§ TODO de
   chaque fichier) peuvent être tranchées en cours de route, en notant le
   choix fait.
3. **À la fin de chaque sprint** : mettre à jour le fichier
   `12-open-decisions.md` avec les décisions tranchées et les nouvelles
   questions émergées.
4. **Si un blocage architectural émerge** : ne pas improviser, remonter la
   question avant de coder une solution non-spécifiée.

---

**Document suivant :** `01-data-model.md` (référence SQL transverse)
