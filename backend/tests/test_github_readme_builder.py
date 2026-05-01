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
    import pytest

    from role_builder.services.github_publish.readme_builder import render_license_file

    with pytest.raises(ValueError, match="unknown license_choice"):
        render_license_file("GPL-3.0", author_login="alice")


# ---------------------------------------------------------------------------
# Badges shields.io (Phase 2 sous-projet B)
# ---------------------------------------------------------------------------


def _project_basic() -> dict[str, str | list[str]]:
    return {
        "display_name": "Agent",
        "description": "desc",
        "language": "fr",
        "service_types": ["claude-code"],
    }


def test_render_readme_includes_documents_count_badge() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    docs = {
        "Role": [{"name": "a"}, {"name": "b"}],
        "Missions": [{"name": "c"}],
    }
    md = render_readme(project=_project_basic(), docs_by_section=docs, github_login="x")
    assert "img.shields.io/badge/Documents-3-" in md


def test_render_readme_includes_language_badge() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    md = render_readme(
        project=_project_basic(), docs_by_section={}, github_login="x",
    )
    assert "img.shields.io/badge/Language-fr-" in md


def test_render_readme_includes_service_types_badge() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    project = {**_project_basic(), "service_types": ["claude-code", "openai-assistant"]}
    md = render_readme(project=project, docs_by_section={}, github_login="x")
    # Shields.io échappe les '-' en '--' dans le label
    assert "img.shields.io/badge/agflow-claude--code__openai--assistant" in md


def test_render_readme_includes_license_badge_when_choice_provided() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    md = render_readme(
        project=_project_basic(),
        docs_by_section={},
        github_login="x",
        license_choice="mit",
    )
    assert "img.shields.io/badge/License-MIT-green" in md


def test_render_readme_skips_license_badge_when_none() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    md = render_readme(
        project=_project_basic(),
        docs_by_section={},
        github_login="x",
        license_choice="none",
    )
    assert "License-" not in md


def test_render_readme_license_badge_polyform_is_blue() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    md = render_readme(
        project=_project_basic(),
        docs_by_section={},
        github_login="x",
        license_choice="polyform-nc",
    )
    assert "img.shields.io/badge/License-PolyForm--NC-blue" in md


# ---------------------------------------------------------------------------
# Stats du corpus
# ---------------------------------------------------------------------------


def test_render_readme_includes_corpus_stats_when_provided() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    md = render_readme(
        project=_project_basic(),
        docs_by_section={},
        github_login="x",
        stats={"source_count": 12, "chunk_count": 530},
    )
    assert "## Stats du corpus" in md
    assert "Sources scrapées : 12" in md
    assert "Chunks indexés : 530" in md


def test_render_readme_omits_stats_section_when_stats_none() -> None:
    from role_builder.services.github_publish.readme_builder import render_readme

    md = render_readme(
        project=_project_basic(), docs_by_section={}, github_login="x",
    )
    assert "Stats du corpus" not in md
    assert "Sources scrapées" not in md
