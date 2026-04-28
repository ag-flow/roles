"""Tests TDD pour services/agflow/role_json_builder.py."""

from __future__ import annotations

import json
from uuid import uuid4


def _make_doc(section: str, name: str) -> dict:
    return {"id": uuid4(), "section": section, "name": name, "content": f"# {name}"}


def test_build_role_json_dict_happy_path_three_sections() -> None:
    """build_role_json_dict avec 3 sections Role/Missions/Skills → ordre verrouillé + doc names."""
    from role_builder.services.agflow.role_json_builder import build_role_json_dict

    project = {
        "display_name": "Agent Test",
        "description": "Un agent de test",
        "identity": "Je suis un agent.",
        "language": "fr",
    }
    docs_by_section = {
        "Skills": [_make_doc("Skills", "skill_a"), _make_doc("Skills", "skill_b")],
        "Role": [_make_doc("Role", "role_doc")],
        "Missions": [_make_doc("Missions", "mission_1")],
    }

    result = build_role_json_dict(project, docs_by_section)

    assert result["display_name"] == "Agent Test"
    assert result["description"] == "Un agent de test"
    assert result["identity"] == "Je suis un agent."
    assert result["language"] == "fr"
    assert result["service_types"] == ["claude-code"]
    sections = result["sections"]
    # Ordre verrouillé : Role → Missions → Skills
    assert sections[0]["name"] == "Role"
    assert sections[1]["name"] == "Missions"
    assert sections[2]["name"] == "Skills"
    assert sections[0]["documents"] == ["role_doc"]
    assert sections[1]["documents"] == ["mission_1"]
    assert sections[2]["documents"] == ["skill_a", "skill_b"]


def test_build_role_json_dict_empty_section_omitted() -> None:
    """Section vide ou absente → omise dans sections."""
    from role_builder.services.agflow.role_json_builder import build_role_json_dict

    project = {"display_name": "Test", "identity": "Mon identité"}
    # Pas de Skills
    docs_by_section = {
        "Role": [_make_doc("Role", "doc1")],
        "Missions": [_make_doc("Missions", "m1")],
    }

    result = build_role_json_dict(project, docs_by_section)

    section_names = [s["name"] for s in result["sections"]]
    assert "Skills" not in section_names
    assert section_names == ["Role", "Missions"]


def test_build_role_json_dict_custom_section_after_locked() -> None:
    """Section custom → ajoutée après les locked, ordre alphabétique."""
    from role_builder.services.agflow.role_json_builder import build_role_json_dict

    project = {"display_name": "Test", "identity": "Identité"}
    docs_by_section = {
        "Role": [_make_doc("Role", "doc1")],
        "Missions": [_make_doc("Missions", "m1")],
        "Skills": [_make_doc("Skills", "s1")],
        "Zebra": [_make_doc("Zebra", "z1")],
        "Alpha": [_make_doc("Alpha", "a1")],
    }

    result = build_role_json_dict(project, docs_by_section)

    section_names = [s["name"] for s in result["sections"]]
    # Locked d'abord, puis custom alphabétique
    assert section_names[:3] == ["Role", "Missions", "Skills"]
    assert section_names[3:] == ["Alpha", "Zebra"]


def test_build_role_json_dict_language_null_defaults_to_fr() -> None:
    """language null en BDD → défaut 'fr'."""
    from role_builder.services.agflow.role_json_builder import build_role_json_dict

    project = {"display_name": "Test", "identity": "Identité", "language": None}
    docs_by_section = {"Role": [_make_doc("Role", "doc1")]}

    result = build_role_json_dict(project, docs_by_section)

    assert result["language"] == "fr"


def test_build_role_json_dict_description_null_returns_empty_string() -> None:
    """description null → empty string ''."""
    from role_builder.services.agflow.role_json_builder import build_role_json_dict

    project = {"display_name": "Test", "identity": "Identité", "description": None}
    docs_by_section = {"Role": [_make_doc("Role", "doc1")]}

    result = build_role_json_dict(project, docs_by_section)

    assert result["description"] == ""


def test_serialize_role_json_valid_json_non_ascii() -> None:
    """serialize_role_json produit du JSON valide avec accents préservés."""
    from role_builder.services.agflow.role_json_builder import serialize_role_json

    role_json = {
        "display_name": "Éclaireur",
        "description": "Rôle spécialisé en analyse",
        "identity": "Je suis un éclaireur.",
        "language": "fr",
        "service_types": ["claude-code"],
        "sections": [],
    }

    serialized = serialize_role_json(role_json)

    # Doit être du JSON valide
    parsed = json.loads(serialized)
    assert parsed["display_name"] == "Éclaireur"
    assert parsed["description"] == "Rôle spécialisé en analyse"
    # Accents préservés (ensure_ascii=False)
    assert "Éclaireur" in serialized
    assert "\\u" not in serialized
