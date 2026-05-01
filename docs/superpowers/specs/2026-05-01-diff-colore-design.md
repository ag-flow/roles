# Diff coloré — Design

**Date :** 2026-05-01
**Phase :** 2 (post-MVP, sous-projet A)
**Sprint d'origine :** Sprint 5 (dette `RunDiff` / `DiffViewer`) + Sprint 7 (`VersionDiff` déjà coloré)
**Effort estimé :** XS — ~30 min impl + tests, 1 commit

## Contexte

Trois composants frontend affichent un diff entre deux contenus textuels :

| Composant | Onglet | Compare | État coloration |
|---|---|---|---|
| `app/projects/[id]/role/VersionDiff.tsx` | Rôle | versions de `role_documents` | **OK** — utilise `react-diff-viewer-continued` (Sprint 7) |
| `app/projects/[id]/analyses/RunDiff.tsx` | Analyses | `output` de deux runs | **manquant** — 2 `<pre>` côte à côte |
| `app/projects/[id]/prompts/DiffViewer.tsx` | Prompts | `template` de deux versions de prompt | **manquant** — 2 `<pre>` côte à côte |

`docs/specs/12-open-decisions.md` § Sprint 5 :

> **Algo de diff coloré pour RunDiff/DiffViewer**
> Reporté Phase 2. `diff-match-patch` (Google) ou `react-diff-view`
> pour mettre en évidence les changements ligne par ligne.

La lib `react-diff-viewer-continued` (MIT, dans `package.json`, déjà
utilisée par `VersionDiff`) couvre le besoin sans nouvelle dépendance.

## Objectif

Aligner les 3 composants sur la même lib + factoriser le hack de typing
dans un composant partagé pour éviter la duplication.

## Décisions

- **Lib** : `react-diff-viewer-continued` (déjà installé, MIT, à jour). Pas
  de `diff-match-patch` ni `react-diff-view` — on n'introduit pas de
  nouvelle dep pour 0 gain fonctionnel.
- **Mode** : `splitView=true` (cohérent avec `VersionDiff` existant).
- **Factorisation** : un composant partagé `frontend/src/components/ColoredDiff.tsx`
  encapsule la lib + le hack `as unknown as FC<...>` (typages legacy de la
  lib incompatibles avec React 18 strict).
- **Périmètre UI** : on swap **uniquement la zone diff centrale**.
  Les modales / dialogs / en-têtes (titres, badge `is_system_default`,
  bouton Fermer) restent dans les composants appelants — ils portent la
  logique métier propre à chaque domaine.

## Composant `ColoredDiff`

### Emplacement

`frontend/src/components/ColoredDiff.tsx`

### API

```typescript
interface ColoredDiffProps {
  oldValue: string;
  newValue: string;
  leftTitle?: string;
  rightTitle?: string;
  splitView?: boolean;  // défaut true
}

export function ColoredDiff(props: ColoredDiffProps): JSX.Element;
```

### Implémentation

Encapsule `react-diff-viewer-continued` avec le hack de typing déjà éprouvé
dans `VersionDiff.tsx` :

```typescript
import ReactDiffViewerImport from 'react-diff-viewer-continued';

interface ReactDiffViewerLikeProps {
  oldValue: string;
  newValue: string;
  splitView?: boolean;
  leftTitle?: string;
  rightTitle?: string;
}

const ReactDiffViewer = ReactDiffViewerImport as unknown as
  FC<ReactDiffViewerLikeProps>;
```

Le composant rend simplement `<ReactDiffViewer {...props} />`.

## Refactor des 3 callers

### `VersionDiff.tsx` (rôle)

Remplace l'usage local de `ReactDiffViewerImport` + le hack par `<ColoredDiff>`.
Aucun changement de comportement utilisateur.

### `RunDiff.tsx` (analyses)

Remplace les 2 blocs `<div><h3>…</h3><pre>{run.output}</pre></div>` par un
seul `<ColoredDiff>` qui prend les `output` en oldValue / newValue. Les
en-têtes (`Run A — {id} · {model} · {status}` et idem B) deviennent les
`leftTitle` / `rightTitle`.

Le wrapper modal (overlay, fond, bouton Fermer, titre "Comparaison de
runs") reste tel quel.

### `DiffViewer.tsx` (prompts)

Remplace les 2 blocs `<div><h3>…</h3><pre>{version.template}</pre></div>`
par un seul `<ColoredDiff>` qui prend les `template` en oldValue / newValue.

Le titre `v{version_number}` + badge `système` (si `is_system_default`)
reste comme préfixe textuel dans `leftTitle` / `rightTitle` ou en
en-tête au-dessus du `ColoredDiff` selon le rendu visuel le plus
lisible. **Choix retenu** : conserver les en-têtes au-dessus (badge
"système" stylé doit rester en JSX, pas en string) et passer
`leftTitle="v{N}"` / `rightTitle="v{M}"` à `ColoredDiff`. Les badges
restent affichés dans des `<h3>` au-dessus de la zone diff.

## Tests

### Nouveau fichier `frontend/src/__tests__/ColoredDiff.test.tsx`

Vitest + RTL :
1. **Rendu de base** : passe `oldValue="abc"` et `newValue="abd"`, vérifie
   que les deux contenus apparaissent dans le DOM.
2. **Titres** : passe `leftTitle="v1"` et `rightTitle="v2"`, vérifie qu'ils
   sont rendus.
3. **Pas de crash sur strings vides** : `oldValue=""` `newValue=""`.

### Tests existants

- `VersionDiff.test.tsx` (5 tests Sprint 7) : doivent rester verts
  (le composant interne change mais l'API / le rendu utilisateur sont
  inchangés).
- Pas de tests pré-existants sur `RunDiff.tsx` ni `DiffViewer.tsx` à ce
  jour. **Décision** : on ne crée pas de test composant pour eux dans ce
  sous-projet — la couverture est portée par `ColoredDiff.test.tsx`. Si on
  veut tester l'intégration plus tard, ce sera dans un autre sous-projet
  (sortie de scope ici).

## Critères de validation

- [ ] `frontend/src/components/ColoredDiff.tsx` créé
- [ ] `ColoredDiff.test.tsx` ajouté (3 tests verts)
- [ ] `VersionDiff.tsx` refactoré pour consommer `ColoredDiff`
- [ ] `RunDiff.tsx` refactoré pour consommer `ColoredDiff`
- [ ] `DiffViewer.tsx` refactoré pour consommer `ColoredDiff`
- [ ] `npm test` : 100% vert (137 tests existants + 3 nouveaux = 140)
- [ ] `npm run typecheck` : OK
- [ ] `npm run lint` : 0 warning
- [ ] `docs/specs/12-open-decisions.md` § Sprint 5 → coche
      **Algo de diff coloré pour RunDiff/DiffViewer**

## Hors-scope (à ne pas faire dans ce sous-projet)

- Test composant pour `RunDiff` ou `DiffViewer`
- Changement de mode (unified vs split)
- Custom theme du diff viewer (couleurs, typo)
- Lazy-load de la lib (split chunks Next.js)
- Évaluation de `diff-match-patch` ou `react-diff-view`
