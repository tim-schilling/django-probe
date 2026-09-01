from __future__ import annotations

from pathlib import Path

import pytest

_HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test collected under src/webapp as a webapp test."""
    for item in items:
        if item.path.is_relative_to(_HERE):
            item.add_marker(pytest.mark.webapp)
