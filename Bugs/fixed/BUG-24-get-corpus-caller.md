# BUG-24 — `get_corpus` : paramètre requis `caller` absent de la spec et falsifiable

- **Zone** : façade MCP / corpus
- **Fichier(s)** : `backend/src/role_builder/mcp_server/tools/corpus.py:17-24` ; spec `docs/specs/v2/01-protocole-mcp.md` §2.4 l.156
- **Sévérité** : majeure
- **Confiance** : haute
- **Difficulté de correction** : **Opus**

## Problème

La spec déclare `roles__get_corpus(request_key, only_new?, cursor?)` — le curseur `(request_key, caller)` est censé être géré côté stack. L'implémentation expose `caller: str` **requis** dans l'inputSchema (vérifié via `list_tools()` : `required: ['request_key', 'caller']`). De plus `caller` est purement déclaratif : n'importe quel appelant peut passer le `caller` d'un autre et **avancer son curseur** (le pull suivant de la victime en `only_new` perdra des documents).

## Scénario d'échec

Un pilote codé sur la spec appelle `get_corpus(request_key, only_new=true)` → erreur de validation Pydantic (champ manquant). Ou : agent B appelle `get_corpus(k, caller="claude-web")` → le vrai claude-web ne reçoit plus les items déposés entre-temps.

## Piste de résolution

Soit amender la spec (décision assumée d'identité déclarée, comme `submitted_by`), soit dériver `caller` de l'identité de session passerelle quand elle existera ; a minima documenter la divergence et rendre `caller` optionnel avec un défaut.

## Pourquoi Opus

L'alignement documentaire + le passage en optionnel sont simples, mais dériver une identité non-falsifiable dépend de la passerelle (chantier transverse) : la décision de conception est le vrai coût.

## ✅ Résolu (2026-07-06)

caller devient optionnel (défaut partagé) — conforme à la signature spec get_corpus(request_key, only_new?, cursor?). Identité non-falsifiable toujours en attente de l'identité passerelle (non inventée).

Vérifié : suite backend verte (481 passed).
