# BUG-44 — Doublons dans la wordlist FR → biais d'entropie des passphrases

- **Zone** : secrets Harpocrate / générateurs
- **Fichier(s)** : `backend/src/role_builder/secrets/harpocrate/generators/passphrase_gen.py:56` (données : `generators/wordlists/fr.txt`)
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

`secrets.choice(wordlist)` est appelé sur la liste brute lue du fichier. `fr.txt` contient 325 lignes mais seulement 323 mots uniques (`carton` et `tomber` apparaissent deux fois). Les mots dupliqués ont une probabilité de sélection doublée, ce qui biaise la distribution et réduit légèrement l'entropie réelle par rapport à la valeur annoncée dans le module.

## Scénario d'échec

Génération d'une passphrase `language="fr"` : distribution non uniforme, entropie par mot < `log2(323)`. Impact marginal mais réel pour un générateur de secret.

## Piste de résolution

Dédupliquer à la lecture (`sorted(set(...))`) ou nettoyer `fr.txt`. Idéalement passer à la wordlist EFF complète comme le note déjà le docstring.

## Pourquoi Sonnet

Déduplication à la lecture, une ligne.

## ✅ Résolu (2026-07-06)

Wordlist dédupliquée à la lecture (dict.fromkeys) : distribution uniforme, entropie = log2(N).

Vérifié : suite backend verte (481 passed).
