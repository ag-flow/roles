# 10 — Frontend UX : onglets, navigation, composants

> Document transversal frontend. À utiliser comme référence structurelle
> pendant tous les sprints qui touchent au front. Pas un sprint à part
> entière, mais une vue d'ensemble cohérente de l'UX.

## Objectif

Définir l'arborescence des écrans, la navigation, les composants
réutilisables et les patterns front-end (WebSocket, fetching, état) pour
garantir la cohérence d'ensemble entre les sprints.

## Stack frontend

- **Framework** : Next.js 14 avec App Router
- **Langage** : TypeScript en mode strict
- **Styling** : à choisir (Tailwind recommandé pour la rapidité MVP)
- **State management** : React state local + SWR ou TanStack Query pour
  les données serveur
- **WebSocket** : natif (window.WebSocket) ou library légère
- **UI library** : à choisir (shadcn/ui recommandé, ou rien et tout fait
  main)

## Arborescence des écrans

```
/                                      # landing (auth ou redirect /projects)
/login                                 # OIDC login si auth multi-user (TODO)
/projects                              # liste des role_projects
/projects/new                          # création d'un projet
/projects/[id]                         # tabs container du projet
  ├── sources                          # onglet Sources
  │   └── [sourceId]                   # détail d'une source + items
  ├── corpus                           # onglet Corpus
  ├── prompts                          # onglet Prompts
  │   └── [promptId]                   # détail + versions d'un prompt
  ├── analyses                         # onglet Analyses
  │   └── [runId]                      # détail d'un run
  └── role                             # onglet Rôle
/my-stack                              # tabs container "Ma stack"
  ├── social-accounts                  # comptes réseaux sociaux
  ├── transcription-services           # clés SaaS
  ├── mistral-config                   # secret Mistral ag.flow
  ├── publication                      # OAuth GitHub
  └── quotas                           # garde-fous
/settings                              # paramètres globaux
```

## Structure du repo frontend

```
frontend/src/
├── app/                               # Next.js App Router
│   ├── layout.tsx                     # root layout (header, theme)
│   ├── page.tsx                       # landing
│   ├── projects/
│   │   ├── page.tsx                   # liste
│   │   ├── new/page.tsx
│   │   └── [id]/
│   │       ├── layout.tsx             # tabs nav + project context
│   │       ├── page.tsx               # redirect → sources
│   │       ├── sources/
│   │       ├── corpus/
│   │       ├── prompts/
│   │       ├── analyses/
│   │       └── role/
│   ├── my-stack/
│   │   ├── layout.tsx                 # tabs nav
│   │   └── ...
│   └── settings/
├── components/                        # composants réutilisables
│   ├── ui/                            # primitives (Button, Input, Modal...)
│   ├── layout/                        # Header, Sidebar, Tabs
│   ├── feedback/                      # Toast, Loader, EmptyState
│   └── project/                       # composants liés au projet
├── lib/                               # logique non-React
│   ├── api/                           # client API typé
│   │   ├── client.ts                  # fetch wrapper + auth
│   │   ├── projects.ts
│   │   ├── sources.ts
│   │   ├── corpus.ts
│   │   ├── synthesis.ts
│   │   ├── stack.ts
│   │   └── publication.ts
│   ├── ws/                            # WebSocket client
│   │   ├── connection.ts
│   │   └── hooks.ts                   # useWebSocketEvent, etc.
│   ├── types/                         # types partagés (générés depuis OpenAPI ?)
│   └── utils/
└── styles/
```

## Patterns transverses

### Client API

Wrapper minimal autour de fetch avec auth et gestion d'erreurs uniformes :

```typescript
// frontend/src/lib/api/client.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL!;

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body);
  }

  if (resp.status === 204) {
    return undefined as T;
  }

  return resp.json();
}

export class ApiError extends Error {
  constructor(public status: number, public body: string) {
    super(`API error ${status}: ${body}`);
  }
}
```

### Modules d'API typés

Un module par domaine, exposant des fonctions typées :

```typescript
// frontend/src/lib/api/projects.ts
import { api } from './client';
import type { RoleProject, CreateRoleProjectRequest } from '../types';

export async function listProjects(): Promise<RoleProject[]> {
  return api('/api/role-projects');
}

export async function createProject(body: CreateRoleProjectRequest): Promise<RoleProject> {
  return api('/api/role-projects', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getProject(id: string): Promise<RoleProject> {
  return api(`/api/role-projects/${id}`);
}
```

### WebSocket : connexion unique

Une seule connexion WebSocket pour toute la session, avec dispatch par
event type :

```typescript
// frontend/src/lib/ws/connection.ts
type EventListener = (event: any) => void;

class WSManager {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<EventListener>> = new Map();
  private reconnectTimer: any = null;

  connect(url: string) {
    this.ws = new WebSocket(url);
    this.ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      const channel = event.channel;
      this.listeners.get(channel)?.forEach(fn => fn(event.payload));
    };
    this.ws.onclose = () => {
      this.reconnectTimer = setTimeout(() => this.connect(url), 3000);
    };
  }

  on(channel: string, fn: EventListener): () => void {
    if (!this.listeners.has(channel)) {
      this.listeners.set(channel, new Set());
    }
    this.listeners.get(channel)!.add(fn);
    return () => this.listeners.get(channel)!.delete(fn);
  }

  disconnect() {
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}

export const wsManager = new WSManager();
```

### Hook React WS

```typescript
// frontend/src/lib/ws/hooks.ts
import { useEffect } from 'react';
import { wsManager } from './connection';

export function useWebSocketEvent(
  channel: string,
  handler: (payload: any) => void,
) {
  useEffect(() => {
    const unsubscribe = wsManager.on(channel, handler);
    return unsubscribe;
  }, [channel, handler]);
}
```

Usage dans un composant :

```typescript
function ItemsList({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<SourceItem[]>([]);

  useWebSocketEvent('source_items_changes', (payload) => {
    if (payload.tenant_id !== currentTenantId) return;
    setItems(prev => prev.map(i => i.id === payload.id ? { ...i, status: payload.status } : i));
  });

  // ...
}
```

### Fetching avec SWR (recommandé)

```typescript
import useSWR from 'swr';
import { api } from '@/lib/api/client';

function useProject(id: string) {
  return useSWR(`/api/role-projects/${id}`, api);
}
```

### Mutations

```typescript
async function handleCreateProject(body: CreateRoleProjectRequest) {
  await createProject(body);
  await mutate('/api/role-projects'); // SWR cache invalidation
}
```

## Composants UI clés

### `ProjectTabs` (layout du projet)

```tsx
// frontend/src/app/projects/[id]/layout.tsx
'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';

const TABS = [
  { key: 'sources', label: 'Sources' },
  { key: 'corpus', label: 'Corpus' },
  { key: 'prompts', label: 'Prompts' },
  { key: 'analyses', label: 'Analyses' },
  { key: 'role', label: 'Rôle' },
];

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  const pathname = usePathname();

  return (
    <div className="project-layout">
      <ProjectHeader projectId={params.id} />
      <nav className="tabs">
        {TABS.map(tab => {
          const href = `/projects/${params.id}/${tab.key}`;
          const active = pathname.startsWith(href);
          return (
            <Link key={tab.key} href={href} className={active ? 'active' : ''}>
              {tab.label}
            </Link>
          );
        })}
      </nav>
      <main>{children}</main>
    </div>
  );
}
```

### `ItemsTable` (onglet Sources)

Tableau filtrable + sélectionnable des items découverts d'une source.

Cf. `03-scrapers.md` § "UI : onglet Sources".

### `CorpusSearchBar` (onglet Corpus)

Barre de recherche avec debounce, résultats sémantiques avec highlights.

Cf. `05-corpus-indexing.md` § "UI : onglet Corpus".

### `PipelineStepper` (onglet Analyses)

Composant qui affiche les 4 étages du pipeline avec leur état actuel.

```
[Extract ✓] → [Cluster ✓] → [Decompose ●] → [Write _]
                                  ↑
                          (en cours, 67%)
```

Permet de relancer un étage spécifique ou tout relancer.

### `RoleDocumentEditor` (onglet Rôle)

- Vue arborescente des sections et documents
- Pour chaque document : version actuelle, autres versions disponibles,
  édition manuelle, bouton "Régénérer"
- Diff side-by-side entre versions
- Lock/unlock (édition manuelle)

### `PushToAgflowDialog` (onglet Rôle)

Modal de confirmation avec :
- Aperçu de ce qui va être poussé (sections + docs count)
- Avertissements si éléments manquants
- Toggle "Générer le prompt orchestrateur après l'import"
- Bouton "Confirmer"

Cf. `08-export-agflow.md`.

### `PublishToGithubDialog` (onglet Rôle ou "Ma stack")

Modal de confirmation pour publication GitHub.

Cf. `09-github-publish.md`.

## Principes UX

### Async-first feedback

Toutes les actions longues affichent un feedback en temps réel :
- Spinner inline pour les actions courtes (<2s)
- Progression bar pour les actions longues
- Toast notification à la fin

### États de chargement

Trois états standardisés pour chaque vue :
- `loading` : skeleton loader
- `error` : message d'erreur avec bouton "Réessayer"
- `empty` : empty state avec call-to-action ("Aucune source, ajoutez-en une")

### Live updates

Les listes d'items en cours de traitement (sources, transcriptions) sont
mises à jour en temps réel via WebSocket. Pas besoin de refresh manuel.

### Navigation préservée

Les onglets du projet préservent leur état lors du switch (filtres
appliqués, sélection en cours). Stocker dans l'URL (search params) plutôt
que dans le state local.

### Mobile : pas une priorité MVP

L'app est conçue pour desktop (1280px+). Responsive minimal pour ne pas
casser sur tablette, mais pas de vue mobile dédiée pour le MVP.

## Authentification (à finaliser)

Cf. `12-open-decisions.md` § Auth.

**Pour le MVP mono-user (Beard) :** auth basique (Basic Auth sur le backend
ou cookie de session simple).

**Plus tard :** OIDC via Keycloak homelab.

Le composant `<AuthGuard>` au niveau du layout root protège toutes les
routes sauf `/login`.

## Internationalisation

Pour le MVP : **français uniquement**. Tous les textes en dur dans les
composants. Pas de système d'i18n.

À évaluer si on étend à l'anglais en Phase 2.

## Critères qualité (transverse)

- [ ] Aucun composant ne dépasse 300 lignes
- [ ] TypeScript strict, pas de `any` non justifié
- [ ] Tous les écrans ont les 3 états (loading, error, empty) gérés
- [ ] Tous les écrans avec des données live ont une connexion WebSocket
      qui pousse les updates
- [ ] Build production réussit sans warning
- [ ] `npm run typecheck` passe
- [ ] Lighthouse perf > 80 sur les pages principales

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Choix précis de la library UI (Tailwind seul, shadcn/ui, autre ?)
- [ ] Choix entre SWR et TanStack Query
- [ ] Génération automatique des types TypeScript depuis l'OpenAPI du
      backend (via `openapi-typescript`) ou écriture manuelle ?
- [ ] Stratégie d'erreur globale : ErrorBoundary par page, par tab, ou
      global ?
- [ ] Stratégie de cache pour les listes longues (chunks d'un corpus, par
      ex.) : pagination ou virtualisation ?

---

**Document précédent :** `09-github-publish.md`
**Document suivant :** `11-sequence-diagrams.md`
