from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from ingest.tests.helpers import payload
from tests.e2e.helpers import assert_no_accessibility_violations

USERNAME = "account-journey"
PASSWORD = "Account-journey-password"
PROJECT_KEY = "4dd9b8fb-65f7-4d09-8af7-4407c9e07de4"


@pytest.mark.django_db(transaction=True)
def test_account_journey_and_accessibility(live_server: LiveServer, page: Page) -> None:
    page.goto(f"{live_server.url}/accounts/signup/")
    expect(page.get_by_role("heading", name="Create an account")).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_label("Username:").fill(USERNAME)
    page.get_by_label("Password:", exact=True).fill(PASSWORD)
    page.get_by_label("Password (again):").fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.wait_for_url("**/token/")

    token = page.locator("#api-token")
    expect(token).to_be_visible()
    original_token = token.inner_text()
    expect(page.get_by_role("link", name="Style guide")).to_have_count(0)
    assert_no_accessibility_violations(page)

    page.get_by_role("button", name="Regenerate API token").click()
    page.wait_for_url("**/token/")
    replacement_token = token.inner_text()
    assert replacement_token != original_token

    rejected = page.request.post(
        f"{live_server.url}/api/submissions/",
        headers={"Authorization": f"Token {original_token}"},
        data=payload(project_key=PROJECT_KEY),
    )
    assert rejected.status == 401

    accepted = page.request.post(
        f"{live_server.url}/api/submissions/",
        headers={"Authorization": f"Token {replacement_token}"},
        data=payload(project_key=PROJECT_KEY),
    )
    assert accepted.status == 201

    page.get_by_role("link", name="Account", exact=True).click()
    expect(page.get_by_role("heading", name="Your account")).to_be_visible()
    expect(page.get_by_role("code").filter(has_text=PROJECT_KEY).first).to_be_visible()
    expect(
        page.locator(".item-list__meta").filter(has_text="1 submission").first
    ).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("link", name="View all submissions").click()
    expect(page.get_by_role("heading", name="Your submissions")).to_be_visible()
    expect(page.get_by_role("code").filter(has_text=PROJECT_KEY)).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("link", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign out")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(live_server.url + "/")

    page.get_by_role("link", name="Sign in").click()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_label("Username:").fill(USERNAME)
    page.get_by_label("Password:").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/account/")
    expect(page.get_by_role("code").filter(has_text=PROJECT_KEY).first).to_be_visible()
