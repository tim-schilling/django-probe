"""Package index lookups, cached in the process."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

PACKAGE_INDEX_URL = "https://pypi.org/pypi/{name}/json"
DJANGO_FRAMEWORK_CLASSIFIER = "Framework :: Django"


@dataclass(frozen=True)
class PackageInfo:
    """A package the index lists, and whether it targets Django."""

    is_django: bool


@lru_cache(maxsize=1024)
def _package_info(name: str) -> PackageInfo | None:
    """What the package index lists about ``name``, or None if it has no such package."""
    request = Request(
        PACKAGE_INDEX_URL.format(name=quote(name, safe="")),
        headers={"User-Agent": "django-probe"},
    )
    try:
        with urlopen(request, timeout=timedelta(seconds=2).total_seconds()) as response:
            classifiers = json.load(response).get("info", {}).get("classifiers", [])
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    return PackageInfo(is_django=DJANGO_FRAMEWORK_CLASSIFIER in classifiers)


def package_info(name: str) -> PackageInfo | None:
    """What the package index lists about ``name``, or None when the lookup fails."""
    try:
        return _package_info(name)
    except (OSError, ValueError) as error:
        logger.warning("Package index lookup failed: %s", type(error).__name__)
        return None
