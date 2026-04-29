"""Tests TDD pour services/github_publish/readme_builder.py."""

from __future__ import annotations


def test_render_readme_includes_display_name_and_sections() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    project = {
        "display_name": "UX Designer Clea",
        "description": "Agent expert en design UX",
        "language": "fr",
        "service_types": ["claude-code"],
    }
    docs = {
        "Role": [{"name": "principe-empathie"}],
        "Missions": [{"name": "audit-ux"}, {"name": "onboarding"}],
    }
    md = render_readme(project=project, docs_by_section=docs, github_login="alice")

    assert "# UX Designer Clea" in md
    assert "Agent expert en design UX" in md
    assert "[@alice]" in md
    assert "**Role** (1 documents)" in md
    assert "**Missions** (2 documents)" in md
    assert "claude-code" in md


def test_render_readme_handles_empty_description() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    project = {"display_name": "X", "description": None, "language": "fr"}
    md = render_readme(project=project, docs_by_section={}, github_login="alice")
    assert "# X" in md
    # Pas de "None" dans le rendu
    assert "None" not in md


def test_render_license_polyform_includes_full_text() -> None:
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("polyform-nc", author_login="alice")
    assert text is not None
    assert "PolyForm Noncommercial License 1.0.0" in text
    assert "Required Notice: Copyright" in text
    assert "alice" in text


def test_render_license_cc_by_nc_sa_includes_attribution_and_link() -> None:
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("cc-by-nc-sa-4.0", author_login="alice")
    assert text is not None
    assert "Creative Commons" in text
    assert "Attribution-NonCommercial-ShareAlike" in text
    assert "alice" in text
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/" in text


def test_render_license_cc_by_includes_link() -> None:
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("cc-by-4.0", author_login="alice")
    assert text is not None
    assert "Attribution 4.0" in text
    assert "https://creativecommons.org/licenses/by/4.0/" in text


def test_render_license_mit() -> None:
    from role_builder.services.github_publish.readme_builder import render_license_file

    text = render_license_file("mit", author_login="alice")
    assert text is not None
    assert "MIT License" in text
    assert "alice" in text
    assert "WITHOUT WARRANTY" in text


def test_render_license_none_returns_none() -> None:
    from role_builder.services.github_publish.readme_builder import render_license_file

    assert render_license_file("none", author_login="alice") is None


def test_render_license_unknown_raises() -> None:
    from role_builder.services.github_publish.readme_builder import render_license_file
    import pytest

    with pytest.raises(ValueError, match="unknown license_choice"):
        render_license_file("GPL-3.0", author_login="alice")
