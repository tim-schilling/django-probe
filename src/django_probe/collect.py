"""Gather the non-pattern half of the payload: versions and installed dependencies."""

from __future__ import annotations

import platform
import re
from importlib import metadata

_NORMALIZE_RE = re.compile(r"[-_.]+")

#: Recorded in every payload so a zero count can be told apart from "nothing looked".
PROBE_SOURCE_DISTRIBUTIONS = ("django-upgrade", "django-probe")


def normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return _NORMALIZE_RE.sub("-", name).lower()


def dependencies() -> dict[str, str]:
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            found[normalize(name)] = dist.version or ""
    return dict(sorted(found.items()))


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


def python_version() -> str:
    return platform.python_version()


def django_version() -> str:
    return _version_of("django") or ""


def client_version() -> str:
    return _version_of("django-probe") or "0.0.0"
