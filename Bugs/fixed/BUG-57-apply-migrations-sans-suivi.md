# BUG-57 — `apply_migrations.sh` rejoue tout sans table de suivi : incompatible avec le runner intégré

- **Zone** : infra / migrations
- **Fichier(s)** : `scripts/apply_migrations.sh:14-17` ; recoupé avec `backend/src/role_builder/migrations.py:99-118` (suivi `schema_migrations`) et les migrations non idempotentes (`0001` `CREATE TABLE` sans `IF NOT EXISTS`, `0002` `RENAME COLUMN`, `0007/0008` `ADD COLUMN` sans `IF NOT EXISTS`)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

Le script applique `migrations/*.sql` en boucle sans jamais lire ni alimenter `schema_migrations`, alors que le backend applique lui-même les migrations au lifespan avec suivi. Les fichiers ne sont pas idempotents.

## Scénario d'échec

- (a) Séquence documentée dans CLAUDE.md — `docker compose up -d` (le backend a déjà tout appliqué) puis `./scripts/apply_migrations.sh` → psql échoue sur `0001` (« relation role_projects already exists ») avec `ON_ERROR_STOP`.
- (b) Pire : DB neuve initialisée via le script seul, puis démarrage du backend → `schema_migrations` vide → le runner rejoue `0001` → exception → **crash loop du conteneur backend**.

## Piste de résolution

Faire écrire au script les versions dans `schema_migrations` (même contrat que le runner : `CREATE TABLE IF NOT EXISTS` + insert par fichier, en sautant les versions déjà présentes), ou supprimer le script et documenter que le backend migre seul.

## Pourquoi Sonnet

Une vingtaine de lignes de bash/psql alignées sur le contrat du runner.

## ✅ Résolu (2026-07-06)

apply_migrations.sh suit désormais schema_migrations (même contrat que le runner) : crée la table, saute les migrations déjà appliquées, insère la version dans la même transaction. Idempotent, compatible base déjà migrée.

(Correction shell/compose, non couverte par la suite pytest.)
