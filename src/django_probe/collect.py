"""Gather the non-pattern half of the payload: versions and installed dependencies."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

PYTHON_VERSION = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:a|b|rc)[0-9]+)?")

_NORMALIZE_RE = re.compile(r"[-_.]+")

# Recorded in every payload so a zero count can be told apart from "nothing looked".
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


def dependencies() -> dict[str, str]:
    """Installed dependencies, excluding local-path, editable, and VCS installs.

    Still includes anything resolved through a package index, public or private -
    see `exclude_by_pattern` to also drop known-internal packages by name.
    """
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name and _installed_from_index(dist):
            found[normalize(name)] = dist.version or ""
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


def parse_python_version(value: str) -> str:
    version = value.strip()
    if not version or (len(version) <= 128 and PYTHON_VERSION.fullmatch(version)):
        return version
    raise ValueError("expected a numeric Python version, such as 3.15 or 3.15.0")


def python_version(root: Path, *, override: str = "") -> str:
    override = parse_python_version(override)
    if override:
        return override
    try:
        return parse_python_version(
            (root / ".python-version").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return ""


def django_version() -> str:
    return _version_of("django") or ""


def client_version() -> str:
    return _version_of("django-probe") or "0.0.0"
