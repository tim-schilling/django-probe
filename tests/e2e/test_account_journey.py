from __future__ import annotations

import pytest
from allauth.socialaccount.models import SocialAccount
from django.test import override_settings
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from ingest.tests.helpers import payload
from tests.e2e.helpers import assert_no_accessibility_violations

USERNAME = "account-journey"
PASSWORD = "Account-journey-password"
MEMBER_USERNAME = "organization-member"
MEMBER_PASSWORD = "Organization-member-password"
ORGANIZATION_NAME = "Django team"
PROJECT_NAME = "Django website"
GITHUB_PROVIDER_SETTINGS = {
    "github": {
        "APPS": [
            {
                "client_id": "github-client-id",
                "secret": "github-secret",
                "key": "",
            }
        ]
    }
}


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_PROVIDER_SETTINGS)
@pytest.mark.django_db(transaction=True)
def test_account_journey(
    live_server: LiveServer,
    django_user_model,
    page: Page,
) -> None:
    """Exercise the accessible owner-to-member organization workflow end to end."""
    django_user_model.objects.create_user(
        username=MEMBER_USERNAME,
        password=MEMBER_PASSWORD,
    )
    page.goto(f"{live_server.url}/accounts/signup/")
    expect(page.get_by_role("heading", name="Create an account")).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_label("Username:").fill(USERNAME)
    page.get_by_label("Password:", exact=True).fill(PASSWORD)
    page.get_by_label("Password (again):").fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.wait_for_url("**/account/")
    expect(page.get_by_role("heading", name="Your account")).to_be_visible()
    expect(page.get_by_text("No organizations yet.")).to_be_visible()
    expect(page.get_by_role("link", name="Style guide")).to_have_count(0)
    assert_no_accessibility_violations(page)

    user = django_user_model.objects.get(username=USERNAME)
    SocialAccount.objects.create(
        user=user,
        provider="github",
        uid="123",
        extra_data={"login": "account-journey"},
    )
    page.goto(f"{live_server.url}/accounts/3rdparty/")
    expect(page.get_by_role("heading", name="Sign-in methods")).to_be_visible()
    expect(page.get_by_label("GitHub — account-journey")).to_be_visible()
    expect(
        page.get_by_role("button", name="Disconnect selected account")
    ).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_role("link", name="Back to your account").click()
    expect(page.get_by_text("GitHub is connected.")).to_be_visible()

    page.get_by_role("link", name="Create organization").click()
    expect(page.get_by_role("heading", name="Create an organization")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_label("Name:").fill(ORGANIZATION_NAME)
    page.get_by_role("button", name="Create organization").click()
    expect(page.get_by_role("heading", name=ORGANIZATION_NAME)).to_be_visible()
    expect(page.get_by_text("Owner", exact=True)).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("link", name="Create project").click()
    expect(page.get_by_role("heading", name="Create a project")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_label("Name:").fill(PROJECT_NAME)
    page.get_by_role("button", name="Create project").click()
    expect(page.get_by_role("heading", name=PROJECT_NAME)).to_be_visible()
    assert_no_accessibility_violations(page)

    # A project with no submissions yet opens its setup instructions, so the
    # package-manager tabs are on screen.
    page.locator("#pd-github-tab-poetry").click()
    expect(page.locator("#pd-github-panel-poetry")).to_be_visible()
    expect(page.locator("#pd-github-panel-uv")).to_be_hidden()
    expect(page.locator("#pd-gitlab-tab-poetry")).to_have_attribute(
        "aria-selected", "true"
    )

    token = page.locator("#project-token")
    expect(token).to_be_visible()
    page.get_by_role("button", name="Show token").click()
    original_token = token.inner_text()
    assert len(original_token) == 64
    assert_no_accessibility_violations(page)

    page.get_by_role("button", name="Regenerate token").click()
    page.get_by_role("button", name="Show token").click()
    replacement_token = token.inner_text()
    assert replacement_token != original_token

    rejected = page.request.post(
        f"{live_server.url}/api/submissions/",
        headers={"Authorization": f"Token {original_token}"},
        data=payload(),
    )
    assert rejected.status == 401

    page.get_by_role("link", name=f"← Back to {ORGANIZATION_NAME}").click()
    page.get_by_role("link", name="Manage members").click()
    expect(page.get_by_role("heading", name="Manage members")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_label("Username:").fill(MEMBER_USERNAME)
    page.get_by_label("Role:").select_option("member")
    page.get_by_role("button", name="Add member").click()
    expect(page.get_by_text(MEMBER_USERNAME, exact=True)).to_be_visible()
    assert_no_accessibility_violations(page)

    accepted = page.request.post(
        f"{live_server.url}/api/submissions/",
        headers={"Authorization": f"Token {replacement_token}"},
        data=payload(),
    )
    assert accepted.status == 201

    page.get_by_role("link", name=f"← Back to {ORGANIZATION_NAME}").click()
    expect(page.get_by_role("link", name=PROJECT_NAME).first).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("link", name=PROJECT_NAME).first.click()
    expect(page.get_by_role("heading", name=PROJECT_NAME)).to_be_visible()
    expect(page.get_by_text("Django 5.1.2")).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("link", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign out")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(live_server.url + "/")

    page.get_by_role("link", name="Sign in").click()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_label("Username:").fill(MEMBER_USERNAME)
    page.get_by_label("Password:").fill(MEMBER_PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/account/")
    expect(page.get_by_role("link", name=ORGANIZATION_NAME).first).to_be_visible()

    page.get_by_role("link", name=ORGANIZATION_NAME).first.click()
    expect(page.get_by_text("Member", exact=True)).to_be_visible()
    # `role` is a label, not a permission: a member gets the same actions as the
    # person who created the organization.
    expect(page.get_by_role("link", name="Create project")).to_be_visible()
    expect(page.get_by_role("link", name="Manage members")).to_be_visible()
    expect(page.get_by_role("link", name=PROJECT_NAME).first).to_be_visible()
    assert_no_accessibility_violations(page)

    page.get_by_role("button", name="Leave organization").click()
    page.wait_for_url("**/account/")
    expect(page.get_by_text("No organizations yet.")).to_be_visible()
