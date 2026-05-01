# Sections custom — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, sous-projet G)
**Sprint d'origine :** Spec § 06 ligne unique "L'utilisateur peut ajouter des sections custom"
**Effort :** M (~1h-1h30)

## Contexte

La spec `06-synthesis.md` § Étage 3 decomposer mentionne :
> Les 3 sections principales sont :
> - Role / Missions / Skills
> L'utilisateur peut ajouter des sections custom au niveau du projet.

Une seule ligne, tout reste à concevoir. Aujourd'hui, la table
`role_documents.section` est `text` sans check constraint et l'export ZIP
boucle simplement sur le dict `docs_by_section`. La pièce manquante est :
1. la persistance des noms de sections custom au niveau projet,
2. l'injection de ces noms dans le prompt système du decomposer pour
   qu'il génère un plan de documents pour chaque section custom en plus
   des 3 standards.

## Décisions

### Modèle de données

Migration `0016_role_projects_custom_sections.sql` :

```sql
ALTER TABLE role_projects
    ADD COLUMN custom_sections jsonb NOT NULL DEFAULT '[]'::jsonb;
```

Valeur stockée : tableau JSON de strings, ex `["Outils", "Style-redactionnel"]`.

### Validation

- 0 à **5** sections custom (au-delà, le decomposer perd en qualité car le
  prompt explose).
- Chaque nom : ASCII, regex `^[A-Za-z][A-Za-z0-9_-]{1,31}$` (commence par
  une lettre, 2-32 chars, sans espaces, kebab-case ou camelCase OK).
- Unicité dans la liste, et **conflit** avec les 3 standards (`Role`,
  `Missions`, `Skills`) interdit.
- Validé par Pydantic dans `CustomSectionsPatch` + en DB côté helper.

### API

`PATCH /api/role-projects/{project_id}/custom-sections` body :
```json
{ "custom_sections": ["Outils", "Style-redactionnel"] }
```
- 204 sur succès
- 422 si validation Pydantic échoue
- 403 si pas owner, 404 si projet inexistant

`GET /api/role-projects` retourne déjà `custom_sections` via `RoleProjectOut`
(grâce à `model_config = ConfigDict(extra="allow")` qui inclut tout).

### Decomposer

`synthesis/decomposer.py` :
- Récupère `project["custom_sections"]` (default `[]`).
- Passe au template via une nouvelle variable `{custom_sections_block}` :
  ```
  Sections supplémentaires (custom) à produire en plus des 3 obligatoires :
  - Outils
  - Style-redactionnel
  ```
  ou chaîne vide si pas de sections custom.
- Le format de sortie JSON inclut alors aussi les clés custom dans `sections`.

Le **prompt système template** (versionné en DB) doit être mis à jour pour
référencer `{custom_sections_block}`. Pour ne pas casser les déploiements
existants où la version system_default n'a pas cette variable :
- **Si la version actuelle ne contient pas `{custom_sections_block}`** :
  on ajoute la directive en post-traitement Python (concat) plutôt qu'en
  format() — pour rester rétro-compatible.
- Une nouvelle version sera seedée en parallèle via le seed_prompts script
  (hors-scope de ce sous-projet).

Choix retenu : **post-traitement** côté code Python (pas de variable de
template). Plus robuste vis-à-vis des templates existants.

### Frontend

Composant `CustomSectionsEditor.tsx` dans la page `role/page.tsx` (ou
`/projects/[id]/settings`). Pour MVP, je le mets en haut de la page Rôle
sous l'onglet "Configuration".

UI minimale :
- Liste des sections existantes avec bouton "Supprimer" par item
- Input + bouton "Ajouter" (validation côté frontend = même regex)
- Sauvegarde via PATCH

## Tests

### Backend
- `test_db_helpers_role_projects.py` : `update_custom_sections` accepte / rejette
- `test_role_projects_route.py` : PATCH custom-sections (204/403/404/422)
- `test_synthesis_decomposer.py` : si project a custom_sections, le prompt
  envoyé au LLM les inclut

### Frontend
- `CustomSectionsEditor.test.tsx` : ajout/suppression + validation regex

## Critères

- [ ] migration 0016
- [ ] schemas Pydantic + helper update + tests
- [ ] route PATCH + tests
- [ ] decomposer post-traitement + test
- [ ] frontend types + UI + tests
- [ ] backend 494 → 500+
- [ ] frontend 147 → 149+
- [ ] commit

## Hors-scope

- Suggestions IA des noms basées sur corpus
- Drag-and-drop pour réordonner
- Export ZIP : pas de changement (boucle déjà sur dict)
- Renommer une section après-coup (impact sur les role_documents existants
  qui pointent vers l'ancien nom — complexe, à designer plus tard)
- Suppression d'une section avec docs déjà générés : pas de cascade DB
  pour MVP, l'utilisateur peut supprimer manuellement les docs
