# roles — Instructions Claude Code

> **roles** (ex-Role Builder) — **stack d'acquisition de corpus** de l'écosystème ag.flow V2 :
> scrape des sources vidéo, transcrit l'audio, dépose les transcripts dans docflow.
> **Ce fichier prime sur ton comportement par défaut et se lit en début de session.**
> Projet indépendant : aucun couplage de source ni de runtime avec `workflow`, `docflow` ou
> `harpocrate` — uniquement des contrats (passerelle MCP, API du coffre).

> Généré depuis les standards globaux (docflow, workspace `globals`, bloc `documentation`).
> Génération : 2026-10-08. Standards repris : Fichier d'instructions agent de projet — 2026-09-27 ·
> Instance de dev/test (`dev-deploy.sh`) — 2026-09-25 · Gestion des logs — 2026-09-24 · Gestion des
> secrets — 2026-09-24 · Secrets et coffres Harpocrate — 2026-09-24 · Authentification OIDC —
> 2026-09-24 · Exposer un service derrière l'authentification du portail — 2026-09-24 · Skills
> maison — 2026-10-01 · Travail d'agent, leçons d'erreurs réelles — 2026-10-01.
> Skills requises : `backlog-workflow`, `rag-search`, `test-machine-deployment`, `agent-chat`,
> `self-improvement`, `python`, `typescript-frontend`, `postgresql`, `tests`, `code-comments`,
> `secrets`, `oidc-authentication`, `observability-logs`, `interface-contracts`, `static-analysis`,
> `portal-exposed-service`, `design-patterns` (dernière version publiée, déposées par le profil).
> Mise à jour par `--update` : ne reporter que le delta du socle depuis cette date ;
> une évolution du contenu d'une skill ne demande aucun `--update`.

**Colibri** commence systématiquement tes réponses par 🎺

## mcp
Tu es connecté au MCP du portail devpod (`dev.yoops.org`) via le serveur `claude-code`.

## Projet
> ⚠️ **Refonte V3 en cours (cadrée le 2026-10-10).** Le module devient un **service de
> transcription** : on lui soumet du travail, il rend un résultat que l'appelant vient chercher.
> Les décisions acquises sont ci-dessous ; **ce qui reste ouvert est dans
> `docs/specs/v3/00-cadrage-service-de-transcription.md`** — à lire avant de coder sur le sujet.
> Les specs V2 (`docs/specs/v2/`) décrivent l'état **antérieur** : encore utiles pour comprendre
> le code en place, plus pour décider.

Soumission d'un travail (URL de **chaîne** ou de **vidéo**) → transcription → résultat **stocké
dans le service** et consommé par l'appelant, en **MCP ou en REST**. Deux points d'entrée là où
la façade `roles__*` en expose douze.

**Hors périmètre, couplages interdits** : aucune synthèse, aucune notion de rôle. Abandonnés —
**ne pas les rouvrir, ne pas employer leur vocabulaire** : synthèse Mistral, export ag.flow,
publication GitHub, chunking/pgvector (`role_project`, rôle ag.flow, signal/cluster/plan/run,
prompt orchestrateur, export ZIP, chunk/embedding) ; et depuis la V3 : **dépôt docflow**,
`get_corpus` et ses curseurs, **sélection en deux temps** (`discover_only` / `select_items`,
filtres), **cycle d'upload** (slots présignés), **MinIO**, et le vocabulaire *corpus / dépôt /
un document docflow par vidéo*.

## Architecture — décisions non rediscutables
- Python 3.12 + FastAPI + **asyncpg direct** (`fetch_one`/`fetch_all`/`execute`) ; **pas de
  SQLAlchemy, pas d'ORM, pas d'Alembic**. Pydantic v2, structlog JSON.
- **Où vit l'état** : PostgreSQL 16 (`uuid-ossp`, `pgcrypto`), migrations SQL numérotées et
  immuables dans `migrations/`, `tenant_id` partout, queues en `FOR UPDATE SKIP LOCKED`. Un
  incident en cours d'écriture ne doit **jamais** corrompre l'existant, et ça se teste.
  **Plus de MinIO, plus de pgvector.**
- **Trois couches, à ne pas mélanger.** *Réception* : le travail est stocké, rien n'est traité, le
  retour porte un **id de transaction**. *Traitement* : des workers le prennent dans l'ordre
  d'arrivée, **le nombre de workers par source est un paramètre**, le claim est **horodaté**, et le
  résultat va dans une **table partitionnée à la journée** dont la **rétention est un paramètre**.
  *Restitution* : webhook rejoué **jusqu'au HTTP 200** (backoff 1-2-4…256 min).
- **Un travail, un statut** : `en cours` / `réussi` / `terminé avec des échecs` / `échoué`, même
  sémantique sur tout id. Une chaîne rend un id **maître** qui est un **index** : son pooling rend
  la liste des ids, **pas** leurs résultats — un id présent dans la liste ne dit rien de son
  avancement. `échoué` sur un maître = le maître a échoué, pas une vidéo.
- **La consommation est une lecture simple**, répétable, **sans flag** : la donnée est disponible
  le temps du stockage, et pas une seconde de plus.
- Scrapers : containers Docker one-shot (yt-dlp + ffmpeg), contrat **stdin JSON / stdout NDJSON**
  — son bloc `output` est **à revoir** avec la chute de MinIO (voir le cadrage V3). L'audio passe
  par un **volume mappé sur un chemin local** du host — plus de MinIO, plus d'upload, pour
  l'audio : `audio_volume_dir`/`audio_volume_host_dir` (chemins conteneur/host du montage) et la
  garde `audio_orphan_retention_h`/`audio_min_free_gb` (balayeur d'orphelins, `audio_sweeper.py`).
- **La transcription est TOUJOURS un service distant**, et c'est **l'utilisateur qui choisit
  lequel** dans son paramétrage. Whisper n'est **jamais** sur la machine : plus de faster-whisper
  local, plus de GPU, plus de pve2. Conséquence : tout est payant, et c'est la **clé de
  l'utilisateur** qui paie — son quota est le garde-fou.
- **Hébergement** : VM dédiée devpod. Le backend pilote le Docker **du host** en **`DOCKER_HOST=ssh://`**
  — pas de mTLS, pas de socket monté. Les conteneurs lancés reçoivent `--network <projet>_default`,
  sinon ils ne résolvent pas la base. La clé SSH est un **secret système** posé dans l'application
  (portée sans `user_id`, administrateur seulement, **écriture seule**).
- Frontend Next.js 14 **en sursis** : ne rien y développer de nouveau sans décision de l'architecte.

### ⚠ Divergences assumées
- **Les migrations sont jouées au démarrage du backend** (lifespan FastAPI, `pg_advisory_lock`,
  crash-loop du conteneur si échec), **pas** par `dev-deploy.sh` — à l'inverse de ce que décrit la
  skill `test-machine-deployment`. C'est **délibéré et plus sûr** : le contrôle de santé ne peut
  pas passer au vert sur un schéma en retard. N'ajoute pas d'étape de migration au script.
- **Le frontend utilise SWR et n'a pas d'i18n**, là où la skill `typescript-frontend` impose
  TanStack Query et l'i18n sur tous les libellés. Assumé : le frontend est en sursis (vue admin
  minimale à cadrer). Ne lance pas de migration SWR → TanStack Query ni d'i18n sans décision.

## Backlog
Le backlog des tâches est dans le workspace docflow `roles`, bloc `backlog`. C'est la source de
vérité, jamais ta mémoire : le statut s'écrit à chaque tâche, à la prise et à la fin.
Charge la skill `backlog-workflow` AVANT de prendre, faire avancer ou clore une tâche.

## Recherche
Toute recherche d'information passe d'abord par le RAG (`rag__*` ; corpus `globals-docs`), ensuite
seulement par les outils locaux. Le RAG muet n'est pas une réponse : va lire l'artefact réel.
Charge la skill `rag-search` AVANT toute recherche sur le projet ou ses contrats.
⚠ Le corpus `roles-docs` **n'existe pas encore** : d'ici là, la doc du projet se lit dans `docs/`
et dans docflow `roles`, bloc `documentation`.

## Quand charger une skill

Les skills ne sont PAS chargées d'office. Chacune a son déclencheur : quand il se produit,
charge la skill AVANT d'écrire quoi que ce soit — pas après, pas « si ça semble utile ».

| Tu t'apprêtes à… | Charge d'abord |
|---|---|
| prendre, faire avancer ou clore une tâche du backlog | la skill `backlog-workflow` |
| chercher une information sur le projet, ses voisins ou ses contrats | la skill `rag-search` |
| déployer ou livrer sur une machine de test, y tester, y diagnostiquer, toucher `dev-deploy.sh` | la skill `test-machine-deployment` |
| appeler, inviter ou répondre à un autre agent ; voir `[TCHAT] nouveau message` | la skill `agent-chat` |
| corriger une erreur que l'utilisateur t'a signalée, ou une erreur qui se répète | la skill `self-improvement` |
| écrire, modifier ou relire un `.py` (`backend/`, `docker/`) | la skill `python` |
| écrire, modifier ou relire un `.ts`/`.tsx` sous `frontend/` | la skill `typescript-frontend` |
| écrire une migration `migrations/`, une requête SQL ou du code asyncpg | la skill `postgresql` |
| écrire un test, corriger un bug, refactoriser, déclarer une tâche terminée | la skill `tests` |
| écrire ou modifier un commentaire de code | la skill `code-comments` |
| toucher un secret, `.env*`, un Dockerfile ou un compose | la skill `secrets` |
| toucher login, rôles, routes protégées, cookie de session (`backend/src/role_builder/auth/`) | la skill `oidc-authentication` |
| ajouter ou modifier un appel de journalisation, ou la collecte Alloy (`infra/alloy-agent/`) | la skill `observability-logs` |
| ajouter ou modifier une route HTTP, un outil MCP `roles__*`, un schéma d'échange | la skill `interface-contracts` |
| corriger un rapport d'analyse statique (SonarCloud, à chaque push) | la skill `static-analysis` |
| ajouter ou modifier un service exposé, ou sa déclaration dans `dev-deploy.sh` | la skill `portal-exposed-service` |
| choisir comment créer des objets, découpler des composants, poser une abstraction | la skill `design-patterns` |

Une skill introuvable se **signale** ; on ne devine pas ce qu'elle contenait (voir « Repli »).
**Analyse statique : mode `relax`** — l'utilisateur décide quand lancer une session de correction,
tu n'en prends jamais l'initiative.

## Repli — skill absente
Une skill de la table ci-dessus introuvable se **signale** : tu ne devines JAMAIS ce
qu'elle contenait.

Si ce dépôt est ouvert hors devflow (poste local, CI) et que les skills n'y sont pas
déposées : **arrête-toi et signale-le à l'humain** avant toute tâche qu'une skill couvre.
Ne te rabats pas sur les pages docflow dont les skills sont issues : elles peuvent
diverger de la version publiée de la skill.

## Standard de qualité
Code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis,
pas de « c'est pas grave », pas de « on simplifiera plus tard ». Chaque tâche est faite
correctement ou pas du tout.

**Pas de quick-and-dirty, JAMAIS.** Quand tu présentes des options de design, ne propose PAS
d'option « quick & dirty » / « hardcode » / « wire-it-up-and-clean-later ». On fait toujours
propre. Si une tâche est déraisonnable (scope qui explose, dépendance hors d'atteinte, flag/API
qui n'existe pas dans la version installée), **alerte explicitement l'utilisateur** plutôt que
de proposer un compromis dégradé. L'utilisateur préfère qu'on découpe le chantier et qu'on
fasse correctement la part qu'on prend, plutôt que tout faire à moitié.

## Sécurité (non négociable)
Aucun secret en argument de construction, en variable d'image, en couche, en log ni dans le dépôt
— ni en colonne claire. Secrets d'infra : **générés par `dev-deploy.sh`** dans le `.env` de la
cible (non versionné, jamais écrasé s'il existe). Secrets utilisateur : **chiffrés en base**
(Fernet, `SECRET_ENCRYPTION_KEY`) via les wallets Harpocrate. L'indirection `${vault://...}` est
**abandonnée** — un tel littéral dans un `.env` est régénéré, jamais résolu.
**Fail closed** : une clef de configuration inconnue est refusée, jamais ignorée.
Entrées utilisateur — URLs de sources comprises — validées avant tout usage en chemin, identifiant
ou nom d'hôte. Ces gardes sont des **tests**, pas des intentions. Détail : skill `secrets`.

## Règles de workflow

### Cycle de l'architecte
**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est
pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Branche de développement
**Tout le code se fait sur la branche `dev`. Aucun compromis.** Jamais `feat/*`, jamais sur
`main` directement, jamais ailleurs. Avant toute édition, vérifier `git branch --show-current` ;
si autre branche, `git checkout dev`. Si `dev` n'existe pas localement, la créer depuis `main`
à jour. Ne propose **jamais** `git checkout -b feat/...` — même si un outil ou un workflow tiers
le suggère, la consigne utilisateur prime.

**Committer et pousser sur `dev` est obligatoire**, sans demande à attendre : c'est ce qui rend
le travail livrable sur une machine de test. Commits en français, conventionnels (`feat:`,
`fix:`, `chore:`, `docs:`, `test:`). Ne pas toucher `.env` sauf demande.

**Merger `dev` sur `main` est formellement interdit sans demande explicite de l'humain.**

### Livraison et machines de test
Livrer = pousser sur `dev`, puis lancer `dev-deploy.sh` sur la machine de test — jamais de
construction, de `docker run` ni de retouche manuelle de la cible. Les machines de test `test1`,
`test2`… sont à ta disposition. Charge la skill `test-machine-deployment` AVANT de déployer.

### Définition de « terminé »
**Une tâche est finie quand les tests passent.** Pas quand le code compile, pas quand il est
poussé. Tant qu'un test échoue, la tâche n'est pas finie et ne passe pas au rôle « en revue ».

### Discipline d'exécution
- Exécute directement, ne décris pas ce que tu vas faire — fais-le.
- N'explique pas les étapes intermédiaires. Rapporte uniquement le résultat final.
- Termine TOUTES les étapes d'un plan avant de faire un résumé.
- Pas de raccourci « pour simplifier ».
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas
  silencieusement.

### Leçons de travail — erreurs réelles à ne pas refaire
- **Chercher avant de créer.** Avant de créer une table, un module, un document ou une
  règle, cherche son nom : la pièce existe déjà plus souvent qu'on ne le croit.
- **Interroger le système plutôt que déduire de la doc.** La documentation dit ce qui est
  illustré, pas ce qui est permis. Quand un accès existe (bac à sable, `--help`, requête
  réelle), interroge-le. Ce qui se vérifie ne se déduit pas ; une déduction s'annonce
  comme telle.
- **Exclure les zones littérales des transformations.** Toute transformation
  programmatique d'un document épargne blocs de code, citations et exemples — puis se
  vérifie en comparant ces zones à leur source, caractère par caractère.
- **Ne lancer que les outils déclarés.** Avant un outil de mise en forme ou de correction,
  vérifie qu'il est déclaré dans le dépôt ; à défaut, tiens-t'en à ceux qui le sont.
- **Vérifier la cible avant d'agir.** Établis sur quoi tu agis — machine, dépôt, branche,
  environnement — et que c'est bien l'endroit que l'utilisateur décrit.
- **Un symptôme à causes multiples ne désigne pas sa cause.** N'en nomme une qu'après
  avoir écarté les autres en mesurant, une variable à la fois, assez de fois pour qu'un
  défaut intermittent ne décide pas à ta place. Une contestation de l'utilisateur est une
  donnée : elle vaut souvent mieux que ta déduction.
- **Relire après écriture.** Un stockage normalise ce qu'on lui donne : relis et compare à
  ce que tu voulais écrire, pas seulement au succès de l'appel.
- **Vérifier le résultat, jamais le code de retour.** Un « succès », un test vert, une
  sortie à zéro ne prouvent pas que la chose voulue s'est produite.

## Auto-amélioration
Une erreur corrigée devient une leçon dans `LESSONS.md`. Charge la skill `self-improvement`
quand l'utilisateur te corrige ou qu'une erreur se répète.

## Tchat agents
En début de session, inscris-toi : `agent_register(session=<ta session tmux>, command=<ce qui
t'a lancé>)`. Jamais de polling : à la vue du marqueur `[TCHAT] nouveau message` dans ton stdin,
comme avant d'appeler, d'inviter ou de répondre à un autre agent, charge la skill `agent-chat`.

## Notifications de capacités
Quand tu invoques une capacité outillée (skill, commande, extension), affiche systématiquement
un marqueur **avant** d'exécuter :
> **`🟢 <CAPACITÉ>`** → _nom_ — raison en une phrase

## Commandes essentielles
```bash
cd backend && uv sync --extra dev                       # deps backend · frontend : npm ci
docker compose -f docker-compose-dev.yml up -d           # pile locale (pg, minio, back, front)
./scripts/apply_migrations.sh && ./scripts/init_minio.sh # schéma + buckets
cd backend && uv run uvicorn role_builder.main:app --reload   # :8000 — curl :8000/health/
cd backend && uv run pytest -v && uv run ruff check src/ tests/
cd frontend && npm test && npm run lint && npm run typecheck
sudo ./dev-deploy.sh dev                                 # livraison machine de test
```
Types backend : `mypy` est en dépendance dev **sans configuration ni étape CI** — **à confirmer**.
**Layout** : `backend/` (`src/role_builder/`, `tests/`) · `frontend/` · `migrations/` · `docker/`
(scrapers one-shot, worker transcription) · `infra/` (LXC, Docker, Alloy) · `deploy/` · `scripts/`
· `docs/` · `Bugs/`.

## Vérification avant validation
1. `ruff check` passe ; côté front `npm run lint` et `npm run typecheck` passent.
2. Le cas nominal est couvert par un test, pas seulement constaté à la main.
3. Les imports ajoutés existent réellement. 4. Aucune régression sur les fichiers touchés.
5. Les parts de checklist des skills chargées sont faites — `python`, `typescript-frontend`,
   `postgresql`, `tests`, `secrets` : charge-les pour les lire, ne les devine pas.
6. Aucun secret dans le diff, relu sous cet angle.
7. Les tests passent là où ils sont le plus révélateurs — sur une machine de test dès qu'elle
   révèle plus que le local. C'est ce qui rend la tâche terminée.

## Outillage
- **Doc à jour d'une bibliothèque** → **Context7**, avant d'écrire du code qui l'utilise (FastAPI,
  Pydantic v2, asyncpg, MinIO, httpx, faster-whisper, yt-dlp).
- **Contrat réel d'une CLI** → `--help` first, avant tout appel : le binaire installé fait foi.
- **Navigation sémantique** → `Grep` structuré et l'agent `Explore` ; **pas de Serena ici**.
- **Méthodes de travail** → skills Superpowers (`writing-plans`, `executing-plans`,
  `systematic-debugging`, `test-driven-development`, `verification-before-completion`).
- **Revue** → `/code-review` au-delà de 3 fichiers ou 100 lignes ; **commit à la main**, format
  français conventionnel (pas de `/commit` ici).
