from __future__ import annotations

import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ingest.models import (
    CLI_AUTH_REQUEST_TTL,
    CliCredential,
    OrganizationMembership,
    Project,
)
from ingest.tests.factories import (
    CliCredentialFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    UserFactory,
)


class CliCredentialModelTests(TestCase):
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
        cls.outsider = UserFactory(username="outsider")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        OrganizationMembershipFactory(
            organization=cls.organization,
            user=cls.member,
            role=OrganizationMembership.Role.MEMBER,
        )

    def url(self, credential) -> str:
        return reverse("cli-auth-verify", args=[credential.code])

    def test_anonymous_redirects_to_login(self):
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)

        response = self.client.get(self.url(credential))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_owner_sees_confirm_state(self):
        """An owner of the credential's organization is shown a plain confirm."""
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.owner)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "Django team")
        self.assertContains(response, "Approve")

    def test_member_sees_confirm_state(self):
        """A plain member, not just an owner, can confirm access for their org."""
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.member)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "Django team")
        self.assertContains(response, "Approve")

    def test_non_member_sees_forbidden_state(self):
        """Someone with no relationship to the org sees an explanation, not a hard error."""
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.outsider)

        response = self.client.get(self.url(credential))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a member of")

    def test_approve_sets_token_and_user(self):
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.owner)

        response = self.client.post(self.url(credential), {"action": "approve"})

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(credential.token)
        self.assertEqual(credential.user, self.owner)

    def test_deny_leaves_no_token(self):
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.owner)

        self.client.post(self.url(credential), {"action": "deny"})

        credential.refresh_from_db()
        self.assertIsNone(credential.token)
        self.assertIsNotNone(credential.denied_at)

    def test_member_can_approve(self):
        """A plain member, not just an owner, can approve access for their org."""
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.member)

        response = self.client.post(self.url(credential), {"action": "approve"})

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(credential.token)
        self.assertEqual(credential.user, self.member)

    def test_non_member_cannot_approve(self):
        credential = CliCredentialFactory(requested_org_slug=self.organization.slug)
        self.client.force_login(self.outsider)

        response = self.client.post(self.url(credential), {"action": "approve"})

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(credential.token)

    def test_choose_state_lists_member_organizations(self):
        """When login wasn't given --org, the approve page offers a picker."""
        second_organization = OrganizationFactory(name="Second team", owner=self.owner)
        OrganizationMembershipFactory(
            organization=second_organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
        )
        credential = CliCredentialFactory(organization=None)
        self.client.force_login(self.member)

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
        """A user who isn't a member of any organization is guided to create one."""
        credential = CliCredentialFactory(organization=None)
        self.client.force_login(self.outsider)

        response = self.client.get(self.url(credential))

        self.assertContains(response, "not a member of any organizations")

    def test_cannot_approve_an_organization_not_a_member_of(self):
        """Posting a tampered organization_id is still authorization-checked."""
        credential = CliCredentialFactory(organization=None)
        self.client.force_login(self.outsider)

        response = self.client.post(
            self.url(credential),
            {"action": "approve", "organization_id": str(self.organization.pk)},
        )

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(credential.token)

    def test_expired_request_shows_invalid_state(self):
        credential = CliCredentialFactory(
            requested_org_slug=self.organization.slug,
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


class CliAuthApiTests(TestCase):
    def start(self, body: dict | None = None):
        return self.client.post(
            reverse("cli-auth-start"),
            data=json.dumps(body if body is not None else {}),
            content_type="application/json",
        )

    def poll(self, code: str):
        return self.client.get(reverse("cli-auth-poll", args=[code]))

    def test_start_creates_a_pending_request(self):
        response = self.start()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("code", body)
        self.assertIn(body["code"], body["verify_url"])
        self.assertEqual(body["expires_in"], 600)
        credential = CliCredential.objects.get(code=body["code"])
        self.assertIsNone(credential.organization)

    def test_start_with_org_slug(self):
        owner = UserFactory(username="owner")
        organization = OrganizationFactory(name="Django team", owner=owner)

        response = self.start({"org_slug": organization.slug, "label": "laptop"})

        self.assertEqual(response.status_code, 201)
        credential = CliCredential.objects.get(code=response.json()["code"])
        self.assertIsNone(credential.organization)
        self.assertEqual(credential.requested_org_slug, organization.slug)
        self.assertEqual(credential.label, "laptop")

    def test_start_rejects_unknown_org_slug(self):
        response = self.start({"org_slug": "does-not-exist"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CliCredential.objects.exists())

    def test_start_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("cli-auth-start")).status_code, 405)

    def test_poll_unknown_code(self):
        self.assertEqual(self.poll("nope").status_code, 404)

    def test_poll_pending(self):
        credential = CliCredentialFactory()

        self.assertEqual(self.poll(credential.code).json(), {"status": "pending"})

    def test_poll_denied(self):
        credential = CliCredentialFactory(denied_at=timezone.now())

        self.assertEqual(self.poll(credential.code).json(), {"status": "denied"})

    def test_poll_expired(self):
        credential = CliCredentialFactory(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertEqual(self.poll(credential.code).json(), {"status": "expired"})

    def test_poll_approved_returns_the_token_once(self):
        """A second poll of the same code 404s once the token has been retrieved."""
        owner = UserFactory(username="owner")
        organization = OrganizationFactory(name="Django team", owner=owner)
        credential = CliCredentialFactory(
            organization=organization, token="issued-token", user=owner
        )

        first = self.poll(credential.code)
        second = self.poll(credential.code)

        self.assertEqual(
            first.json(),
            {
                "status": "approved",
                "token": "issued-token",
                "organization": {"slug": organization.slug, "name": organization.name},
            },
        )
        self.assertEqual(second.status_code, 404)


class CliProjectsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        cls.credential = CliCredentialFactory(
            organization=cls.organization, user=cls.owner, token="issued-token"
        )

    def post(self, body: dict, **extra: str):
        return self.client.post(
            reverse("cli-projects-create"),
            data=json.dumps(body),
            content_type="application/json",
            **extra,
        )

    def test_creates_project(self):
        response = self.post(
            {"name": "Website"}, HTTP_AUTHORIZATION="CliToken issued-token"
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "Website")
        self.assertEqual(body["organization"]["slug"], self.organization.slug)
        project = Project.objects.get(organization=self.organization)
        self.assertEqual(project.token, body["token"])

    def test_updates_last_used_at(self):
        self.assertIsNone(self.credential.last_used_at)

        self.post({"name": "Website"}, HTTP_AUTHORIZATION="CliToken issued-token")

        self.credential.refresh_from_db()
        self.assertIsNotNone(self.credential.last_used_at)

    def test_missing_authorization_header_rejected(self):
        response = self.post({"name": "Website"})

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Project.objects.exists())

    def test_wrong_scheme_rejected(self):
        response = self.post(
            {"name": "Website"}, HTTP_AUTHORIZATION="Token issued-token"
        )

        self.assertEqual(response.status_code, 401)

    def test_unknown_token_rejected(self):
        response = self.post({"name": "Website"}, HTTP_AUTHORIZATION="CliToken nope")

        self.assertEqual(response.status_code, 401)

    def test_revoked_token_rejected(self):
        self.credential.revoked_at = timezone.now()
        self.credential.save(update_fields=["revoked_at"])

        response = self.post(
            {"name": "Website"}, HTTP_AUTHORIZATION="CliToken issued-token"
        )

        self.assertEqual(response.status_code, 401)

    def test_membership_revoked_since_login_rejected(self):
        """Losing ownership after login cuts off project creation immediately."""
        OrganizationMembership.objects.filter(
            organization=self.organization, user=self.owner
        ).delete()

        response = self.post(
            {"name": "Website"}, HTTP_AUTHORIZATION="CliToken issued-token"
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.exists())

    def test_org_slug_mismatch_rejected(self):
        response = self.post(
            {"name": "Website", "org_slug": "some-other-org"},
            HTTP_AUTHORIZATION="CliToken issued-token",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Project.objects.exists())

    def test_matching_org_slug_accepted(self):
        response = self.post(
            {"name": "Website", "org_slug": self.organization.slug},
            HTTP_AUTHORIZATION="CliToken issued-token",
        )

        self.assertEqual(response.status_code, 201)

    def test_missing_name_rejected(self):
        response = self.post({}, HTTP_AUTHORIZATION="CliToken issued-token")

        self.assertEqual(response.status_code, 400)


class CliCredentialsRevokeApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        cls.credential = CliCredentialFactory(
            organization=cls.organization, user=cls.owner, token="issued-token"
        )

    def revoke(self, **extra: str):
        return self.client.post(reverse("cli-credentials-revoke"), **extra)

    def test_revokes_own_token(self):
        response = self.revoke(HTTP_AUTHORIZATION="CliToken issued-token")

        self.assertEqual(response.status_code, 200)
        self.credential.refresh_from_db()
        self.assertIsNotNone(self.credential.revoked_at)

    def test_cannot_be_replayed(self):
        self.revoke(HTTP_AUTHORIZATION="CliToken issued-token")

        second = self.revoke(HTTP_AUTHORIZATION="CliToken issued-token")

        self.assertEqual(second.status_code, 401)

    def test_missing_authorization_header_rejected(self):
        response = self.revoke()

        self.assertEqual(response.status_code, 401)
        self.credential.refresh_from_db()
        self.assertIsNone(self.credential.revoked_at)

    def test_get_not_allowed(self):
        response = self.client.get(reverse("cli-credentials-revoke"))

        self.assertEqual(response.status_code, 405)
