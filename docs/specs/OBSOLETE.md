# ⚠️ Specs obsolètes — refonte V2 (stack d'acquisition pilotée)

> Depuis le 2026-07-04, Role Builder pivote avec l'écosystème ag.flow V2 :
> plus de Docker service, la synthèse est faite par le pilote (Claude web),
> le corpus est déposé dans docflow, la stack est consommée via MCP
> (`roles__*`) et hébergée sur un host `usage=ressources`.
> Voir `docs/specs/v2/00-fondations-v2.md`.

## Obsolètes (ne plus implémenter, référence historique uniquement)

| Spec | Raison |
|---|---|
| `05-corpus-indexing.md` | Chunking/embeddings/pgvector supprimés — la recherche sur le corpus est le métier d'agflow-rag sur docflow. |
| `06-synthesis.md` | Le pipeline 5 étages et la bibliothèque de prompts sont remplacés par la synthèse du pilote. Dépendance Mistral supprimée. |
| `08-export-agflow.md` | L'API admin du Docker service ag.flow n'existe plus. Destination = docflow, sans export ni prompt orchestrateur. |
| `09-github-publish.md` | Publication retirée du périmètre (le contenu vit dans docflow ; capacité docflow→GitHub éventuelle, ailleurs). |
| `10-frontend-ux.md` | L'interface primaire devient conversationnelle (pilote + MCP). Une vue admin minimale reste à cadrer. |

## Conservées avec adaptations (voir fondations v2 §2, §5)

- `00-overview.md` — vision et intégration ag.flow remplacées par
  `v2/00-fondations-v2.md` ; le phasage « contrats stdin/NDJSON figés »
  a rempli son office.
- `01-data-model.md` — cœur conservé (sources, items, queues, credentials,
  workers) ; tables de synthèse/publication/pgvector supprimées ;
  `role_projects` remplacé par `acquisition_requests`
  (cf. `v2/01-protocole-mcp.md` §4).
- `02-foundations.md` — infra conservée (compose, MinIO, coffre) ; cible
  de déploiement = host `usage=ressources` du portail devpod ; extension
  pgvector plus requise.
- `03-scrapers.md` — conservée intégralement (contrats figés).
- `04-transcription.md` — conservée ; l'étape post-transcription devient
  le dépôt docflow (plus de chunking).
- `07-user-stack.md` — conservée moins la configuration Mistral.
- `11-sequence-diagrams.md` — diagrammes acquisition valides, diagrammes
  synthèse/export obsolètes.
- `12-open-decisions.md` — journal historique précieux (décisions
  d'implémentation des sprints 1-8) ; ne plus y ajouter que des décisions V2.
