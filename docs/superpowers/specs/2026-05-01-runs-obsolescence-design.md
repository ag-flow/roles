# Cache obsolescence runs — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, sous-projet C)
**Sprint d'origine :** Sprint 5 (open-decision § Synthesis "Cache obsolescence runs")
**Effort :** S-M (~1h impl + tests)

## Objectif

Marquer automatiquement les `runs` comme **obsolètes** quand un paramètre
qui les régit a été modifié après leur exécution :
1. `role_projects.global_directives` édité → tous les runs du projet → obsolete
2. `prompt.set_system_default(prompt_id, new_version_id)` → tous les runs du
   projet utilisant une **autre** version de ce prompt → obsolete

Visibilité côté UI : badge orange "obsolète" sur la carte du run dans la
liste de l'onglet Analyses.

## Décisions

### Schéma

Migration `0014_runs_is_obsolete.sql` :

```sql
ALTER TABLE runs ADD COLUMN is_obsolete BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX runs_obsolete_idx ON runs (role_project_id, is_obsolete)
    WHERE is_obsolete = false;
```

L'index partial accélère les listings "runs actifs" si une UI le filtre
plus tard.

### Sémantique

- `is_obsolete = true` est **monotone** : aucun chemin ne le repasse à
  `false`. Un run obsolète reste obsolète (sa traçabilité n'a plus de
  rapport avec les paramètres courants).
- Le run reste **lisible** et **téléchargeable** — l'obsolescence n'est
  pas une suppression. Juste une indication visuelle.
- Pas de purge automatique des runs obsolete (l'utilisateur peut
  manuellement les supprimer s'il veut faire de la place).

### Helpers DB

`db_helpers/runs.py` (nouveau ou ajout) :

```python
async def mark_obsolete_for_project(
    role_project_id: UUID, *, pool: asyncpg.Pool,
) -> int:
    """UPDATE runs SET is_obsolete=true WHERE role_project_id=$1
    AND is_obsolete=false. Retourne le rowcount."""

async def mark_obsolete_for_prompt(
    prompt_id: UUID, *, except_version_id: UUID, pool: asyncpg.Pool,
) -> int:
    """UPDATE runs SET is_obsolete=true
    WHERE prompt_version_id IN (
      SELECT id FROM prompt_versions WHERE prompt_id = $1 AND id != $2
    ) AND is_obsolete=false."""
```

`db_helpers/role_projects.py` (nouveau helper) :

```python
async def update_global_directives(
    role_project_id: UUID, directives: str | None, *, pool: asyncpg.Pool,
) -> None:
    """UPDATE + ValueError si rowcount=0."""
```

### Routes

**Nouvelle route** `PATCH /api/role-projects/{id}/global-directives` :

```python
class GlobalDirectivesPatch(BaseModel):
    global_directives: str | None

@router.patch("/role-projects/{project_id}/global-directives",
              status_code=status.HTTP_204_NO_CONTENT)
async def patch_global_directives(...):
    1. Vérifier ownership (user_id == project.user_id)
    2. update_global_directives(...)
    3. mark_obsolete_for_project(project_id)
    4. log + return 204
```

**Modification route** `PUT /api/prompts/{prompt_id}/system-default/{version_id}` :

Ajouter `mark_obsolete_for_prompt(prompt_id, except_version_id=version_id)`
après `set_system_default`. Pas de breaking change d'API.

### Schéma Pydantic Run

`schemas/runs.py` (ou équivalent) — ajouter le champ :

```python
class RunOut(BaseModel):
    ...
    is_obsolete: bool = False
```

### Frontend

`lib/types.ts` — ajouter `is_obsolete?: boolean` à `Run`.

`app/projects/[id]/analyses/RunCard.tsx` — afficher un badge orange
"obsolète" si `run.is_obsolete === true`. Reuse `StatusIndicator`
ou un `<span>` stylé (cohérent avec les autres badges du projet).

Pas de filtre / toggle "masquer obsoletes" pour MVP.

## Tests

### Backend (pytest)
- `test_db_helpers_runs_obsolescence.py` — 4 tests :
  1. `mark_obsolete_for_project` met les runs en is_obsolete=true
  2. `mark_obsolete_for_project` n'écrase pas les `failed`/`completed` en
     status (la colonne is_obsolete est indépendante)
  3. `mark_obsolete_for_prompt` exclut bien `except_version_id`
  4. Aucune ligne touchée si le projet n'a pas de runs
- `test_db_helpers_role_projects.py` — ajout test `update_global_directives`
- `test_role_projects_route.py` — test PATCH /global-directives :
  - 204 sur succès + DB mise à jour + runs marqués obsolete
  - 404 si projet inexistant
  - 403 si pas owner
- `test_prompts_route.py` — test set_system_default propagé :
  - vérifier que `mark_obsolete_for_prompt` est appelé après le set

### Frontend (Vitest)
- `RunCard.test.tsx` — 2 tests :
  1. Badge "obsolète" affiché si `is_obsolete=true`
  2. Pas de badge si `is_obsolete=false` ou undefined

## Critères de complétude

- [ ] migration 0014 + smoke test
- [ ] 2 helpers `runs.py` + 1 helper `role_projects.py` + tests
- [ ] route PATCH global-directives + tests
- [ ] route set_system_default modifiée + test
- [ ] schema RunOut.is_obsolete ajouté
- [ ] frontend types + RunCard badge + 2 tests
- [ ] backend tests verts (459 → 470+)
- [ ] frontend tests verts (141 → 143+)
- [ ] commit

## Hors-scope

- Filtre "masquer obsoletes" dans la UI
- Purge automatique des runs obsolete
- Récupérer les "anciennes" valeurs de directives pour expliquer pourquoi
  obsolete (audit log)
- Re-déclenchement automatique des étages affectés (le user lance manuellement)
