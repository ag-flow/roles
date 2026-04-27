"""Tests pour synthesis.prompts_seed — idempotent seed des 5 prompts système."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubPool:
    """Pool stub minimaliste pour les tests de prompts_seed (pas d'appels directs)."""

    pass


async def test_first_run_creates_all_5_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Première exécution : 5 actions 'created' (aucune version existante)."""
    import role_builder.synthesis.prompts_seed as mod

    prompt_id = uuid4()
    version_id = uuid4()

    async def fake_upsert_prompt(**kwargs: Any) -> Any:
        return prompt_id

    async def fake_get_system_default_version(name: str, *, pool: Any) -> None:
        return None  # Pas de version existante

    async def fake_list_versions(pid: Any, *, pool: Any) -> list[Any]:
        return []  # Aucune version existante → next=1

    async def fake_insert_prompt_version(**kwargs: Any) -> Any:
        return version_id

    monkeypatch.setattr(mod.prompts_helper, "upsert_prompt", fake_upsert_prompt)
    monkeypatch.setattr(
        mod.prompts_helper, "get_system_default_version", fake_get_system_default_version
    )
    monkeypatch.setattr(mod.prompts_helper, "list_versions", fake_list_versions)
    monkeypatch.setattr(mod.prompts_helper, "insert_prompt_version", fake_insert_prompt_version)

    actions = await mod.seed_system_prompts(_StubPool())  # type: ignore[arg-type]

    assert len(actions) == 5
    assert all(v == "created" for v in actions.values())
    expected_names = {
        "extractor",
        "clusterer",
        "decomposer",
        "document_writer",
        "identity_synthesizer",
    }
    assert set(actions.keys()) == expected_names


async def test_second_run_unchanged_when_templates_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deuxième exécution sans modification : 5 actions 'unchanged'."""
    import role_builder.synthesis.prompts_seed as mod

    prompt_id = uuid4()

    async def fake_upsert_prompt(**kwargs: Any) -> Any:
        return prompt_id

    # Simuler que la version existante correspond au template actuel.
    # On lit le fichier réel pour obtenir le bon contenu.
    from pathlib import Path

    templates_dir = Path(mod.__file__).parent / "templates"

    async def fake_get_system_default_version(name: str, *, pool: Any) -> dict[str, Any]:
        # Trouver le template_file correspondant à ce nom
        defn = next(d for d in mod.SEED_DEFINITIONS if d["name"] == name)
        template_content = (templates_dir / str(defn["template_file"])).read_text(encoding="utf-8")
        return {"id": uuid4(), "template": template_content, "prompt_name": name}

    async def fake_list_versions(pid: Any, *, pool: Any) -> list[Any]:
        return [{"version_number": 1}]

    async def fake_insert_prompt_version(**kwargs: Any) -> Any:
        return uuid4()

    monkeypatch.setattr(mod.prompts_helper, "upsert_prompt", fake_upsert_prompt)
    monkeypatch.setattr(
        mod.prompts_helper, "get_system_default_version", fake_get_system_default_version
    )
    monkeypatch.setattr(mod.prompts_helper, "list_versions", fake_list_versions)
    monkeypatch.setattr(mod.prompts_helper, "insert_prompt_version", fake_insert_prompt_version)

    actions = await mod.seed_system_prompts(_StubPool())  # type: ignore[arg-type]

    assert len(actions) == 5
    assert all(v == "unchanged" for v in actions.values())


async def test_modified_template_creates_new_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si le template a changé pour un prompt, action = 'version_added'."""
    import role_builder.synthesis.prompts_seed as mod

    extractor_id = uuid4()
    other_id = uuid4()
    inserted_calls: list[dict[str, Any]] = []

    async def fake_upsert_prompt(**kwargs: Any) -> Any:
        # extractor obtient extractor_id, les autres obtiennent other_id
        if kwargs["name"] == "extractor":
            return extractor_id
        return other_id

    async def fake_get_system_default_version(name: str, *, pool: Any) -> dict[str, Any] | None:
        # Simule un template différent pour 'extractor', None pour les autres
        if name == "extractor":
            return {"id": uuid4(), "template": "ANCIEN TEMPLATE", "prompt_name": name}
        return None

    async def fake_list_versions(pid: Any, *, pool: Any) -> list[Any]:
        # extractor a déjà une version → next=2
        # les autres n'en ont pas → action='created'
        if pid == extractor_id:
            return [{"version_number": 1}]
        return []

    async def fake_insert_prompt_version(**kwargs: Any) -> Any:
        inserted_calls.append(dict(kwargs))
        return uuid4()

    monkeypatch.setattr(mod.prompts_helper, "upsert_prompt", fake_upsert_prompt)
    monkeypatch.setattr(
        mod.prompts_helper, "get_system_default_version", fake_get_system_default_version
    )
    monkeypatch.setattr(mod.prompts_helper, "list_versions", fake_list_versions)
    monkeypatch.setattr(mod.prompts_helper, "insert_prompt_version", fake_insert_prompt_version)

    actions = await mod.seed_system_prompts(_StubPool())  # type: ignore[arg-type]

    # extractor → version_added (template modifié, version existante)
    assert actions["extractor"] == "version_added"
    # Les 4 autres → created (get_system_default_version retourne None + list_versions=[])
    for name in ("clusterer", "decomposer", "document_writer", "identity_synthesizer"):
        assert actions[name] == "created", f"{name} should be 'created'"

    # Vérifier que is_system_default=True est bien passé à insert_prompt_version
    for call in inserted_calls:
        assert call["is_system_default"] is True

    # Vérifier que la version d'extractor est bien 2 (max=1, next=2)
    extractor_calls = [c for c in inserted_calls if c["prompt_id"] == extractor_id]
    assert len(extractor_calls) == 1
    assert extractor_calls[0]["version_number"] == 2
