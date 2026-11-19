"""Load the vendored Django API vocabularies."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import cast

from django_probe.django_api import django_api


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


_VOCABULARY_DIRECTORY = Path(__file__).parent
_VOCABULARIES = {
    path.name.removesuffix(".json.gz"): path
    for path in _VOCABULARY_DIRECTORY.glob("[0-9]*.json.gz")
}
DJANGO_API_VERSIONS = tuple(sorted(_VOCABULARIES, key=_version_key))


def _read_api_names(version: str) -> list[str]:
    """Read one vendored API catalog without retaining an intermediate set."""
    path = _VOCABULARIES[version]
    return cast(list[str], json.loads(gzip.decompress(path.read_bytes()))["names"])


def is_django_api_name(name: str) -> bool:
    """Return whether a name is public API in any supported Django version.

    This includes members reached through a subclass, such as `User.save`.
    """
    return django_api().fold(name) == name
