# Plan TDD — Diff coloré

**Spec :** `docs/superpowers/specs/2026-05-01-diff-colore-design.md`
**Date :** 2026-05-01
**Effort :** XS (~30 min)

## Étapes

### 1. Créer le composant et son test (TDD)

**1.1 — Test rouge**

Créer `frontend/src/__tests__/ColoredDiff.test.tsx` avec 3 tests :

- `it("rend les deux contenus", ...)` — mount avec `oldValue="abc def"` et
  `newValue="abc xyz"`, assert que `getByText` ou pattern trouve les deux.
- `it("rend les titres leftTitle et rightTitle", ...)` — mount avec
  `leftTitle="v1"` et `rightTitle="v2"`, assert présence dans le DOM.
- `it("ne crash pas sur strings vides", ...)` — mount avec `oldValue=""`
  et `newValue=""`, juste vérifier que le render n'explose pas.

`npm test ColoredDiff` → 3 rouges (composant n'existe pas).

**1.2 — Impl minimale**

Créer `frontend/src/components/ColoredDiff.tsx` :

```typescript
'use client';

import type { FC } from 'react';
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

export interface ColoredDiffProps {
  oldValue: string;
  newValue: string;
  leftTitle?: string;
  rightTitle?: string;
  splitView?: boolean;
}

export function ColoredDiff({
  oldValue,
  newValue,
  leftTitle,
  rightTitle,
  splitView = true,
}: ColoredDiffProps) {
  return (
    <ReactDiffViewer
      oldValue={oldValue}
      newValue={newValue}
      leftTitle={leftTitle}
      rightTitle={rightTitle}
      splitView={splitView}
    />
  );
}
```

`npm test ColoredDiff` → 3 verts.

### 2. Refactor `VersionDiff.tsx` (rôle)

Remplace l'import `ReactDiffViewerImport` + le hack local + le JSX
`<ReactDiffViewer>` par :

```typescript
import { ColoredDiff } from '@/components/ColoredDiff';
…
<ColoredDiff
  oldValue={other.data.content}
  newValue={currentContent}
  leftTitle={`v${other.data.version}`}
  rightTitle={`v${currentVersion} (current)`}
/>
```

Vérifier que `VersionDiff.test.tsx` reste vert (5 tests existants Sprint 7).

### 3. Refactor `RunDiff.tsx` (analyses)

Remplace les 2 blocs `<div><h3>…</h3><pre>{run.output}</pre></div>` par
un seul `<ColoredDiff>` avec :
- `oldValue={runA.output ?? ''}`
- `newValue={runB.output ?? ''}`
- `leftTitle={`Run A — ${runA.id.slice(0, 8)} · ${runA.llm_model ?? ''} · ${runA.status}`}`
- `rightTitle={`Run B — ${runB.id.slice(0, 8)} · ${runB.llm_model ?? ''} · ${runB.status}`}`

La modale (overlay, fond, bouton Fermer, titre "Comparaison de runs")
reste intacte. La grille `1fr 1fr` est supprimée — `ColoredDiff` gère
son propre split.

### 4. Refactor `DiffViewer.tsx` (prompts)

Plus délicat à cause des badges `système` qui doivent rester en JSX :

- Garder les 2 `<h3>` au-dessus avec le numéro de version + badge
  conditionnel `is_system_default`
- Sous les 2 en-têtes, un seul `<ColoredDiff>` avec :
  - `oldValue={versionA.template}`
  - `newValue={versionB.template}`
  - **pas** de `leftTitle` / `rightTitle` (déjà au-dessus en JSX riche)

Le layout passe de `grid 1fr 1fr (2 colonnes)` à `flex column` :
ligne en-têtes (2 colonnes), puis le diff.

Choix : conserver les 2 colonnes pour les en-têtes pour aligner avec le
split du diff en dessous.

### 5. Vérifier

```bash
cd frontend
npm test
npm run typecheck
npm run lint
```

Cibles :
- 137 + 3 = **140 tests verts**
- typecheck : 0 erreur
- lint : 0 warning

### 6. Marquer décision résolue

Dans `docs/specs/12-open-decisions.md` § Sprint 5 :

```markdown
- [x] **Algo de diff coloré pour RunDiff/DiffViewer**
      Reporté Phase 2. `diff-match-patch` (Google) ou `react-diff-view`
      pour mettre en évidence les changements ligne par ligne.
      → **Décision (Phase 2, 2026-05-01) :** factorisation d'un composant
      `ColoredDiff` partagé qui encapsule `react-diff-viewer-continued`
      (déjà installé Sprint 7 pour `VersionDiff`). Refactor de `RunDiff`
      (analyses) et `DiffViewer` (prompts) pour le consommer. Pas de
      nouvelle dépendance.
```

### 7. Commit

```bash
git add frontend/src/components/ColoredDiff.tsx \
        frontend/src/__tests__/ColoredDiff.test.tsx \
        frontend/src/app/projects/[id]/role/VersionDiff.tsx \
        frontend/src/app/projects/[id]/analyses/RunDiff.tsx \
        frontend/src/app/projects/[id]/prompts/DiffViewer.tsx \
        docs/specs/12-open-decisions.md

git commit -m "feat(frontend): diff coloré ColoredDiff partagé (RunDiff + DiffViewer)"
```

Message multi-ligne en français, format conventionnel.

## Critères de complétude

- [ ] 3 tests `ColoredDiff` verts
- [ ] 5 tests `VersionDiff` toujours verts
- [ ] `npm test` total : 140 verts
- [ ] typecheck OK
- [ ] lint OK
- [ ] open-decisions cochée
- [ ] commit créé
