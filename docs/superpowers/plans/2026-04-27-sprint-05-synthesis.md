# Sprint 5 — Synthesis Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** À partir d'un corpus indexé (chunks pgvector + signaux extraits via Mistral), générer automatiquement les documents atomiques d'un rôle ag.flow (sections Role / Missions / Skills) via une chaîne de prompts en 4 étages + un identity_synthesizer final. Onglets Prompts (gestion + versionning) et Analyses (déclenchement + suivi des runs) dans l'UI.

**Architecture:**
- **5 étages** dans `services/synthesis/{extractor,clusterer,decomposer,document_writer,identity_synthesizer}.py`. Chaque étage suit le même pattern : load prompt version → format avec contexte projet → invoke `agflow_client.chat` → persist (signaux/clusters/document_plans/role_documents) → update `runs.status`.
- **Bibliothèque prompts** versionnée DB (`prompts` + `prompt_versions` tables, déjà migrées Sprint 1). Seed initial via commande Python (`scripts/seed_prompts.py`) qui lit `backend/src/role_builder/synthesis/templates/*.md`. Idempotent, utilise `is_system_default=true`.
- **Routes API** : un endpoint POST par étage + `/role-documents/{id}/regenerate` + `/role-documents/{id}/set-current`.
- **Frontend** : onglets `analyses/` (PipelineStepper + RunCard + RunDiff) et `prompts/` (liste + VersionEditor + DiffViewer). Pas de pipeline auto MVP — l'utilisateur clique étage par étage.
- **WebSocket** : les events `runs_changes` (PG NOTIFY câblé Sprint 1 migration 0010) sont déjà relayés par `ws_relay` Sprint 2. Le frontend les consomme via `useWebSocketEvent('runs_changes')`.

**Tech Stack:**
- Backend : `agflow_client.invoke_chat` (Sprint 4), `corpus_search.find_relevant_chunks` (Sprint 4), `pydantic` pour valider les sorties JSON des LLM.
- Frontend : SWR + WebSocket + Server Actions Auth.js v5 (déjà en place).
- Pas de nouvelle dépendance Python ni npm.

**Décisions actées :**
- Modèle LLM : `settings.mistral_chat_model` (défaut `mistral-large-latest`).
- `response_format={"type": "json_object"}` pour les 3 premiers étages (extractor, clusterer, decomposer).
- `document_writer` + `identity_synthesizer` retournent du markdown libre.
- Sections verrouillées : `Role`, `Missions`, `Skills` (cf. spec 00 + 06).
- Seed via commande Python idempotente (templates `.md` versionnés en repo, table `prompts` reste vierge sans le seed).
- **Pas d'endpoint `/runs/full-pipeline` MVP** : déclenchement manuel par étage pour traçabilité + contrôle utilisateur.
- **Cost tracking** : `runs.cost_usd` calculé via `tokens_input * input_rate + tokens_output * output_rate` (rates par modèle dans Settings, hardcodés Mistral pour MVP).
- Multi-tenant : continue de passer par `TENANT_ID_DEFAULT` jusqu'au sprint Ma stack (Sprint 6).

**Critères de fin** (cf. spec 06 § Critères de fin de sprint) :
- Tous prompts système seedés en base (5 prompts × 1 version system_default).
- Pipeline complet s'exécute end-to-end sur un corpus de test (mock Mistral en tests, runtime réel via UI manuel).
- L'utilisateur peut promouvoir manuellement chaque doc en `is_current`.
- Régénération d'un doc avec `instruction_override` fonctionne.
- Comparaison side-by-side de deux runs dans l'UI (diff simple, pas algo avancé MVP).
- Identity générée à partir des documents `is_current`.
- Si pas de clé Mistral configurée → message d'erreur clair, pipeline bloqué.
- Coûts trackés dans `runs.cost_usd`.
- WebSocket `runs_changes` push la progression au front.

---

## File Structure

```
agflow.roles/
├── backend/
│   └── src/role_builder/
│       ├── config.py                                         # Phase A modify (rates Mistral pour cost calc)
│       ├── main.py                                           # Phase G modify (include routers synthesis + prompts)
│       ├── synthesis/                                        # Phase A NEW (paquet)
│       │   ├── __init__.py
│       │   ├── prompts_seed.py                               # Phase A : helper de seed
│       │   ├── extractor.py                                  # Phase B
│       │   ├── clusterer.py                                  # Phase C
│       │   ├── decomposer.py                                 # Phase D
│       │   ├── document_writer.py                            # Phase E
│       │   ├── identity_synthesizer.py                       # Phase F
│       │   └── templates/
│       │       ├── extractor_v1.md                           # Phase B
│       │       ├── clusterer_v1.md                           # Phase C
│       │       ├── decomposer_v1.md                          # Phase D
│       │       ├── document_writer_v1.md                     # Phase E
│       │       └── identity_synthesizer_v1.md                # Phase F
│       ├── db_helpers/
│       │   ├── prompts.py                                    # Phase A (CRUD prompts + versions)
│       │   ├── runs.py                                       # Phase A (insert/update/list runs)
│       │   ├── signals.py                                    # Phase B
│       │   ├── clusters.py                                   # Phase C
│       │   ├── document_plans.py                             # Phase D
│       │   └── role_documents.py                             # Phase E
│       ├── schemas/
│       │   ├── prompts.py                                    # Phase A
│       │   ├── runs.py                                       # Phase G
│       │   └── synthesis.py                                  # Phase G (DTOs trigger)
│       └── routes/
│           ├── prompts.py                                    # Phase A (CRUD via API)
│           └── synthesis.py                                  # Phase G (POST /runs/...)
├── backend/
│   ├── scripts/
│   │   └── seed_prompts.py                                   # Phase A NEW (commande CLI)
│   └── tests/
│       ├── test_synthesis_extractor.py                       # Phase B
│       ├── test_synthesis_clusterer.py                       # Phase C
│       ├── test_synthesis_decomposer.py                      # Phase D
│       ├── test_synthesis_document_writer.py                 # Phase E
│       ├── test_synthesis_identity_synthesizer.py            # Phase F
│       ├── test_db_helpers_prompts.py                        # Phase A
│       ├── test_db_helpers_runs.py                           # Phase A
│       ├── test_prompts_seed.py                              # Phase A
│       └── test_synthesis_route.py                           # Phase G
│
└── frontend/
    └── src/
        ├── lib/api/
        │   ├── prompts.ts                                    # Phase I
        │   ├── runs.ts                                       # Phase H
        │   └── synthesis.ts                                  # Phase H
        ├── lib/types.ts                                      # Phase H+I (extend)
        └── app/projects/[id]/
            ├── analyses/
            │   ├── page.tsx                                  # Phase H
            │   ├── PipelineStepper.tsx                       # Phase H
            │   ├── RunCard.tsx                               # Phase H
            │   └── RunDiff.tsx                               # Phase H
            └── prompts/
                ├── page.tsx                                  # Phase I
                ├── [promptId]/page.tsx                       # Phase I
                ├── VersionEditor.tsx                         # Phase I
                └── DiffViewer.tsx                            # Phase I
```

---

# Phase A — Bibliothèque de prompts (DB + helpers + seed + routes)

## A1 : Settings cost rates + paquet synthesis

**Files:**
- Modify: `backend/src/role_builder/config.py`
- Create: `backend/src/role_builder/synthesis/__init__.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Étendre Settings**

Ajouter à `Settings` :
```python
mistral_input_token_rate_usd: float = 0.000002    # $2/M tokens input pour mistral-large-latest (à mettre à jour)
mistral_output_token_rate_usd: float = 0.000006   # $6/M tokens output
```

`backend/src/role_builder/synthesis/__init__.py` :
```python
"""Pipeline de synthèse : extractor → clusterer → decomposer → document_writer → identity_synthesizer."""
```

Étendre `test_config.py` pour vérifier les 2 nouveaux defaults.

Commit : `feat(backend): config rates Mistral input/output token + paquet synthesis`

## A2 : `db_helpers/prompts.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/prompts.py`
- Create: `backend/tests/test_db_helpers_prompts.py`

Signatures :
```python
async def upsert_prompt(
    *, name: str, type: str, target_section: str | None = None,
    description: str | None = None, pool: asyncpg.Pool,
) -> UUID: ...

async def get_prompt_by_name(name: str, *, pool) -> dict | None: ...
async def list_prompts(*, pool) -> list[dict]: ...

async def insert_prompt_version(
    *, prompt_id: UUID, version_number: int, template: str,
    parameters_schema: dict | None = None,
    is_system_default: bool = False,
    created_by: UUID | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """Insert. Si is_system_default=True, désactive le précédent system_default
    via UPDATE (l'index unique partial WHERE is_system_default=true exige une
    seule version active à la fois)."""

async def get_system_default_version(prompt_name: str, *, pool) -> dict | None:
    """JOIN prompts/prompt_versions, retourne la version active system_default."""

async def list_versions(prompt_id: UUID, *, pool) -> list[dict]: ...
```

Tests TDD (~6 tests, asyncpg stub pattern Sprint 1/2/3) :
1. `upsert_prompt` insert si nouveau, update sinon.
2. `get_prompt_by_name` retourne None si absent, dict sinon.
3. `insert_prompt_version` avec `is_system_default=True` UPDATE le précédent.
4. `get_system_default_version` JOIN correct.
5. `list_versions` retourne triés par `version_number DESC`.
6. `list_prompts` retourne tous les prompts.

Commit : `feat(backend): db_helpers/prompts (CRUD prompts + versions + system_default management)`

## A3 : `db_helpers/runs.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/runs.py`
- Create: `backend/tests/test_db_helpers_runs.py`

Signatures :
```python
async def create_run(
    *, role_project_id: UUID, tenant_id: UUID, prompt_version_id: UUID,
    input_summary: dict | None = None, parameters: dict | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT runs avec status='pending'."""

async def mark_running(run_id: UUID, *, pool) -> None: ...

async def mark_done(
    run_id: UUID, *, output: str | None,
    llm_provider: str = "mistral", llm_model: str,
    tokens_input: int, tokens_output: int, cost_usd: float,
    pool: asyncpg.Pool,
) -> None: ...

async def mark_failed(run_id: UUID, error: str, *, pool) -> None: ...

async def list_runs(
    role_project_id: UUID, *, status: str | None = None, limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict]: ...

async def get_run(run_id: UUID, *, pool) -> dict | None: ...
```

Tests : 5-6 tests TDD.

Commit : `feat(backend): db_helpers/runs (create + lifecycle + list)`

## A4 : Templates de prompts (seed source)

**Files:**
- Create: `backend/src/role_builder/synthesis/templates/extractor_v1.md`
- Create: `backend/src/role_builder/synthesis/templates/clusterer_v1.md`
- Create: `backend/src/role_builder/synthesis/templates/decomposer_v1.md`
- Create: `backend/src/role_builder/synthesis/templates/document_writer_v1.md`
- Create: `backend/src/role_builder/synthesis/templates/identity_synthesizer_v1.md`

Contenus exacts depuis `docs/specs/06-synthesis.md` (chaque étage a son prompt système). À copier-coller depuis la spec.

Pour `extractor_v1.md` :
```markdown
Tu es un analyste expert en extraction de connaissances à partir de transcripts.

Ton objectif : extraire des SIGNAUX atomiques et exploitables d'un corpus
audio transcrit. Un signal est une unité d'information qui capture un trait
distinctif du raisonnement, de l'expertise ou du style de la personne
analysée.

Types de signaux :
- heuristique : une règle pratique, un principe d'action
- anecdote : une histoire vécue, un cas concret raconté
- vocab : un terme ou une expression spécifique au domaine
- cadre : un modèle mental, un framework de pensée
- opinion : une position tranchée ou une préférence affirmée

Pour chaque signal extrait :
1. Identifie son type
2. Donne un titre court (5-10 mots)
3. Décris-le avec précision (2-3 phrases)
4. Note le contexte (où il apparaît, à quelle fréquence)
5. Pointe les chunks sources (chunk_id UUID dans source_chunks)

Directives globales du projet : {global_directives}

Voici les chunks à analyser (avec leur chunk_id) :
{chunks}

Réponds en JSON strict, sans préambule, format :
{{"signals": [{{"type": "heuristique|anecdote|vocab|cadre|opinion", "content": {{"title": "...", "description": "...", "context": "..."}}, "source_chunks": ["uuid1", "uuid2"]}}]}}
```

Idem pour les 4 autres (cf. spec 06 § Étage N : Prompt système).

Note : utiliser `{{` et `}}` pour échapper les accolades dans `.format()` Python (les accolades simples `{}` sont des placeholders).

Commit : `feat(backend): templates Markdown des 5 prompts système (extractor/clusterer/decomposer/writer/identity)`

## A5 : `synthesis/prompts_seed.py` + script seed (TDD)

**Files:**
- Create: `backend/src/role_builder/synthesis/prompts_seed.py`
- Create: `backend/scripts/seed_prompts.py`
- Create: `backend/tests/test_prompts_seed.py`

`prompts_seed.py` :
```python
"""Seed initial des 5 prompts système avec leur version v1.

Idempotent : à chaque exécution, vérifie si une version system_default existe
pour chaque prompt et n'en crée une nouvelle que si manquante ou si le
template a changé.
"""
from __future__ import annotations

from pathlib import Path

import asyncpg

from role_builder.db_helpers import prompts as prompts_helper


SEED_DEFINITIONS: list[dict[str, object]] = [
    {
        "name": "extractor",
        "type": "extractor",
        "target_section": None,
        "description": "Extrait des signaux atomiques (heuristique/anecdote/vocab/cadre/opinion) depuis des chunks de corpus.",
        "template_file": "extractor_v1.md",
    },
    {
        "name": "clusterer",
        "type": "clusterer",
        "target_section": None,
        "description": "Regroupe des signaux en clusters thématiques cohérents.",
        "template_file": "clusterer_v1.md",
    },
    {
        "name": "decomposer",
        "type": "decomposer",
        "target_section": None,
        "description": "Produit un plan de documents par section (Role/Missions/Skills) à partir des clusters.",
        "template_file": "decomposer_v1.md",
    },
    {
        "name": "document_writer",
        "type": "writer",
        "target_section": None,
        "description": "Rédige un document atomique markdown à partir d'un brief, signaux supportants et chunks RAG.",
        "template_file": "document_writer_v1.md",
    },
    {
        "name": "identity_synthesizer",
        "type": "identity",
        "target_section": None,
        "description": "Produit l'identity du rôle à partir des documents current.",
        "template_file": "identity_synthesizer_v1.md",
    },
]


def _read_template(name: str) -> str:
    """Lit un template depuis le paquet synthesis/templates/."""
    path = Path(__file__).parent / "templates" / name
    return path.read_text(encoding="utf-8")


async def seed_system_prompts(pool: asyncpg.Pool) -> dict[str, int]:
    """Idempotent. Retourne un dict {prompt_name: action} avec action in
    {created, version_added, unchanged}."""
    actions: dict[str, str] = {}
    for definition in SEED_DEFINITIONS:
        name = str(definition["name"])
        template = _read_template(str(definition["template_file"]))

        prompt_id = await prompts_helper.upsert_prompt(
            name=name,
            type=str(definition["type"]),
            target_section=definition["target_section"],  # type: ignore[arg-type]
            description=str(definition["description"]),
            pool=pool,
        )

        existing = await prompts_helper.get_system_default_version(name, pool=pool)
        if existing is not None and existing["template"] == template:
            actions[name] = "unchanged"
            continue

        # Calcul du nouveau version_number = max + 1
        versions = await prompts_helper.list_versions(prompt_id, pool=pool)
        next_version = (max((v["version_number"] for v in versions), default=0)) + 1

        await prompts_helper.insert_prompt_version(
            prompt_id=prompt_id,
            version_number=next_version,
            template=template,
            is_system_default=True,
            pool=pool,
        )
        actions[name] = "created" if not versions else "version_added"

    return actions
```

Tests `test_prompts_seed.py` (3-4 tests) :
1. Première exec : 5 actions `created`.
2. Deuxième exec sans modif templates : 5 actions `unchanged`.
3. Modif template : action `version_added`.
4. Vérifier que `is_system_default=True` est bien transmis.

`backend/scripts/seed_prompts.py` :
```python
"""CLI : python -m scripts.seed_prompts (depuis le dossier backend/)."""
from __future__ import annotations

import asyncio

import asyncpg

from role_builder.config import settings
from role_builder.synthesis.prompts_seed import seed_system_prompts


async def main() -> None:
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        actions = await seed_system_prompts(pool)
        for name, action in actions.items():
            print(f"  {name}: {action}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
```

Commit : `feat(backend): synthesis/prompts_seed (idempotent, lit templates/*.md) + scripts/seed_prompts.py`

## A6 : Schemas + routes prompts CRUD (TDD)

**Files:**
- Create: `backend/src/role_builder/schemas/prompts.py`
- Create: `backend/src/role_builder/routes/prompts.py`
- Create: `backend/tests/test_prompts_route.py`

Schemas Pydantic :
```python
class PromptOut(BaseModel):
    id: UUID
    name: str
    type: str
    target_section: str | None = None
    description: str | None = None

class PromptVersionOut(BaseModel):
    id: UUID
    prompt_id: UUID
    version_number: int
    template: str
    is_system_default: bool
    created_at: datetime

class CreateVersionRequest(BaseModel):
    template: str
```

Endpoints (sous router avec `Depends(get_current_user)`) :
- `GET /api/prompts` → list[PromptOut]
- `GET /api/prompts/{prompt_id}/versions` → list[PromptVersionOut]
- `POST /api/prompts/{prompt_id}/versions` body `CreateVersionRequest` → crée une nouvelle version (créé par user, `is_system_default=False`, version_number = max+1)
- `PUT /api/prompts/{prompt_id}/system-default/{version_id}` → promote une version comme system_default

Tests : 4 tests (GET list, GET versions, POST nouvelle version, PUT promote).

Commit : `feat(backend): schemas + routes prompts (GET list, GET versions, POST version, PUT system-default)`

---

# Phase B — Étage 1 : Extractor

## B1 : `db_helpers/signals.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/signals.py`
- Create: `backend/tests/test_db_helpers_signals.py`

Signatures :
```python
async def insert_signal(
    *, run_id: UUID, role_project_id: UUID, tenant_id: UUID,
    source_item_id: UUID | None = None, source_chunks: list[UUID],
    signal_type: str, content: dict,
    pool: asyncpg.Pool,
) -> UUID: ...

async def list_signals_by_run(run_id: UUID, *, pool) -> list[dict]: ...
async def list_signals_by_project(
    role_project_id: UUID, *, type: str | None = None, pool,
) -> list[dict]: ...
async def get_signals_by_ids(ids: list[UUID], *, pool) -> list[dict]: ...
```

Tests : 4 tests TDD asyncpg stub.

Commit : `feat(backend): db_helpers/signals (insert + list_by_run/project + get_by_ids)`

## B2 : `synthesis/extractor.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/synthesis/extractor.py`
- Create: `backend/tests/test_synthesis_extractor.py`

Signature :
```python
async def run_extraction(
    role_project_id: UUID,
    *,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    chunks_per_batch: int = 5,
    pool: asyncpg.Pool,
) -> UUID:
    """Lance l'extraction sur tous les chunks indexed du projet.

    Steps :
      1. Resolve prompt_version (system_default si non fourni).
      2. Get role_project (pour global_directives).
      3. List corpus_chunks du projet.
      4. Create run (status=running).
      5. Pour chaque batch de N chunks :
         a. Format prompt avec global_directives + chunks textuels.
         b. agflow_client.invoke_chat(messages, response_format=json_object).
         c. Parse JSON, valider format {signals: [...]}.
         d. db_helpers.signals.insert_signal pour chacun.
         e. Accumuler tokens/cost.
      6. Mark run done avec output={signals_count: N}.

    Retourne run_id. Lève RuntimeError si projet sans mistral_secret_ref OU
    sans corpus_chunks.
    """
```

Implémentation utilise :
- `db_helpers.role_projects.get_by_id(role_project_id, pool=pool)` (à ajouter au helper si manquant)
- `db_helpers.corpus_chunks.list_by_project(role_project_id, pool=pool)` (existe Sprint 4)
- `db_helpers.prompts.get_system_default_version("extractor", pool=pool)` ou `prompts.get_version_by_id(prompt_version_id, pool=pool)`
- `db_helpers.runs.create_run/mark_running/mark_done/mark_failed`
- `services.agflow_client.get_agflow_client().invoke_chat(...)`
- `db_helpers.signals.insert_signal`
- Cost calc : `(tokens_input * settings.mistral_input_token_rate_usd) + (tokens_output * settings.mistral_output_token_rate_usd)`.

Pour valider la sortie JSON, utiliser un schéma Pydantic interne :
```python
class _ExtractorSignal(BaseModel):
    type: Literal["heuristique", "anecdote", "vocab", "cadre", "opinion"]
    content: dict
    source_chunks: list[str]  # UUIDs en str

class _ExtractorResponse(BaseModel):
    signals: list[_ExtractorSignal]
```

`_ExtractorResponse.model_validate_json(...)` parse + valide.

Tests TDD (~5 tests) :
1. Happy path : 5 chunks → invoke_chat retourne JSON avec 2 signaux → 2 INSERT signals + run done.
2. Pas de chunks indexed → RuntimeError clair.
3. JSON invalide retourné par Mistral → mark_failed avec error.
4. Multiple batches (10 chunks, batch=5) → 2 invocations Mistral.
5. `instruction_override` propagé dans messages user.

Mock `agflow_client.get_agflow_client()` avec un stub qui retourne un `ChatResult` pré-construit (content + tokens).
Mock `db_helpers` via monkeypatch.

Commit : `feat(backend): synthesis/extractor (corpus chunks → signaux JSON, batching configurable)`

## B3 : Helper `db_helpers.role_projects.get_by_id` (si manquant)

**Files:**
- Modify: `backend/src/role_builder/db_helpers/role_projects.py`
- Modify: `backend/tests/test_db_helpers_role_projects.py` (si fichier de test existe, sinon créer)

Si `role_projects.py` n'a que `get_user_id_for_project`, ajouter :
```python
async def get_by_id(role_project_id: UUID, *, pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM role_projects WHERE id = $1",
            role_project_id,
        )
    return dict(row) if row else None
```

+ test stub asyncpg.

Commit : `feat(backend): db_helpers/role_projects.get_by_id (full row pour pipeline synthèse)`

---

# Phase C — Étage 2 : Clusterer

## C1 : `db_helpers/clusters.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/clusters.py`
- Create: `backend/tests/test_db_helpers_clusters.py`

Signatures :
```python
async def insert_cluster(
    *, run_id, role_project_id, tenant_id,
    name: str, description: str | None, signal_ids: list[UUID],
    pool,
) -> UUID: ...

async def list_clusters_by_run(run_id, *, pool) -> list[dict]: ...
async def list_clusters_by_project(role_project_id, *, pool) -> list[dict]: ...
```

Tests : 3 tests.

Commit : `feat(backend): db_helpers/clusters (insert + list_by_run/project)`

## C2 : `synthesis/clusterer.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/synthesis/clusterer.py`
- Create: `backend/tests/test_synthesis_clusterer.py`

Signature :
```python
async def run_clustering(
    role_project_id: UUID,
    *,
    signal_run_id: UUID | None = None,  # filtre signaux par run, sinon tous les signaux du projet
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """signaux → clusters thématiques.

    Steps :
      1. Resolve prompt_version.
      2. Get signaux (filter par run_id si fourni, sinon tous les signaux du projet).
      3. Create run.
      4. Format prompt avec signaux sérialisés (JSON inline).
      5. invoke_chat → JSON {clusters: [{name, description, signal_ids: [...]}]}.
      6. Pour chaque cluster : insert_cluster.
      7. Mark run done.
    """
```

Pattern d'implémentation strictement aligné sur extractor (B2). Tests : 4-5 (happy path, pas de signaux, JSON invalide, instruction_override propagé).

Schema Pydantic interne `_ClustererResponse` :
```python
class _Cluster(BaseModel):
    name: str
    description: str | None = None
    signal_ids: list[str]

class _ClustererResponse(BaseModel):
    clusters: list[_Cluster]
```

Commit : `feat(backend): synthesis/clusterer (signaux → clusters thématiques)`

---

# Phase D — Étage 3 : Decomposer

## D1 : `db_helpers/document_plans.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/document_plans.py`
- Create: `backend/tests/test_db_helpers_document_plans.py`

Signatures :
```python
async def insert_document_plan(
    *, run_id, role_project_id, tenant_id,
    section: str, planned_documents: list[dict],
    pool,
) -> UUID:
    """planned_documents = list de {name, brief, supporting_signals: [signal_id, ...]}."""

async def list_plans_by_run(run_id, *, pool) -> list[dict]: ...
async def list_plans_by_project(role_project_id, *, section: str | None = None, pool) -> list[dict]: ...
async def get_latest_plan_per_section(role_project_id, *, pool) -> dict[str, dict]:
    """Retourne {section: plan_dict} avec le dernier plan par section."""
```

Tests : 4 tests.

Commit : `feat(backend): db_helpers/document_plans (insert + list + get_latest_per_section)`

## D2 : `synthesis/decomposer.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/synthesis/decomposer.py`
- Create: `backend/tests/test_synthesis_decomposer.py`

Signature :
```python
async def run_decomposition(
    role_project_id: UUID,
    *,
    cluster_run_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """clusters → plan de documents par section (Role/Missions/Skills).

    Schema sortie attendu :
      {"sections": {
          "Role":     {"documents": [{name, brief, supporting_signals}]},
          "Missions": {"documents": [...]},
          "Skills":   {"documents": [...]}
      }}
    """
```

Implémentation : récupère clusters + signaux référencés, format prompt, invoke, parse, insert un `document_plan` PAR SECTION (3 inserts si tout va bien).

Schema Pydantic :
```python
class _PlannedDoc(BaseModel):
    name: str
    brief: str
    supporting_signals: list[str]

class _SectionPlan(BaseModel):
    documents: list[_PlannedDoc]

class _DecomposerResponse(BaseModel):
    sections: dict[Literal["Role", "Missions", "Skills"], _SectionPlan]
```

Tests : 4 tests.

Commit : `feat(backend): synthesis/decomposer (clusters → plan documents par section verrouillée)`

---

# Phase E — Étage 4 : Document writer + role_documents helpers

## E1 : `db_helpers/role_documents.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/db_helpers/role_documents.py`
- Create: `backend/tests/test_db_helpers_role_documents.py`

Signatures :
```python
async def insert_role_document(
    *, role_project_id, tenant_id,
    section: str, name: str, content: str,
    source_run_id: UUID,
    is_current: bool = False,
    pool,
) -> UUID:
    """Calcule version = max(version) + 1 pour (role_project_id, section, name)."""

async def get_by_id(doc_id: UUID, *, pool) -> dict | None: ...

async def list_by_section(
    role_project_id: UUID, section: str, *,
    only_current: bool = False, pool,
) -> list[dict]: ...

async def list_current_by_project(role_project_id: UUID, *, pool) -> list[dict]: ...

async def set_current(doc_id: UUID, *, pool) -> None:
    """Démote l'ancien current de (project, section, name) puis promote ce doc.
    Doit être atomique (transaction)."""

async def lock_document(doc_id: UUID, *, pool) -> None: ...
async def unlock_document(doc_id: UUID, *, pool) -> None: ...
```

L'index unique partiel `role_documents_current_unique ON (role_project_id, section, name) WHERE is_current = true` (migration 0008) impose qu'on désactive l'ancien current avant d'activer le nouveau, dans la même transaction.

Tests : 5 tests.

Commit : `feat(backend): db_helpers/role_documents (insert + set_current atomic + lock/unlock)`

## E2 : `synthesis/document_writer.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/synthesis/document_writer.py`
- Create: `backend/tests/test_synthesis_document_writer.py`

Signature :
```python
async def write_document(
    role_project_id: UUID,
    section: str,
    doc_plan: dict,  # {name, brief, supporting_signals}
    *,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
    rag_top_k: int = 8,
    rag_min_similarity: float = 0.5,
    pool: asyncpg.Pool,
) -> UUID:
    """Écrit UN document atomique. Retourne le run_id (le doc lui-même est inséré
    avec is_current=False — l'utilisateur promeut manuellement).

    Steps :
      1. Resolve prompt_version (system_default writer).
      2. Get signaux supportants via signal_ids.
      3. Get RAG chunks via corpus_search.find_relevant_chunks(brief, top_k).
      4. Format prompt avec section/name/brief/global_directives/signals/chunks.
      5. Create run.
      6. invoke_chat (markdown libre, pas de response_format JSON).
      7. Insert role_document (is_current=False).
      8. Mark run done avec output=markdown produit.
    """
```

Note : pas de schema Pydantic strict en sortie (markdown libre). Le markdown du LLM est le contenu du doc.

Tests : 4-5 tests :
1. Happy path : invoke_chat retourne markdown → role_document inséré + run done.
2. RAG retourne 0 chunks → quand même produit le doc avec juste les signaux.
3. `instruction_override` propagé dans user message.
4. Section verrouillée (Role/Missions/Skills) ou custom — vérifier qu'on n'impose pas la liste verrouillée à ce niveau (c'est decomposer qui les a).

Commit : `feat(backend): synthesis/document_writer (1 doc à la fois, RAG via corpus_search, markdown libre)`

## E3 : Endpoint write-documents-batch (1 commit)

Service-level helper qui itère sur tous les docs du dernier `document_plan` d'une section et lance `write_document` pour chacun (en parallèle bornée via `asyncio.Semaphore`).

```python
async def write_all_documents_for_plan(
    role_project_id: UUID,
    plan_id: UUID,
    *,
    parallelism: int = 3,
    pool: asyncpg.Pool,
) -> list[UUID]:
    """Lance N write_document en parallèle, retourne les run_ids."""
```

Tests : 1 test qui vérifie le sémaphore + l'appel par doc.

Commit : `feat(backend): synthesis/write_all_documents_for_plan (parallélisme borné par section)`

---

# Phase F — Étage 5 : Identity synthesizer

## F1 : `synthesis/identity_synthesizer.py` (TDD)

**Files:**
- Create: `backend/src/role_builder/synthesis/identity_synthesizer.py`
- Create: `backend/tests/test_synthesis_identity_synthesizer.py`

Signature :
```python
async def synthesize_identity(
    role_project_id: UUID,
    *,
    prompt_version_id: UUID | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """À partir des role_documents.is_current=True, produit l'identity du rôle.

    Steps :
      1. List documents current du projet.
      2. Format prompt avec display_name, description, global_directives, documents (groupés par section).
      3. invoke_chat (markdown libre).
      4. UPDATE role_projects.identity = markdown produit.
      5. Mark run done.
    """
```

Tests : 3 tests :
1. Happy path : 5 docs current → invoke_chat → role_projects.identity updated.
2. Aucun doc current → RuntimeError clair "promote at least one document".
3. Vérifier que les docs sont groupés par section dans le prompt.

Helper `db_helpers.role_projects.update_identity(role_project_id, identity: str, *, pool)` à ajouter.

Commit : `feat(backend): synthesis/identity_synthesizer (docs current → identity markdown)`

---

# Phase G — Routes API synthesis (1 routeur, 6 endpoints)

## G1 : Schemas + route synthesis (TDD)

**Files:**
- Create: `backend/src/role_builder/schemas/synthesis.py`
- Create: `backend/src/role_builder/schemas/runs.py`
- Create: `backend/src/role_builder/routes/synthesis.py`
- Create: `backend/tests/test_synthesis_route.py`
- Modify: `backend/src/role_builder/main.py` (include router)

Endpoints (sous router avec `Depends(get_current_user)`) :

```python
@router.post("/role-projects/{project_id}/runs/extract", status_code=202)
async def trigger_extraction(...) -> {"run_id": str}: ...

@router.post("/role-projects/{project_id}/runs/cluster", status_code=202)
async def trigger_clustering(...) -> {"run_id": str}: ...

@router.post("/role-projects/{project_id}/runs/decompose", status_code=202)
async def trigger_decomposition(...) -> {"run_id": str}: ...

@router.post("/role-projects/{project_id}/runs/write-documents", status_code=202)
async def trigger_document_writing(plan_id: UUID, ...) -> {"run_ids": [str, ...]}:
    """Body : {"plan_id": uuid, "parallelism": 3}."""

@router.post("/role-projects/{project_id}/runs/synthesize-identity", status_code=202)
async def trigger_identity_synthesis(...) -> {"run_id": str}: ...

@router.post("/role-documents/{doc_id}/regenerate", status_code=202)
async def regenerate_document(...) -> {"run_id": str}:
    """Body : {"instruction_override": str | null}.
    Retrouve le plan/section/name depuis role_documents → relance write_document."""

@router.post("/role-documents/{doc_id}/set-current")
async def set_current_version(doc_id: UUID, ...) -> {"status": "ok"}: ...

@router.get("/role-projects/{project_id}/runs")
async def list_runs(project_id: UUID, status: str | None = None, limit: int = 50, ...) -> list[RunOut]: ...

@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, ...) -> RunOut: ...
```

Implémentation : chaque trigger est une simple wrapper sur la fonction du module synthesis correspondant. La fonction synthesis est lancée en `asyncio.create_task` pour ne pas bloquer la réponse HTTP — on retourne 202 immédiatement avec `run_id`.

Pour `regenerate_document` : retrouver le plan via `source_run_id` du role_document → reconstituer doc_plan dict → appeler `write_document(... instruction_override=...)`.

Schema runs.py :
```python
class RunOut(BaseModel):
    id: UUID
    role_project_id: UUID
    prompt_version_id: UUID
    status: str
    output: str | None
    llm_provider: str | None
    llm_model: str | None
    tokens_input: int | None
    tokens_output: int | None
    cost_usd: float | None
    instruction_override: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime
```

Tests `test_synthesis_route.py` (~6-8 tests) :
1. POST extract → 202 + run_id (mock `synthesis.extractor.run_extraction`).
2. POST cluster, decompose, write-documents, synthesize-identity → 202.
3. POST regenerate → 202.
4. POST set-current → 200.
5. GET runs avec/sans filtre status.
6. GET run by id.

Commit : `feat(backend): routes synthesis (6 trigger endpoints + 2 list/get + set-current + regenerate)`

---

# Phase H — Frontend onglet Analyses

## H1 : Types + clients API runs/synthesis (1 commit, TDD)

**Files:**
- Modify: `frontend/src/lib/types.ts` (ajout `Run`, `Cluster`, `Signal`, `RoleDocument`, `DocumentPlan`)
- Create: `frontend/src/lib/api/runs.ts`
- Create: `frontend/src/lib/api/synthesis.ts`
- Create: `frontend/src/__tests__/synthesis-api.test.ts`

Types :
```typescript
export interface Run {
  id: string;
  role_project_id: string;
  prompt_version_id: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  output: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  tokens_input: number | null;
  tokens_output: number | null;
  cost_usd: number | null;
  instruction_override: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
}
```

Client `synthesis.ts` :
```typescript
import { api } from './client';

export async function triggerExtraction(projectId: string, body: { prompt_version_id?: string; instruction_override?: string } = {}) {
  return api<{ run_id: string }>(`/api/role-projects/${projectId}/runs/extract`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
// + triggerClustering, triggerDecomposition, triggerDocumentWriting, triggerIdentitySynthesis,
//   regenerateDocument, setCurrentVersion
```

Client `runs.ts` :
```typescript
export async function listRuns(projectId: string, opts: { status?: string; limit?: number } = {}): Promise<Run[]> { ... }
export async function getRun(runId: string): Promise<Run> { ... }
```

Tests Vitest (~5 tests) : URLs construites + body parsing.

Commit : `feat(frontend): clients API runs + synthesis (7 trigger endpoints) + types Run/Cluster/Signal/RoleDocument`

## H2 : Page Analyses + PipelineStepper + RunCard (1 commit)

**Files:**
- Create: `frontend/src/app/projects/[id]/analyses/page.tsx`
- Create: `frontend/src/app/projects/[id]/analyses/PipelineStepper.tsx`
- Create: `frontend/src/app/projects/[id]/analyses/RunCard.tsx`

`page.tsx` (Client Component à cause des interactions) :
- Header avec `<PipelineStepper>` (5 étages avec boutons "Lancer")
- Liste des runs récents via SWR
- Chaque run rendu en `<RunCard>` cliquable

`PipelineStepper.tsx` :
- 5 boutons : "Extraire signaux", "Regrouper en clusters", "Planifier documents", "Écrire documents", "Générer identity"
- Chaque bouton appelle le trigger correspondant + toast feedback
- État disabled si étage précédent pas done (pour MVP, autorise tout)

`RunCard.tsx` :
- Affiche : type (depuis prompt_version → prompt.type), status (avec couleur), tokens/cost, timestamps, error si failed
- Click → ouvre modal avec output complet

Live updates via `useWebSocketEvent('runs_changes', () => mutate(...))`.

Commit : `feat(frontend): page Analyses (PipelineStepper 5 étages + RunCard live updates WS)`

## H3 : RunDiff side-by-side (1 commit)

**Files:**
- Create: `frontend/src/app/projects/[id]/analyses/RunDiff.tsx`

Composant qui prend 2 runs en props et affiche leurs `output` côte à côte en 2 colonnes. Pour MVP : pas de coloration de diff (juste affichage côte à côte). Ajout futur via `diff-match-patch` ou `react-diff-view`.

Bouton "Comparer" dans la liste runs ouvre une modal avec dropdown pour choisir le 2e run.

Commit : `feat(frontend): RunDiff (comparaison side-by-side de 2 runs)`

---

# Phase I — Frontend onglet Prompts

## I1 : Types + clients API prompts (1 commit, TDD)

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api/prompts.ts`
- Create: `frontend/src/__tests__/prompts-api.test.ts`

Types Prompt + PromptVersion. Client `listPrompts`, `listVersions(promptId)`, `createVersion(promptId, template)`, `setSystemDefault(promptId, versionId)`.

Tests : 4 tests Vitest.

Commit : `feat(frontend): clients API prompts (CRUD versions) + types`

## I2 : Page Prompts + détail (2 commits)

**Files:**
- Create: `frontend/src/app/projects/[id]/prompts/page.tsx`
- Create: `frontend/src/app/projects/[id]/prompts/[promptId]/page.tsx`
- Create: `frontend/src/app/projects/[id]/prompts/VersionEditor.tsx`
- Create: `frontend/src/app/projects/[id]/prompts/DiffViewer.tsx`

`prompts/page.tsx` : liste les 5 prompts (extractor, clusterer, decomposer, document_writer, identity_synthesizer) + leur version system_default + bouton "Voir versions".

`[promptId]/page.tsx` : liste des versions + bouton "Restaurer la version système" + bouton "Nouvelle version" (ouvre `VersionEditor`).

`VersionEditor.tsx` : textarea grand format pour le template + Save crée nouvelle version via API. **Note prompts {global_directives}, {chunks}, etc.** rappel pédagogique.

`DiffViewer.tsx` : compare 2 versions côte à côte (texte brut, scrollable).

Commit 1 : `feat(frontend): page Prompts (liste + détail versions)`
Commit 2 : `feat(frontend): VersionEditor + DiffViewer (édition + comparaison versions prompts)`

---

# Phase J — Tag + open-decisions

## J1 : MAJ `12-open-decisions.md`

Acter Sprint 5 :
- Modèle Mistral chat : `mistral-large-latest` par défaut.
- Cost calc : tokens × rates (rates hardcodés Mistral, à mettre à jour si pricing change).
- 5 prompts seedés depuis templates `.md` versionnés en repo (commande `python -m scripts.seed_prompts`).
- Pas de pipeline auto MVP — l'utilisateur clique étage par étage.
- Régénération un doc à la fois (instruction_override propagé).
- Diff visuel : affichage côte à côte texte brut, pas de coloration MVP.
- Validation JSON sortie LLM via Pydantic interne par étage.

Reportés Phase 2 :
- Pipeline auto `/runs/full-pipeline` (déclenche les 5 étages d'un coup).
- Algo de diff coloré (`diff-match-patch` ou `react-diff-view`).
- Cache obsolescence : si `global_directives` change, marquer les anciens runs "obsolete".
- Map-reduce pour gros corpus (> 500 chunks dans extractor).
- Word-level confidence dans le RAG (sélection des meilleurs chunks via `avg_logprob` du transcript).

Commit : `docs(specs): décisions Sprint 5 actées`

## J2 : Tag

Run global :
- `cd backend && uv run pytest -v` → ~155+ verts (118 + ~38 nouveaux Sprint 5)
- `cd backend && uv run ruff check src/ tests/`
- `cd frontend && npm test && npm run typecheck && npm run lint`

```bash
git tag -a v0.5.0-sprint-5 -m "Sprint 5 — Synthesis pipeline terminé

Pipeline complet en 5 étages : extractor → clusterer → decomposer →
document_writer → identity_synthesizer. Bibliothèque de prompts versionnée
en DB, seed initial via commande Python idempotente. Onglets Prompts
(liste + édition + diff) et Analyses (stepper + runs + comparaison
side-by-side). Cost tracking par run.

Décisions actées :
- Modèle par défaut : mistral-large-latest
- response_format json_object pour extractor/clusterer/decomposer
- Validation Pydantic des sorties LLM par étage
- Pas de pipeline auto MVP (déclenchement manuel par étage)
- Diff visuel texte brut (algo coloré Phase 2)
"
```

---

## Récapitulatif estimé

~38 commits :
- A : 6 (settings, db_helpers prompts/runs, templates, seed, schemas+routes prompts)
- B : 3 (signals helper, extractor, role_projects.get_by_id)
- C : 2 (clusters helper, clusterer)
- D : 2 (document_plans helper, decomposer)
- E : 3 (role_documents helper, document_writer, write_all_documents_for_plan)
- F : 1 (identity_synthesizer + helper update_identity)
- G : 1 (routes synthesis 7 endpoints)
- H : 3 (types/api, page+stepper+card, RunDiff)
- I : 3 (api prompts, page prompts, VersionEditor + DiffViewer)
- J : 2 (open-decisions, tag)

Tag final : `v0.5.0-sprint-5`.
