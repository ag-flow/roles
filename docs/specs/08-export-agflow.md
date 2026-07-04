> ⚠️ **OBSOLÈTE — Refonte V2 (2026-07-04).** L'API admin du Docker service ag.flow n'existe plus. Destination du corpus et des rôles = docflow.
> Voir `docs/specs/OBSOLETE.md` et `docs/specs/v2/00-fondations-v2.md`. Conservé pour référence historique uniquement — ne plus implémenter.

# 08 — Export vers ag.flow

> Sprint 7 : livraison du rôle vers ag.flow. À l'issue de ce sprint,
> l'utilisateur peut pousser un rôle entièrement construit vers ag.flow
> en un clic, et déclencher optionnellement la génération du prompt
> orchestrateur côté ag.flow.

## Objectif du sprint

- Construction du ZIP conforme au format `POST /api/admin/roles/{id}/import`
- Création du rôle ag.flow si pas encore créé (`POST /api/admin/roles`)
- Upload du ZIP via l'endpoint d'import
- Déclenchement optionnel de `/generate-prompts`
- Endpoint `/role-projects/{id}/push-to-agflow`
- UI : bouton "Pousser vers ag.flow" sur la page rôle, avec feedback en temps réel

## Modèle conceptuel

### Le format d'export ag.flow

L'export final est un ZIP conforme à l'endpoint
`POST /api/admin/roles/{role_id}/import` :

```
role.json                # display_name, description, identity, sections meta
section_role/
├── document_1.md
└── document_2.md
section_missions/
├── document_1.md
└── ...
section_skills/
└── ...
```

### Que contient `role.json`

Format structuré attendu par ag.flow (à finaliser selon le schéma exact
documenté dans `https://docker-agflow.yoops.org/openapi.json`) :

```json
{
  "display_name": "UX Designer Clea",
  "description": "Agent expert en design UX inspiré de Clea",
  "identity": "...markdown content...",
  "language": "fr",
  "service_types": ["claude-code", "aider"],
  "sections": [
    {
      "name": "Role",
      "documents": ["principe-empathie-utilisateur", "biais-pragmatique-vs-perfection"]
    },
    {
      "name": "Missions",
      "documents": ["audit-ux-application", "conception-parcours-onboarding"]
    },
    {
      "name": "Skills",
      "documents": ["user-research-interviews", "heuristic-evaluation"]
    }
  ]
}
```

> **TODO :** confirmer le schéma exact attendu par ag.flow (cf. § 12). Le
> format ci-dessus est une hypothèse raisonnable mais à valider via
> l'OpenAPI réel.

### Délégation de la génération du prompt orchestrateur

L'application **ne produit pas** le `prompt_orchestrator_md` final. C'est
ag.flow qui le génère via son endpoint `/generate-prompts`, qui synthétise
en interne tous les documents du rôle en un prompt système exécutable.

Côté Role Builder, on expose juste un bouton "Générer le prompt
orchestrateur côté ag.flow" qui appelle cet endpoint.

## Architecture

### Service `agflow_exporter.py`

```
backend/src/role_builder/services/agflow/
├── __init__.py
├── exporter.py              # construction du ZIP
├── client.py                # client HTTP ag.flow
└── role_json_builder.py     # produit role.json
```

### Construction du ZIP

```python
# backend/src/role_builder/services/agflow/exporter.py
"""Build the ZIP file for ag.flow import."""
import io
import json
import zipfile
from uuid import UUID

from role_builder.db import db_pool


async def build_role_zip(project_id: UUID) -> bytes:
    """Build the complete ZIP for a role project.

    Returns the ZIP file as bytes ready for upload.
    """
    # 1. Fetch project metadata
    project = await db.get_role_project(project_id)
    if not project.identity:
        raise ValueError("Identity not generated yet — run identity_synthesizer first")

    # 2. Fetch all current documents grouped by section
    docs_by_section = await db.list_current_role_documents_by_section(project_id)

    sections_meta = []
    for section_name, documents in docs_by_section.items():
        sections_meta.append({
            "name": section_name,
            "documents": [d.name for d in documents],
        })

    # 3. Build role.json
    role_json = {
        "display_name": project.display_name,
        "description": project.description or "",
        "identity": project.identity,
        "language": project.language or "fr",
        "service_types": project.service_types or ["claude-code"],
        "sections": sections_meta,
    }

    # 4. Build ZIP in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # role.json at root
        zf.writestr("role.json", json.dumps(role_json, indent=2, ensure_ascii=False))

        # One folder per section
        for section_name, documents in docs_by_section.items():
            folder = f"section_{section_name.lower()}"
            for doc in documents:
                zf.writestr(f"{folder}/{doc.name}.md", doc.content)

    return buffer.getvalue()
```

### Client ag.flow

```python
# backend/src/role_builder/services/agflow/client.py
"""HTTP client for ag.flow API."""
import httpx

from role_builder.config import settings


class AgFlowClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.agflow_base_url,
            timeout=120.0,
        )

    async def create_role(
        self,
        *,
        display_name: str,
        description: str | None = None,
    ) -> dict:
        """POST /api/admin/roles — create an empty role."""
        resp = await self._http.post(
            "/api/admin/roles",
            json={"display_name": display_name, "description": description},
        )
        resp.raise_for_status()
        return resp.json()

    async def import_role_zip(self, role_id: str, zip_bytes: bytes) -> dict:
        """POST /api/admin/roles/{role_id}/import — upload the ZIP."""
        files = {"file": ("role.zip", zip_bytes, "application/zip")}
        resp = await self._http.post(
            f"/api/admin/roles/{role_id}/import",
            files=files,
        )
        resp.raise_for_status()
        return resp.json()

    async def generate_prompts(self, role_id: str) -> dict:
        """POST /api/admin/roles/{role_id}/generate-prompts."""
        resp = await self._http.post(
            f"/api/admin/roles/{role_id}/generate-prompts",
        )
        resp.raise_for_status()
        return resp.json()

    async def get_role(self, role_id: str) -> dict:
        """GET /api/admin/roles/{role_id} — verify after import."""
        resp = await self._http.get(f"/api/admin/roles/{role_id}")
        resp.raise_for_status()
        return resp.json()


agflow = AgFlowClient()
```

### Orchestration du push

```python
# backend/src/role_builder/services/agflow/__init__.py
"""High-level orchestration of role push to ag.flow."""

from .exporter import build_role_zip
from .client import agflow


async def push_role_to_agflow(
    project_id: UUID,
    *,
    generate_prompts: bool = False,
) -> dict:
    """Full orchestration of a role push.

    Steps:
      1. Build ZIP
      2. Create role in ag.flow if not yet created
      3. Upload ZIP via /import
      4. Optionally trigger /generate-prompts
      5. Return final role detail

    Returns:
      {
        "agflow_role_id": "...",
        "zip_size_bytes": ...,
        "documents_count": ...,
        "prompt_generated": bool,
        "agflow_url": "...",
      }
    """
    project = await db.get_role_project(project_id)

    # 1. Build ZIP
    zip_bytes = await build_role_zip(project_id)

    # 2. Create role if needed
    if not project.target_role_id:
        created = await agflow.create_role(
            display_name=project.display_name,
            description=project.description,
        )
        agflow_role_id = created["id"]
        await db.update_role_project(
            project_id=project_id,
            target_role_id=agflow_role_id,
        )
    else:
        agflow_role_id = project.target_role_id

    # 3. Import ZIP
    import_result = await agflow.import_role_zip(agflow_role_id, zip_bytes)

    # 4. Optionally generate prompts
    prompt_generated = False
    if generate_prompts:
        await agflow.generate_prompts(agflow_role_id)
        prompt_generated = True

    return {
        "agflow_role_id": agflow_role_id,
        "zip_size_bytes": len(zip_bytes),
        "documents_count": import_result.get("documents_count"),
        "prompt_generated": prompt_generated,
        "agflow_url": f"{settings.agflow_base_url}/admin/roles/{agflow_role_id}",
    }
```

## Endpoints API

```python
# backend/src/role_builder/routes/agflow_export.py

@router.post("/role-projects/{project_id}/push-to-agflow")
async def push_to_agflow(
    project_id: UUID,
    body: PushToAgflowRequest,
) -> PushToAgflowResponse:
    """Push the role to ag.flow.

    Body:
      - generate_prompts: bool (optional, default False)
    """
    result = await agflow_export.push_role_to_agflow(
        project_id,
        generate_prompts=body.generate_prompts,
    )
    return PushToAgflowResponse(**result)


@router.get("/role-projects/{project_id}/preview-zip")
async def preview_zip_contents(project_id: UUID) -> dict:
    """Preview what will be pushed to ag.flow without actually pushing."""
    project = await db.get_role_project(project_id)
    docs_by_section = await db.list_current_role_documents_by_section(project_id)

    return {
        "display_name": project.display_name,
        "identity_length": len(project.identity or ""),
        "sections": [
            {
                "name": section,
                "documents": [{"name": d.name, "size": len(d.content)} for d in docs],
            }
            for section, docs in docs_by_section.items()
        ],
        "ready_to_push": bool(project.identity and docs_by_section),
        "missing": _check_missing_pieces(project, docs_by_section),
    }


def _check_missing_pieces(project, docs_by_section: dict) -> list[str]:
    """Return human-readable list of missing things."""
    missing = []
    if not project.identity:
        missing.append("Identity not generated")
    for required in ["Role", "Missions", "Skills"]:
        if required not in docs_by_section or not docs_by_section[required]:
            missing.append(f"Section '{required}' has no current documents")
    return missing


@router.post("/role-projects/{project_id}/generate-prompts-on-agflow")
async def generate_prompts_on_agflow(project_id: UUID) -> dict:
    """Trigger /generate-prompts on the existing ag.flow role."""
    project = await db.get_role_project(project_id)
    if not project.target_role_id:
        raise HTTPException(400, "Role not yet pushed to ag.flow")

    result = await agflow.generate_prompts(project.target_role_id)
    return {"status": "generated", "result": result}
```

### Schémas Pydantic

```python
# backend/src/role_builder/schemas/agflow_export.py

class PushToAgflowRequest(BaseModel):
    generate_prompts: bool = False


class PushToAgflowResponse(BaseModel):
    agflow_role_id: str
    zip_size_bytes: int
    documents_count: int | None
    prompt_generated: bool
    agflow_url: str
```

## Validations avant push

Avant de lancer un push, vérifier :

1. `project.identity` n'est pas null (le synthesizer d'identity a été lancé)
2. Chaque section verrouillée (`Role`, `Missions`, `Skills`) a au moins 1
   document avec `is_current = true`
3. Tous les documents promus en current ont un contenu non vide
4. La connectivité ag.flow est OK (ping `GET /api/health` ou équivalent)

Si une validation échoue, retourner un 400 avec message clair pour que l'UI
puisse guider l'utilisateur.

## UI : intégration dans la page "Rôle"

### Nouveaux composants

```
frontend/src/app/projects/[id]/role/
├── page.tsx                           # vue rôle existante
├── PushToAgflowButton.tsx             # bouton avec modal de confirmation
├── PushPreview.tsx                    # affichage du contenu prévu
├── PushProgressDialog.tsx             # progression en direct
└── PostPushBanner.tsx                 # affiché après push réussi
```

### Workflow utilisateur

1. Sur la page rôle, bouton **"Pousser vers ag.flow"**
2. Modal de confirmation qui montre :
   - Nombre de documents par section
   - Présence ou non de l'identity
   - Avertissements si éléments manquants
   - Checkbox "Générer le prompt orchestrateur après l'import"
3. Au clic "Confirmer", appel `POST /push-to-agflow`
4. Loader pendant le push (typiquement 2-10 secondes)
5. Après succès : bandeau de confirmation avec lien direct vers le rôle
   dans l'admin ag.flow
6. Après échec : message d'erreur avec détail technique

### Affichage du target_role_id

Une fois un rôle poussé, afficher en permanence sur la page rôle :
- L'ID ag.flow
- Lien direct vers l'admin ag.flow
- Date du dernier push (depuis l'historique des runs ou un nouveau champ)

Le bouton "Pousser vers ag.flow" devient "Mettre à jour ag.flow" si déjà
poussé une fois.

## Cas particuliers

### Republication

Si le rôle a déjà été poussé (`target_role_id` non null), le push suivant :

1. Utilise le même `target_role_id`
2. Ré-uploade le ZIP (l'endpoint `/import` doit gérer l'upsert côté ag.flow)
3. Optionnellement régénère les prompts

### Suppression du rôle ag.flow

Pas dans le scope du MVP. L'utilisateur supprime via l'admin ag.flow s'il
le souhaite. Si on supprime un projet Role Builder, on garde le
`target_role_id` historique mais on ne pousse plus.

### Conflit de display_name

Ag.flow peut refuser une création si le `display_name` existe déjà. Côté
Role Builder, intercepter l'erreur 409 et proposer à l'utilisateur de
choisir un autre nom.

### Taille du ZIP

Pour un rôle typique (3 sections, 10 documents/section, ~500 mots/doc), le
ZIP fait ~100-200 KB. Largement sous les limites typiques d'upload HTTP.
Si on dépasse 10 MB un jour, prévoir un endpoint multipart streamé.

## Critères de fin de sprint

- [ ] `build_role_zip` produit un ZIP valide (testable manuellement)
- [ ] L'endpoint `/preview-zip` retourne un récapitulatif correct
- [ ] L'endpoint `/push-to-agflow` crée le rôle si nécessaire et upload
      le ZIP
- [ ] Test end-to-end : un projet complet est poussé vers une instance
      ag.flow et apparaît dans son admin
- [ ] Le bouton "Générer le prompt orchestrateur" déclenche bien
      `/generate-prompts` et l'UI confirme le succès
- [ ] Validations bloquent le push si elements manquants (identity, docs)
- [ ] Lien vers le rôle ag.flow disponible après push
- [ ] Republication fonctionne (push d'un rôle déjà poussé)
- [ ] Erreurs ag.flow remontées proprement à l'UI (timeout, 4xx, 5xx)

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Confirmer le format exact de `role.json` attendu par ag.flow (lire
      l'OpenAPI réel `https://docker-agflow.yoops.org/openapi.json` au
      moment de l'implémentation)
- [ ] Confirmer la structure des sous-dossiers : `section_role/` ou autre
      convention ?
- [ ] Authentification ag.flow : token bearer, OIDC, autre ? Stockage de
      ce token côté Role Builder (env var ? OpenBao ?)
- [ ] Stratégie en cas d'échec partiel : si le ZIP s'uploade mais que
      `generate-prompts` échoue, on est en état intermédiaire. Comment
      le signaler à l'user ?
- [ ] Faut-il un endpoint pour télécharger le ZIP en local (debug) sans
      le pousser ?

---

**Document précédent :** `07-user-stack.md`
**Document suivant :** `09-github-publish.md`
