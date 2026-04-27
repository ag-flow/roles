# 07 — Onglet "Ma stack" : configuration utilisateur

> Sprint 6 : config user. À l'issue de ce sprint, l'utilisateur peut
> configurer ses comptes réseaux sociaux, ses clés SaaS de transcription,
> son secret Mistral ag.flow, ses quotas et garde-fous, et voir le statut
> de chaque clé en temps réel.

## Objectif du sprint

- Onglet "Ma stack" complet avec 4 sous-onglets
- CRUD pour les credentials cookies (déjà partiellement fait dans § 03)
- CRUD pour les clés SaaS de transcription
- Lien vers ag.flow pour la clé Mistral
- Quotas mensuels et alertes
- Monitoring du crédit restant (polling + détection à l'usage)

## Modèle conceptuel

L'onglet "Ma stack" centralise toute la configuration personnelle de
l'utilisateur. C'est ici qu'il déclare ses comptes externes, ses clés API,
et ses préférences de pipeline.

Les 4 sous-onglets :

1. **Comptes réseaux sociaux** — cookies pour le scraping (YouTube,
   Instagram, TikTok)
2. **Services de transcription** — clés SaaS (Deepgram, AssemblyAI, OpenAI
   Whisper, Speechmatics)
3. **Mistral pour la synthèse** — référence au secret ag.flow
4. **Quotas et garde-fous** — caps mensuels, alertes

## Sous-onglet 1 : Comptes réseaux sociaux

### Fonctionnalités

Pour chaque plateforme supportée (YouTube, Instagram, TikTok) :

- Bouton "Ajouter un compte" avec guide d'export des cookies
- Liste des comptes configurés avec :
  - Nom personnalisable (ex: "Compte perso", "Compte pro")
  - Statut : `active` | `expired` | `invalid` | `revoked`
  - Date de dernière validation
  - Bouton "Tester maintenant" (lance un appel API simple)
  - Bouton "Révoquer"

### Format des cookies

- **YouTube** : cookies exportés du navigateur (format Netscape `cookies.txt`)
- **Instagram** : cookies de session exportés du navigateur
- **TikTok** : cookies exportés du navigateur

### UX d'ajout

Modal avec :
1. Sélecteur de plateforme
2. Champ libellé (ex: "Compte perso")
3. Zone d'upload du fichier `cookies.txt` (drag & drop)
4. Mini-guide visuel : "Comment exporter mes cookies ?" avec lien vers une
   doc qui explique l'utilisation d'extensions comme "Get cookies.txt"

### Test de validité

À la création et au clic sur "Tester maintenant", l'application lance un
appel test au scraper :

- Pour YouTube : tenter de récupérer les métadonnées d'une vidéo publique
  triviale (ex: vidéo "Me at the zoo")
- Pour Instagram : récupérer le profil public d'un compte connu
- Pour TikTok : idem

Si l'appel réussit → `status = active`, `last_validated_at = now()`.
Si 401/403 → `status = invalid`.
Si timeout → ne change pas le statut, juste log.

### Stockage

- Cookies bruts : OpenBao path
  `secret/scraping-credentials/{tenant_id}/{platform}/{credential_id}`
- Métadonnées : table `user_credentials` (cf. § 01)

### Endpoints API

```python
# backend/src/role_builder/routes/credentials.py

@router.get("/credentials")
async def list_credentials(
    platform: str | None = None,
) -> list[UserCredentialOut]:
    """List user's credentials, optionally filtered by platform."""
    ...


@router.post("/credentials")
async def create_credential(body: CreateCredentialRequest) -> UserCredentialOut:
    """Upload cookies for a platform.

    Body:
      - platform: youtube|instagram|tiktok
      - label: str
      - cookies_b64: base64 of cookies.txt
    """
    # 1. Test validity
    is_valid = await scraper_test.validate_cookies(body.platform, body.cookies_b64)
    if not is_valid:
        raise HTTPException(400, "Invalid cookies")

    # 2. Store in OpenBao
    cred_id = uuid4()
    openbao_path = f"scraping-credentials/{tenant_id}/{body.platform}/{cred_id}"
    await openbao.put(openbao_path, {"cookies": body.cookies_b64})

    # 3. Insert metadata
    await db.insert_user_credential(
        id=cred_id,
        tenant_id=tenant_id,
        user_id=user_id,
        platform=body.platform,
        label=body.label,
        openbao_path=openbao_path,
        status="active",
        last_validated_at=datetime.utcnow(),
    )
    return UserCredentialOut(...)


@router.post("/credentials/{cred_id}/test")
async def test_credential(cred_id: UUID) -> dict:
    """Re-validate a credential."""
    ...


@router.delete("/credentials/{cred_id}")
async def revoke_credential(cred_id: UUID) -> None:
    """Mark as revoked + delete from OpenBao."""
    ...
```

## Sous-onglet 2 : Services de transcription

### Fonctionnalités

Pour chaque provider SaaS supporté :

- Champ saisie de la clé API
- Test de validité immédiat (appel API trivial)
- Statut : `active` | `low` | `exhausted` | `invalid`
- Affichage du crédit restant (si le provider l'expose)
- **Slider "Nombre de containers" (1 à 5)** — défaut : 1
- Toggle "Provider primaire" (un seul à la fois)
- Toggle "Activer en fallback" (plusieurs possibles)

**Si aucune clé n'est active :** message indiquant que les transcriptions
utiliseront le pool shared (faster-whisper local) avec une queue partagée.

### Stockage

- Clés brutes : OpenBao path
  `secret/transcription-keys/{tenant_id}/{provider}/{key_id}`
- Métadonnées : table `user_transcription_keys` (cf. § 01)

### Test de validité par provider

| Provider | Test trivial |
|----------|--------------|
| OpenAI Whisper | `GET /v1/models` (vérifie que la clé permet l'accès) |
| Deepgram | `GET /v1/projects` |
| AssemblyAI | `GET /v2/transcript` (limite=1) |
| Speechmatics | `GET /v2/jobs` |

### Endpoints API

```python
@router.get("/transcription-keys")
async def list_transcription_keys() -> list[TranscriptionKeyOut]:
    """List the user's transcription keys with status."""
    ...


@router.post("/transcription-keys")
async def create_transcription_key(body: CreateTranscriptionKeyRequest) -> TranscriptionKeyOut:
    """Add a new SaaS transcription key.

    Body:
      - provider: deepgram|assemblyai|openai-whisper|speechmatics
      - label: str
      - api_key: str
      - workers_count: int (1..5)
      - is_primary: bool
      - is_fallback: bool
    """
    # 1. Validate the key by calling the provider
    is_valid = await transcription_test.validate_key(body.provider, body.api_key)
    if not is_valid:
        raise HTTPException(400, "Invalid API key")

    # 2. Store in OpenBao
    key_id = uuid4()
    path = f"transcription-keys/{tenant_id}/{body.provider}/{key_id}"
    await openbao.put(path, {"api_key": body.api_key})

    # 3. If is_primary=True, ensure no other primary
    if body.is_primary:
        await db.unset_other_primary(user_id)

    # 4. Insert metadata
    await db.insert_transcription_key(
        id=key_id,
        tenant_id=tenant_id,
        user_id=user_id,
        provider=body.provider,
        label=body.label,
        openbao_path=path,
        status="active",
        is_primary=body.is_primary,
        is_fallback=body.is_fallback,
        workers_count=body.workers_count,
        last_validated_at=datetime.utcnow(),
    )

    # 5. Trigger worker provisioning if needed
    await worker_manager.ensure_user_workers_running(user_id)

    return TranscriptionKeyOut(...)


@router.patch("/transcription-keys/{key_id}")
async def update_transcription_key(key_id: UUID, body: UpdateTranscriptionKeyRequest) -> TranscriptionKeyOut:
    """Update settings (workers_count, is_primary, etc.)."""
    ...


@router.post("/transcription-keys/{key_id}/test")
async def test_transcription_key(key_id: UUID) -> dict:
    """Re-validate the key + check balance if available."""
    ...


@router.delete("/transcription-keys/{key_id}")
async def revoke_transcription_key(key_id: UUID) -> None:
    """Revoke a key. Stops associated workers."""
    # 1. Stop workers using this key
    await worker_manager.stop_workers_for_key(key_id)

    # 2. Reassign user's pending jobs to shared if no other key active
    await db.maybe_reassign_pending_jobs_to_shared(user_id)

    # 3. Delete from OpenBao
    await openbao.delete(key.openbao_path)

    # 4. Remove from DB
    await db.delete_transcription_key(key_id)
```

## Sous-onglet 3 : Mistral pour la synthèse

### Modèle conceptuel

**Décision :** la clé Mistral n'est pas gérée par cette application. Elle
est stockée dans le coffre de secrets d'**ag.flow**.

L'application stocke uniquement une **référence** à l'identifiant du secret
ag.flow dans la table `role_projects` (champ `mistral_secret_ref`).

### Fonctionnalités

- Champ "Identifiant du secret Mistral dans ag.flow" (ex: `mistral-prod-key`)
- Bouton "Vérifier" qui appelle `GET /api/admin/secrets` sur ag.flow et
  vérifie que le secret existe
- Statut : `configured` | `not-found` | `not-configured`
- Lien direct vers l'admin ag.flow pour configurer le secret si besoin

### Pas de gestion côté Role Builder

- Pas de champ pour saisir la clé en clair
- Pas de stockage local
- Pas de monitoring de crédit Mistral (à voir côté ag.flow)

### Endpoints API

```python
@router.get("/role-projects/{project_id}/mistral-config")
async def get_mistral_config(project_id: UUID) -> dict:
    """Get the current Mistral secret reference for this project."""
    project = await db.get_role_project(project_id)
    return {
        "secret_ref": project.mistral_secret_ref,
        "status": await check_mistral_secret_exists(project.mistral_secret_ref),
    }


@router.put("/role-projects/{project_id}/mistral-config")
async def set_mistral_config(project_id: UUID, body: dict) -> dict:
    """Set the Mistral secret reference."""
    secret_ref = body["secret_ref"]
    # Verify the secret exists in ag.flow
    if not await check_mistral_secret_exists(secret_ref):
        raise HTTPException(400, "Secret not found in ag.flow")

    await db.update_role_project(
        project_id=project_id,
        mistral_secret_ref=secret_ref,
    )
    return {"status": "configured"}


async def check_mistral_secret_exists(secret_ref: str | None) -> str:
    """Check the status of the Mistral secret in ag.flow."""
    if not secret_ref:
        return "not-configured"

    # GET /api/admin/secrets on ag.flow, check if secret_ref is in the list
    ...
```

## Sous-onglet 4 : Quotas et garde-fous

### Fonctionnalités

Pour chaque clé SaaS active :

- **Cap mensuel** : "ne pas dépasser X$ par mois sur Deepgram"
- **Alertes** : email à 50%, 80%, 95% du cap atteint
- **Action au cap atteint** :
  - Pause des workers user de ce provider
  - Bascule des jobs en attente vers le pool shared
  - Notification utilisateur

### Estimation pré-job

Avant de lancer une transcription chère, l'application **estime le coût** :

```
coût_estimé = durée_audio_min × prix_par_min(provider)
```

Et :
- L'affiche dans l'UI en temps réel (badge "$X estimé" sur les jobs en attente)
- Refuse de lancer si ça dépasse le crédit estimé restant
- Avertit si ça dépasse le cap mensuel configuré
- Permet à l'utilisateur de basculer manuellement sur un autre provider ou
  sur le pool shared

### Tracking du spend mensuel

Champ `current_month_spend_usd` sur `user_transcription_keys`.

- Incrémenté à chaque transcription réussie
- Reset le 1er de chaque mois (job cron)
- Comparaison avec `monthly_cap_usd` à chaque incrément

### Endpoints API

```python
@router.patch("/transcription-keys/{key_id}/quota")
async def update_quota(key_id: UUID, body: UpdateQuotaRequest) -> dict:
    """Update monthly cap and alerts."""
    # body: {"monthly_cap_usd": 50.0, "alert_at_pct": [50, 80, 95]}
    ...


@router.get("/transcription-keys/{key_id}/usage")
async def get_usage(key_id: UUID) -> dict:
    """Get current month usage stats."""
    ...
```

## Monitoring du crédit restant

### Stratégie hybride

**Polling proactif** (quand le provider l'expose) :

Worker dédié qui tourne toutes les heures :

```python
# backend/src/role_builder/services/credit_monitor.py
async def poll_credit_balances() -> None:
    """Poll remaining credit for all active keys that support balance API."""
    keys = await db.list_active_keys_with_balance_support()

    for key in keys:
        try:
            api_key = await openbao.get(key.openbao_path)
            provider = build_provider(key.provider, api_key=api_key["api_key"])
            credit = await provider.get_remaining_credit()

            if credit is None:
                continue

            await db.update_key_balance(
                key_id=key.id,
                balance=credit.balance_usd,
                checked_at=datetime.utcnow(),
            )

            # Trigger alerts if threshold crossed
            await alerting.check_balance_thresholds(key, credit.balance_usd)
        except Exception as exc:
            log.error("balance_poll_failed", key_id=str(key.id), exc_info=exc)


# Lancé via APScheduler ou cron interne
```

Providers qui exposent une balance API :
- **Deepgram** : oui (`GET /v1/projects/{project_id}/balance`)
- **AssemblyAI** : non
- **OpenAI** : partiel via `/v1/usage`
- **Speechmatics** : limité

**Détection à l'usage** (universelle) :

Le worker de transcription intercepte les erreurs API et les classifie
(cf. § 04 module `error_classifier`).

### Quand un crédit est détecté épuisé

1. Clé marquée `exhausted` en base
2. Workers user de ce provider mis en pause (containers stoppés)
3. Jobs en attente du user pour ce provider basculent vers le pool shared
4. Notification immédiate (UI + email)
5. Affichage rouge dans "Ma stack" avec lien vers le dashboard du provider

### Service de notification

```python
# backend/src/role_builder/services/notifications.py
async def notify_user_credit_exhausted(user_id: UUID, key: UserTranscriptionKey) -> None:
    """Send notifications when a key is exhausted."""
    # 1. WebSocket push (déjà fait via PG NOTIFY)
    # 2. Email
    user = await db.get_user(user_id)
    await email.send(
        to=user.email,
        subject=f"[Role Builder] Crédit épuisé sur {key.provider}",
        body=f"""Bonjour,

Votre clé {key.provider} ({key.label}) n'a plus de crédit. Vos transcriptions
en attente ont été automatiquement basculées sur le pool partagé.

Pour réactiver votre provider, rechargez votre compte chez {key.provider}
et revenez dans Role Builder pour réactiver la clé.

Lien direct : {settings.app_base_url}/my-stack/transcription
""",
    )
```

## UI : structure des composants

```
frontend/src/app/my-stack/
├── page.tsx                          # tabs container
├── social-accounts/
│   ├── page.tsx
│   ├── AccountsList.tsx
│   ├── AddAccountModal.tsx
│   └── CookiesGuide.tsx
├── transcription-services/
│   ├── page.tsx
│   ├── KeysList.tsx
│   ├── AddKeyModal.tsx
│   ├── KeySettings.tsx               # workers_count slider, primary toggle
│   └── BalanceBadge.tsx
├── mistral-config/
│   ├── page.tsx
│   └── ConfigForm.tsx
└── quotas/
    ├── page.tsx
    ├── QuotaForm.tsx
    └── UsageChart.tsx
```

## Cron jobs à mettre en place

| Job | Fréquence | Description |
|-----|-----------|-------------|
| `poll_credit_balances` | toutes les heures | Cf. ci-dessus |
| `reset_monthly_spend` | 1er de chaque mois 00:00 UTC | `current_month_spend_usd = 0` |
| `cleanup_revoked_secrets` | quotidien | Supprime de OpenBao les secrets liés à des credentials révoqués depuis > 7 jours |

Implémenter via APScheduler dans le backend FastAPI :

```python
# backend/src/role_builder/services/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_credit_balances, "interval", hours=1)
    scheduler.add_job(reset_monthly_spend, "cron", day=1, hour=0, minute=0)
    scheduler.add_job(cleanup_revoked_secrets, "cron", hour=3)
    return scheduler
```

Lancé au startup de FastAPI dans le `lifespan`.

## Critères de fin de sprint

- [ ] CRUD complet pour les credentials cookies, avec test de validité
- [ ] CRUD complet pour les clés SaaS de transcription, avec test
- [ ] Provisioning automatique des workers user à la création/modification
      d'une clé primaire
- [ ] Suppression d'une clé stoppe les workers et bascule les jobs en
      attente
- [ ] Configuration de la référence Mistral ag.flow avec validation
- [ ] Quotas mensuels configurables, alertes email à 50/80/95%
- [ ] Polling Deepgram fonctionne, balance affichée en temps réel
- [ ] Détection à l'usage testée : on simule un 402, la clé passe à
      `exhausted`, les workers s'arrêtent
- [ ] Cron `reset_monthly_spend` testé manuellement (déclencher en local)

## TODO du fichier (à trancher pendant l'implémentation)

- [ ] UX d'export des cookies : on documente avec captures d'écran ou on
      fournit une extension navigateur dédiée ?
- [ ] Service email : SMTP local, SendGrid, Mailgun, Postmark ? Choix à
      faire selon ce que Beard a en homelab
- [ ] Détection a posteriori du quota mensuel atteint : si on calcule
      `current_month_spend_usd` au fil de l'eau, est-ce qu'on passe la clé
      en `exhausted` automatiquement ou on attend le prochain `429 quota` ?
- [ ] Support de l'OAuth pour les providers qui le permettent (peu pour la
      transcription, mais à anticiper) ? Pour le MVP, juste API keys.
- [ ] Format précis des `error_history` sur `transcription_jobs` : on
      garde combien d'entrées max ?

---

**Document précédent :** `06-synthesis.md`
**Document suivant :** `08-export-agflow.md`
