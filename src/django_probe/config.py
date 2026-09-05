"""Read the optional project token from pyproject.toml.

The token isn't derived from anything about the project (like a hash of the git
remote) — it's an opaque value copied from a project's page on the Django Probe web
app, so it carries no information an attacker could work backward from.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

TOKEN_ENV = "DJANGO_PROBE_TOKEN"


def pyproject_path(root: Path) -> Path:
    return root / "pyproject.toml"


def read_token(root: Path) -> str | None:
    path = pyproject_path(root)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    token = data.get("tool", {}).get("django_probe", {}).get("token")
    return token if isinstance(token, str) and token else None


def resolve_token(root: Path) -> str | None:
    """Resolve the token, preferring `DJANGO_PROBE_TOKEN` over pyproject.toml.

    The environment variable lets a token be kept out of a committed pyproject.toml,
    e.g. as a CI secret.
    """
    env_token = os.environ.get(TOKEN_ENV)
    return env_token or read_token(root)


def django_settings_enabled(root: Path) -> bool:
    """Return whether the opt-in Django settings inventory is enabled."""
    path = pyproject_path(root)
    if not path.is_file():
        return False
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return (
        data.get("tool", {})
        .get("django_probe", {})
        .get("usage", {})
        .get("django_settings")
        is True
    )
