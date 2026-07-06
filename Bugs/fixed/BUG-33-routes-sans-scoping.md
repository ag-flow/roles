# BUG-33 — Routes sources/items/scraping-jobs sans scoping user ni tenant : fuite cross-utilisateur

- **Zone** : routes HTTP / sources & jobs
- **Fichier(s)** : `backend/src/role_builder/routes/sources.py:66-115` ; `routes/scraping_jobs.py:39-48` (helpers `get_source`, `list_items_by_source`, `list_jobs` sans filtre)
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

`POST /sources/{id}/discover`, `GET /sources/{id}/items`, `POST /sources/{id}/items/select` et `GET /api/scraping-jobs` ne filtrent ni par `user_id` ni par `tenant_id` : n'importe quel utilisateur authentifié peut découvrir/relancer la source d'un autre, lister ses items et voir tous les jobs (le `tenant_id` d'autrui est même renvoyé dans `ScrapingJobResponse`). C'est incohérent avec le reste de l'API (credentials, keys, secrets, wallets, role-projects sont tous scopés `user_id`).

## Scénario d'échec

Keycloak activé, deux comptes ; B appelle `GET /api/sources/{source-de-A}/items` → titres, URLs de thumbnails, statuts du corpus privé de A ; `POST .../discover` déclenche des scrapes consommant les cookies rattachés à la source de A.

## Piste de résolution

Joindre `sources → role_projects.user_id` (ou porter `user_id` sur `sources`) et filtrer partout ; filtrer `list_jobs` par tenant/user du `CurrentUser`.

## Pourquoi Opus

Toucher 3 routes + 3 helpers, et décider du scoping des sources V2 (`role_project_id` potentiellement NULL).

## ✅ Résolu (2026-07-06)

Garde _require_owned_source (role_project du user, sinon 404) sur discover/items/select ; list_jobs scopé au tenant de l'appelant.

Vérifié : suite backend verte (481 passed).
