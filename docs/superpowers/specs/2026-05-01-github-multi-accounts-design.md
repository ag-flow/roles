# Multi-comptes GitHub par user — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, sous-projet D)
**Sprint d'origine :** Sprint 8 (open-decision § GitHub publication)
**Effort :** M (~1h-1h30)

## Objectif

Permettre à un utilisateur de connecter **plusieurs comptes GitHub** (cas
d'usage : compte perso + compte d'organisation). Choisir le compte
au moment de chaque publication.

## Décisions

### Schéma

Migration `0015_github_integrations_multi_accounts.sql` :

```sql
ALTER TABLE github_integrations
    DROP CONSTRAINT IF EXISTS github_integrations_user_id_key;
ALTER TABLE github_integrations
    ADD CONSTRAINT github_integrations_user_id_github_user_id_key
        UNIQUE (user_id, github_user_id);
```

Rétro-compat : les rows existantes restent, juste la contrainte change.

### Helpers

`db_helpers/github_integrations.py` :
- `upsert(...)` : ON CONFLICT (user_id, github_user_id) DO UPDATE
- `get_by_user_id(user_id)` : conserve, retourne **la plus récente** (le
  comportement "compte primaire" pour les routes qui ne précisent pas)
- `list_by_user_id(user_id)` : **nouveau**, liste toutes les intégrations
- `get_by_id(id)` : **nouveau**, lookup direct par id
- `delete_by_id(id)` : **nouveau**, supprime une intégration spécifique

### Routes

- `GET /api/auth/github/integrations` (**nouveau**) → `list[GithubIntegrationOut]`
- `DELETE /api/auth/github/integrations/{id}` (**nouveau**) → 204 ou 404
- `DELETE /api/auth/github` (existant) : conservé mais marqué deprecated
  dans les logs ; supprime la primary (= la plus récente)
- `GET /api/auth/github/status` (existant) : conservé, retourne la
  primary
- `GET /api/github/repos` : ajoute query param optionnel `integration_id`
  (défaut = primary)
- `POST /api/role-projects/{id}/publish-to-github` : ajoute champ optionnel
  `integration_id` dans `PublishRequest` (défaut = primary)

### Frontend

- `lib/api/github.ts` : `listIntegrations`, `deleteIntegration`
- `my-stack/publication/ConnectGithubButton.tsx` : affiche la **liste**
  des intégrations, bouton "Déconnecter" par item + bouton "Ajouter un
  compte" (toujours appelle `start_oauth`)
- `projects/[id]/role/PublishToGithubConfigDialog.tsx` : si
  `integrations.length > 1`, dropdown "Compte GitHub". Stocké dans
  l'état local du dialog, envoyé dans le body publish.

### Persistance du choix par projet

**Hors-scope** : on ne persiste pas le `integration_id` dans
`role_publication_config`. L'utilisateur le choisit à chaque publication.
Si plus tard on veut persister, on ajoutera une colonne (ne casse rien :
les rows existantes sans cette colonne fallback sur primary).

## Tests

### Backend
- `test_db_helpers_github_integrations.py` : refacto pour multi (déjà
  existe ?). Ajouter tests `list_by_user_id`, `get_by_id`, `delete_by_id`
- `test_github_auth_route.py` : tests pour `GET /integrations` et
  `DELETE /integrations/{id}`
- `test_github_publish_route.py` : pas de breaking — le param
  `integration_id` est optionnel

### Frontend
- `ConnectGithubButton.test.tsx` : si déjà existant, étendre. Sinon créer.
- `PublishToGithubConfigDialog.test.tsx` : test sélecteur si > 1

## Critères de complétude

- [ ] migration 0015
- [ ] helpers étendus + tests
- [ ] 2 nouvelles routes auth + tests
- [ ] route publish accepte integration_id
- [ ] frontend list + delete + sélecteur dialog
- [ ] backend tests verts (468 → 480+)
- [ ] frontend tests verts (144 → 147+)
- [ ] commit
