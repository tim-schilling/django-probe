"""Gather the non-pattern half of the payload: versions and installed dependencies."""

from __future__ import annotations

import fnmatch
import platform
import re
from collections.abc import Sequence
from importlib import metadata

_NORMALIZE_RE = re.compile(r"[-_.]+")

#: Recorded in every payload so a zero count can be told apart from "nothing looked".
PROBE_SOURCE_DISTRIBUTIONS = ("django-probe",)


def normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return _NORMALIZE_RE.sub("-", name).lower()


def _installed_from_index(dist: metadata.Distribution) -> bool:
    """Whether this distribution was resolved through a normal package index.

    PEP 610 has pip/uv write a `direct_url.json` only for a local-path install
    (editable or not), a VCS checkout, or a direct archive URL - never for a plain
    index-resolved install. Its absence is the only local signal that separates an
    index install from a private-repo or `pip install -e .` checkout. It can't tell
    a private package index apart from PyPI itself, since both resolve the same way -
    use `exclude_by_pattern` for those.
    """
    return dist.read_text("direct_url.json") is None


def dependencies(*, include_versions: bool = True) -> dict[str, str]:
    """Installed dependencies, excluding local-path, editable, and VCS installs.

    Still includes anything resolved through a package index, public or private -
    see `exclude_by_pattern` to also drop known-internal packages by name.
    """
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name and _installed_from_index(dist):
            found[normalize(name)] = (dist.version or "") if include_versions else ""
    return dict(sorted(found.items()))


def exclude_by_pattern(
    dependencies: dict[str, str], patterns: Sequence[str]
) -> dict[str, str]:
    """Drop dependencies matching any of an org's configured internal name patterns."""
    if not patterns:
        return dependencies
    normalized_patterns = [normalize(pattern) for pattern in patterns]
    return {
        name: version
        for name, version in dependencies.items()
        if not any(
            fnmatch.fnmatchcase(name, pattern) for pattern in normalized_patterns
        )
    }


def _version_of(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def probe_sources() -> dict[str, str]:
    return {
        name: version
        for name in PROBE_SOURCE_DISTRIBUTIONS
        if (version := _version_of(name)) is not None
    }


def python_version() -> str:
    return platform.python_version()


def django_version() -> str:
    return _version_of("django") or ""


def client_version() -> str:
    return _version_of("django-probe") or "0.0.0"
