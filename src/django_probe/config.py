"""Read Django Probe configuration from pyproject.toml."""

from __future__ import annotations

import os
import sys
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
