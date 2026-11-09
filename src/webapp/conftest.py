from __future__ import annotations

from pathlib import Path

import pytest
from django.test import override_settings

_HERE = Path(__file__).parent


@pytest.fixture(autouse=True)
def use_fast_password_hasher():
    with override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
    ):
        yield


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test collected under src/webapp as a webapp test."""
    for item in items:
        if item.path.is_relative_to(_HERE):
            item.add_marker(pytest.mark.webapp)
