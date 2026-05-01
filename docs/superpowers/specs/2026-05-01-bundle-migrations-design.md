# Bundle migrations DB + auto-run startup — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, bug-fix infra prio haute)
**Effort :** S (~30-45 min)
**Bug d'origine :** sur Postgres frais en prod (image
`ghcr.io/ag-flow/backend-roles:sha-100a91b`), le backend log en boucle
`asyncpg.exceptions.UndefinedTableError: relation "chunking_jobs" does not exist`
parce que les migrations ne sont ni embarquées dans l'image ni jouées
au démarrage.

## Objectif

Reprendre le pattern de `agflow.docker` : embarquer `migrations/` dans
l'image et exécuter les migrations manquantes au lifespan FastAPI,
idempotent et multi-replica safe via advisory lock.

## Décisions

### Image & contexte de build

- Le contexte CI passe de `backend/` à `.` (racine du repo) car le
  Dockerfile a besoin à la fois de `backend/` ET de `migrations/`.
- Adaptation `.github/workflows/build-app.yml` matrix component
  `backend-roles` : `context: "."`, `dockerfile: "backend/Dockerfile"`.
- `backend/Dockerfile` utilise des paths root-relatifs :
  ```
  COPY backend/pyproject.toml backend/uv.lock /app/
  COPY backend/src/ /app/src/
  COPY migrations/ /app/migrations/
  ```

### Runner

`backend/src/role_builder/migrations.py` :
- `_lock_key()` = int8 stable, dérivé de `sha256(b"agflow_roles_migrations")[:8]`.
  Namespace différent de `agflow.docker` (qui utilise `b"agflow_docker_migrations"`)
  pour ne pas se bloquer mutuellement sur un cluster partagé.
- `_list_migration_files(dir)` : pattern `^\d{3,}_.*\.sql$`, tri lexicographique.
- `run_migrations(dir, *, pool)` :
  1. `pg_try_advisory_lock(key)` puis fallback `pg_advisory_lock(key)` bloquant.
  2. `CREATE TABLE IF NOT EXISTS schema_migrations(version text PK, applied_at timestamptz)`.
  3. Récupère `SELECT version FROM schema_migrations`.
  4. Pour chaque fichier `*.sql` trié : skip si déjà appliqué, sinon
     `BEGIN; EXEC sql; INSERT schema_migrations; COMMIT`.
  5. Une migration **blank** (commentaires + espaces) saute l'execute SQL
     mais est quand même enregistrée — utile pour `0001_extensions.sql`.
  6. `pg_advisory_unlock(key)` dans un `finally`.
  7. Retourne la liste des versions appliquées (pour log).

### Lifespan FastAPI

`main.py` lifespan, AVANT toute autre tâche bg :
- `_resolve_migrations_dir()` : `settings.migrations_dir` (override
  explicite) → `/app/migrations` (image docker) → `Path(__file__).parents[3] / "migrations"`
  (dev local depuis `backend/src/role_builder/main.py`).
- `await run_migrations(dir, pool=db_pool.pool)` ; si fail → exception
  remontée → swarm restart en boucle (visibilité immédiate).
- Bypass via `settings.disable_migrations=True` (utilisé par les tests).

### Extensions

`migrations/0001_extensions.sql` est **vidé** de tout `CREATE EXTENSION`.
Les extensions (uuid-ossp, pgcrypto, vector) sont créées en amont par
l'admin DB (compte superuser) via `install.sh --setup-db` du repo
`ag-flow/Configurations`.

Le fichier est conservé comme marker (commentaire-only) pour préserver la
séquence numérique 0001..0015 et apparaître dans `schema_migrations`.

## Tests

`backend/tests/test_migrations.py` — 9 tests :
- applique tout quand DB vierge
- skip versions déjà en `schema_migrations`
- idempotent quand tout est appliqué
- migration blank/comment-only enregistrée sans execute SQL
- `pg_try_advisory_lock` puis `pg_advisory_unlock`
- fallback `pg_advisory_lock` bloquant si try retourne false
- ignore les fichiers ne matchant pas le pattern
- lève `FileNotFoundError` si dossier inexistant
- `_lock_key` stable + dans la plage int8 signed

Conftest : `disable_migrations=True` ajouté à la fixture `client` et au
setup `app_with_stub_relay` pour ne pas exécuter au boot des tests.

## Critères

- [x] migration 0001 vidée des CREATE EXTENSION
- [x] `migrations.py` runner créé + 9 tests verts
- [x] `Dockerfile` paths root-relatifs + COPY migrations/
- [x] workflow CI : context `.` pour backend-roles
- [x] lifespan main.py appelle `run_migrations` avant les autres tâches
- [x] `disable_migrations` setting + bypass tests
- [x] backend tests verts (483 → 492)
- [x] commit

## Validation manuelle (à faire post-merge)

- `docker build -f backend/Dockerfile -t backend-roles:dev .` (depuis racine repo)
- `docker run --rm --entrypoint=sh backend-roles:dev -c "ls /app/migrations/ | wc -l"` → 15
- Lancer contre Postgres frais (avec extensions pré-installées) : logs
  doivent montrer la séquence appliquée + Application startup complete,
  AUCUN UndefinedTableError.
- Redémarrer le container : 2ᵉ startup ne ré-applique rien.
