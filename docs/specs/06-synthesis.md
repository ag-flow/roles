# 06 — Pipeline de synthèse : du corpus aux documents structurés

> Sprint 5 : synthèse. À l'issue de ce sprint, à partir d'un corpus indexé,
> l'application peut générer automatiquement les documents atomiques d'un
> rôle (Role, Missions, Skills) via une chaîne de prompts Mistral.

## Objectif du sprint

- Implémenter les 4 étages du pipeline : extractor → clusterer → decomposer
  → writer
- Implémenter le synthesizer d'identity (à partir des documents produits)
- Bibliothèque de prompts versionnés et éditables
- Comparaison de runs côte à côte
- Régénération ciblée d'un seul document
- Onglets "Prompts" et "Analyses" fonctionnels

## Modèle conceptuel

### Architecture en 4 étages

```
corpus chunks (pgvector)
    ↓  [extractor]              produit des SIGNAUX
                                 (heuristiques, anecdotes,
                                  vocabulaire, cadres mentaux,
                                  opinions tranchées)
signaux
    ↓  [clusterer]               produit des CLUSTERS thématiques
clusters
    ↓  [decomposer]              produit un PLAN de documents cibles
                                 par section
                                 ex: "la section Skills doit contenir
                                  7 documents : X, Y, Z..."
plan de documents
    ↓  [document_writer]         appelé N fois (un par document du plan)
documents markdown atomiques
    ↓  [identity_synthesizer]    produit l'IDENTITY (à partir des docs)
identity markdown
```

### Pourquoi le decomposer ?

C'est l'étage clé qui rend possible la production de **documents
atomiques**. Plutôt qu'un seul gros document par section, le decomposer
décide combien et quels documents produire à partir de l'analyse du corpus.

**Output attendu (JSON structuré) :**

```json
{
  "section": "Skills",
  "documents": [
    {
      "name": "user-research-interviews",
      "brief": "Approche des interviews utilisateurs avec accent sur l'écoute active et les questions ouvertes",
      "supporting_signals": ["sig_001", "sig_042", "sig_117"]
    },
    ...
  ]
}
```

### Identity dérivée des documents (pas du corpus)

L'identity du rôle est produite par un synthesizer dédié qui s'appuie sur
les **documents déjà produits** (Role + Missions + Skills) plutôt que
directement sur le corpus.

Garantit la cohérence interne : l'identity est un résumé condensé du rôle
effectif tel qu'il a émergé.

### Remarques utilisateur à deux niveaux

**Au niveau du rôle (projet)** : `role_projects.global_directives`. Ce
texte est injecté dans tous les prompts de synthèse.

> Exemple : *"Cet agent doit être à l'aise sur le e-commerce mobile et
> avoir un biais vers les méthodes lean."*

**Au niveau d'un run individuel** : `runs.instruction_override`. Permet de
régénérer un document spécifique avec une consigne ponctuelle.

> Exemple : *"Moins de jargon, plus d'exemples concrets."*

## Architecture

### Service de synthèse

```
backend/src/role_builder/services/synthesis/
├── __init__.py
├── orchestrator.py        # déclenche les étages, gère les runs
├── extractor.py           # étage 1
├── clusterer.py           # étage 2
├── decomposer.py          # étage 3
├── document_writer.py     # étage 4
├── identity_synthesizer.py # étage 5
├── prompts.py             # bibliothèque + résolution de version
└── llm_client.py          # appel Mistral via ag.flow
```

### Backend LLM : Mistral via ag.flow

Le LLM utilisé pour la synthèse est **Mistral**, dont la clé est fournie
par l'utilisateur et stockée dans le coffre de secrets d'ag.flow.

L'application invoque Mistral via les ressources LLM d'ag.flow plutôt qu'en
appelant directement `api.mistral.ai`. Cela évite de dupliquer la gestion
de secrets pour les LLM.

> **Si l'utilisateur n'a pas configuré sa clé Mistral dans ag.flow, le
> pipeline de synthèse ne peut pas s'exécuter.** L'application doit
> afficher un message clair invitant à la configurer.

### `llm_client.py`

```python
# backend/src/role_builder/services/synthesis/llm_client.py
"""LLM invocation via ag.flow."""
import httpx
from typing import Sequence

from role_builder.config import settings


class LLMClient:
    """Invoke Mistral LLM through ag.flow."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.agflow_base_url,
            timeout=300.0,
        )

    async def chat(
        self,
        *,
        secret_ref: str,
        model: str = "mistral-large-latest",
        messages: list[dict],
        response_format: str | None = None,  # "json_object" possible
    ) -> dict:
        """Invoke a chat completion via ag.flow.

        Returns:
            {"content": "...", "tokens_input": N, "tokens_output": N, "cost_usd": ...}
        """
        # Le mécanisme exact d'invocation ag.flow est à finaliser.
        # Schéma probable :
        resp = await self._http.post(
            "/api/admin/llm/chat",  # à confirmer
            json={
                "secret_ref": secret_ref,
                "model": model,
                "messages": messages,
                "response_format": response_format,
            },
        )
        resp.raise_for_status()
        return resp.json()


llm = LLMClient()
```

### Bibliothèque de prompts

Versionnée en base via `prompts` + `prompt_versions` (cf. § 01).

**Décisions de design :**
- Tous les prompts sont éditables par l'utilisateur, mais versionnés
- Versions système par défaut, l'utilisateur expert peut forker
- Les prompts sont **partagés entre rôles** (bibliothèque globale)
- Chaque rôle pointe vers des versions précises au moment de l'exécution

### Résolution d'une version de prompt

```python
async def resolve_prompt_version(
    prompt_name: str,
    *,
    project_override: dict[str, UUID] | None = None,
) -> PromptVersion:
    """Get the active version of a prompt for a project.

    Order of precedence:
      1. project_override (explicit override per project)
      2. system default version
    """
    if project_override and prompt_name in project_override:
        return await db.get_prompt_version(project_override[prompt_name])

    return await db.get_system_default_version(prompt_name)
```

## Étage 1 : extractor

### Rôle

Lit les chunks du corpus (par batch) et produit des **signaux** structurés.
Un signal = une unité d'information atomique extraite du corpus.

### Types de signaux

Taxonomie initiale (à raffiner) :

| Type | Description | Exemple |
|------|-------------|---------|
| `heuristique` | Règle pratique, principe d'action | "Toujours commencer par observer l'utilisateur en silence" |
| `anecdote` | Histoire vécue, cas concret | "Une fois, sur un projet bancaire..." |
| `vocab` | Terme spécifique au domaine | "On appelle ça le 'happy path'" |
| `cadre` | Modèle mental, framework | "Le double diamant" |
| `opinion` | Position tranchée, préférence | "Les wireframes sont une perte de temps" |

### Format de sortie attendu (JSON)

```json
{
  "signals": [
    {
      "type": "heuristique",
      "content": {
        "title": "Observer en silence avant de questionner",
        "description": "En interview UX, laisser l'utilisateur s'exprimer librement les premières minutes avant de poser des questions ciblées.",
        "context": "Mentionné comme première étape systématique dans 3 vidéos différentes."
      },
      "source_chunks": ["chunk_id_1", "chunk_id_42"]
    },
    ...
  ]
}
```

### Prompt système (template à seed)

```
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
5. Pointe les chunks sources

Directives globales du projet : {global_directives}

Voici les chunks à analyser :
{chunks}

Réponds en JSON strict, sans préambule.
```

### Implémentation

```python
# backend/src/role_builder/services/synthesis/extractor.py
"""Extractor: corpus chunks → signals."""
from uuid import UUID
import json

from role_builder.services.synthesis.llm_client import llm
from role_builder.services.synthesis.prompts import resolve_prompt_version


CHUNKS_PER_BATCH = 5  # ajustable


async def run_extraction(
    project_id: UUID,
    *,
    prompt_version_id: UUID | None = None,
    instruction_override: str | None = None,
) -> UUID:
    """Run extraction on all chunks of a project. Returns the run_id."""
    project = await db.get_role_project(project_id)
    if not project.mistral_secret_ref:
        raise ValueError("Mistral secret not configured for this project")

    prompt_version = (
        await db.get_prompt_version(prompt_version_id)
        if prompt_version_id
        else await resolve_prompt_version("extractor")
    )

    run_id = await db.create_run(
        role_project_id=project_id,
        prompt_version_id=prompt_version.id,
        instruction_override=instruction_override,
        status="running",
    )

    chunks = await db.list_corpus_chunks(project_id)
    total_signals = 0

    try:
        for batch in batched(chunks, CHUNKS_PER_BATCH):
            chunks_text = format_chunks_for_prompt(batch)
            messages = [
                {"role": "system", "content": prompt_version.template.format(
                    global_directives=project.global_directives or "(aucune)",
                    chunks=chunks_text,
                )}
            ]
            if instruction_override:
                messages.append({"role": "user", "content": instruction_override})

            response = await llm.chat(
                secret_ref=project.mistral_secret_ref,
                messages=messages,
                response_format="json_object",
            )

            data = json.loads(response["content"])
            for signal in data["signals"]:
                await db.insert_signal(
                    run_id=run_id,
                    role_project_id=project_id,
                    tenant_id=project.tenant_id,
                    source_chunks=signal["source_chunks"],
                    signal_type=signal["type"],
                    content=signal["content"],
                )
                total_signals += 1

        await db.update_run(
            run_id=run_id,
            status="done",
            output=json.dumps({"signals_count": total_signals}),
        )
    except Exception as exc:
        await db.update_run(run_id=run_id, status="failed", error=str(exc))
        raise

    return run_id
```

## Étage 2 : clusterer

### Rôle

Reçoit les signaux d'un run d'extraction et les regroupe en clusters
thématiques.

### Format de sortie

```json
{
  "clusters": [
    {
      "name": "Méthodes d'observation",
      "description": "Techniques et principes pour observer les utilisateurs en contexte réel.",
      "signal_ids": ["sig_001", "sig_005", "sig_023"]
    },
    ...
  ]
}
```

### Prompt système

```
Tu es un analyste qui regroupe des signaux d'analyse en clusters thématiques
cohérents.

Ton objectif : prendre une liste de signaux extraits d'un corpus, et les
regrouper en clusters cohérents qui pourront ensuite servir à structurer un
rôle d'agent IA.

Principes :
- Un cluster doit avoir une cohérence forte (signaux qui parlent du même
  thème)
- Un signal peut appartenir à un seul cluster (pas de chevauchement)
- Donne à chaque cluster un nom court et descriptif
- Vise 5 à 15 clusters au total
- Ne fais pas de cluster "divers" ou "autres" : si un signal n'appartient
  à aucun cluster, exclus-le

Directives globales du projet : {global_directives}

Voici les signaux à clusteriser :
{signals}

Réponds en JSON strict.
```

## Étage 3 : decomposer

### Rôle

Reçoit les clusters d'un run de clustering et produit un **plan de
documents** pour chacune des sections cibles (Role, Missions, Skills).

### Sections cibles verrouillées

Les 3 sections principales sont :
- **Role** — qui est l'agent, ses principes cognitifs, ses traits d'identité
- **Missions** — les missions types qu'il peut accomplir
- **Skills** — les compétences atomiques qu'il maîtrise

L'utilisateur peut ajouter des sections custom au niveau du projet.

### Format de sortie

```json
{
  "sections": {
    "Role": {
      "documents": [
        {
          "name": "principe-empathie-utilisateur",
          "brief": "Définit l'empathie comme principe fondateur de l'agent.",
          "supporting_signals": ["sig_002", "sig_017"]
        }
      ]
    },
    "Missions": {
      "documents": [...]
    },
    "Skills": {
      "documents": [...]
    }
  }
}
```

### Prompt système

```
Tu es un architecte de rôles d'agents IA.

Ton objectif : à partir de clusters thématiques, produire un PLAN DE
DOCUMENTS atomiques qui composeront le rôle. Ces documents seront ensuite
écrits un par un par un autre agent.

Le rôle est composé de 3 sections obligatoires :
- Role : principes cognitifs, traits d'identité (1 doc = 1 principe ou trait)
- Missions : missions types que l'agent peut accomplir (1 doc = 1 mission)
- Skills : compétences atomiques (1 doc = 1 compétence)

Pour chaque section :
1. Décide combien de documents produire (en général 3 à 10 par section)
2. Donne à chaque document un nom court en kebab-case
3. Rédige un brief de 2-3 phrases qui guidera la rédaction
4. Liste les signaux qui supportent ce document

Directives globales du projet : {global_directives}

Voici les clusters thématiques :
{clusters}

Voici les signaux complets référencés par les clusters :
{signals}

Réponds en JSON strict.
```

## Étage 4 : document_writer

### Rôle

Écrit **un seul document atomique** à partir d'un brief, des signaux
supportants, et des chunks de corpus pertinents (RAG).

### Pipeline d'écriture d'un document

```python
async def write_document(
    project_id: UUID,
    section: str,
    doc_plan: dict,
    *,
    instruction_override: str | None = None,
) -> UUID:
    """Write a single document. Returns run_id."""
    project = await db.get_role_project(project_id)
    prompt_version = await resolve_prompt_version("document_writer")

    # 1. Récupérer les signaux supportants
    signals = await db.list_signals_by_ids(doc_plan["supporting_signals"])

    # 2. RAG : chunks pertinents (cf. § 05)
    rag_chunks = await find_relevant_chunks(
        project_id=project_id,
        query=doc_plan["brief"],
        top_k=8,
    )

    # 3. Build prompt
    messages = [
        {"role": "system", "content": prompt_version.template.format(
            section=section,
            doc_name=doc_plan["name"],
            doc_brief=doc_plan["brief"],
            global_directives=project.global_directives or "(aucune)",
            signals=format_signals(signals),
            chunks=format_chunks(rag_chunks),
        )}
    ]
    if instruction_override:
        messages.append({"role": "user", "content": instruction_override})

    # 4. LLM call
    response = await llm.chat(
        secret_ref=project.mistral_secret_ref,
        messages=messages,
    )

    # 5. Create run + role_document candidate
    run_id = await db.create_run(
        role_project_id=project_id,
        prompt_version_id=prompt_version.id,
        instruction_override=instruction_override,
        status="done",
        output=response["content"],
    )

    # Créer un role_document NON-current (l'user devra le promouvoir)
    await db.insert_role_document(
        role_project_id=project_id,
        section=section,
        name=doc_plan["name"],
        content=response["content"],
        source_run_id=run_id,
        is_current=False,
    )

    return run_id
```

### Prompt système

```
Tu rédiges un document atomique pour le rôle d'un agent IA.

Section cible : {section}
Nom du document : {doc_name}
Brief : {doc_brief}

Directives globales du projet : {global_directives}

Tu disposes des signaux extraits du corpus qui supportent ce document :
{signals}

Tu as également accès à ces extraits du corpus original (utilise-les pour
illustrer avec des exemples concrets) :
{chunks}

Style attendu :
- Markdown pur, sans titre principal (le titre vient du contexte)
- Structuré avec des sous-sections si utile
- Concret, avec des exemples tirés du corpus
- Voix de l'expert (style direct, pas méta-descriptif)
- Longueur : 200 à 600 mots

Rédige le document maintenant.
```

## Étage 5 : identity_synthesizer

### Rôle

Produit l'identity du rôle à partir des documents finaux (current) du
projet, pas du corpus.

### Pipeline

```python
async def synthesize_identity(project_id: UUID) -> UUID:
    """Synthesize the role's identity from current documents."""
    project = await db.get_role_project(project_id)
    prompt_version = await resolve_prompt_version("identity_synthesizer")

    # Récupérer tous les documents current du projet
    documents = await db.list_role_documents(project_id, only_current=True)

    messages = [
        {"role": "system", "content": prompt_version.template.format(
            display_name=project.display_name,
            description=project.description or "",
            global_directives=project.global_directives or "(aucune)",
            documents=format_documents(documents),
        )}
    ]

    response = await llm.chat(
        secret_ref=project.mistral_secret_ref,
        messages=messages,
    )

    run_id = await db.create_run(...)

    # Stocke l'identity directement sur role_projects
    await db.update_role_project(
        project_id=project_id,
        identity=response["content"],
    )

    return run_id
```

## Endpoints API

```python
# backend/src/role_builder/routes/synthesis.py

@router.post("/role-projects/{project_id}/runs/extract")
async def trigger_extraction(project_id: UUID, body: dict) -> dict:
    """Trigger extractor on all chunks."""
    run_id = await synthesis.run_extraction(
        project_id,
        prompt_version_id=body.get("prompt_version_id"),
        instruction_override=body.get("instruction_override"),
    )
    return {"run_id": str(run_id)}


@router.post("/role-projects/{project_id}/runs/cluster")
async def trigger_clustering(project_id: UUID, body: dict) -> dict:
    """Trigger clusterer on signals."""
    ...


@router.post("/role-projects/{project_id}/runs/decompose")
async def trigger_decomposition(project_id: UUID, body: dict) -> dict:
    """Trigger decomposer on clusters."""
    ...


@router.post("/role-projects/{project_id}/runs/write-documents")
async def trigger_document_writing(project_id: UUID, body: dict) -> dict:
    """Trigger document_writer on a plan (in parallel)."""
    ...


@router.post("/role-documents/{doc_id}/regenerate")
async def regenerate_document(doc_id: UUID, body: dict) -> dict:
    """Regenerate a single document with optional instruction override."""
    ...


@router.post("/role-documents/{doc_id}/set-current")
async def set_current_version(doc_id: UUID) -> dict:
    """Promote a document version as the current one."""
    ...


@router.post("/role-projects/{project_id}/runs/synthesize-identity")
async def trigger_identity_synthesis(project_id: UUID) -> dict:
    """Synthesize the role's identity from current documents."""
    ...
```

## UI : onglets "Prompts" et "Analyses"

### Onglet "Prompts"

- Liste de tous les prompts (extractor, clusterer, decomposer, writer,
  identity_synthesizer)
- Pour chaque prompt : versions disponibles, version active par défaut
- Édition d'un prompt : crée une nouvelle version, ne modifie pas
  l'existante
- Bouton "Restaurer la version système"
- Diff side-by-side entre deux versions

### Onglet "Analyses"

- Bouton "Lancer le pipeline complet" : enchaîne extract → cluster →
  decompose → write
- Boutons individuels pour relancer un étage donné
- Liste des runs avec leur statut et leurs outputs
- Vue d'un run : input/output/coût/erreurs
- Comparaison de deux runs côte à côte

### Composants React

```
frontend/src/app/projects/[id]/
├── prompts/
│   ├── page.tsx                 # liste des prompts
│   ├── [promptId]/
│   │   ├── page.tsx            # détail + versions
│   │   └── VersionEditor.tsx
│   └── DiffViewer.tsx
├── analyses/
│   ├── page.tsx                 # liste des runs + boutons d'action
│   ├── PipelineStepper.tsx
│   ├── RunCard.tsx
│   └── RunDiff.tsx
```

## Critères de fin de sprint

- [ ] Tous les prompts système sont seedés en base
- [ ] Le pipeline complet s'exécute end-to-end sur un corpus de test
      (5-10 vidéos) et produit des role_documents non-current
- [ ] L'utilisateur peut promouvoir manuellement chaque doc en is_current
- [ ] Régénération d'un doc avec instruction_override fonctionne
- [ ] Comparaison side-by-side de deux runs dans l'UI
- [ ] L'identity est générée à partir des documents current
- [ ] Si pas de clé Mistral ag.flow → message d'erreur clair, pipeline
      bloqué
- [ ] Coûts trackés dans `runs.cost_usd`
- [ ] WebSocket : la progression d'un run est visible en temps réel

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Mécanisme exact d'invocation Mistral via ag.flow : endpoint, format
      de requête, gestion du streaming
- [ ] Format JSON exact en sortie du decomposer : schema strict à valider
      via JSON Schema avant de stocker
- [ ] Taxonomie des signaux : la liste actuelle (heuristique/anecdote/
      vocab/cadre/opinion) est-elle suffisante ? Tester sur un corpus réel
      avant de figer.
- [ ] Map-reduce pour les gros corpus : si un projet a 500 chunks,
      l'extractor ne peut pas tout passer d'un coup. Stratégie batch déjà
      prévue, mais à régler la taille de batch selon les retours qualité.
- [ ] Pipeline complet en une commande : faut-il un endpoint
      `/runs/full-pipeline` qui enchaîne tout, ou laisser l'utilisateur
      contrôler chaque étape ?
- [ ] Stratégie de cache : si l'utilisateur modifie les directives globales,
      les anciens runs sont-ils marqués "obsolètes" ? Pour le MVP, rien
      d'automatique.
- [ ] Diff visuel des role_documents (versions) : algorithme à utiliser
      (diff-match-patch, jsdiff) ?
- [ ] Edition manuelle d'un role_document après génération : marquer
      `locked=true` pour empêcher l'écrasement par régénération automatique

---

**Document précédent :** `05-corpus-indexing.md`
**Document suivant :** `07-user-stack.md`
