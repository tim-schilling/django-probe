from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ingest.models import ApiToken, Submission

PASSWORD = "Account-test-password"


def create_submission(
    user: User | None, project_key: uuid.UUID | None = None
) -> Submission:
    return Submission.objects.create(
        user=user,
        project_key=project_key,
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
    def test_account_requires_login(self):
        response = self.client.get(reverse("account"))

        self.assertRedirects(response, f"{reverse('account_login')}?next=/account/")

    def test_submissions_require_login(self):
        response = self.client.get(reverse("account-submissions"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next=/account/submissions/",
        )

    def test_token_requires_login(self):
        response = self.client.get(reverse("token"))

        self.assertRedirects(response, f"{reverse('account_login')}?next=/token/")


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("owner", password=PASSWORD)
        cls.other_user = User.objects.create_user("other", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.user)

    def test_empty_account_has_next_step(self):
        response = self.client.get(reverse("account"))

        self.assertContains(response, "No projects yet")
        self.assertContains(response, "0")
        self.assertContains(response, reverse("token"))

        history_response = self.client.get(reverse("account-submissions"))
        self.assertContains(history_response, "No submissions yet")
        self.assertContains(history_response, reverse("token"))

    def test_account_groups_only_users_projects(self):
        project_key = uuid.uuid4()
        other_project_key = uuid.uuid4()
        create_submission(self.user, project_key)
        create_submission(self.user, project_key)
        create_submission(self.other_user, other_project_key)
        create_submission(None, uuid.uuid4())

        response = self.client.get(reverse("account"))

        self.assertContains(response, str(project_key))
        self.assertContains(response, "2 submissions")
        self.assertNotContains(response, str(other_project_key))
        self.assertEqual(response.context["submission_count"], 2)

    def test_recent_submissions_are_limited_and_private(self):
        own_submissions = [create_submission(self.user) for _ in range(7)]
        create_submission(self.other_user)

        response = self.client.get(reverse("account"))

        self.assertEqual(
            list(response.context["recent_submissions"]),
            list(reversed(own_submissions[-5:])),
        )

    def test_submission_history_is_private(self):
        own_project_key = uuid.uuid4()
        other_project_key = uuid.uuid4()
        create_submission(self.user, own_project_key)
        create_submission(self.other_user, other_project_key)

        response = self.client.get(reverse("account-submissions"))

        self.assertContains(response, str(own_project_key))
        self.assertNotContains(response, str(other_project_key))
        self.assertEqual(
            list(response.context["submissions"]), list(self.user.submissions.all())
        )


class OwnedAccountTemplateTests(TestCase):
    def test_login_uses_project_template(self):
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/login.html")
        self.assertContains(response, "manage your API token")

    def test_signup_uses_project_template(self):
        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/signup.html")
        self.assertContains(response, "Create an account")

    def test_logout_uses_project_template(self):
        user = User.objects.create_user("owner")
        self.client.force_login(user)

        response = self.client.get(reverse("account_logout"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "account/logout.html")
        self.assertContains(response, "Are you sure")


class AuthenticationJourneyTests(TestCase):
    def test_signup_signs_in_and_redirects_to_token(self):
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

    def test_login_redirects_to_private_account(self):
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

    def test_logout_ends_private_session(self):
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

    def test_retrieval_creates_one_stable_token_for_current_user(self):
        first_response = self.client.get(reverse("token"))
        second_response = self.client.get(reverse("token"))

        first_token = first_response.context["api_token"]
        self.assertEqual(second_response.context["api_token"], first_token)
        self.assertEqual(self.user.api_tokens.count(), 1)
        self.assertTrue(ApiToken.objects.filter(pk=self.other_token.pk).exists())

    def test_regeneration_rotates_only_current_users_token(self):
        first_token = ApiToken.objects.create(user=self.user)

        response = self.client.post(reverse("token"))

        self.assertRedirects(response, reverse("token"), fetch_redirect_response=False)
        replacement = self.user.api_tokens.get()
        self.assertNotEqual(replacement.key, first_token.key)
        self.assertFalse(ApiToken.objects.filter(pk=first_token.pk).exists())
        self.assertTrue(ApiToken.objects.filter(pk=self.other_token.pk).exists())

    def test_token_rejects_unsupported_methods(self):
        response = self.client.put(reverse("token"))

        self.assertEqual(response.status_code, 405)


class AccountNavigationTests(TestCase):
    def test_anonymous_navigation_offers_authentication(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("account_login"))
        self.assertContains(response, reverse("account_signup"))
        self.assertNotContains(response, reverse("account"))
        self.assertNotContains(response, reverse("style-guide"))

    def test_member_navigation_links_private_pages_but_not_style_guide(self):
        user = User.objects.create_user("member", password=PASSWORD)
        self.client.force_login(user)

        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("account"))
        self.assertContains(response, reverse("token"))
        self.assertContains(response, reverse("account_logout"))
        self.assertNotContains(response, reverse("style-guide"))

    def test_staff_navigation_links_style_guide(self):
        user = User.objects.create_user("staff", password=PASSWORD, is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("style-guide"))
