from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ingest.models import (
    ApiToken,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
)

PASSWORD = "Account-test-password"


def create_submission(
    user: User | None,
    project: Project | None = None,
    project_key: uuid.UUID | None = None,
) -> Submission:
    return Submission.objects.create(
        user=user,
        project=project,
        project_key=project.key if project else project_key,
        schema_version=1,
        client_version="0.1.0",
        python_version="3.12.3",
        django_version="5.1.2",
        files_scanned=12,
        probe_sources={"django-probe": "0.1.0"},
        patterns={"probe:queryset_filter": 3},
        dependencies={"django": "5.1.2"},
    )


class AccountAccessTests(TestCase):
    def test_account(self):
        """Anonymous users are redirected from the account overview to login."""
        response = self.client.get(reverse("account"))

        self.assertRedirects(response, f"{reverse('account_login')}?next=/account/")

    def test_submissions(self):
        """Anonymous users are redirected from submission history to login."""
        response = self.client.get(reverse("account-submissions"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next=/account/submissions/",
        )

    def test_token(self):
        """Anonymous users are redirected from token management to login."""
        response = self.client.get(reverse("token"))

        self.assertRedirects(response, f"{reverse('account_login')}?next=/token/")


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("owner", password=PASSWORD)
        cls.other_user = User.objects.create_user("other", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.user)

    def test_empty_state(self):
        """A new account points the user toward organization and token setup."""
        response = self.client.get(reverse("account"))

        self.assertContains(response, "No organizations yet")
        self.assertContains(response, reverse("organization-create"))
        self.assertContains(response, reverse("token"))

        history_response = self.client.get(reverse("account-submissions"))
        self.assertContains(history_response, "No accessible submissions yet")

    def test_organization_scope(self):
        """The account lists only organizations where the user is a member."""
        own_organization = Organization.objects.create_with_owner(
            name="Own organization", owner=self.user
        )
        other_organization = Organization.objects.create_with_owner(
            name="Other organization", owner=self.other_user
        )

        response = self.client.get(reverse("account"))

        self.assertContains(response, own_organization.name)
        self.assertContains(response, "Owner")
        self.assertNotContains(response, other_organization.name)

    def test_submission_scope(self):
        """History includes accessible organization submissions and the user's unassigned ones."""
        own_organization = Organization.objects.create_with_owner(
            name="Own organization", owner=self.user
        )
        other_organization = Organization.objects.create_with_owner(
            name="Other organization", owner=self.other_user
        )
        colleague = User.objects.create_user("colleague", password=PASSWORD)
        OrganizationMembership.objects.create(
            organization=own_organization,
            user=colleague,
            role=OrganizationMembership.Role.MEMBER,
        )
        own_project = Project.objects.create(
            organization=own_organization, name="Own project"
        )
        other_project = Project.objects.create(
            organization=other_organization, name="Other project"
        )
        organization_submission = create_submission(colleague, own_project)
        unassigned_submission = create_submission(self.user)
        create_submission(self.other_user, other_project)
        create_submission(self.other_user)

        response = self.client.get(reverse("account-submissions"))

        self.assertEqual(
            list(response.context["submissions"]),
            [unassigned_submission, organization_submission],
        )


class OwnedAccountTemplateTests(TestCase):
    def test_login(self):
        """Login uses the repository-owned account template and guidance."""
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/login.html")
        self.assertContains(response, "manage your API token")

    def test_signup(self):
        """Signup uses the repository-owned account template and guidance."""
        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/signup.html")
        self.assertContains(response, "Create an account")

    def test_logout(self):
        """Logout uses the repository-owned confirmation template."""
        user = User.objects.create_user("owner")
        self.client.force_login(user)

        response = self.client.get(reverse("account_logout"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/logout.html")
        self.assertContains(response, "Are you sure")


class AuthenticationJourneyTests(TestCase):
    def test_signup(self):
        """Signup creates a signed-in user and continues to token management."""
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "",
                "username": "new-member",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("token"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="new-member").exists())
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

    def test_login(self):
        """Login continues to the private account overview."""
        User.objects.create_user("returning-member", password=PASSWORD)

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
        user = User.objects.create_user("member", password=PASSWORD)
        self.client.force_login(user)

        response = self.client.post(reverse("account_logout"))

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        account_response = self.client.get(reverse("account"))
        self.assertRedirects(
            account_response,
            f"{reverse('account_login')}?next=/account/",
        )


class TokenManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("owner", password=PASSWORD)
        cls.other_user = User.objects.create_user("other", password=PASSWORD)
        cls.other_token = ApiToken.objects.create(user=cls.other_user)

    def setUp(self):
        self.client.force_login(self.user)

    def test_stable_token(self):
        """Repeated retrieval keeps one token and does not affect another user."""
        first_response = self.client.get(reverse("token"))
        second_response = self.client.get(reverse("token"))

        first_token = first_response.context["api_token"]
        self.assertEqual(second_response.context["api_token"], first_token)
        self.assertEqual(self.user.api_tokens.count(), 1)
        self.assertTrue(ApiToken.objects.filter(pk=self.other_token.pk).exists())

    def test_regeneration(self):
        """Regeneration rotates only the current user's token."""
        first_token = ApiToken.objects.create(user=self.user)

        response = self.client.post(reverse("token"))

        self.assertRedirects(response, reverse("token"), fetch_redirect_response=False)
        replacement = self.user.api_tokens.get()
        self.assertNotEqual(replacement.key, first_token.key)
        self.assertFalse(ApiToken.objects.filter(pk=first_token.pk).exists())
        self.assertTrue(ApiToken.objects.filter(pk=self.other_token.pk).exists())

    def test_unsupported_method(self):
        """Token management accepts retrieval and regeneration only."""
        response = self.client.put(reverse("token"))

        self.assertEqual(response.status_code, 405)


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
        user = User.objects.create_user("member", password=PASSWORD)
        self.client.force_login(user)

        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("account"))
        self.assertContains(response, reverse("token"))
        self.assertContains(response, reverse("account_logout"))
        self.assertNotContains(response, reverse("style-guide"))

    def test_staff(self):
        """Staff navigation includes the internal style guide."""
        user = User.objects.create_user("staff", password=PASSWORD, is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("style-guide"))
