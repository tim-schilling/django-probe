from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from ingest.models import CliCredential, Organization
from tests.e2e.helpers import assert_no_accessibility_violations

USERNAME = "cli-auth-owner"
PASSWORD = "Cli-auth-owner-password"
ORGANIZATION_NAME = "Django team"
SECOND_ORGANIZATION_NAME = "Second team"


@pytest.mark.django_db(transaction=True)
def test_cli_auth_approve_journey(
    live_server: LiveServer,
    django_user_model,
    page: Page,
) -> None:
    """Exercise both the org-preset confirm and the org-picker approve states."""
    owner = django_user_model.objects.create_user(username=USERNAME, password=PASSWORD)
    organization = Organization.objects.create_with_owner(
        name=ORGANIZATION_NAME, owner=owner
    )
    second_organization = Organization.objects.create_with_owner(
        name=SECOND_ORGANIZATION_NAME, owner=owner
    )
    preset_credential = CliCredential.objects.create(
        organization=organization, label="laptop"
    )
    picker_credential = CliCredential.objects.create(label="workstation")

    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_label("Username:").fill(USERNAME)
    page.get_by_label("Password:").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/account/")

    page.goto(f"{live_server.url}/cli-auth/{preset_credential.code}/")
    expect(page.get_by_role("heading", name="Approve CLI access")).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_role("button", name="Approve").click()
    expect(page.get_by_text("Approved.")).to_be_visible()
    assert_no_accessibility_violations(page)

    page.goto(f"{live_server.url}/cli-auth/{picker_credential.code}/")
    expect(page.get_by_text(ORGANIZATION_NAME)).to_be_visible()
    expect(page.get_by_text(SECOND_ORGANIZATION_NAME)).to_be_visible()
    assert_no_accessibility_violations(page)
    page.get_by_label(SECOND_ORGANIZATION_NAME).check()
    page.get_by_role("button", name="Approve").click()
    expect(page.get_by_text("Approved.")).to_be_visible()

    picker_credential.refresh_from_db()
    assert picker_credential.organization == second_organization
