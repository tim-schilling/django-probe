from __future__ import annotations

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page


def assert_no_accessibility_violations(page: Page) -> None:
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
