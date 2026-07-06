# BUG-61 — `archive_v1_tables.sh` : une archive partielle bloque définitivement les runs suivants

- **Zone** : infra / scripts
- **Fichier(s)** : `scripts/archive_v1_tables.sh:44-56` (skip si fichier présent) et `:38-47` (`pg_dump | gzip > "$OUT_FILE"`)
- **Sévérité** : mineure
- **Confiance** : haute
- **Difficulté de correction** : **Sonnet**

## Problème

La redirection `> "$OUT_FILE"` crée le fichier avant que le pipeline réussisse. Si `pg_dump` échoue (mauvais `DATABASE_URL`, table déjà droppée, coupure), `set -euo pipefail` interrompt le script mais laisse un `.gz` tronqué/vide. Au run suivant, le test `[ -f "$OUT_FILE" ]` saute le dump et `gzip -t` échoue → `exit` sec sans le message « REFUS » ni indication de supprimer le fichier ; le garde-fou pré-0006 devient un mur.

## Scénario d'échec

Premier lancement avec `DATABASE_URL` erroné → fichier vide créé → correction de l'URL → relance : « Archive déjà présente… Vérification… » puis échec `gzip -t` inexpliqué ; l'opérateur peut croire l'archive faite.

## Piste de résolution

Dumper vers `"$OUT_FILE.tmp"` puis `mv` atomique après `gzip -t`, et/ou `trap 'rm -f "$OUT_FILE.tmp"' ERR`.

## Pourquoi Sonnet

Écriture atomique via fichier temporaire + trap.

## ✅ Résolu (2026-07-06)

archive_v1_tables.sh : dump vers .tmp, gzip -t de validation, puis mv atomique ; trap de nettoyage. Un pg_dump échoué ne laisse plus d'archive tronquée.

(Correction shell/compose, non couverte par la suite pytest.)
