"""Réexporte la fixture `pool` (Postgres éphémère, schéma complet) pour les
tests du lot dépôt. Les helpers de peuplement vivent dans `helpers.py` (un
conftest qui définit des fonctions prenant un paramètre `pool` masquerait la
fixture importée — F811).
"""

from __future__ import annotations

from tests.services.acquisition.conftest import pool  # noqa: F401
