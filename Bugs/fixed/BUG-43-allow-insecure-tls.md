# BUG-43 — `HARPOCRATE_ALLOW_INSECURE=1` désactive aussi la vérification TLS des URLs https

- **Zone** : secrets Harpocrate / transport HTTP
- **Fichier(s)** : `backend/src/role_builder/secrets/harpocrate/http.py:68`
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`self._verify_tls = os.environ.get("HARPOCRATE_ALLOW_INSECURE", "0") != "1"` puis `httpx.request(..., verify=self._verify_tls)`. Le flag est documenté et pensé uniquement pour autoriser `http://` en dev (`_check_base_url`), mais il coupe en plus la validation des certificats pour **toutes** les requêtes, y compris vers une base `https://`.

## Scénario d'échec

Un opérateur pose `HARPOCRATE_ALLOW_INSECURE=1` pour tester un endpoint local en clair, tout en gardant une base `https://vault.yoops.org` réelle ailleurs : les connexions HTTPS acceptent alors silencieusement n'importe quel certificat → MITM possible sur le transport qui véhicule les tokens `hrpv_*` et les blobs chiffrés.

## Piste de résolution

Dissocier — garder `verify=True` par défaut même en mode insecure, et n'exiger `verify=False` que via un flag distinct explicite (`HARPOCRATE_TLS_NO_VERIFY`), ou ne désactiver la vérif que lorsque l'URL est effectivement `http://`.

## Pourquoi Sonnet

Découplage de deux conditions dans le constructeur.

## ✅ Résolu (2026-07-06)

La vérification TLS est pilotée par un flag dédié HARPOCRATE_TLS_NO_VERIFY ; HARPOCRATE_ALLOW_INSECURE ne touche plus la vérif des https.

Vérifié : suite backend verte (481 passed).
