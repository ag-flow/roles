# Recherche de bugs — agflow.roles (2026-07-05)

Audit complet du dépôt par revue multi-agents (backend services, acquisition, façade MCP, routes/auth/config, secrets Harpocrate, frontend, infra). Chaque bug a son propre fichier avec problème, scénario d'échec concret, piste de résolution et estimation de difficulté de correction.

## État des corrections (2026-07-06)

**51 bugs corrigés sur 62** — les fichiers résolus sont dans [`fixed/`](fixed/).

- **Fable (1)** : BUG-22.
- **Opus (16)** : BUG-04, 10, 11, 17, 18, 19, 23, 24, 32, 33, 34, 36, 42, 45, 48 (+ BUG-20, 21 réglés via BUG-22).
- **Sonnet (30)** : BUG-03, 05, 06, 07, 08, 09, 12, 13, 14, 15, 16, 25, 26, 27, 28, 29, 30, 31, 35, 37, 38, 39, 40, 41, 43, 44, 46, 47, 49, 57, 59, 60, 61.

**⏸️ Restants (11)** :
- **Frontend « en sursis »** (règle CLAUDE.md « ne rien y développer sans décision ») — 7 : BUG-50, 51, 52, 53, 54, 55, 56.
- **Deploy/contrat non vérifiables dans le devcontainer** — 4 : BUG-01 (contrat scraper figé), BUG-02 (socket docker + réseau compose), BUG-58 (volumes vs credentials), BUG-62 (migration 0001/pgvector).

Suite backend : **481 passed** (2 échecs préexistants `test_migration_0009`, sans rapport — tables `user_secrets`/`user_transcription_keys` non touchées). Endpoint MCP vérifié empiriquement (POST /mcp → 200, Host non-localhost). Lint `ruff` clean. Tests exécutés contre un Postgres pgvector réel.

## Échelle de difficulté

- **Sonnet** — correction localisée, mécanique, contrat clair (une condition, un try/except, un paramètre).
- **Opus** — correction moyenne : transaction, refactor de flux, nouvel état, décision de config, race à traiter proprement.
- **Fable** — correction difficile/architecturale : nouveau worker asynchrone, re-compactage de migration, identité non-falsifiable, décision de conception transverse.

## Index

### Critiques (le produit ne fonctionne pas en déploiement réel)
- [BUG-01 — Payload download sans `items` : pipeline d'acquisition no-op marqué en succès](BUG-01-download-payload-sans-items.md) — Opus
- [BUG-02 — Backend conteneurisé sans CLI docker ni socket : aucun scraper/worker ne démarre](BUG-02-backend-sans-docker-cli.md) — Opus
- [BUG-03 — Endpoint MCP réellement servi sur `/mcp/mcp`, pas `/mcp`](fixed/BUG-03-mcp-endpoint-double-prefixe.md) — Sonnet
- [BUG-04 — Protection DNS-rebinding : 421 pour tout Host non-localhost (passerelle bloquée)](fixed/BUG-04-mcp-dns-rebinding-421.md) — Opus

### Majeures — services cœur
- [BUG-05 — `published_at` chaîne ISO → colonne timestamptz : DataError, découverte en échec](fixed/BUG-05-published-at-str-timestamptz.md) — Sonnet
- [BUG-06 — docker_runner : stderr=PIPE jamais lu → deadlock du container, orchestrator gelé](fixed/BUG-06-docker-runner-stderr-deadlock.md) — Sonnet
- [BUG-07 — docker_runner : aucun cleanup du subprocess si le générateur est abandonné](fixed/BUG-07-docker-runner-pas-de-cleanup.md) — Sonnet
- [BUG-08 — WorkerManager : conflit de nom Docker au respawn (containers jamais supprimés)](fixed/BUG-08-worker-manager-conflit-nom.md) — Sonnet
- [BUG-09 — ScraperOrchestrator : une erreur DB transitoire tue la boucle pour toute la vie du process](fixed/BUG-09-orchestrator-run-loop-meurt.md) — Sonnet
- [BUG-10 — ScraperOrchestrator : le sémaphore `max_concurrent_scrapers` n'a aucun effet](fixed/BUG-10-orchestrator-semaphore-inutile.md) — Opus
- [BUG-11 — WSRelay : aucune reconnexion si la connexion LISTEN asyncpg tombe](fixed/BUG-11-ws-relay-pas-de-reconnexion.md) — Opus
- [BUG-12 — scraping_jobs `claimed`/`processing` orphelins après crash : aucune récupération](fixed/BUG-12-scraping-jobs-orphelins.md) — Sonnet

### Majeures — acquisition / MCP
- [BUG-13 — `apply_selection`/`select_items` : item_ids d'une autre source acceptés, `selected_count` faux](fixed/BUG-13-selection-item-ids-non-valides.md) — Sonnet
- [BUG-14 — Requête figée en `acquiring` pour toujours quand 0 item est sélectionné](fixed/BUG-14-requete-figee-acquiring.md) — Sonnet
- [BUG-15 — Pagination `list_discovered` instable : doublons et pertes d'items entre pages](fixed/BUG-15-pagination-list-discovered.md) — Sonnet
- [BUG-16 — Un event `discovered` tardif écrase le statut `cancelled`](fixed/BUG-16-discovered-ecrase-cancelled.md) — Sonnet
- [BUG-17 — Annulation non étanche : dépôts et relances possibles sur une requête `cancelled`](fixed/BUG-17-annulation-non-etanche.md) — Opus
- [BUG-18 — `retry_failed` sur un item upload fabrique un job scraper impossible](fixed/BUG-18-retry-failed-item-upload.md) — Opus
- [BUG-19 — Échecs de découverte/transcription jamais propagés : requêtes et items bloqués sans issue](fixed/BUG-19-echecs-non-propages.md) — Opus
- [BUG-20 — `finalize_upload` non atomique : double appel → double transcription puis re-dépôt](fixed/BUG-20-finalize-non-atomique.md) — Opus
- [BUG-21 — Le cleanup périodique peut détruire un slot pendant son `finalize` (ffmpeg)](fixed/BUG-21-cleanup-vs-finalize-race.md) — Opus
- [BUG-22 — `finalize_upload` bloque l'appel MCP pendant toute l'extraction ffmpeg et charge la vidéo en RAM](fixed/BUG-22-finalize-bloque-event-loop.md) — Fable
- [BUG-23 — `filters` jamais validés : `submit(mode=auto)` invalide bloque la requête en `discovering`](fixed/BUG-23-filters-non-valides.md) — Opus
- [BUG-24 — `get_corpus` : paramètre requis `caller` absent de la spec et falsifiable](fixed/BUG-24-get-corpus-caller.md) — Opus
- [BUG-25 — Curseur `get_corpus` : l'upsert peut reculer le curseur, `next_cursor` perdu en mode serveur](fixed/BUG-25-get-corpus-curseur.md) — Sonnet

### Mineures — acquisition / MCP
- [BUG-26 — `retry_failed` réinitialise l'item avant le check d'idempotence](fixed/BUG-26-retry-failed-ordre.md) — Sonnet
- [BUG-27 — `item_ids` non-UUID → erreur de transport au lieu de l'enveloppe `{"error"}`](fixed/BUG-27-item-ids-erreur-transport.md) — Sonnet
- [BUG-28 — `list_discovered` : `cursor` non numérique et `limit` négatif non validés](fixed/BUG-28-cursor-limit-non-valides.md) — Sonnet
- [BUG-29 — `item_done` sans `audio_s3_key` → item en `queued_transcription` sans job](fixed/BUG-29-item-done-sans-audio-key.md) — Sonnet
- [BUG-30 — Hosts YouTube/TikTok courants non reconnus (`m.`, `music.`, `vm.tiktok.com`)](fixed/BUG-30-platform-detection-hosts.md) — Sonnet

### Majeures/mineures — routes, auth, config
- [BUG-31 — POST /sources : aucune vérification de propriété → credentials d'un autre utilisateur](fixed/BUG-31-sources-sans-verif-propriete.md) — Sonnet
- [BUG-32 — POST /sources/{id}/items/select : non transactionnel, non idempotent, 500 FK](fixed/BUG-32-rest-select-non-atomique.md) — Opus
- [BUG-33 — Routes sources/items/scraping-jobs sans scoping user ni tenant : fuite cross-utilisateur](fixed/BUG-33-routes-sans-scoping.md) — Opus
- [BUG-34 — Façade MCP montée sans aucune authentification](fixed/BUG-34-mcp-sans-auth.md) — Opus
- [BUG-35 — Validation JWKS Keycloak bloquante dans l'event loop (urllib sync, timeout 30 s)](fixed/BUG-35-jwks-bloquant-event-loop.md) — Sonnet
- [BUG-36 — WebSocket /ws : déconnexion client jamais lue, exception de send ≠ WebSocketDisconnect](fixed/BUG-36-websocket-deconnexion.md) — Opus
- [BUG-37 — Enregistrement wallet : panne réseau Harpocrate renvoyée en 400 « token refusé »](fixed/BUG-37-register-wallet-400.md) — Sonnet
- [BUG-38 — Suppression secret/wallet non transactionnelle : 500 FK et destruction prématurée de la valeur](fixed/BUG-38-suppression-non-transactionnelle.md) — Sonnet
- [BUG-39 — CORS `allow_origins=["*"]` combiné à `allow_credentials=True`](fixed/BUG-39-cors-wildcard-credentials.md) — Sonnet
- [BUG-40 — `_claims_to_user` : `sub` non-UUID → 500 sur un token pourtant valide](fixed/BUG-40-sub-non-uuid-500.md) — Sonnet
- [BUG-41 — POST /api/auth/local-login : brute force illimité sur le compte admin](fixed/BUG-41-local-login-brute-force.md) — Sonnet

### Secrets Harpocrate
- [BUG-42 — `create()`/`create_placeholder()` n'appliquent pas `_normalize_name` (path-style)](fixed/BUG-42-create-sans-normalize.md) — Opus
- [BUG-43 — `HARPOCRATE_ALLOW_INSECURE=1` désactive aussi la vérification TLS des URLs https](fixed/BUG-43-allow-insecure-tls.md) — Sonnet
- [BUG-44 — Doublons dans la wordlist FR → biais d'entropie des passphrases](fixed/BUG-44-passphrase-wordlist-doublons.md) — Sonnet
- [BUG-45 — `get_bytes()` fait un round-trip UTF-8 et ne gère pas les données binaires annoncées](fixed/BUG-45-get-bytes-utf8.md) — Opus
- [BUG-46 — `get()` exige `encrypted_wallet_key` même quand la wallet_key est en cache](fixed/BUG-46-get-encrypted-wallet-key.md) — Sonnet
- [BUG-47 — Certificat TLS généré sans SAN ni KeyUsage/ExtendedKeyUsage](fixed/BUG-47-tls-sans-san.md) — Sonnet
- [BUG-48 — Secrets passés en argv de `docker run` (visibles via /proc et `docker inspect`)](fixed/BUG-48-secrets-en-argv-docker.md) — Opus

### Infra & config
- [BUG-49 — minio_client : endpoint `host:port` sans schéma mal parsé (host = numéro de port)](fixed/BUG-49-minio-endpoint-parse.md) — Sonnet
- [BUG-57 — `apply_migrations.sh` rejoue tout sans table de suivi : incompatible avec le runner intégré](fixed/BUG-57-apply-migrations-sans-suivi.md) — Sonnet
- [BUG-58 — `dev-deploy.sh` régénère les credentials sans invalider les volumes initialisés](BUG-58-dev-deploy-creds-volumes.md) — Opus
- [BUG-59 — `IMAGE_TAG` du `.env` lu par compose mais pas par `build.sh`](fixed/BUG-59-image-tag-build-vs-compose.md) — Sonnet
- [BUG-60 — `SCRAPER_IMAGE_TAG`/`WORKER_IMAGE_TAG` du `.env` silencieusement ignorés](fixed/BUG-60-scraper-worker-image-tag.md) — Sonnet
- [BUG-61 — `archive_v1_tables.sh` : une archive partielle bloque définitivement les runs suivants](fixed/BUG-61-archive-v1-partielle.md) — Sonnet
- [BUG-62 — Migration 0001 exige l'extension `vector` alors que la V2 l'a abandonnée](BUG-62-migration-0001-vector.md) — Opus

### Frontend (en sursis — vue admin minimale)
- [BUG-50 — Reconnexion WebSocket zombie après `disconnect()` + sockets dupliquées](BUG-50-ws-reconnexion-zombie.md) — Sonnet
- [BUG-51 — `NEXT_PUBLIC_API_URL` inliné au build : WS/API pointent sur localhost:8000 du client](BUG-51-next-public-api-url-build.md) — Opus
- [BUG-52 — `refreshToken` Keycloak exposé au JavaScript du navigateur via la session](BUG-52-refresh-token-expose.md) — Sonnet
- [BUG-53 — Aucun refresh de token : session 30 jours avec un accessToken expiré en minutes](BUG-53-pas-de-refresh-token.md) — Opus
- [BUG-54 — Le middleware redirige les appels API non authentifiés vers la page HTML de login](BUG-54-middleware-redirige-api.md) — Sonnet
- [BUG-55 — Timer de debounce de `KeySettings` jamais nettoyé au unmount](BUG-55-keysettings-timer.md) — Sonnet
- [BUG-56 — Échec du login local-admin sans aucun feedback](BUG-56-login-sans-feedback.md) — Sonnet

## Récapitulatif difficulté

| Difficulté | Nombre |
|---|---|
| Sonnet | 35 |
| Opus   | 21 |
| Fable  | 1  |

Total : 57 bugs confirmés (les doublons signalés par plusieurs agents ont été fusionnés).
