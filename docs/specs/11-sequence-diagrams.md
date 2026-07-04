> ℹ️ **Conservée avec adaptations V2 (2026-07-04).** Diagrammes acquisition valides ; diagrammes synthèse/export obsolètes.
> Voir `docs/specs/v2/00-fondations-v2.md` et `docs/specs/v2/01-protocole-mcp.md`.

# 11 — Diagrammes de séquence

> Référence visuelle pour comprendre les flux principaux de l'application.
> Les diagrammes utilisent Mermaid (rendu par GitHub, GitLab, VS Code, et
> la plupart des viewers Markdown modernes).

## Sommaire

| Diagramme | Domaine | Sprint |
|-----------|---------|--------|
| 1. Création projet et ajout sources | Projets | 2 |
| 2. Découverte d'une chaîne et sélection | Scraping | 2 |
| 3. Pipeline événementiel scraping → transcription | Scraping/Transcription | 2-3 |
| 4. Indexation pgvector et disponibilité corpus | Corpus | 4 |
| 5. Pipeline de synthèse (Mistral via ag.flow) | Synthèse | 5 |
| 6. Génération identity et export ag.flow | Synthèse/Export | 5-7 |
| 7. Régénération ciblée d'un document | Synthèse | 5 |
| 8. Provisioning de workers user | Transcription | 3 |
| 9. Auto-stop d'un worker idle | Transcription | 3 |
| 10. Bascule sur épuisement de crédit | Transcription | 3 |
| 11. Connexion GitHub OAuth | Publication | 8 |
| 12. Publication d'un rôle sur GitHub | Publication | 8 |

---

## 1. Création d'un projet et ajout de sources

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant OB as OpenBao

    U->>FE: Crée un projet de rôle "UX Designer Clea"
    FE->>BE: POST /role-projects {name, description}
    BE->>DB: INSERT role_projects
    BE-->>FE: role_project_id
    FE-->>U: Affiche le projet vide

    U->>FE: Configure les credentials YouTube (cookies.txt)
    FE->>BE: POST /credentials {platform, payload}
    BE->>OB: PUT secret/scraping/{tenant}/youtube
    OB-->>BE: ok, path
    BE->>DB: INSERT user_credentials (openbao_path)
    BE-->>FE: credentials_id, status=active

    U->>FE: Ajoute URL chaîne YouTube
    FE->>BE: POST /sources {url, credentials_id}
    BE->>DB: INSERT sources
    BE-->>FE: source_id, status=pending_discovery
```

## 2. Découverte d'une chaîne et sélection

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant OB as OpenBao
    participant SC as Scraper container

    U->>FE: Lance la découverte de la chaîne
    FE->>BE: POST /sources/{id}/discover
    BE->>OB: GET secret cookies YouTube
    OB-->>BE: cookies (clear)
    BE->>SC: docker run scraper-youtube<br/>(stdin: discover task + cookies b64)
    activate SC

    SC-->>BE: NDJSON {type:"started"}
    SC-->>BE: NDJSON {type:"discovered", items:[127 vidéos]}
    BE->>DB: INSERT 127 source_items (status=pending)
    BE-->>FE: WebSocket: items disponibles
    FE-->>U: Affiche la liste avec filtres

    SC->>SC: exit 0
    deactivate SC

    U->>FE: Filtre (durée >5min, depuis 2022)<br/>et sélectionne 55 vidéos
    FE->>BE: POST /sources/{id}/items/select<br/>(item_ids[])
    BE->>DB: UPDATE source_items SET selected=true
    BE->>DB: INSERT 55 scraping_jobs (status=pending)
    BE-->>FE: 55 jobs queued
```

## 3. Pipeline événementiel scraping → transcription

```mermaid
sequenceDiagram
    autonumber
    participant BE as Backend
    participant DB as PostgreSQL
    participant OB as OpenBao
    participant SC as Scraper container
    participant MIO as MinIO
    participant TW as Transcription Worker
    participant PR as Provider
    participant FE as Frontend (WS)

    Note over BE,DB: Backend pull les scraping_jobs FIFO

    BE->>DB: SELECT scraping_jobs<br/>FOR UPDATE SKIP LOCKED LIMIT 1
    DB-->>BE: job (item_1)
    BE->>OB: GET credentials
    OB-->>BE: cookies
    BE->>SC: docker run scraper-youtube<br/>(download task)
    activate SC

    SC->>SC: yt-dlp -x audio mp3 16kHz mono
    SC->>MIO: PUT corpus-audio/{tenant}/{role}/{src}/{item_1}.mp3
    MIO-->>SC: ok
    SC-->>BE: {type:"item_done", audio_s3_key:"..."}
    BE->>DB: UPDATE source_items SET status=audio_ready
    BE->>DB: INSERT transcription_jobs (worker_pool_id, status=pending)
    BE-->>FE: WS: item_1 audio_ready

    Note over SC,BE: Le scraper continue avec item_2, ...

    Note over TW,DB: En parallèle: worker poll sa queue (par pool)

    TW->>DB: SELECT transcription_jobs<br/>WHERE worker_pool_id=$1<br/>FOR UPDATE SKIP LOCKED LIMIT 1
    DB-->>TW: job (item_1)
    TW->>MIO: GET audio item_1
    MIO-->>TW: audio bytes
    TW->>PR: provider.transcribe(audio, language=auto)

    alt Provider = local faster-whisper
        PR->>PR: GPU inference RTX 4090
    else Provider = SaaS (Deepgram/AssemblyAI/etc.)
        PR->>PR: HTTP API call vers SaaS
    end

    PR-->>TW: PivotTranscript
    TW->>MIO: PUT corpus-transcripts/{...}/{item_1}.json
    TW->>DB: UPDATE last_activity_at, status=transcribed
    TW->>DB: INSERT chunking_job
    TW-->>FE: WS: item_1 transcribed
```

## 4. Indexation pgvector et disponibilité corpus

```mermaid
sequenceDiagram
    autonumber
    participant BE as Backend (chunking worker)
    participant DB as PostgreSQL<br/>(+pgvector)
    participant MIO as MinIO
    participant AG as ag.flow<br/>(Embeddings Mistral)
    participant FE as Frontend (WS)

    Note over BE: Worker chunking détecte chunking_jobs.pending

    BE->>DB: SELECT chunking_jobs FOR UPDATE SKIP LOCKED LIMIT 1
    DB-->>BE: job
    BE->>MIO: GET transcript JSON
    MIO-->>BE: PivotTranscript

    BE->>BE: Découpe en chunks taille fixe<br/>(target 500 tokens, overlap 50)

    loop par batch de 32 chunks
        BE->>AG: POST embeddings (texts batch)
        AG-->>BE: vectors[]
        BE->>DB: INSERT corpus_chunks (text, embedding, timestamps)
    end

    BE->>DB: UPDATE source_items SET status=indexed
    BE->>DB: UPDATE chunking_jobs SET status=done
    BE-->>FE: WS: item indexed (visible dans corpus)
    Note over FE: Item utilisable pour analyses<br/>les autres items continuent en parallèle
```

## 5. Pipeline de synthèse (Mistral via ag.flow)

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant AG as ag.flow<br/>(LLM Mistral)

    U->>FE: Lance "Extraire les signaux" sur le corpus
    FE->>BE: POST /runs/extract {prompt:"extractor_v3"}
    BE->>DB: INSERT run (status=running)
    BE-->>FE: run_id

    loop map sur chaque batch de chunks
        BE->>DB: SELECT corpus_chunks
        BE->>AG: invoke LLM (Mistral via secret user)<br/>messages=extractor + chunks
        AG-->>BE: signaux JSON
        BE->>DB: INSERT signals
    end

    BE->>DB: UPDATE run SET status=done
    BE-->>FE: WS: run done, N signaux produits

    U->>FE: Lance "Regrouper en clusters thématiques"
    FE->>BE: POST /runs/cluster {prompt:"clusterer_v2", input:signals}
    BE->>AG: invoke LLM (clusterer + signaux)
    AG-->>BE: clusters JSON
    BE->>DB: INSERT clusters
    BE-->>FE: WS: clusters disponibles

    U->>FE: Lance "Planifier les documents"
    FE->>BE: POST /runs/decompose {prompt:"decomposer_v1"}
    BE->>AG: invoke LLM (decomposer + clusters + sections cibles)
    AG-->>BE: plan JSON
    BE->>DB: INSERT document_plans
    BE-->>FE: WS: plan disponible

    U->>FE: Génère tous les documents
    FE->>BE: POST /runs/write-documents {plan_id, parallel:true}
    par pour chaque document du plan
        BE->>AG: invoke LLM (writer + brief + signals + chunks RAG)
        AG-->>BE: markdown
        BE->>DB: INSERT runs (un par doc)
        BE->>DB: INSERT role_documents (is_current=false)
    end
    BE-->>FE: WS: tous les runs terminés

    U->>FE: Promeut chaque run en role_documents.current
    FE->>BE: POST /role-documents/{id}/set-current
    BE->>DB: UPDATE role_documents SET is_current=true
    BE-->>FE: documents intégrés au rôle
```

## 6. Génération de l'identity et export vers ag.flow

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant AG as ag.flow API

    U->>FE: Génère l'identity du rôle
    FE->>BE: POST /runs/synthesize-identity
    BE->>DB: SELECT role_documents WHERE is_current
    BE->>AG: invoke LLM (identity prompt + tous les docs courants)
    AG-->>BE: identity markdown
    BE->>DB: UPDATE role_projects SET identity=markdown
    BE-->>FE: identity prête

    U->>FE: Bouton "Pousser vers ag.flow"

    FE->>BE: POST /role-projects/{id}/push-to-agflow
    BE->>BE: Construit le ZIP<br/>(role.json + sections/*.md)

    alt Le rôle ag.flow n'existe pas encore
        BE->>AG: POST /api/admin/roles<br/>{display_name, description}
        AG-->>BE: role_id ag.flow
        BE->>DB: UPDATE role_projects SET target_role_id
    end

    BE->>AG: POST /api/admin/roles/{id}/import<br/>(multipart: ZIP)
    AG->>AG: Unzip, upsert sections/documents
    AG-->>BE: RoleDetail

    opt Génération du prompt orchestrateur
        BE->>AG: POST /api/admin/roles/{id}/generate-prompts
        AG->>AG: Synthèse via Mistral
        AG-->>BE: prompt_orchestrator_md
    end

    BE-->>FE: succès + lien vers ag.flow
    FE-->>U: Rôle disponible dans ag.flow
```

## 7. Régénération ciblée d'un seul document

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant AG as ag.flow<br/>(LLM)

    U->>FE: Mécontent du document<br/>"Skills/heuristic-evaluation.md"
    U->>FE: Saisit consigne ponctuelle:<br/>"Plus d'exemples concrets"
    U->>FE: Bouton "Régénérer"

    FE->>BE: POST /role-documents/{doc_id}/regenerate<br/>{instruction_override}

    BE->>DB: SELECT document_plan entry pour ce doc
    BE->>DB: SELECT supporting_signals
    BE->>DB: SELECT corpus_chunks (RAG par embedding)

    BE->>AG: invoke LLM (writer prompt + brief + signaux<br/>+ chunks + instruction_override<br/>+ remarques globales)
    AG-->>BE: nouveau markdown

    BE->>DB: INSERT runs
    BE->>DB: INSERT role_documents (version+1, is_current=false)
    BE-->>FE: nouveau document candidat

    U->>FE: Compare ancien vs nouveau (side-by-side)
    alt Préfère le nouveau
        U->>FE: Promeut le nouveau
        FE->>BE: POST /role-documents/{new_id}/set-current
        BE->>DB: UPDATE old set is_current=false
        BE->>DB: UPDATE new set is_current=true
    else Préfère l'ancien
        Note over BE: Le nouveau reste en base mais non-current
    end
```

## 8. Provisioning de workers user à partir d'une clé SaaS

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant OB as OpenBao
    participant DK as Docker daemon
    participant W as Worker container

    U->>FE: Saisit sa clé Deepgram<br/>+ slider 3 workers<br/>+ marque comme primaire
    FE->>BE: POST /transcription-keys<br/>{provider, key, workers_count, is_primary}
    BE->>BE: Test API key (appel Deepgram trivial)
    BE->>OB: PUT secret/transcription-keys/{tenant}/deepgram/{id}
    OB-->>BE: path
    BE->>DB: INSERT user_transcription_keys<br/>(status=active, workers_count=3)

    Note over BE,DK: Provisioning à la demande au prochain job

    U->>FE: Lance un scraping qui produira des transcription_jobs
    FE->>BE: POST /sources/{id}/items/select
    BE->>DB: INSERT transcription_jobs<br/>(worker_pool_id="user_{user_id}")

    BE->>DB: SELECT user_transcription_keys WHERE status=active
    DB-->>BE: 1 clé Deepgram, 3 workers attendus

    BE->>DB: SELECT count(*) FROM transcription_workers<br/>WHERE worker_pool_id=$1 AND status IN (idle,busy,starting)
    DB-->>BE: 0 workers actifs

    par 3 workers à provisionner
        BE->>OB: GET secret deepgram key
        OB-->>BE: api_key
        BE->>DK: docker run -d --name worker_user_X_deepgram_1<br/>-e DEEPGRAM_API_KEY=...<br/>-e WORKER_POOL_ID=user_{user_id}
        DK-->>BE: container_id
        BE->>DB: INSERT transcription_workers<br/>(status=starting)
    end

    Note over W: Workers démarrent et poll la queue

    W->>DB: SELECT transcription_jobs<br/>WHERE worker_pool_id=$1
    DB-->>W: jobs
    W->>W: process...
    W->>DB: UPDATE last_activity_at
```

## 9. Auto-stop d'un worker user après 5 minutes d'inactivité

```mermaid
sequenceDiagram
    autonumber
    participant ORC as Orchestrateur backend<br/>(cron 1 min)
    participant DB as PostgreSQL
    participant DK as Docker daemon
    participant W as Worker container

    Note over ORC: Tourne toutes les minutes

    ORC->>DB: SELECT transcription_workers<br/>WHERE status='idle'<br/>AND last_activity_at < now() - 5 min<br/>AND worker_pool_id != 'shared_default'
    DB-->>ORC: liste des workers idle expirés

    loop pour chaque worker à arrêter
        ORC->>DB: UPDATE workers SET status='stopping'
        ORC->>DK: docker stop {container_id}
        DK->>W: SIGTERM
        W->>W: cleanup, exit 0
        DK-->>ORC: ok
        ORC->>DB: UPDATE workers SET status='stopped', stopped_at=now()
    end

    Note over ORC: Au prochain job du pool,<br/>les workers seront re-provisionnés
```

## 10. Bascule sur épuisement de crédit

```mermaid
sequenceDiagram
    autonumber
    participant W as Worker user (Deepgram)
    participant PR as Provider Deepgram
    participant DB as PostgreSQL
    participant ORC as Orchestrateur backend
    participant DK as Docker daemon
    participant FE as Frontend (WS)
    participant MAIL as Email service

    W->>DB: SELECT next job (worker_pool_id=user_X)
    DB-->>W: job
    W->>PR: transcribe(audio)
    PR--xW: HTTP 402 "insufficient_credits"

    W->>W: classify error: exhausted (pas un rate-limit)
    W->>DB: UPDATE user_transcription_keys<br/>SET status='exhausted'
    W->>DB: UPDATE current_job SET status='pending',<br/>worker_pool_id='shared_default',<br/>error_history += 'deepgram exhausted'
    W-->>FE: WS: warning credit exhausted

    Note over ORC: Détecte status=exhausted

    ORC->>DB: SELECT workers WHERE provider='deepgram'<br/>AND tenant_id=user_X
    DB-->>ORC: 3 workers
    loop pour chaque worker
        ORC->>DK: docker stop
        ORC->>DB: UPDATE workers SET status='stopped'
    end

    ORC->>DB: UPDATE transcription_jobs<br/>SET worker_pool_id='shared_default'<br/>WHERE worker_pool_id='user_X' AND status='pending'

    ORC->>MAIL: send email "Deepgram credit exhausted"
    ORC-->>FE: WS: notification rouge dans Ma stack

    Note over FE: User peut recharger et réactiver<br/>la clé manuellement plus tard
```

## 11. Connexion GitHub via OAuth

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant GH as GitHub OAuth
    participant OB as OpenBao
    participant DB as PostgreSQL

    U->>FE: Clique "Connecter GitHub"
    FE->>BE: GET /auth/github/start
    BE->>BE: Génère state CSRF (cache 10 min)
    BE-->>FE: redirect_url GitHub
    FE->>GH: redirect (avec state, scope=public_repo)
    U->>GH: Authorize app
    GH->>FE: redirect callback?code=...&state=...
    FE->>BE: GET /auth/github/callback?code&state
    BE->>BE: Vérifie state CSRF
    BE->>GH: POST /access_token (échange code)
    GH-->>BE: access_token
    BE->>GH: GET /user (récupère login + id)
    GH-->>BE: {login, id}
    BE->>OB: PUT secret/github-tokens/{tenant}/{user}
    OB-->>BE: path
    BE->>DB: INSERT github_integrations
    BE-->>FE: success
    FE-->>U: GitHub connecté ✓
```

## 12. Publication d'un rôle sur GitHub

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant OB as OpenBao
    participant GH as GitHub API

    U->>FE: Bouton "Publier sur GitHub"
    FE->>BE: GET /role-projects/{id}/publication-config
    BE->>DB: SELECT role_publication_config
    DB-->>BE: {repo, subdirectory, branch}
    BE-->>FE: config

    alt Pas de config
        U->>FE: Sélectionne repo + sous-répertoire
        FE->>BE: GET /github/repos
        BE->>OB: GET token
        BE->>GH: GET /user/repos
        GH-->>BE: liste repos
        BE-->>FE: liste
        U->>FE: Choisit, valide
        FE->>BE: POST /role-projects/{id}/publication-config
        BE->>DB: INSERT role_publication_config
    end

    U->>FE: Confirme la publication
    FE->>BE: POST /role-projects/{id}/publish

    BE->>DB: SELECT role + identity + role_documents (current)
    BE->>BE: Génère le contenu:<br/>- README.md<br/>- role.json<br/>- identity.md<br/>- sections/*/*.md
    BE->>OB: GET github token
    OB-->>BE: token

    loop pour chaque fichier à publier
        BE->>GH: GET contents/{path} (pour vérifier existant + sha)
        GH-->>BE: file ou 404
        BE->>GH: PUT /repos/{owner}/{repo}/contents/{path}<br/>{content_b64, message, branch, sha?}
        GH-->>BE: commit info
    end

    BE->>DB: INSERT role_publications<br/>(commit_sha, published_at)
    BE-->>FE: succès + URL publique
    FE-->>U: Lien direct vers le repo/sous-répertoire
```

---

**Document précédent :** `10-frontend-ux.md`
**Document suivant :** `12-open-decisions.md`
