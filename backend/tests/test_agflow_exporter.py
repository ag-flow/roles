"""Tests TDD pour services/agflow/exporter.py."""

from __future__ import annotations

import io
import json
import zipfile
from uuid import uuid4


def _make_doc(section: str, name: str, content: str = "# contenu") -> dict:
    return {"id": uuid4(), "section": section, "name": name, "content": content}


def _make_project(**overrides) -> dict:
    base = {
        "display_name": "Agent Éditeur",
        "description": "Agent de rédaction",
        "identity": "Je suis un agent spécialisé.",
        "language": "fr",
    }
    base.update(overrides)
    return base


def test_build_role_zip_happy_path() -> None:
    """Happy path : ZIP contient role.json + 6 fichiers .md dans 3 dossiers."""
    from role_builder.services.agflow.exporter import build_role_zip

    project = _make_project()
    docs_by_section = {
        "Role": [_make_doc("Role", "doc_a"), _make_doc("Role", "doc_b")],
        "Missions": [_make_doc("Missions", "mission_1"), _make_doc("Missions", "mission_2")],
        "Skills": [_make_doc("Skills", "skill_x"), _make_doc("Skills", "skill_y")],
    }

    result = build_role_zip(project, docs_by_section)

    assert len(result.zip_bytes) > 0
    assert result.documents_count == 6

    with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "role.json" in names
        assert "section_role/doc_a.md" in names
        assert "section_role/doc_b.md" in names
        assert "section_missions/mission_1.md" in names
        assert "section_missions/mission_2.md" in names
        assert "section_skills/skill_x.md" in names
        assert "section_skills/skill_y.md" in names


def test_build_role_zip_identity_null_raises() -> None:
    """identity null → ValueError 'identity not generated yet'."""
    from role_builder.services.agflow.exporter import build_role_zip

    project = _make_project(identity=None)
    docs_by_section = {"Role": [_make_doc("Role", "doc1")]}

    import pytest

    with pytest.raises(ValueError, match="identity not generated yet"):
        build_role_zip(project, docs_by_section)


def test_build_role_zip_identity_whitespace_raises() -> None:
    """identity whitespace uniquement → ValueError."""
    from role_builder.services.agflow.exporter import build_role_zip

    project = _make_project(identity="   ")
    docs_by_section = {"Role": [_make_doc("Role", "doc1")]}

    import pytest

    with pytest.raises(ValueError, match="identity not generated yet"):
        build_role_zip(project, docs_by_section)


def test_build_role_zip_no_docs_raises() -> None:
    """docs_by_section vide → ValueError."""
    from role_builder.services.agflow.exporter import build_role_zip

    project = _make_project()

    import pytest

    with pytest.raises(ValueError, match="no current documents to export"):
        build_role_zip(project, {})


def test_build_role_zip_role_json_valid() -> None:
    """role.json dans le ZIP est du JSON valide avec les bonnes keys."""
    from role_builder.services.agflow.exporter import build_role_zip

    project = _make_project()
    docs_by_section = {
        "Role": [_make_doc("Role", "doc1")],
        "Missions": [_make_doc("Missions", "m1")],
        "Skills": [_make_doc("Skills", "s1")],
    }

    result = build_role_zip(project, docs_by_section)

    with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
        role_json_content = zf.read("role.json").decode("utf-8")
    parsed = json.loads(role_json_content)

    assert "display_name" in parsed
    assert "description" in parsed
    assert "identity" in parsed
    assert "language" in parsed
    assert "service_types" in parsed
    assert "sections" in parsed
    assert parsed["display_name"] == "Agent Éditeur"


def test_build_role_zip_doc_with_spaces_in_name() -> None:
    """Doc avec nom contenant espaces → crée le fichier sans erreur."""
    from role_builder.services.agflow.exporter import build_role_zip

    project = _make_project()
    docs_by_section = {
        "Role": [_make_doc("Role", "doc avec espaces")],
    }

    result = build_role_zip(project, docs_by_section)

    with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
        names = zf.namelist()
    assert "section_role/doc avec espaces.md" in names
