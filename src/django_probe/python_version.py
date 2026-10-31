"""Find the Python version a project uses."""

from __future__ import annotations

import re
import sys
import warnings
from collections.abc import Callable
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


def project_python_version(root: Path, *, override: str | None = None) -> str:
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
