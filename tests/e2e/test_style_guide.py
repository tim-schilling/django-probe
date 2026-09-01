from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from tests.e2e.helpers import assert_no_accessibility_violations

USERNAME = "style-guide-review"
PASSWORD = "Style-guide-review-password"


@pytest.mark.django_db(transaction=True)
def test_staff_style_guide_and_dialog_are_accessible(
    live_server: LiveServer,
    django_user_model,
    page: Page,
) -> None:
    django_user_model.objects.create_user(
        username=USERNAME,
        password=PASSWORD,
        is_staff=True,
    )

    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_label("Username:").fill(USERNAME)
    page.get_by_label("Password:").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/account/")

    response = page.goto(f"{live_server.url}/style-guide/")
    assert response is not None and response.ok
    expect(page.get_by_role("heading", name="Frontend style guide")).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("button", name="Open dialog example").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    assert dialog.evaluate("dialog => dialog.contains(document.activeElement)")
    assert_no_accessibility_violations(page)
