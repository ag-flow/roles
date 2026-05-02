# Alloy collector — agflow.roles

Pousse les logs Docker + journald de ce LXC vers la stack Loki centrale.

## Architecture

- **Loki + Grafana central** : LXC 116 (`agflow-logs`). Endpoint push :
  `http://<IP_LXC116>:3100/loki/api/v1/push` (par défaut `192.168.10.110`).
  Grafana exposé sur **https://log.yoops.org** (SSO Keycloak realm `yoops`,
  client `grafana`, rôles `admin|editor|viewer`).
- **Ce dossier** : le **collecteur Alloy** déployé sur chaque LXC qui doit
  remonter ses logs. Ne touche PAS au repo de la stack centrale.

## Labels appliqués

Toutes les entrées poussées portent ces labels :

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

## Fichiers

- `docker-compose.yml` — service Alloy avec mounts socket Docker + journal
- `config.alloy` — config full (Docker + journald), à utiliser quand Docker
  est installé sur le LXC
- `config-journald-only.alloy` — variante sans Docker, pour les LXC légers
- `.env.template` — variables `LOKI_URL` + `HOSTNAME`

## Déploiement

Depuis le poste local (Windows / Linux), à la racine du repo :

```bash
./infra/deploy-alloy.sh 220
# ou avec un alias SSH (config dans ~/.ssh/config) :
PVE_HOST=pve ./infra/deploy-alloy.sh 220
```

Le script :
1. Crée `/opt/alloy/` dans le LXC cible
2. rsync `infra/alloy-agent/` vers `/opt/alloy/`
3. Si pas de `.env` côté cible, copie `.env.template` et alerte
4. `docker compose up -d`
5. Smoke : `curl http://<lxc-ip>:12345/-/ready` puis dump des 20 dernières
   lignes de logs du container

## Ajouter un nouveau host à la collecte

1. Déployer ce dossier sur le LXC (cf. ci-dessus)
2. Vérifier dans Grafana → Explore (datasource Loki) que les requêtes
   `{module="roles", host="lxc<N>"}` retournent des résultats
3. Le dashboard "Docker" doit faire apparaître le `host` dans le sélecteur

## Notes

- En mode Swarm, Alloy collecte automatiquement les logs des services via
  le socket Docker — pas de config supplémentaire à prévoir.
- L'agent écoute sur le port `12345/tcp` (admin Alloy : `/-/ready`,
  `/metrics`). Il n'expose rien d'autre côté réseau.
- Les logs Docker sont lus via le socket : pas besoin du driver
  `loki` côté daemon Docker.
