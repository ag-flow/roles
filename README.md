# roles

**Stack d'acquisition de corpus** de l'écosystème ag.flow V2 : `roles` scrape des sources vidéo
(YouTube / Instagram / TikTok), transcrit l'audio, et **dépose les transcripts dans docflow** —
un document par vidéo. C'est tout.

La **synthèse** (transformer un corpus en documents de rôle) est le travail du **pilote**
(Claude web) et se fait hors de cette stack. `roles` ne connaît pas la notion de rôle et ne
proxifie jamais le contenu des transcripts.

Consommation via la passerelle MCP, namespace `roles__*`, en **ticket asynchrone** :
`submit_acquisition` → `select_items` → `request_status` → `get_corpus` (incrémental).

> **Refonte V2 (2026-07-04)** — le pipeline de synthèse (5 étages, Mistral), l'export ag.flow,
> la publication GitHub et le chunking/pgvector sont **abandonnés** : `docs/specs/OBSOLETE.md`.

## Documentation

- **Fondations V2** : `docs/specs/v2/00-fondations-v2.md` (vision, architecture, frontière des données)
- **Protocole MCP** : `docs/specs/v2/01-protocole-mcp.md` (tools `roles__*`, cycle de vie, modèle de données)
- **Contrat de la façade** : `docs/contracts/roles-mcp.openapi.json` (OpenAPI 3.1) + article
  « Contrat — façade MCP `roles__*` » dans docflow `roles` / `documentation`
- **Secrets & wallets** : `docs/specs/v2/02-secrets-wallets-selfservice.md`
- **Modèle de données** : `docs/specs/01-data-model.md` (spec V1 conservée, lire sa bannière)
- **Journaux et observabilité** : `docs/logs.md`
- **Instructions agent** : `CLAUDE.md`

Les conventions de code (Python, frontend, tests, migrations, secrets, analyse statique) vivent
dans les **skills** déposées par le profil de skills du workspace, pas dans ce dépôt — voir la
table « Quand charger une skill » de `CLAUDE.md`.

## Démarrage local

```bash
cd backend && uv sync --extra dev
docker compose -f docker-compose-dev.yml up -d        # postgres, minio, backend, frontend
cd backend && uv run uvicorn role_builder.main:app --reload   # :8000
curl http://localhost:8000/health/
```

Les migrations SQL (`migrations/*.sql`) sont jouées **au démarrage du backend** (lifespan
FastAPI), pas par un script externe : un échec fait redémarrer le conteneur en boucle, de sorte
qu'un schéma en retard ne peut pas être servi.

## Déploiement sur machine de test

```bash
# 1) pousser sur dev — le script déploie ce que git contient, pas l'arbre local
git push origin dev
# 2) sur la machine de test, dans le dépôt
sudo ./dev-deploy.sh dev
```

Les **ports publiés se paramètrent** dans le `.env` de la cible. Laissés aux défauts, ils sont
résolus par le script après l'arrêt de la stack : un défaut occupé bascule sur le premier port
libre à partir de défaut+10000, et le choix est persisté. Une valeur écrite explicitement est
respectée, et le déploiement échoue si elle est occupée — plutôt que de déplacer en silence un
port dont quelque chose dépend.

`dev-deploy.sh` est le **seul** geste de livraison : il se met à jour depuis git, complète les
secrets manquants du `.env` sans écraser l'existant, construit les images, relance la stack et
vérifie `/health/`. Aucune construction ni `docker run` à la main, aucune retouche manuelle de
la cible — un correctif d'infra se met **dans le script**, sinon il est perdu au redéploiement
suivant.

### Accès au dépôt privé (premier clone)

Le dépôt est privé : la machine cible a besoin d'une **deploy key SSH en lecture seule**.
Génère-la **sur la machine** (jamais collée depuis ailleurs) :

```bash
sudo ./dev-deploy.sh --bootstrap-deploy-key
```

Le script crée la clé si elle manque, configure SSH pour github.com, affiche la **clé publique**
et s'arrête : enregistre-la dans *Settings → Deploy keys* du dépôt (lecture seule), puis relance
`sudo ./dev-deploy.sh dev`.

## Journaux

```bash
docker compose -f docker-compose-dev.yml logs --tail=50 backend
docker compose -f docker-compose-dev.yml logs --tail=50 frontend
```

Les journaux sont aussi collectés par l'agent Alloy (`infra/alloy-agent/`) et consultables dans
Grafana — c'est là qu'on diagnostique un incident, pas dans une sortie de commande tronquée.

## Licence

Double licence : `LICENSE` (usage non commercial) et `COMMERCIAL-LICENSE.md`.
