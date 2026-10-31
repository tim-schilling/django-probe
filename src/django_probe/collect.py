"""Gather the non-pattern half of the payload: versions and installed dependencies."""

from __future__ import annotations

import fnmatch
import re
import sys
import warnings
from collections.abc import Callable, Sequence
from importlib import metadata
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PYTHON_VERSION = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:a|b|rc)[0-9]+)?")
DOCKERFILE_PYTHON = re.compile(
    r"^[ \t]*FROM[ \t]+(?:--\S+[ \t]+)*(?:\S+/)?python:([0-9][^\s@-]*)",
    re.IGNORECASE | re.MULTILINE,
)
LOWER_BOUND_OPERATORS = frozenset({">=", "~=", "==", "==="})

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
    if PYTHON_VERSION.fullmatch(version):
        return version
    raise ValueError("expected a numeric Python version, such as 3.15 or 3.15.0")


def _lowest_supported_python(specifiers: object) -> str:
    if not isinstance(specifiers, str):
        return ""
    bounds = [
        specifier.version.removesuffix(".*")
        for specifier in SpecifierSet(specifiers)
        if specifier.operator in LOWER_BOUND_OPERATORS
    ]
    return max(bounds, key=Version, default="")


def _tool_versions_python(text: str) -> str:
    for line in text.splitlines():
        fields = line.split("#")[0].split()
        if len(fields) >= 2 and fields[0] == "python":
            return fields[1]
    return ""


def _runtime_txt_python(text: str) -> str:
    return text.strip().removeprefix("python-")


def _pipfile_python(text: str) -> str:
    requires = tomllib.loads(text).get("requires")
    if not isinstance(requires, dict):
        return ""
    version = requires.get("python_full_version") or requires.get("python_version")
    return version if isinstance(version, str) else ""


def _dockerfile_python(text: str) -> str:
    """The final Python stage, since earlier stages only build the image."""
    versions = DOCKERFILE_PYTHON.findall(text)
    return versions[-1] if versions else ""


def _pyproject_python(text: str) -> str:
    project = tomllib.loads(text).get("project")
    if not isinstance(project, dict):
        return ""
    return _lowest_supported_python(project.get("requires-python"))


def _uv_lock_python(text: str) -> str:
    return _lowest_supported_python(tomllib.loads(text).get("requires-python"))


# Pinned versions come first, since a range only gives the lowest supported version.
PYTHON_VERSION_SOURCES: tuple[tuple[str, Callable[[str], str]], ...] = (
    (".python-version", str),
    (".tool-versions", _tool_versions_python),
    ("runtime.txt", _runtime_txt_python),
    ("Pipfile", _pipfile_python),
    ("Dockerfile", _dockerfile_python),
    ("pyproject.toml", _pyproject_python),
    ("uv.lock", _uv_lock_python),
)


def python_version(root: Path, *, override: str | None = None) -> str:
    if override:
        return parse_python_version(override)
    for filename, extract in PYTHON_VERSION_SOURCES:
        try:
            text = (root / filename).read_text(encoding="utf-8")
            return parse_python_version(extract(text))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    warnings.warn(
        "no valid Python version found, reporting it as unknown. "
        "Pass --python-version or add a .python-version file.",
        RuntimeWarning,
        stacklevel=2,
    )
    return ""


def django_version() -> str:
    return _version_of("django") or ""


def client_version() -> str:
    return _version_of("django-probe") or "0.0.0"
