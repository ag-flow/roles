# 00-v2 — Role Builder : Fondations révisées (stack d'acquisition pilotée)

> Document fondateur de la refonte. S'aligne sur la refonte V2 d'ag.flow
> workflow (paradigme pull / pilote — cf. repo `workflow`,
> `docs/specs/v2/00-fondations-v2.md`).
>
> **Statut :** v2.0 — 2026-07-04
> **Rend obsolètes :** specs 05 (chunking/pgvector), 06 (pipeline de synthèse),
> 08 (export ag.flow), 09 (publication GitHub), et l'essentiel de 10 (frontend).
> Voir `docs/specs/OBSOLETE.md`.

---

## 1. Vision révisée

Role Builder devient une **stack d'acquisition de corpus** : elle scrape,
transcrit, et dépose les transcripts dans **docflow**. C'est tout.

La synthèse (transformer un corpus en documents de rôle structurés) n'est
plus un pipeline mécanique de la stack : c'est le travail du **pilote**
(Claude web), qui lit les transcripts dans docflow, synthétise avec son
propre jugement, et stocke les documents de rôle dans docflow.

| | V1 | V2 |
|---|---|---|
| Synthèse | pipeline 5 étages (extractor→clusterer→decomposer→writer→identity), prompts versionnés, Mistral | **le pilote** — jugement, pas de machinerie |
| Destination | export ZIP vers l'API admin du Docker service ag.flow | **docflow** (transcripts ET documents de rôle) |
| Consommation | `prompt_orchestrator_md` compilé, injecté dans un agent provisionné | les agents **lisent les documents** (docflow, via workflow `agent_ref` ou directement) |
| Déclenchement | UI web mono-utilisateur | **MCP** via la passerelle (`roles__*`), multi-acteurs |
| Recherche corpus | pgvector interne (`corpus_chunks`) | **agflow-rag** indexe docflow — plus d'index interne |
| Publication GitHub | intégrée (sprint 8) | **retirée** — le contenu vit dans docflow ; renaîtra éventuellement comme capacité docflow→GitHub |

La justification du retrait du pipeline : les 4 étages étaient la
décomposition mécanique d'un travail de jugement, construite pour compenser
l'absence d'un agent intelligent dans la boucle. Le pilote **est** la boucle.

## 2. Ce qui survit — le cœur dur

La **stack d'acquisition**, éprouvée sur les sprints 1-4 :

- **Scraping multi-plateforme** (YouTube/Instagram/TikTok) : containers
  one-shot, contrat **stdin JSON / stdout NDJSON** (figé depuis Phase 1,
  précisément pour ce genre de migration), cookies utilisateur.
- **Transcription** : pools de workers (faster-whisper GPU + SaaS OpenAI
  Whisper/Deepgram/...), gestion des clés, caps mensuels, bascule shared,
  format pivot JSON indépendant du provider.
- **Queues PostgreSQL** `FOR UPDATE SKIP LOCKED`, statuts par item,
  `tenant_id` partout (le multi-acteurs était anticipé dès le sprint 1).
- **MinIO** pour l'audio brut (`keep_audio` conservé) et les transcripts
  bruts intermédiaires.
- **Ma stack** (spec 07) : gestion des cookies, clés SaaS, quotas —
  **moins** la configuration Mistral, qui disparaît.

## 3. Architecture V2

```
Claude web (pilote)                    autres acteurs (futurs agents)
      │  roles__* via passerelle MCP        │
      ▼                                     ▼
┌─────────────────────────────────────────────────┐
│  STACK RÔLES (compose, host usage=ressources)   │
│  ├── façade MCP roles__* (tickets/requêtes)     │
│  ├── queues PG (scraping, transcription)        │
│  ├── scrapers one-shot (stdin/NDJSON)           │
│  ├── workers transcription (SaaS, CPU)          │
│  └── dépose les transcripts → docflow           │
│         (cliente de la passerelle MCP)          │
└─────────────────────────────────────────────────┘
        worker faster-whisper GPU : épinglé pve2
                      │
                      ▼
                  DOCFLOW  ←── le pilote lit, synthétise,
              (transcripts,      stocke les documents de rôle
               documents         (docflow__*, aucun tool roles__
               de rôle)           impliqué dans la synthèse)
```

**Double posture MCP** — première brique de l'écosystème dans ce cas :
la stack est à la fois **backend MCP** (elle expose `roles__*` derrière la
passerelle) et **client MCP** (elle écrit dans docflow via la passerelle).
Elle a donc une identité machine propre auprès de la passerelle, à
provisionner comme un secret de déploiement (`${vault://...}`).

**Hébergement** : template compose dans la galerie devpod, déployé sur un
host `usage=ressources` (services CPU : backend/MCP, scrapers, workers
SaaS). Le worker faster-whisper reste épinglé sur pve2 (GPU RTX 4090) —
stack éclatée, gérée par le modèle de déploiement par nœud.

## 4. Modèle d'interaction : ticket asynchrone

Les ressources d'exécution (images Docker scrapers/workers) sont
**partagées entre tous les acteurs**. Toute demande passe par une queue
asynchrone avec **clé de requête** :

1. Le pilote **soumet** une acquisition → reçoit une `request_key`.
2. La stack déroule : discover → (sélection) → download → transcription →
   dépôt docflow, item par item.
3. Le pilote **pull** de temps en temps : statut, puis récupération des
   références du corpus prêt.

Principes :

- **Livraison incrémentale.** Un corpus de 55 vidéos tombe item par item
  sur des heures. `roles__get_corpus` retourne à tout moment les refs
  docflow des items déjà transcrits (+ flag `complete`, + `only_new`).
  Le pilote peut commencer sa synthèse sans attendre la fin.
- **Références, jamais de contenu.** La stack retourne des refs docflow ;
  le texte se lit via `docflow__get_document`. La stack n'est pas un proxy
  de lecture.
- **Un document docflow par vidéo** (type fonctionnel `transcript`,
  métadonnées : plateforme, source, titre, durée, date de publication,
  request_key). Corpus structuré pour consommation incrémentale par le
  pilote — jamais de pavé agrégé.
- **Sélection en deux temps, mode par défaut** (décision V2.1) :
  - mode nominal : `submit` en `discover_only` découvre **toute la chaîne** →
    `list_discovered` retourne les métadonnées riches (titre, extrait de
    description, tags, durée, date) → le pilote thématise et présente la
    liste à l'humain → `select_items` sur la liste retenue → download.
    La **thématisation est le travail du pilote** — aucun LLM dans la stack.
  - raccourci : `mode=auto` avec filtres déclaratifs (`max_items`, `since`,
    `min/max_duration`) — un seul aller-retour pour les cas simples.
- **Intake par upload** (V2.1) : médias hors plateformes (enregistrements,
  conférences, podcasts en fichier) via **URL présignée MinIO** — le binaire
  ne transite jamais par MCP. L'item rejoint ensuite le pipeline standard,
  indiscernable d'un item scrapé côté corpus (`platform=upload`).
- **Équité multi-acteurs : FIFO en V1.** `priority` et `tenant_id`
  existent déjà comme hooks ; quotas/round-robin = question ouverte,
  à traiter quand plusieurs acteurs réels se disputeront la ressource.

## 5. Frontière des données

- **Audio brut** : MinIO, interne à la stack (`keep_audio` pilote la
  rétention). Ne franchit jamais la frontière — docflow ne stocke pas de
  binaire.
- **Transcripts** : le format pivot JSON reste l'artefact interne (MinIO) ;
  le **texte** (+ métadonnées) est déposé dans docflow. Docflow est la
  source de vérité du corpus consommable.
- **Documents de rôle** : produits et stockés dans docflow **par le
  pilote**, hors périmètre de la stack. La stack ne sait pas ce qu'est un
  rôle — elle livre du corpus.
- **Plus d'index sémantique interne** : la chaîne chunking/embedding/
  pgvector (sprint 4) est supprimée. La recherche sur le corpus est le
  métier d'**agflow-rag** sur docflow.

## 6. Ce qui est retiré (pertes assumées)

- Pipeline de synthèse complet (sprint 5 + Phase 2 associée) : étages,
  bibliothèque de prompts, tables `runs`/`signals`/`clusters`/
  `document_plans`/`role_documents`, obsolescence des runs, full-pipeline.
- Dépendance Mistral (clé, secret_ref, cost tracking, embeddings).
- Export ag.flow (sprint 7) : ZIP, `role.json`, `/generate-prompts` —
  l'API admin du Docker service n'existe plus.
- Publication GitHub (sprint 8) : retirée du périmètre. Le code
  (Trees API, OAuth, multi-comptes) est de qualité — il pourra renaître
  comme capacité docflow→GitHub, ailleurs.
- Chunking + embeddings + `corpus_chunks` (sprint 4).
- L'essentiel du frontend Next.js (onglets Prompts, Analyses, Rôle,
  publication). Survit au besoin : une vue minimale d'administration
  (requêtes en cours, Ma stack) — à cadrer, l'interface primaire devient
  la conversation avec le pilote.

## 7. Traçabilité

Aligné sur le principe causal de la refonte workflow :

- Chaque document docflow déposé porte la chaîne : `request_key` →
  `source_item` → source → plateforme/URL d'origine, + provider de
  transcription et coût.
- La stack garde ses tables d'items/jobs comme **journal d'acquisition**
  (qui a demandé quoi, quand, ce que ça a coûté).
- Le pilote, en synthétisant, référence les transcripts docflow sources
  dans les documents de rôle qu'il produit (référencement docflow natif) —
  la chaîne rôle → transcript → vidéo d'origine reste rejouable.

## 8. Contraintes architecturales conservées

- FastAPI + asyncpg (pas de SQLAlchemy), migrations SQL brutes, structlog
  JSON, fichiers ≤ 300 lignes, `tenant_id` partout, contrats
  stdin/NDJSON des containers figés, format pivot transcript inchangé.
- Secrets via le coffre existant (`${vault://...}`) — inchangé.
- WebSocket/PG NOTIFY : conservé en interne pour l'éventuelle vue admin ;
  le canal primaire de suivi devient le pull MCP.

## 9. Questions ouvertes

- Équité/quotas multi-acteurs sur les ressources partagées (V2 = FIFO).
- Vue admin minimale : garder un frontend réduit ou tout basculer en
  conversationnel + tools MCP d'admin (`roles__list_requests` suffit-il) ?
- Contrat exact de dépôt docflow : quel workspace/bloc docflow cible par
  requête ? (paramètre du `submit` vs convention par tenant — à trancher
  avec la spec docflow des types fonctionnels.)
- Identité machine de la stack auprès de la passerelle (provisioning,
  rotation).
- Devenir du code GitHub publish (archivage ? extraction en lib ?).
