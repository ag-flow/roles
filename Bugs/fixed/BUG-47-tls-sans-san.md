# BUG-47 — Certificat TLS généré sans SAN ni KeyUsage/ExtendedKeyUsage

- **Zone** : secrets Harpocrate / générateurs
- **Fichier(s)** : `backend/src/role_builder/secrets/harpocrate/generators/tls_certificate_gen.py:88`
- **Sévérité** : mineure
- **Confiance** : moyenne
- **Difficulté de correction** : **Sonnet**

## Problème

Si `subject_alt_names` est vide, aucune extension SAN n'est ajoutée (bloc conditionnel `if san_list`), et le certificat n'a ni `KeyUsage` ni `ExtendedKeyUsage(serverAuth)`. Les stacks TLS modernes (Go, navigateurs, nombreuses libs) rejettent un certificat serveur sans SAN, même pour du chiffrement interne — l'usage documenté (« chiffrement interne entre services ») échouera à la vérification.

## Scénario d'échec

Descripteur `{"type":"tls_certificate","common_name":"svc.internal"}` sans SAN → cert émis mais refusé par le client TLS (« x509: certificate relies on legacy Common Name field »).

## Piste de résolution

Injecter automatiquement un SAN DNS égal au CN lorsque la liste est vide, et ajouter les extensions `KeyUsage`/`ExtendedKeyUsage` appropriées.

## Pourquoi Sonnet

Ajout d'extensions x509 standard avec `cryptography`.

## ✅ Résolu (2026-07-06)

SAN DNS = CN par défaut si liste vide + extensions KeyUsage et ExtendedKeyUsage(serverAuth/clientAuth).

Vérifié : suite backend verte (481 passed).
