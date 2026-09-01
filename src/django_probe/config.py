"""Read the optional project key from pyproject.toml.

The key is a random UUID rather than a hash of the git remote. A hashed remote would
be zero-config, but public repositories are enumerable, so such a hash is reversible
by dictionary attack. A UUID has no preimage.
"""

from __future__ import annotations

import os
from pathlib import Path

import tomllib

PROJECT_KEY_ENV = "DJANGO_PROBE_PROJECT_KEY"


def pyproject_path(root: Path) -> Path:
    return root / "pyproject.toml"


def read_project_key(root: Path) -> str | None:
    path = pyproject_path(root)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    key = data.get("tool", {}).get("django_probe", {}).get("project_key")
    return key if isinstance(key, str) and key else None


def resolve_project_key(root: Path) -> str | None:
    """Resolve the project key, preferring `DJANGO_PROBE_PROJECT_KEY` over pyproject.toml.

    The environment variable lets a private repository report as a stable project
    without committing a project_key to pyproject.toml.
    """
    env_key = os.environ.get(PROJECT_KEY_ENV)
    return env_key or read_project_key(root)
