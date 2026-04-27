# 09 — Publication GitHub via OAuth

> Sprint 8 : publication publique. À l'issue de ce sprint, l'utilisateur
> peut connecter son compte GitHub et publier un rôle sur un repo qu'il
> contrôle, avec un sous-répertoire de son choix.

## Objectif du sprint

- Flow OAuth GitHub complet (state CSRF, scope, callback)
- Stockage du token GitHub dans OpenBao
- UI pour configurer la cible de publication (repo + sous-répertoire)
- Construction et push des fichiers via l'API GitHub
- Génération automatique d'un README.md pour le rôle publié
- Historique des publications par rôle
- Bouton "Dépublier"

## Modèle conceptuel

### Vision

L'utilisateur peut **publier publiquement** un rôle qu'il a construit sur
**son propre repo GitHub**. Cette publication est volontaire, manuelle, et
entièrement contrôlée par l'utilisateur.

**Pour le MVP :** pas de modération, pas de showcase officiel. Une vitrine
officielle sera ajoutée dans une phase ultérieure.

### Pourquoi publier

- Partager son rôle avec la communauté
- Versionner via Git (chaque republication = un commit)
- Préparer une éventuelle vitrine officielle
- Donner crédit à l'auteur du contenu source via un README explicite

### Ce qui est publié vs ce qui ne l'est pas

**Publié :**
- README.md (généré automatiquement)
- role.json (même fichier que pour l'import ag.flow)
- identity.md (contenu de l'identity)
- sections/*/*.md (tous les documents current)

**NON publié :**
- Le corpus source (transcriptions complètes) — risque de droits d'auteur
- Les audios bruts — idem
- Les prompts utilisés — pour ne pas exposer la stratégie éditoriale du user
- Les signaux et clusters intermédiaires
- Les métadonnées internes (run_ids, embeddings, etc.)

## OAuth GitHub

### Configuration de l'OAuth App

À configurer dans les settings GitHub de Beard :

- **Application name** : Role Builder
- **Homepage URL** : URL de l'app
- **Authorization callback URL** : `{APP_URL}/api/auth/github/callback`
- **Scopes demandés** :
  - `public_repo` : pour publier sur des repos publics (suffisant pour le
    MVP)
  - `repo` : pour publier sur des repos privés (option future)

### Variables d'environnement

```bash
GITHUB_OAUTH_CLIENT_ID=Iv1.xxxxx
GITHUB_OAUTH_CLIENT_SECRET=yyyyy
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/github/callback
GITHUB_OAUTH_SCOPE=public_repo
```

### Flow OAuth complet

1. **Démarrage** : utilisateur clique "Connecter GitHub"
2. **Generate state CSRF** : token aléatoire stocké côté backend (en
   session ou en table temporaire avec expiration 10 min)
3. **Redirect vers GitHub** :
   ```
   https://github.com/login/oauth/authorize
     ?client_id={CLIENT_ID}
     &redirect_uri={REDIRECT_URI}
     &scope=public_repo
     &state={STATE}
   ```
4. **GitHub redirige vers le callback** avec `code` et `state`
5. **Vérification du state CSRF** côté backend
6. **Échange code → access_token** :
   ```
   POST https://github.com/login/oauth/access_token
     client_id, client_secret, code, redirect_uri
   ```
7. **Récupération des infos user** :
   ```
   GET https://api.github.com/user
   Authorization: Bearer {access_token}
   ```
8. **Stockage du token dans OpenBao** :
   `secret/github-tokens/{tenant_id}/{user_id}`
9. **Insert dans `github_integrations`** avec login, github_user_id, scope

### Implémentation

```python
# backend/src/role_builder/services/github/oauth.py
import secrets as py_secrets
import httpx

from role_builder.config import settings
from role_builder.services.openbao_client import openbao


class GitHubOAuth:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)
        # state cache : in-memory pour le MVP, à migrer en Redis ou table PG si multi-instance
        self._state_cache: dict[str, dict] = {}

    def build_authorize_url(self, user_id: UUID) -> tuple[str, str]:
        """Generate the redirect URL and the CSRF state."""
        state = py_secrets.token_urlsafe(32)
        self._state_cache[state] = {
            "user_id": str(user_id),
            "expires_at": (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
        }
        params = {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": settings.github_oauth_scope,
            "state": state,
        }
        url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        return url, state

    def verify_state(self, state: str) -> dict:
        """Verify state and return cached info."""
        info = self._state_cache.pop(state, None)
        if info is None:
            raise ValueError("Invalid or expired state")
        if datetime.fromisoformat(info["expires_at"]) < datetime.utcnow():
            raise ValueError("State expired")
        return info

    async def exchange_code(self, code: str) -> str:
        """Exchange authorization code for access token."""
        resp = await self._http.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def get_user_info(self, access_token: str) -> dict:
        """Get authenticated user info."""
        resp = await self._http.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()


github_oauth = GitHubOAuth()
```

### Endpoints OAuth

```python
# backend/src/role_builder/routes/github_auth.py

@router.get("/auth/github/start")
async def start_oauth(user_id: UUID = Depends(get_current_user_id)) -> dict:
    """Initiate the OAuth flow."""
    url, _state = github_oauth.build_authorize_url(user_id)
    return {"redirect_url": url}


@router.get("/auth/github/callback")
async def oauth_callback(code: str, state: str) -> dict:
    """Handle the OAuth callback."""
    info = github_oauth.verify_state(state)
    user_id = UUID(info["user_id"])

    # Exchange code for token
    access_token = await github_oauth.exchange_code(code)

    # Get user info
    gh_user = await github_oauth.get_user_info(access_token)

    # Store token in OpenBao
    path = f"github-tokens/{tenant_id}/{user_id}"
    await openbao.put(path, {"access_token": access_token})

    # Insert / upsert into github_integrations
    await db.upsert_github_integration(
        tenant_id=tenant_id,
        user_id=user_id,
        github_login=gh_user["login"],
        github_user_id=gh_user["id"],
        openbao_path=path,
        scope=settings.github_oauth_scope,
        last_validated_at=datetime.utcnow(),
    )

    return {
        "status": "connected",
        "github_login": gh_user["login"],
    }


@router.delete("/auth/github")
async def disconnect_github(user_id: UUID = Depends(get_current_user_id)) -> dict:
    """Disconnect GitHub: revoke token + delete integration."""
    integration = await db.get_github_integration(user_id)
    if not integration:
        return {"status": "not-connected"}

    await openbao.delete(integration.openbao_path)
    await db.delete_github_integration(user_id)
    return {"status": "disconnected"}
```

## Configuration de la cible de publication

### Modèle de données

Cf. `01-data-model.md` : tables `role_publication_config` et
`role_publications`.

### Sélection du repo

Une fois GitHub connecté, l'utilisateur configure pour chaque rôle :

- **Repo cible** : sélectionné dans une dropdown des repos accessibles
  (l'app appelle `GET /user/repos`)
- **Sous-répertoire** : chemin dans le repo où pousser le rôle
  (ex: `roles/ux-designer-clea/`). Si pas existant, créé au push.
- **Branche** : par défaut `main`, configurable
- **Message de commit** : template configurable, par défaut
  `Update role {role_name}`

### Endpoint pour lister les repos

```python
@router.get("/github/repos")
async def list_repos(user_id: UUID = Depends(get_current_user_id)) -> list[dict]:
    """List the user's GitHub repos."""
    integration = await db.get_github_integration(user_id)
    if not integration:
        raise HTTPException(400, "GitHub not connected")

    token_data = await openbao.get(integration.openbao_path)
    access_token = token_data["access_token"]

    # GET /user/repos with pagination
    repos = []
    page = 1
    async with httpx.AsyncClient() as http:
        while True:
            resp = await http.get(
                "https://api.github.com/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1

    return [
        {
            "full_name": r["full_name"],
            "private": r["private"],
            "default_branch": r["default_branch"],
            "html_url": r["html_url"],
        }
        for r in repos
    ]
```

### Endpoints config

```python
@router.get("/role-projects/{project_id}/publication-config")
async def get_publication_config(project_id: UUID) -> dict:
    """Get the current publication config."""
    config = await db.get_publication_config(project_id)
    return config or {}


@router.put("/role-projects/{project_id}/publication-config")
async def set_publication_config(
    project_id: UUID,
    body: PublicationConfigRequest,
) -> dict:
    """Set or update the publication config."""
    await db.upsert_publication_config(
        role_project_id=project_id,
        repo_full_name=body.repo_full_name,
        target_subdirectory=body.target_subdirectory,
        branch=body.branch,
        commit_message_template=body.commit_message_template,
    )
    return {"status": "saved"}
```

## Construction et push des fichiers

### Génération du contenu

Mêmes fichiers que pour l'export ag.flow + un README généré.

```python
# backend/src/role_builder/services/github/publisher.py
"""Publish a role to GitHub."""


async def build_publication_files(project_id: UUID) -> dict[str, str]:
    """Build all files to publish (path -> content)."""
    project = await db.get_role_project(project_id)
    docs_by_section = await db.list_current_role_documents_by_section(project_id)

    files = {}

    # README.md
    files["README.md"] = render_readme(project, docs_by_section)

    # role.json (même contenu que pour ag.flow)
    files["role.json"] = json.dumps(_build_role_json(project, docs_by_section), indent=2, ensure_ascii=False)

    # identity.md
    files["identity.md"] = project.identity or ""

    # sections/*/*.md
    for section, documents in docs_by_section.items():
        for doc in documents:
            files[f"sections/{section.lower()}/{doc.name}.md"] = doc.content

    return files


def render_readme(project, docs_by_section: dict) -> str:
    """Generate the README.md."""
    sections_summary = "\n".join(
        f"- **{s}** ({len(docs)} documents)"
        for s, docs in docs_by_section.items()
    )

    return f"""# {project.display_name}

> {project.description or ''}

**Auteur :** [@{integration.github_login}](https://github.com/{integration.github_login})
**Langue :** {project.language or 'fr'}
**Dernière mise à jour :** {datetime.utcnow().strftime('%Y-%m-%d')}
**Service types ag.flow :** {', '.join(project.service_types or ['claude-code'])}

## Sections

{sections_summary}

## Importer dans ag.flow

1. Téléchargez ce répertoire en ZIP
2. Dans ag.flow, créez un rôle vide avec le `display_name` de votre choix
3. Utilisez `POST /api/admin/roles/{{id}}/import` avec le ZIP
4. Optionnel : déclenchez `POST /api/admin/roles/{{id}}/generate-prompts`
   pour régénérer le prompt orchestrateur

## Structure

```
.
├── README.md          (ce fichier)
├── role.json          (métadonnées + structure des sections)
├── identity.md        (identité de l'agent)
└── sections/          (un sous-dossier par section)
```

---

Généré par Role Builder.
"""
```

### Push vers GitHub

GitHub permet d'écrire des fichiers via `PUT /repos/{owner}/{repo}/contents/{path}`.

Pour modifier un fichier existant, il faut connaître son `sha`. Pour
détecter "fichier existant ou pas", on fait d'abord un `GET` :

```python
async def push_files_to_github(
    user_id: UUID,
    project_id: UUID,
) -> dict:
    """Push all files to GitHub. Returns commit info."""
    integration = await db.get_github_integration(user_id)
    config = await db.get_publication_config(project_id)
    project = await db.get_role_project(project_id)

    if not integration or not config:
        raise ValueError("GitHub not connected or publication not configured")

    token_data = await openbao.get(integration.openbao_path)
    access_token = token_data["access_token"]

    files = await build_publication_files(project_id)

    owner, repo = config.repo_full_name.split("/")
    base_path = config.target_subdirectory.strip("/")

    commit_msg = config.commit_message_template.format(role_name=project.display_name)

    last_commit_sha = None

    async with httpx.AsyncClient() as http:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }

        for relpath, content in files.items():
            full_path = f"{base_path}/{relpath}"

            # Check if exists
            existing_sha = None
            check_resp = await http.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{full_path}",
                params={"ref": config.branch},
                headers=headers,
            )
            if check_resp.status_code == 200:
                existing_sha = check_resp.json()["sha"]
            elif check_resp.status_code != 404:
                check_resp.raise_for_status()

            # PUT
            put_body = {
                "message": commit_msg,
                "content": base64.b64encode(content.encode()).decode(),
                "branch": config.branch,
            }
            if existing_sha:
                put_body["sha"] = existing_sha

            put_resp = await http.put(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{full_path}",
                json=put_body,
                headers=headers,
            )
            put_resp.raise_for_status()
            last_commit_sha = put_resp.json()["commit"]["sha"]

    # Record publication
    await db.insert_role_publication(
        role_project_id=project_id,
        tenant_id=tenant_id,
        user_id=user_id,
        commit_sha=last_commit_sha,
        files_count=len(files),
        summary=f"Pushed to {config.repo_full_name}/{base_path}",
    )

    return {
        "commit_sha": last_commit_sha,
        "url": f"https://github.com/{owner}/{repo}/tree/{config.branch}/{base_path}",
        "files_count": len(files),
    }
```

> **Note de performance :** N appels GET + N appels PUT pour N fichiers.
> Pour ~30 fichiers (typique), ça fait 60 appels et ~10-20 secondes. Pas
> idéal mais acceptable pour le MVP. Optimisations possibles : utiliser
> l'API Trees (un seul commit pour N fichiers via `git_data` API).

### Endpoint de publication

```python
@router.post("/role-projects/{project_id}/publish")
async def publish_to_github(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """Publish a role to GitHub."""
    result = await github_publisher.push_files_to_github(user_id, project_id)
    return result


@router.post("/role-projects/{project_id}/unpublish")
async def unpublish_from_github(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """Delete the published files from GitHub."""
    # Iterate files in base_path and DELETE each
    ...


@router.get("/role-projects/{project_id}/publications")
async def list_publications(project_id: UUID) -> list[dict]:
    """List the publication history of a role."""
    return await db.list_role_publications(project_id)
```

## UI : intégration

### Dans "Ma stack" → "Publication"

Nouveau sous-onglet :

- Bouton "Connecter GitHub" si pas connecté
- Si connecté : affiche `@github_login`, scope, bouton "Déconnecter"

### Dans la page rôle

- Bouton "Publier sur GitHub" :
  - Si pas connecté : redirige vers "Ma stack" → Publication
  - Si pas configuré : ouvre une modal de config (repo + sous-répertoire)
  - Sinon : affiche un dialog de confirmation, puis push
- Affichage de l'état : "Publié sur `user/repo/sous-rep`" + lien direct
- Badge "Modifications non publiées" si l'`updated_at` du rôle > date de
  dernière publication
- Bouton "Dépublier"
- Section "Historique des publications" avec date, commit SHA, lien

## Mises à jour : à la discrétion de l'utilisateur

Quand l'utilisateur modifie son rôle après une première publication :
- L'application n'auto-publie **pas**
- Un badge "Modifications non publiées" apparaît
- L'utilisateur déclenche manuellement la republication
- Chaque republication crée un nouveau commit (pas de tag/release auto
  dans le MVP)

## Critères de fin de sprint

- [ ] Flow OAuth complet : un utilisateur peut connecter son GitHub
- [ ] Token stocké dans OpenBao, pas en base
- [ ] Liste des repos disponibles pour configuration
- [ ] Configuration sauvée par projet
- [ ] Premier push réussit : les fichiers apparaissent dans le repo
- [ ] Republication update les fichiers existants (avec sha)
- [ ] README généré contient les bonnes infos
- [ ] Historique des publications affiché
- [ ] Dépublication fonctionne (DELETE)
- [ ] Déconnexion GitHub stoppe les publications futures

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] Optimisation push : passer aux API Trees pour faire 1 seul commit
      au lieu de N (Phase 2)
- [ ] Stratégie de tag/release par version : utile ou overkill pour le MVP ?
- [ ] Licence par défaut suggérée dans le README (CC-BY ? MIT ? autre ?)
- [ ] Modération et vitrine officielle (phase ultérieure, à designer
      séparément)
- [ ] Format final du README : ajouter des badges (shields.io) ? Stats ?
- [ ] Multi-comptes GitHub par user : pour le MVP, 1 seul compte par user.
      À étendre plus tard ?
- [ ] State CSRF : in-memory pour le MVP. Pour la prod multi-instance,
      migrer vers Redis ou table PG temporaire.

---

**Document précédent :** `08-export-agflow.md`
**Document suivant :** `10-frontend-ux.md`
