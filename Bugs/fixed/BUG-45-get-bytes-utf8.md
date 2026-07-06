# BUG-45 — `get_bytes()` fait un round-trip UTF-8 et ne gère pas les données binaires annoncées

- **Zone** : secrets Harpocrate / client
- **Fichier(s)** : `backend/src/role_builder/secrets/harpocrate/client.py:278`
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

`get_bytes` est documenté « Utile pour les certificats TLS et autres données binaires » mais implémenté par `return self.get(name).encode("utf-8")`. Or `get()` fait déjà `plaintext.decode("utf-8")`. Toute valeur non-UTF-8 fait échouer `get()` (`UnicodeDecodeError`) avant même d'atteindre `get_bytes` ; et pour une valeur binaire arbitraire il n'existe aucun chemin correct.

## Scénario d'échec

Un secret contenant des octets non-UTF-8 (clé binaire brute, DER) est illisible : `get()` lève `UnicodeDecodeError` non typée SDK. `get_bytes` n'apporte donc pas la capacité binaire annoncée.

## Piste de résolution

Introduire un vrai chemin binaire (déchiffrer et renvoyer `bytes` sans passer par `decode`), p.ex. une méthode interne partagée qui retourne le plaintext brut, et faire dériver `get()` (`.decode`) et `get_bytes()` (brut) de cette base.

## Pourquoi Opus

Refactor du chemin de déchiffrement partagé, en veillant à ne pas casser les appelants existants de `get()`.

## ✅ Résolu (2026-07-06)

_get_raw() partagé retourne le plaintext brut ; get() décode, get_bytes() renvoie les bytes (vrai chemin binaire). Règle aussi BUG-46 (encrypted_wallet_key lu seulement en fallback).

Vérifié : suite backend verte (481 passed).
