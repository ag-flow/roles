"""Génération du README.md et du LICENSE pour un rôle publié sur GitHub.

Le README est en français (langue du projet). Le fichier LICENSE est généré
selon le choix utilisateur (PolyForm-NC / CC-BY-NC-SA-4.0 / CC-BY-4.0 / MIT)
ou absent si 'none'.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def render_readme(
    *,
    project: dict[str, Any],
    docs_by_section: dict[str, list[dict[str, Any]]],
    github_login: str,
) -> str:
    """Compose le README.md à pousser dans le repo cible."""
    sections_summary = "\n".join(
        f"- **{section}** ({len(docs)} documents)"
        for section, docs in docs_by_section.items()
    )
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    description = project.get("description") or ""
    language = project.get("language") or "fr"
    service_types = project.get("service_types") or ["claude-code"]
    service_types_str = ", ".join(service_types)

    return f"""# {project["display_name"]}

> {description}

**Auteur :** [@{github_login}](https://github.com/{github_login})
**Langue :** {language}
**Dernière mise à jour :** {today}
**Service types ag.flow :** {service_types_str}

## Sections

{sections_summary}

## Importer dans ag.flow

1. Téléchargez ce répertoire en ZIP
2. Dans ag.flow, créez un rôle vide avec le `display_name` de votre choix
3. Utilisez `POST /api/admin/roles/{{id}}/import` avec le ZIP
4. Optionnel : déclenchez `POST /api/admin/roles/{{id}}/generate-prompts`
   pour régénérer le prompt orchestrateur

## Structure

```
.
├── README.md          (ce fichier)
├── LICENSE            (la licence choisie pour ce rôle)
├── role.json          (métadonnées + structure des sections)
├── identity.md        (identité de l'agent)
└── sections/          (un sous-dossier par section)
```

---

Généré par Role Builder.
"""


_POLYFORM_NC = """Copyright (c) {year} {author_login}

This content is licensed under the PolyForm Noncommercial License 1.0.0.

Required Notice: Copyright (c) {year} {author_login} (https://github.com/{author_login})

# PolyForm Noncommercial License 1.0.0

<https://polyformproject.org/licenses/noncommercial/1.0.0>

The verbatim text of PolyForm Noncommercial 1.0.0 follows. See
<https://polyformproject.org/licenses/noncommercial/1.0.0> for the
full normative text. You may not modify the text of this license.
"""

_CC_BY_NC_SA = """Copyright (c) {year} {author_login} (https://github.com/{author_login})

This work is licensed under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International License.

To view a copy of this license, visit:
<https://creativecommons.org/licenses/by-nc-sa/4.0/>
"""

_CC_BY = """Copyright (c) {year} {author_login} (https://github.com/{author_login})

This work is licensed under the Creative Commons Attribution 4.0
International License (CC-BY 4.0).

To view a copy of this license, visit:
<https://creativecommons.org/licenses/by/4.0/>
"""

_MIT = """MIT License

Copyright (c) {year} {author_login}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"""


def render_license_file(license_choice: str, *, author_login: str) -> str | None:
    """Retourne le contenu d'un fichier LICENSE selon le choix utilisateur.

    Retourne None si license_choice == 'none' (pas de fichier à publier).
    """
    if license_choice == "none":
        return None

    year = datetime.now(tz=UTC).year
    fmt = {"year": year, "author_login": author_login}
    if license_choice == "polyform-nc":
        return _POLYFORM_NC.format(**fmt)
    if license_choice == "cc-by-nc-sa-4.0":
        return _CC_BY_NC_SA.format(**fmt)
    if license_choice == "cc-by-4.0":
        return _CC_BY.format(**fmt)
    if license_choice == "mit":
        return _MIT.format(**fmt)
    raise ValueError(f"unknown license_choice: {license_choice}")
