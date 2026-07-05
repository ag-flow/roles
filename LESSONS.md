# Leçons

- [git] Ne jamais `git stash -u` sur cet arbre (travail V2 massif non commité) pour tester une baseline : `uv run` régénère `uv.lock` pendant l'état stashé et le `pop` conflicte (restauration délicate). Comparer via `git worktree add` ou `git show HEAD:fichier`.
- [tests] Ne jamais `importlib.reload()` un module sous settings monkeypatchés : l'état rechargé survit au test et pollue les suivants (cause de l'ex-flake test_me_route, corrigée le 2026-07-05 en rendant le user stub disable_auth paresseux).
- [tests] Un conftest qui définit des helpers avec un paramètre nommé `pool` masque la fixture `pool` importée (ruff F811) — mettre les helpers dans un module séparé (`helpers.py`).
