from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from tests.e2e.helpers import assert_no_accessibility_violations


@pytest.mark.django_db(transaction=True)
def test_home_package_manager_tabs_are_accessible_and_stay_in_sync(
    live_server: LiveServer,
    page: Page,
) -> None:
    response = page.goto(live_server.url)
    assert response is not None and response.ok
    expect(page.get_by_role("heading", name="Get started locally")).to_be_visible()
    assert_no_accessibility_violations(page)

    install_panel = page.locator("#install-panel-uv")
    expect(install_panel).to_be_visible()
    expect(page.locator("#install-panel-pip")).to_be_hidden()

    page.get_by_role("tab", name="pip").first.click()

    expect(page.locator("#install-panel-pip")).to_be_visible()
    expect(page.locator("#install-panel-uv")).to_be_hidden()
    expect(page.get_by_role("tab", name="pip").first).to_have_attribute(
        "aria-selected", "true"
    )

    for tab in page.get_by_role("tab", name="pip").all():
        expect(tab).to_have_attribute("aria-selected", "true")

    assert_no_accessibility_violations(page)


@pytest.mark.django_db(transaction=True)
def test_home_ci_provider_tabs_switch_workflow_and_keep_package_manager_choice(
    live_server: LiveServer,
    page: Page,
) -> None:
    response = page.goto(live_server.url)
    assert response is not None and response.ok
    expect(page.get_by_role("heading", name="Add it to CI")).to_be_visible()

    expect(page.locator("#ci-panel-github")).to_be_visible()
    expect(page.locator("#ci-panel-gitlab")).to_be_hidden()

    page.locator("#github-tab-pip").click()
    expect(page.locator("#github-panel-pip")).to_be_visible()
    expect(
        page.locator("#github-panel-pip").get_by_text("pip install -r requirements.txt")
    ).to_be_visible()

    page.get_by_role("tab", name="GitLab CI").click()
    expect(page.locator("#ci-panel-gitlab")).to_be_visible()
    expect(page.locator("#ci-panel-github")).to_be_hidden()

    expect(page.locator("#gitlab-panel-pip")).to_be_visible()
    expect(
        page.locator("#gitlab-panel-pip").get_by_text("pip install -r requirements.txt")
    ).to_be_visible()

    assert_no_accessibility_violations(page)
