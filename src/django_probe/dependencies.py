"""
Resolve the project's dependencies from its lock file, or from what's installed.
"""

from __future__ import annotations

import sys
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from django_probe import collect
from django_probe.config import DependencyMode

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DISABLED = "none"
INSTALLED = "installed"
UNRESOLVED = ""
REQUIRED_DISTRIBUTION = "django"

LockEntry = dict[str, object]


@dataclass(frozen=True)
class Dependencies:
    packages: dict[str, str]
    source: str


@dataclass(frozen=True)
class LockFormat:
    name: str
    filename: str
    from_pypi: Callable[[LockEntry], bool]


PYPI_HOSTS = frozenset({"pypi.org", "pypi.python.org"})


def _is_pypi(url: str) -> bool:
    return urllib.parse.urlparse(url).hostname in PYPI_HOSTS


def _uv_from_pypi(entry: LockEntry) -> bool:
    source = entry.get("source")
    if not isinstance(source, dict):
        return False
    registry = source.get("registry")
    return isinstance(registry, str) and _is_pypi(registry)


def _poetry_from_pypi(entry: LockEntry) -> bool:
    source = entry.get("source")
    if source is None:
        return True
    if not isinstance(source, dict) or source.get("type") != "legacy":
        return False
    url = source.get("url")
    return isinstance(url, str) and _is_pypi(url)


#: pdm names a VCS entry after its backend, and marks the rest with "path" or "url".
#: Index entries carry none of these, so this has to enumerate rather than allow-list.
PDM_NON_INDEX_KEYS = ("git", "hg", "svn", "bzr", "path", "url")


def _pdm_from_pypi(entry: LockEntry) -> bool:
    # pdm.lock records no index URL, so a package from a private index is
    # indistinguishable from one off PyPI and is reported either way.
    return not any(key in entry for key in PDM_NON_INDEX_KEYS)


LOCK_FORMATS = (
    LockFormat("uv", "uv.lock", _uv_from_pypi),
    LockFormat("poetry", "poetry.lock", _poetry_from_pypi),
    LockFormat("pdm", "pdm.lock", _pdm_from_pypi),
)


def _highest(versions: list[str]) -> str:
    """Pick one version for a name that markers split across several."""
    parsed = []
    for version in versions:
        try:
            parsed.append((Version(version), version))
        except InvalidVersion:
            continue
    if not parsed:
        return ""
    return max(parsed, key=lambda candidate: candidate[0])[1]


def _find_lock(root: Path) -> tuple[Path, LockFormat] | None:
    for lock_format in LOCK_FORMATS:
        path = root / lock_format.filename
        if path.is_file():
            return path, lock_format
    return None


def _packages_from_lock(
    path: Path, lock_format: LockFormat
) -> tuple[dict[str, str], bool] | None:
    """Reportable packages and whether Django was locked at all, or None if unreadable."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    entries = data.get("package")
    if not isinstance(entries, list):
        return None

    candidates: dict[str, list[str]] = {}
    locked: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        normalized = collect.normalize(name)
        locked.add(normalized)
        if not lock_format.from_pypi(entry):
            continue
        version = entry.get("version")
        candidates.setdefault(normalized, []).append(
            version if isinstance(version, str) else ""
        )
    packages = {
        name: _highest(versions) for name, versions in sorted(candidates.items())
    }
    return packages, REQUIRED_DISTRIBUTION in locked


def _resolve_packages(root: Path) -> tuple[dict[str, str], str, bool]:
    found = _find_lock(root)
    if found is not None:
        path, lock_format = found
        result = _packages_from_lock(path, lock_format)
        if result is not None:
            packages, found_django = result
            return packages, lock_format.name, found_django
    return collect.dependencies(), INSTALLED, bool(collect.django_version())


def resolve(
    root: Path,
    *,
    mode: DependencyMode = "versions",
    exclude_patterns: Sequence[str] = (),
) -> Dependencies:
    if mode == "none":
        return Dependencies({}, DISABLED)

    # A Django installed from a VCS checkout is excluded from what we report, but
    # seeing it still proves we read the project rather than some other environment.
    packages, source, found_django = _resolve_packages(root)
    if not found_django:
        return Dependencies({}, UNRESOLVED)

    packages = collect.exclude_by_pattern(packages, exclude_patterns)
    if mode == "names":
        packages = dict.fromkeys(packages, "")
    return Dependencies(packages, source)


def unresolved_message(root: Path) -> str:
    """Explain which layer came up short, and what would fix it."""
    found = _find_lock(root)
    if found is None:
        return (
            f"could not find {REQUIRED_DISTRIBUTION} among the installed "
            "distributions, so any dependencies reported would describe a different "
            "environment. Install the project's dependencies, add a lock file, or "
            'set dependencies = "none" under [tool.django_probe].'
        )
    path, lock_format = found
    return (
        f"could not find {REQUIRED_DISTRIBUTION} in {path.name}, so any dependencies "
        f"reported would be incomplete. Re-run your {lock_format.name} lock command, "
        'or set dependencies = "none" under [tool.django_probe].'
    )
