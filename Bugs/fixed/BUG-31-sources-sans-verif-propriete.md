# BUG-31 — POST /sources : aucune vérification de propriété → credentials d'un autre utilisateur

- **Zone** : routes HTTP / sources
- **Fichier(s)** : `backend/src/role_builder/routes/sources.py:40-59` ; `db_helpers/sources.py:11` ; `db_helpers/credentials.py:106`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

La route insère directement sans vérifier (1) que `role_project_id` existe, (2) qu'il appartient au user courant, (3) que `credentials_id` appartient au user courant. `sources.role_project_id` et `sources.credentials_id` sont des FK : un UUID inexistant lève `ForeignKeyViolationError` non attrapée → 500. Pire : un `credentials_id` valide appartenant à un autre utilisateur est accepté ; l'orchestrateur résout ensuite le credential via `get_credential_by_id` (explicitement non scopé) et scrape avec les cookies de la victime.

## Scénario d'échec

Auth Keycloak activée : user A devine/observe l'UUID d'un credential de B (ex. via les events WS partagés du tenant) → `POST /api/role-projects/{son-projet}/sources` avec `credentials_id` de B → les scrapes de A s'exécutent avec les cookies YouTube de B. Variante triviale : UUID bidon → 500 au lieu de 404/400.

## Piste de résolution

Vérifier `role_projects.user_id == user.user_id` (404 sinon) et, si `credentials_id` fourni, `get_credential(cred_id, user_id=user.user_id)` (404 sinon) avant l'insert ; attraper `ForeignKeyViolationError` en filet.

## Pourquoi Sonnet

Deux lookups préalables déjà disponibles dans les helpers + un except.

## ✅ Résolu (2026-07-06)

create_source vérifie la propriété du role_project et du credentials_id (404 sinon) : plus de FK 500 ni d'usage des cookies d'autrui.

Vérifié : suite backend verte (481 passed).
