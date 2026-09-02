from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from ingest.models import User
from ingest.tests.factories import (
    PASSWORD,
    OrganizationFactory,
    ProjectFactory,
    SubmissionFactory,
    UserFactory,
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

        history_response = self.client.get(reverse("account-submissions"))
        self.assertContains(history_response, "No accessible submissions yet")

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

        response = self.client.get(reverse("account-submissions"))

        self.assertEqual(list(response.context["submissions"]), [own_submission])


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
