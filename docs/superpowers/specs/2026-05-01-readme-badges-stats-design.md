# Badges shields.io + stats corpus dans README — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, sous-projet B)
**Sprint d'origine :** Sprint 8 (open-decision GitHub publication)
**Effort :** XS (~30-40 min)

## Objectif

Enrichir le README publié sur GitHub avec :
1. **Badges shields.io** : licence, langue, service types ag.flow, nb de documents
2. **Stats du corpus** : nombre de sources scrapées + nombre de chunks indexés

## Décisions

### Badges

Insérés **juste après** la description (avant l'en-tête auteur), un bandeau
de 4 badges :

```markdown
[![Documents](https://img.shields.io/badge/Documents-12-orange.svg)](#)
[![Language](https://img.shields.io/badge/Language-fr-blue.svg)](#)
[![Service](https://img.shields.io/badge/agflow-claude--code-purple.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)
```

- **Documents** : count total cumulé sur toutes les sections (toujours présent)
- **Language** : `project["language"]` (fr par défaut, toujours présent)
- **Service** : service_types joints par `__` shields.io (toujours présent)
- **License** : couleur selon le choix
  - `polyform-nc` → bleu
  - `cc-by-nc-sa-4.0` → jaune
  - `cc-by-4.0` → vert
  - `mit` → vert
  - `none` → **pas de badge** (cohérent avec absence de fichier LICENSE)

### Stats corpus

Section "Stats du corpus" insérée **après** "Sections" si stats fournies :

```markdown
## Stats du corpus

- Sources scrapées : 12
- Chunks indexés : 530
```

Si `stats=None`, la section est complètement omise (rétro-compat).

### API

`render_readme` reçoit un nouveau kwarg optionnel :

```python
def render_readme(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    github_login: str,
    stats: dict[str, int] | None = None,  # nouveau
) -> str:
```

`build_publication_files` propage `stats` (kwarg optionnel) jusqu'au render.

### Calcul des stats

Nouveau helper `db_helpers/corpus_stats.py` :

```python
async def get_corpus_stats(pool, role_project_id: UUID) -> dict[str, int]:
    """Retourne {"source_count": N, "chunk_count": M}."""
```

2 SELECT COUNT séparés (sources + corpus_chunks). Pas de JOIN — plus
robuste si une table est vide.

`push_publication` (Trees API) appelle `get_corpus_stats(pool, project["id"])`
et passe le résultat à `build_publication_files`. Idem pour
`push_publication_legacy_n_put` pour cohérence (fallback).

## Tests

### `test_github_readme_builder.py` — 6 nouveaux tests
1. badge documents count présent
2. badge language présent avec valeur projet
3. badge service types joins corrects
4. badge license MIT (vert)
5. **pas** de badge license si `license_choice="none"` — *mais render_readme ne reçoit pas license_choice*. **Décision** : on passe le badge license via un kwarg optionnel `license_choice` à `render_readme` (cohérent avec `render_license_file`).
6. stats section présente si stats fournies, absente sinon

### `test_corpus_stats.py` — 1 nouveau fichier
- Test avec mock asyncpg pool (pattern existant `_FakePool` ou `MagicMock`)

### Tests existants
- 8 tests `test_github_readme_builder.py` doivent rester verts (rétro-compat)
- 2 tests `test_github_publisher.py` `build_publication_files_*` doivent rester verts

## Critères de complétude

- [ ] 6 nouveaux tests `readme_builder` verts
- [ ] 1+ nouveau test `corpus_stats` vert
- [ ] backend tests : 448 → 455+ verts
- [ ] ruff clean
- [ ] commit

## Hors-scope

- Calcul de stats au niveau "documents par section" (déjà dans le résumé)
- Badge "build status" CI sur le repo source
- Templating shields.io configurable par l'utilisateur
- Lien réel sous chaque badge (les `#` sont OK pour MVP)
