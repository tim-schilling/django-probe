"""Read Django Probe configuration from pyproject.toml."""

from __future__ import annotations

import keyword
import os
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

TOKEN_ENV = "DJANGO_PROBE_TOKEN"
DependencyMode = Literal["versions", "names", "none"]


def pyproject_path(root: Path) -> Path:
    return root / "pyproject.toml"


def read_config(root: Path) -> dict[str, object]:
    path = pyproject_path(root)
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    config = data.get("tool", {}).get("django_probe", {})
    return config if isinstance(config, dict) else {}


def read_token(root: Path) -> str | None:
    token = read_config(root).get("token")
    return token if isinstance(token, str) and token else None


def dependency_mode(root: Path) -> DependencyMode:
    value = read_config(root).get("dependencies", "versions")
    return value if value in {"versions", "names", "none"} else "versions"


def dependency_exclude_patterns(root: Path) -> tuple[str, ...]:
    """Fnmatch-style name patterns (e.g. "acme-*") for internal packages to omit.

    A private package index resolves like a normal one, so it leaves no local trace
    to filter on (see `collect._installed_from_index`); an org can list its own
    naming here to exclude those packages without relying on PyPI verification.
    """
    value = read_config(root).get("dependencies_exclude", [])
    if not isinstance(value, list) or any(not isinstance(p, str) for p in value):
        warnings.warn(
            "dependencies_exclude must be a list of name patterns; ignoring it.",
            RuntimeWarning,
            stacklevel=2,
        )
        return ()
    return tuple(value)


def resolve_token(root: Path) -> str | None:
    """Resolve the token, preferring `DJANGO_PROBE_TOKEN` over pyproject.toml.

    The environment variable lets a token be kept out of a committed pyproject.toml,
    e.g. as a CI secret.
    """
    env_token = os.environ.get(TOKEN_ENV)
    return env_token or read_token(root)


def django_settings_enabled(root: Path) -> bool:
    """Return whether the Django settings inventory is enabled (on by default)."""
    return read_config(root).get("django_settings") is not False


MONKEYPATCH_PACKAGES = frozenset({"django"})


def monkeypatch_packages(root: Path, usage_packages: Sequence[str]) -> tuple[str, ...]:
    """Return the packages whose monkeypatched members are collected.

    Defaults to the supported entries of ``usage_packages``, so disabling package
    usage also disables monkeypatches. Only Django has a catalog that separates its
    members from attributes the application adds, so other packages that are
    configured explicitly are dropped with a warning.
    """
    value = read_config(root).get("monkeypatches")
    if value is None:
        return tuple(name for name in usage_packages if name in MONKEYPATCH_PACKAGES)
    if not isinstance(value, list) or any(not isinstance(p, str) for p in value):
        warnings.warn(
            "monkeypatches must be a list of package names; monkeypatches omitted.",
            RuntimeWarning,
            stacklevel=2,
        )
        return ()
    unsupported = [name for name in value if name not in MONKEYPATCH_PACKAGES]
    if unsupported:
        warnings.warn(
            f"monkeypatches only supports 'django'; ignoring {', '.join(unsupported)}.",
            RuntimeWarning,
            stacklevel=2,
        )
    return tuple(name for name in dict.fromkeys(value) if name in MONKEYPATCH_PACKAGES)


def packages(root: Path) -> tuple[str, ...]:
    """Return the configured top-level Python import namespaces."""
    value = read_config(root).get("packages", ["django"])
    if not isinstance(value, list) or any(
        not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name)
        for name in value
    ):
        warnings.warn(
            "packages must be a list of top-level Python import names; "
            "package usage omitted.",
            RuntimeWarning,
            stacklevel=2,
        )
        return ()
    return tuple(dict.fromkeys(value))
