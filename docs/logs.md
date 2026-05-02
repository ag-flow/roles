# Logs — collecte et observabilité

## Architecture

- **Stack centrale** : LXC 116 (`agflow-logs`) héberge **Loki + Grafana**.
  Endpoint push : `http://192.168.10.110:3100/loki/api/v1/push`. Grafana
  est exposé sur **https://log.yoops.org** avec SSO Keycloak (realm
  `yoops`, client `grafana`, rôles `admin|editor|viewer`).
- **Collecteur** : un agent **Grafana Alloy** (image `grafana/alloy:v1.5.1`)
  tourne sur chaque LXC à instrumenter. Il lit le socket Docker et le
  journal systemd, applique des labels et pousse vers Loki.
- Ce repo livre **uniquement** le collecteur (`infra/alloy-agent/`). La
  stack Loki/Grafana centrale est gérée hors-repo (côté ops).

## Labels appliqués

| Label | Source | Exemple |
|---|---|---|
| `cluster` | fixe | `homelab` |
| `module` | fixe | `roles` |
| `host` | env `HOSTNAME` | `lxc220` |
| `job` | fixe par source | `docker` ou `systemd-journal` |
| `container` | label compose | `agflowroles-backend-1` |
| `compose_service` | label compose | `backend` |
| `compose_project` | label compose | `agflowroles` |
| `unit` | journald | `docker.service` |

Filtrage typique côté Grafana :

```
{module="roles", host="lxc220"}                       # tout le LXC
{module="roles", compose_service="backend"}           # juste le backend
{module="roles", job="systemd-journal", unit="docker.service"}
```

## Déploiement

Depuis le poste local, à la racine du repo `agflow.roles` :

```bash
./infra/deploy-alloy.sh 220
```

Le script détecte automatiquement la présence de Docker dans le LXC et
choisit le mode container (`config.alloy` via docker-compose) ou le mode
binaire systemd (`02-install-alloy.sh`). Smoke-check final via
`http://<lxc>:12345/-/ready`.

## Fichiers

- `infra/alloy-agent/docker-compose.yml` — service Alloy (image officielle)
- `infra/alloy-agent/config.alloy` — config full (Docker socket + journald)
- `infra/alloy-agent/config-journald-only.alloy` — variante sans Docker
- `infra/alloy-agent/.env.template` — `LOKI_URL` + `HOSTNAME`
- `infra/alloy-agent/README.md` — documentation locale du dossier
- `infra/deploy-alloy.sh` — script d'installation depuis le poste

## Ajouter un nouveau host

1. Sur ton poste : `./infra/deploy-alloy.sh <CTID>`
2. Dans Grafana → Explore → datasource Loki, requête
   `{module="roles", host="lxc<CTID>"}` doit retourner des entrées dans
   les ~30 secondes.

## Conventions de logs côté code

- **Backend (Python)** : `structlog` JSON en stdout (cf. `logging_setup.py`).
  Le collecteur lit ces lignes via le socket Docker et les indexe directement.
  Toujours utiliser `log = structlog.get_logger(__name__)`, jamais `print()`.
- **Frontend (Next.js)** : logs SSR vont en stdout, idem côté collecteur.
- **Niveaux** : `debug` (dev only), `info` (événements métier), `warning`
  (situation anormale récupérable), `error` (échec opération), `exception`
  (avec traceback).

## Hors-scope ce repo

- Configuration Loki / Grafana / Promtail / Alertmanager côté LXC 116
  (gestion via le repo `ag-flow.Configuration`).
- Rétention, ratelimit, dashboards Grafana — réglés côté stack centrale.
