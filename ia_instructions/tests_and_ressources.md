# Ressources attribuées à l'agent

Ce fichier est la **mémoire** des ressources mises à disposition de l'agent de ce dépôt —
distinct des règles d'usage, qui vivent dans la skill `test-machine-deployment`. Les règles
disent *comment* s'en servir ; ce fichier dit *lesquelles* on a, ici et maintenant.

Tenir à jour **à chaque notification** : une ressource attribuée s'ajoute, une ressource reprise
se retire. C'est ce qui permet de retrouver une machine sans la redemander.

## Machines de test

| Alias SSH | Nom d'hôte réel | À quoi elle sert | Attribuée le |
|---|---|---|---|
| `test1` | `host-test-23` | Déploiement et validation de la stack `roles` | 2026-10-08 |

### `test1` — ce qu'il y a derrière, vérifié le 2026-10-08

Debian 12 (bookworm), 4 vCPU / 7 Go, Docker 29.8.1, disque 40 Go dont 23 Go utilisés (62 %).
Accès par jump host (`devflow-jump@100.74.13.151`), utilisateur `root`.

**Ce n'est PAS une VM dédiée à `roles`.** Elle porte déjà six projets compose :

| Projet | Ce qu'il est |
|---|---|
| `wsportal-dev` | le portail devpod lui-même (+ postgres, caddy) |
| `wsportal-dev-others` | Grafana, Loki, VictoriaMetrics, Alloy, Zulip |
| `harpocrate` | frontend, backend, postgres, testdb |
| `browserless-chromium` | le Chromium d'épreuve des IHM |
| `alloy-collector`, `alloy-metrics` | collecte de journaux et de métriques |

**Conséquences à tenir avant tout déploiement de `roles` :**

- **Trois des cinq ports du compose `roles` sont déjà pris** — `8000` par
  `harpocrate-backend`, `5432` par `harpocrate-postgres`, `3000` par
  `browserless-chromium`. Seuls `9000` et `9001` (MinIO) sont libres. Le `.env` de la cible
  doit donc porter `BACKEND_PORT`, `FRONTEND_PORT` et `POSTGRES_PORT` distincts des défauts.
- **Une purge Docker y est collatérale.** Le cache de construction (2,43 Go) et les images sont
  partagés par les six projets : un `docker builder prune -af` ralentirait la prochaine
  construction du portail et de harpocrate.
- **Un accès GitHub fonctionne déjà** depuis l'hôte (clé de compte `gaelgael5`), donc le clone
  du dépôt privé passe sans `--bootstrap-deploy-key`. Ce n'est pas une deploy key en lecture
  seule : écart au standard, assumé par qui a provisionné la machine.
- Le dépôt `roles` **n'y est pas encore cloné** : le premier déploiement est une installation.

> **Un alias qui répond ne prouve rien** : les alias sont recyclés (le même nom a désigné trois
> machines en un mois). Avant tout déploiement ou diagnostic, vérifier ce qu'il y a derrière —
> nom d'hôte réel, stack attendue, conteneurs actifs.

## Autres ressources

_Aucune._
