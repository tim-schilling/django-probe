"""Assemble the submission payload.

Everything the server ever receives is built here, in one function, so the privacy
claim can be checked by reading a single file: integers, package names and version
strings, and nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from django_probe import collect
from django_probe.config import DependencyMode
from django_probe.scan import scan_path

SCHEMA_VERSION = 1


class SubmissionPayload(TypedDict):
    """The full shape of what a client ever sends a server.

    Mirrors the fields ``webapp.ingest.validation.validate_payload`` accepts.
    """

    schema_version: int
    client_version: str
    python_version: str
    django_version: str
    files_scanned: int
    probe_sources: dict[str, str]
    patterns: dict[str, int]
    usage_packages: list[str]
    usage: dict[str, int]
    django_settings: dict[str, int]
    django_settings_scanned: bool
    dependencies: dict[str, str]


def build_payload(
    root: Path,
    *,
    dependency_mode: DependencyMode = "versions",
    dependency_exclude_patterns: Sequence[str] = (),
) -> SubmissionPayload:
    result = scan_path(root)
    if dependency_mode == "none":
        dependencies = {}
    else:
        dependencies = collect.dependencies(
            include_versions=dependency_mode == "versions"
        )
        dependencies = collect.exclude_by_pattern(
            dependencies, dependency_exclude_patterns
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "client_version": collect.client_version(),
        "python_version": collect.python_version(),
        "django_version": collect.django_version(),
        "files_scanned": result.files_scanned,
        "probe_sources": collect.probe_sources(),
        "patterns": dict(sorted(result.patterns.items())),
        "usage_packages": list(result.usage_packages),
        "usage": dict(sorted(result.usage.items())),
        "django_settings": dict(sorted(result.django_settings.items())),
        "django_settings_scanned": result.django_settings_scanned,
        "dependencies": dependencies,
    }
