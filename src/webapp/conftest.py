from __future__ import annotations

from pathlib import Path

import pytest
from django.test import override_settings

from ingest.package_index import PackageInfo

_HERE = Path(__file__).parent


@pytest.fixture(autouse=True)
def use_fast_password_hasher():
    with override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
    ):
        yield


@pytest.fixture(autouse=True)
def trust_package_index(monkeypatch):
    """Keep the webapp suite offline; index checks have their own tests."""
    monkeypatch.setattr(
        "ingest.stats.package_info",
        lambda name: PackageInfo(is_django=name == "djangorestframework"),
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test collected under src/webapp as a webapp test."""
    for item in items:
        if item.path.is_relative_to(_HERE):
            item.add_marker(pytest.mark.webapp)
