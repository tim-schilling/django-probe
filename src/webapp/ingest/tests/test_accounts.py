from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from ingest.models import User
from ingest.tests.factories import (
    PASSWORD,
    CliCredentialFactory,
    OrganizationFactory,
    ProjectFactory,
    SubmissionFactory,
    UserFactory,
    issue_cli_credential,
)


class AccountAccessTests(TestCase):
    def test_account(self):
        """Anonymous users are redirected from the account overview to login."""
        response = self.client.get(reverse("account"))

        self.assertRedirects(response, f"{reverse('account_login')}?next=/account/")


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory(username="owner")
        cls.other_user = UserFactory(username="other")

    def setUp(self):
        self.client.force_login(self.user)

    def test_user_uses_uuid7_primary_key(self):
        self.assertEqual(self.user.pk.version, 7)

    def test_empty_state(self):
        """A new account points the user toward organization setup."""
        response = self.client.get(reverse("account"))

        self.assertContains(response, "No organizations yet")
        self.assertContains(response, reverse("organization-create"))

    def test_organization_scope(self):
        """The account lists only organizations where the user is a member."""
        own_organization = OrganizationFactory(name="Own organization", owner=self.user)
        other_organization = OrganizationFactory(
            name="Other organization", owner=self.other_user
        )

        response = self.client.get(reverse("account"))

        self.assertContains(response, own_organization.name)
        self.assertContains(response, "Owner")
        self.assertNotContains(response, other_organization.name)

    def test_submission_scope(self):
        """History includes only submissions belonging to accessible organizations."""
        own_organization = OrganizationFactory(name="Own organization", owner=self.user)
        other_organization = OrganizationFactory(
            name="Other organization", owner=self.other_user
        )
        own_project = ProjectFactory(organization=own_organization, name="Own project")
        other_project = ProjectFactory(
            organization=other_organization, name="Other project"
        )
        own_submission = SubmissionFactory(project=own_project)
        SubmissionFactory(project=other_project)
        SubmissionFactory()

        response = self.client.get(reverse("account"))

        projects = list(response.context["projects"])
        self.assertEqual(projects, [own_project])
        self.assertEqual(projects[0].account_submissions, [own_submission])
        self.assertContains(response, own_project.name)
        self.assertContains(response, own_organization.name)
        self.assertNotContains(response, other_project.name)

    def test_projects_show_empty_submission_state(self):
        """Projects without submissions explain that their history is empty."""
        organization = OrganizationFactory(name="Own organization", owner=self.user)
        project = ProjectFactory(organization=organization, name="Empty project")

        response = self.client.get(reverse("account"))

        self.assertContains(response, project.name)
        self.assertContains(response, "No submissions for this project yet.")


class OwnedAccountTemplateTests(TestCase):
    def test_login(self):
        """Login uses the repository-owned account template and guidance."""
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/login.html")
        self.assertContains(response, "manage your organizations")

    def test_signup(self):
        """Signup uses the repository-owned account template and guidance."""
        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/signup.html")
        self.assertContains(response, "Create an account")

    def test_logout(self):
        """Logout uses the repository-owned confirmation template."""
        user = UserFactory(username="owner")
        self.client.force_login(user)

        response = self.client.get(reverse("account_logout"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/logout.html")
        self.assertContains(response, "Are you sure")


class AuthenticationJourneyTests(TestCase):
    def test_signup(self):
        """Signup creates a signed-in user and continues to the account overview."""
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "",
                "username": "new-member",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertRedirects(
            response, reverse("account"), fetch_redirect_response=False
        )
        self.assertTrue(User.objects.filter(username="new-member").exists())
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

    def test_login(self):
        """Login continues to the private account overview."""
        UserFactory(username="returning-member")

        response = self.client.post(
            reverse("account_login"),
            {"login": "returning-member", "password": PASSWORD},
        )

        self.assertRedirects(
            response,
            reverse("account"),
            fetch_redirect_response=False,
        )

    def test_logout(self):
        """Logout ends the session and protects private account pages again."""
        user = UserFactory(username="member")
        self.client.force_login(user)

        response = self.client.post(reverse("account_logout"))

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        account_response = self.client.get(reverse("account"))
        self.assertRedirects(
            account_response,
            f"{reverse('account_login')}?next=/account/",
        )


class AccountNavigationTests(TestCase):
    def test_anonymous(self):
        """Anonymous navigation offers authentication but no private links."""
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("account_login"))
        self.assertContains(response, reverse("account_signup"))
        self.assertNotContains(response, reverse("account"))
        self.assertNotContains(response, reverse("style-guide"))

    def test_member_navigation(self):
        """Member navigation links private pages but not the staff style guide."""
        user = UserFactory(username="member")
        self.client.force_login(user)

        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("account"))
        self.assertContains(response, reverse("account_logout"))
        self.assertNotContains(response, reverse("style-guide"))

    def test_staff(self):
        """Staff navigation includes the internal style guide."""
        user = UserFactory(username="staff", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("style-guide"))


class CliCredentialManagementTests(TestCase):
    """Self-service revocation. Without it a lost laptop can only be dealt with by
    someone with database or Django admin access."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.other = UserFactory(username="other")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)

    def revoke_url(self, credential) -> str:
        return reverse("cli-credential-revoke", kwargs={"credential_id": credential.pk})

    def test_account_lists_the_signed_in_users_credentials(self):
        credential, _ = issue_cli_credential(
            organization=self.organization, user=self.owner, label="work-laptop"
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("account"))

        self.assertContains(response, "work-laptop")
        self.assertContains(response, self.revoke_url(credential))

    def test_account_does_not_list_other_peoples_credentials(self):
        issue_cli_credential(
            organization=self.organization, user=self.owner, label="work-laptop"
        )
        self.client.force_login(self.other)

        response = self.client.get(reverse("account"))

        self.assertNotContains(response, "work-laptop")

    def test_pending_requests_are_not_listed(self):
        """A request nobody collected is not a credential and cannot be revoked."""
        CliCredentialFactory(user=self.owner, label="never-collected")
        self.client.force_login(self.owner)

        response = self.client.get(reverse("account"))

        self.assertNotContains(response, "never-collected")

    def test_revoking_stops_the_credential_working(self):
        credential, token = issue_cli_credential(
            organization=self.organization, user=self.owner
        )
        self.client.force_login(self.owner)

        response = self.client.post(self.revoke_url(credential))

        credential.refresh_from_db()
        self.assertRedirects(response, reverse("account"))
        self.assertIsNotNone(credential.revoked_at)
        api = self.client.post(
            reverse("cli-projects-create"),
            data='{"name": "Website"}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"CliToken {token}",
        )
        self.assertEqual(api.status_code, 401)

    def test_cannot_revoke_someone_elses_credential(self):
        credential, _ = issue_cli_credential(
            organization=self.organization, user=self.owner
        )
        self.client.force_login(self.other)

        response = self.client.post(self.revoke_url(credential))

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(credential.revoked_at)

    def test_revoking_requires_a_post(self):
        credential, _ = issue_cli_credential(
            organization=self.organization, user=self.owner
        )
        self.client.force_login(self.owner)

        response = self.client.get(self.revoke_url(credential))

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 405)
        self.assertIsNone(credential.revoked_at)

    def test_revoking_is_idempotent(self):
        credential, _ = issue_cli_credential(
            organization=self.organization, user=self.owner
        )
        self.client.force_login(self.owner)
        self.client.post(self.revoke_url(credential))
        credential.refresh_from_db()
        first_revoked_at = credential.revoked_at

        self.client.post(self.revoke_url(credential))

        credential.refresh_from_db()
        self.assertEqual(credential.revoked_at, first_revoked_at)

    def test_anonymous_users_are_redirected(self):
        credential, _ = issue_cli_credential(
            organization=self.organization, user=self.owner
        )

        response = self.client.post(self.revoke_url(credential))

        credential.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(credential.revoked_at)
