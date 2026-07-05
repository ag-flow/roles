# 02 — Secrets & wallets self-service

> Chantier « clés Harpocrate self-service » (cadré 2026-07-05). Remplace le modèle
> « token Harpocrate global au boot » : chaque utilisateur gère ses wallets et ses
> secrets depuis l'UI. Migration `0009_user_wallets_secrets.sql` (additive).
> Complète : `00-fondations-v2.md` (modèle V2), `../vault.md` (client Harpocrate).

## 1. Principe

Au démarrage de l'application, **aucun wallet Harpocrate n'existe**. Harpocrate est
**optionnel** : l'application est pleinement fonctionnelle en stockage local chiffré.

Trois surfaces, dans l'ordre du parcours utilisateur :

1. **Page Wallets** (accessible à tout utilisateur authentifié, non réservée à
   l'admin) : enregistrer zéro, un ou plusieurs wallets Harpocrate.
2. **Page Secrets** : saisir des secrets **typés**, avec choix de la destination
   de stockage (local ou l'un des wallets).
3. **Définition de service** (ex. transcription Whisper) : on ne saisit plus de
   valeur — on **sélectionne un secret existant**, filtré par type.

L'indirection service → secret est le cœur du modèle : un service ne porte jamais
de valeur, seulement un `secret_id`. Rotation = remplacer le secret, sans toucher
aux services qui le référencent.

## 2. Modèle de données (migration 0009)

### `user_wallets`

| Champ | Rôle |
|---|---|
| `label` | Nom affiché du wallet |
| `api_token_encrypted` | Token `hrpv_1_*` chiffré (Fernet, `SECRET_ENCRYPTION_KEY`) |
| `api_url` | Défaut `https://vault.yoops.org` |
| `status` | `active` / `invalid` (token rejeté par Harpocrate) |

Index `(user_id, created_at)` : le tri chronologique sert la présélection UI
(« premier wallet »).

Le wallet est le seul secret qui ne peut pas être dans un wallet : son token est
un secret **local par construction**, chiffré avec la même clé d'instance que les
secrets locaux.

### `user_secrets`

| Champ | Rôle |
|---|---|
| `secret_type` | Enum : `openai-whisper`, `deepgram`, `assemblyai`, `speechmatics`, `youtube-cookies`, `instagram-cookies`, `tiktok-cookies` |
| `label` | Nom affiché |
| `storage` | `local` ou `wallet` |
| `value_encrypted` | Valeur chiffrée Fernet — **forme locale uniquement** |
| `wallet_id` + `wallet_path` | Référence Harpocrate — **forme wallet uniquement** |
| `status` | `active` / `invalid` |

**Contrainte de forme** (`user_secrets_storage_shape`) : exactement l'une des deux
formes — locale (`value_encrypted` non nul, pas de wallet) ou wallet (`wallet_id`
et `wallet_path` non nuls, pas de valeur en base). Un secret ne peut pas être les
deux, ni aucun des deux.

### Rattachement aux services

`user_transcription_keys.secret_id` et `user_credentials.secret_id` (FK
`ON DELETE RESTRICT`). Les colonnes legacy portant des valeurs sont invalidées
par la migration suivante (0010), une fois les routes basculées.

## 3. Chiffrement & modèle de menace

- **Clé d'instance `SECRET_ENCRYPTION_KEY`** : générée/réparée clé-par-clé par
  `dev-deploy.sh` dans `/data/.env` (contrat standard, doc 03 du corpus globals).
  Chiffrement **Fernet** (AES-128-CBC + HMAC) via `services/secret_cipher`.
- **Ce que protège le stockage local chiffré** : les dumps et backups de la base,
  la lecture directe des lignes SQL. **Ce qu'il ne protège pas** : un attaquant
  ayant accès à la machine (la clé vit à côté de la base). C'est un compromis
  assumé pour l'option locale ; Harpocrate (end-to-end, la clé de déchiffrement
  ne quitte pas le client) reste l'option recommandée pour les secrets sensibles.
- **Jamais de relecture** : aucune route ne renvoie une valeur en clair. Les
  listes exposent libellé, type, destination, statut. Seule action : **remplacer**.
- Aucune valeur ni token en log (redaction structlog standard du projet).

## 4. Parcours & règles UX

### Page Wallets

- Liste des wallets de l'utilisateur (label, URL, statut) + ajout (label, URL
  pré-remplie, token `hrpv_1_*`).
- À l'ajout : **validation du token** par un appel Harpocrate (liste ou lecture
  à vide) avant persistance ; token invalide → refus explicite.
- Suppression : refusée tant qu'un secret référence le wallet
  (`ON DELETE RESTRICT`) — message listant les secrets bloquants.

### Page Secrets

- Saisie : type (liste des `secret_type`), libellé, valeur, **destination**.
- **Présélection de la destination** :
  - aucun wallet enregistré → `local` présélectionné ;
  - au moins un wallet → **premier wallet** de la liste (ordre `created_at`)
    présélectionné. `local` reste toujours disponible dans la liste.
- À l'enregistrement :
  - `local` → chiffrement Fernet, écriture `value_encrypted` ;
  - `wallet` → écriture de la valeur **dans le wallet Harpocrate** (SDK, token du
    wallet déchiffré en RAM le temps de l'appel), persistance du seul
    `wallet_path` en base. Échec de l'écriture Harpocrate → rien n'est persisté
    (pas de secret « fantôme »).
- Suppression : refusée si un service référence le secret (RESTRICT) — message
  listant les services bloquants.

### Définition de service

- Le formulaire (ex. clé de transcription Whisper) présente une liste des secrets
  **actifs de l'utilisateur, filtrés par le type attendu** par le service.
- Aucune saisie de valeur à ce niveau. Un même secret est réutilisable par
  plusieurs services.

## 5. Résolution à l'usage

Quand un service a besoin de sa valeur (`services/secret_store`) :

- `storage=local` → déchiffrement Fernet de `value_encrypted` ;
- `storage=wallet` → déchiffrement du token du wallet, lecture Harpocrate de
  `wallet_path` via le SDK (déchiffrement AES-GCM local, cf. `../vault.md`).
- Échec de lecture wallet (token révoqué, chemin disparu) → le secret passe
  `status=invalid`, le service échoue avec une erreur actionnable (« ressaisir le
  secret X »), jamais de valeur vide silencieuse.
- La valeur en clair ne vit qu'en RAM, au point d'injection.

## 6. API (état implémenté)

| Route | Rôle |
|---|---|
| `GET /wallets` | Wallets de l'utilisateur (jamais le token) |
| `POST /wallets` | Ajout + validation du token |
| `DELETE /wallets/{id}` | Suppression (RESTRICT) |
| `GET /secrets` | Secrets de l'utilisateur (jamais la valeur) |
| `POST /secrets` | Création (local ou wallet selon destination) |
| `DELETE /secrets/{id}` | Suppression (RESTRICT) |

## 7. Reste à faire

- [ ] **Bascule des routes services** : sélection par `secret_id`, suppression de
      la saisie de valeur dans les formulaires de service.
- [ ] **Migration 0010** : invalidation des lignes legacy (`vault_secret_name`,
      valeurs portées par les services) après bascule.
- [ ] **Frontend** : pages Wallets et Secrets (aucune n'existe à ce jour),
      présélection de destination conforme au §4.
- [ ] **Remplacement de valeur** (action « remplacer » sans changer l'identité du
      secret ni ses références).
- [ ] *(second temps)* **Migration local → wallet** pour l'utilisateur qui ajoute
      un wallet après coup : déplacer un secret local vers un wallet (écriture
      Harpocrate + bascule de forme + purge de `value_encrypted`).
