from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ingest.models import CLI_AUTH_REQUEST_TTL, OrganizationMembership
from ingest.tests.factories import (
    CliCredentialFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    UserFactory,
)


class CliCredentialModelTests(TestCase):
    def test_code_generated_on_create(self):
        credential = CliCredentialFactory()

        self.assertTrue(credential.code)

    def test_code_is_unique(self):
        first = CliCredentialFactory()
        second = CliCredentialFactory()

        self.assertNotEqual(first.code, second.code)

    def test_defaults_to_pending(self):
        credential = CliCredentialFactory()

        self.assertIsNone(credential.token)
        self.assertIsNone(credential.denied_at)
        self.assertGreater(credential.expires_at, timezone.now())

    def test_expires_after_the_request_ttl(self):
        credential = CliCredentialFactory()

        expected = credential.created_at + CLI_AUTH_REQUEST_TTL
        self.assertLess(abs(credential.expires_at - expected), timedelta(seconds=5))


class CliAuthVerifyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.member = UserFactory(username="member")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        OrganizationMembershipFactory(
            organization=cls.organization,
            user=cls.member,
            role=OrganizationMembership.Role.MEMBER,
        )

    def url(self, credential) -> str:
        return reverse("cli-auth-verify", args=[credential.code])

    def test_anonymous_redirects_to_login(self):
        credential = CliCredentialFactory(organization=self.organization)

        response = self.client.get(self.url(credential))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_owner_sees_confirm_state(self):
        """An owner of the credential's organization is shown a plain confirm."""
        credential = CliCredentialFactory(organization=self.organization)
        self.client.force_login(self.owner)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "Django team")
        self.assertContains(response, "Approve")

    def test_non_owner_sees_forbidden_state(self):
        """A non-owner sees a friendly explanation rather than a hard error."""
        credential = CliCredentialFactory(organization=self.organization)
        self.client.force_login(self.member)

        response = self.client.get(self.url(credential))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "don't have owner access")

    def test_approve_sets_token_and_user(self):
        credential = CliCredentialFactory(organization=self.organization)
        self.client.force_login(self.owner)

        response = self.client.post(self.url(credential), {"action": "approve"})

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(credential.token)
        self.assertEqual(credential.user, self.owner)

    def test_deny_leaves_no_token(self):
        credential = CliCredentialFactory(organization=self.organization)
        self.client.force_login(self.owner)

        self.client.post(self.url(credential), {"action": "deny"})

        credential.refresh_from_db()
        self.assertIsNone(credential.token)
        self.assertIsNotNone(credential.denied_at)

    def test_non_owner_cannot_approve(self):
        credential = CliCredentialFactory(organization=self.organization)
        self.client.force_login(self.member)

        response = self.client.post(self.url(credential), {"action": "approve"})

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(credential.token)

    def test_choose_state_lists_owned_organizations(self):
        """When login wasn't given --org, the approve page offers a picker."""
        second_organization = OrganizationFactory(name="Second team", owner=self.owner)
        credential = CliCredentialFactory(organization=None)
        self.client.force_login(self.owner)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "Django team")
        self.assertContains(response, "Second team")

        approve_response = self.client.post(
            self.url(credential),
            {"action": "approve", "organization_id": str(second_organization.pk)},
        )
        credential.refresh_from_db()

        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(credential.organization, second_organization)
        self.assertTrue(credential.token)

    def test_no_organizations_state(self):
        """A user who owns no organizations is guided to create one."""
        credential = CliCredentialFactory(organization=None)
        self.client.force_login(self.member)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "don't own any organizations")

    def test_cannot_approve_an_organization_not_owned(self):
        """Posting a tampered organization_id is still authorization-checked."""
        credential = CliCredentialFactory(organization=None)
        self.client.force_login(self.member)

        response = self.client.post(
            self.url(credential),
            {"action": "approve", "organization_id": str(self.organization.pk)},
        )

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(credential.token)

    def test_expired_request_shows_invalid_state(self):
        credential = CliCredentialFactory(
            organization=self.organization,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_login(self.owner)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "no longer valid")

    def test_already_approved_request_cannot_be_reapproved(self):
        credential = CliCredentialFactory(
            organization=self.organization, token="already-issued", user=self.owner
        )
        self.client.force_login(self.owner)

        response = self.client.post(self.url(credential), {"action": "approve"})

        credential.refresh_from_db()
        self.assertContains(response, "no longer valid")
        self.assertEqual(credential.token, "already-issued")
