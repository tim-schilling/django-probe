"""Assemble the submission payload.

Everything the server ever receives is built here, in one function, so the privacy
claim can be checked by reading a single file: integers, package names and version
strings, and nothing else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django_probe import collect
from django_probe.scan import scan_path

SCHEMA_VERSION = 3


def build_payload(root: Path) -> dict[str, Any]:
    result = scan_path(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "client_version": collect.client_version(),
        "python_version": collect.python_version(),
        "django_version": collect.django_version(),
        "files_scanned": result.files_scanned,
        "probe_sources": collect.probe_sources(),
        "patterns": dict(sorted(result.patterns.items())),
        "dependencies": collect.dependencies(),
        "django_settings": dict(sorted(result.django_settings.items())),
        "django_settings_scanned": result.django_settings_scanned,
    }
