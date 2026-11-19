"""Load the vendored Django API vocabularies."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import cast

from django_probe.django_api import django_api
from django_probe.settings import DJANGO_SETTING_NAMES
from django_probe.usage import SETTINGS_PREFIX


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
    return django_api().defines(name)


def drop_undefined_django_names(usage: dict[str, int]) -> dict[str, int]:
    """Drop Django usage names that no supported Django version defines.

    Older clients sent attributes the application added, such as monkeypatched
    methods. Reads of known settings are kept. Other packages have no catalog, so
    their names are kept as submitted.
    """
    return {
        name: count
        for name, count in usage.items()
        if not name.startswith("django.")
        or is_django_api_name(name)
        or name.removeprefix(SETTINGS_PREFIX) in DJANGO_SETTING_NAMES
    }
