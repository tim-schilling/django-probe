"""Read and write the optional project key in pyproject.toml.

The key is a random UUID rather than a hash of the git remote. A hashed remote would
be zero-config, but public repositories are enumerable, so such a hash is reversible
by dictionary attack. A UUID has no preimage.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import tomllib

TOOL_TABLE = "[tool.django_probe]"


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


def write_project_key(root: Path, key: str | None = None) -> str:
    """Write a project key to pyproject.toml, returning the key in use.

    Appends the table as text rather than round-tripping the document, which would
    mean a tomlkit dependency for a single scalar.
    """
    path = pyproject_path(root)
    existing = read_project_key(root)
    if existing is not None:
        return existing

    key = key or str(uuid.uuid4())
    content = path.read_text(encoding="utf-8") if path.is_file() else ""

    if TOOL_TABLE in content:
        content = content.replace(TOOL_TABLE, f'{TOOL_TABLE}\nproject_key = "{key}"', 1)
    else:
        separator = "" if content.endswith("\n") or not content else "\n"
        content = f'{content}{separator}\n{TOOL_TABLE}\nproject_key = "{key}"\n'

    path.write_text(content, encoding="utf-8")
    return key
