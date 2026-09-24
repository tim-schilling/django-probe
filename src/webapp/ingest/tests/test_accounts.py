from __future__ import annotations

import json
from datetime import date, datetime, timezone

from allauth.socialaccount.models import SocialAccount
from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import translation

from django_probe import __version__
from ingest.export import iter_json
from ingest.models import Organization, Submission, User
from ingest.tests.factories import (
    PASSWORD,
    CliCredentialFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    ProjectFactory,
    SubmissionFactory,
    UserFactory,
    issue_cli_credential,
)

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


class AccountAccessTests(TestCase):
    def test_account(self):
        """Anonymous users are redirected from the account overview to login."""
        response = self.client.get(reverse("account"))

        self.assertRedirects(response, f"{reverse('account_login')}?next=/account/")

    def test_account_export(self):
        response = self.client.get(reverse("account-export"))

        self.assertRedirects(
            response, f"{reverse('account_login')}?next=/account/export/"
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

    @override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_PROVIDER_SETTINGS)
    def test_can_connect_github(self):
        response = self.client.get(reverse("account"))

        self.assertContains(response, "Connect GitHub")
        self.assertContains(
            response,
            f'href="{reverse("github_login")}?process=connect&amp;next=%2Faccount%2F"',
        )

    @override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_PROVIDER_SETTINGS)
    def test_connected_github_account(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="github",
            uid="123",
            extra_data={"login": "octocat"},
        )

        response = self.client.get(reverse("account"))

        self.assertContains(response, "GitHub is connected")
        self.assertContains(response, "octocat")
        self.assertContains(response, reverse("socialaccount_connections"))
        self.assertNotContains(response, "Connect GitHub")

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
        self.assertEqual(projects[0].latest_submission_id, own_submission.pk)
        self.assertEqual(
            projects[0].latest_client_version, own_submission.client_version
        )
        self.assertContains(response, own_project.name)
        self.assertContains(response, own_organization.name)
        self.assertNotContains(response, other_project.name)

    def test_client_versions(self):
        """Different latest client versions are highlighted, while missing ones are not."""
        organization = OrganizationFactory(owner=self.user)
        old_project = ProjectFactory(organization=organization, name="Old client")
        missing_project = ProjectFactory(
            organization=organization, name="Missing client"
        )
        current_project = ProjectFactory(
            organization=organization, name="Current client"
        )
        SubmissionFactory(project=old_project, client_version=__version__)
        latest_submission = SubmissionFactory(
            project=old_project, client_version="0.3.2"
        )
        SubmissionFactory(project=missing_project, client_version="")
        SubmissionFactory(project=current_project, client_version=__version__)

        response = self.client.get(reverse("account"))

        projects = {project.pk: project for project in response.context["projects"]}
        self.assertEqual(
            projects[old_project.pk].latest_client_version,
            latest_submission.client_version,
        )
        self.assertContains(response, "0.3.2")
        self.assertContains(response, "Out of date", count=1)
        self.assertContains(response, "Latest")
        self.assertContains(response, __version__)
        self.assertContains(response, "View changelog")
        self.assertContains(
            response,
            f"https://github.com/tim-schilling/django-probe/blob/{__version__}/docs/changelog.md",
        )
        self.assertNotContains(response, "Not reported")
        self.assertContains(response, '<td class="table__meta">-</td>', html=True)

    def test_projects_show_empty_submission_state(self):
        """Projects without submissions explain that their history is empty."""
        organization = OrganizationFactory(name="Own organization", owner=self.user)
        project = ProjectFactory(organization=organization, name="Empty project")

        response = self.client.get(reverse("account"))

        self.assertContains(response, project.name)
        self.assertContains(response, "No submissions yet")

    def test_credential_dates_use_the_active_locale(self):
        organization = OrganizationFactory(owner=self.user)
        credential, _ = issue_cli_credential(
            user=self.user,
            organization=organization,
        )
        credential.token_expires_at = datetime(2027, 1, 15, 18, tzinfo=timezone.utc)
        credential.last_used_at = datetime(2027, 2, 3, 18, tzinfo=timezone.utc)
        credential.save(update_fields=["token_expires_at", "last_used_at"])

        with translation.override("de"):
            response = self.client.get(reverse("account"))

        self.assertContains(response, "15.01.2027")
        self.assertContains(response, "03.02.2027")

    def test_account_offers_an_export(self):
        response = self.client.get(reverse("account"))

        self.assertContains(response, reverse("account-export"))

    def test_account_delete_retains_submissions_by_default(self):
        organization = OrganizationFactory(owner=self.user)
        project = ProjectFactory(organization=organization)
        submission = SubmissionFactory(project=project)

        response = self.client.post(
            reverse("account-delete"), {"username": self.user.username}
        )

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Organization.objects.filter(pk=organization.pk).exists())
        submission.refresh_from_db()
        self.assertIsNone(submission.project_id)

    def test_account_delete_can_delete_sole_member_submissions(self):
        organization = OrganizationFactory(owner=self.user)
        project = ProjectFactory(organization=organization)
        submission = SubmissionFactory(project=project)

        self.client.post(
            reverse("account-delete"),
            {"username": self.user.username, "delete_submissions": "on"},
        )

        self.assertFalse(Submission.objects.filter(pk=submission.pk).exists())

    def test_account_delete_requires_username(self):
        organization = OrganizationFactory(owner=self.user)
        project = ProjectFactory(organization=organization)
        submission = SubmissionFactory(project=project)

        response = self.client.post(
            reverse("account-delete"),
            {"username": "wrong", "delete_submissions": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(Submission.objects.filter(pk=submission.pk).exists())


class AccountExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory(username="owner", email="owner@example.com")
        cls.other_user = UserFactory(username="other")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.user)
        cls.project = ProjectFactory(organization=cls.organization, name="Storefront")

    def setUp(self):
        self.client.force_login(self.user)

    def body(self) -> str:
        """Drain the streamed response into the file a browser would save."""
        response = self.client.get(reverse("account-export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        return b"".join(response.streaming_content).decode()

    def export(self) -> dict:
        return json.loads(self.body())

    def test_downloads_as_a_dated_json_file(self):
        response = self.client.get(reverse("account-export"))

        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="django-probe-owner-{date.today():%Y-%m-%d}.json"',
        )

    def test_includes_the_account_and_its_github_identity(self):
        SocialAccount.objects.create(user=self.user, provider="github", uid="12345")

        document = self.export()

        self.assertEqual(document["account"]["username"], "owner")
        self.assertEqual(document["account"]["email"], "owner@example.com")
        [identity] = document["account"]["identities"]
        self.assertEqual(identity["provider"], "github")
        self.assertEqual(identity["uid"], "12345")
        self.assertIsNotNone(identity["connected_at"])

    def test_includes_organizations_projects_and_submissions(self):
        submission = SubmissionFactory(project=self.project, django_version="5.2.1")

        document = self.export()

        organization = document["organizations"][0]
        self.assertEqual(organization["name"], "Django team")
        self.assertEqual(organization["your_role"], "owner")
        [project] = organization["projects"]
        self.assertEqual(project["name"], "Storefront")
        self.assertEqual(
            project["submissions"],
            [
                {
                    "id": str(submission.pk),
                    "created_at": submission.created_at.isoformat(),
                    "schema_version": submission.schema_version,
                    "client_version": submission.client_version,
                    "python_version": submission.python_version,
                    "django_version": "5.2.1",
                    "files_scanned": submission.files_scanned,
                    "probe_sources": submission.probe_sources,
                    "patterns": submission.patterns,
                    "usage_packages": submission.usage_packages,
                    "usage": submission.usage,
                    "dependencies": submission.dependencies,
                    "dependencies_source": submission.dependencies_source,
                    "django_settings": submission.django_settings,
                    "django_settings_scanned": submission.django_settings_scanned,
                }
            ],
        )

    def test_omits_project_tokens(self):
        SubmissionFactory(project=self.project)

        self.assertNotIn(self.project.token, self.body())

    def test_omits_other_peoples_organizations(self):
        other_organization = OrganizationFactory(
            name="Other team", owner=self.other_user
        )
        ProjectFactory(organization=other_organization, name="Other project")

        body = self.body()

        self.assertNotIn("Other team", body)
        self.assertNotIn("Other project", body)

    def test_omits_the_other_members_of_a_shared_organization(self):
        """A shared organization is exported for the member asking, without the
        usernames and roles of everyone else in it."""
        OrganizationMembershipFactory(
            organization=self.organization, user=UserFactory(username="teammate-zed")
        )

        body = self.body()

        self.assertIn("Django team", body)
        self.assertNotIn("teammate-zed", body)

    def test_includes_credentials_without_their_digests(self):
        credential, token = issue_cli_credential(
            user=self.user, organization=self.organization, label="laptop"
        )
        CliCredentialFactory(user=self.other_user, label="someone-elses")

        document = self.export()

        self.assertEqual(
            [entry["label"] for entry in document["cli_credentials"]], ["laptop"]
        )
        self.assertEqual(document["cli_credentials"][0]["status"], "active")
        self.assertEqual(document["cli_credentials"][0]["organization"], "Django team")
        serialized = json.dumps(document)
        self.assertNotIn(token, serialized)
        self.assertNotIn(credential.token_digest, serialized)

    def test_rejects_a_post(self):
        response = self.client.post(reverse("account-export"))

        self.assertEqual(response.status_code, 405)

    def test_submissions_are_read_in_chunks(self):
        """One query per project rather than one per submission, so streaming did
        not trade a buffered response for an N+1."""
        for _ in range(5):
            SubmissionFactory(project=self.project)

        with self.assertNumQueries(7):
            self.body()


class JsonStreamTests(SimpleTestCase):
    def test_matches_json_dumps(self):
        """Streaming changed how the file is written, not what it contains."""
        document = {
            "quoting": 'a "b" \\ c',
            "unicode": "caf\u00e9",
            "scalars": [1, 2.5, True, False, None],
            "empty": {"object": {}, "list": []},
            "nested": {"a": {"b": [{"c": ["d"]}]}},
        }

        self.assertEqual("".join(iter_json(document)), json.dumps(document, indent=2))

    def test_an_iterable_stands_in_for_a_list(self):
        streamed = "".join(iter_json({"items": (number for number in range(3))}))

        self.assertEqual(streamed, json.dumps({"items": [0, 1, 2]}, indent=2))

    def test_pulls_items_only_as_it_writes_them(self):
        pulled = []

        def items():
            for number in range(3):
                pulled.append(number)
                yield number

        stream = iter_json({"items": items()})
        while "0" not in next(stream):
            pass

        self.assertEqual(pulled, [0])


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

    @override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_PROVIDER_SETTINGS)
    def test_socialaccount_connections(self):
        """Connected identities use the repository-owned management template."""
        user = UserFactory(username="owner")
        account = SocialAccount.objects.create(
            user=user,
            provider="github",
            uid="123",
            extra_data={"login": "octocat"},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("socialaccount_connections"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "socialaccount/connections.html")
        self.assertContains(response, "octocat")
        self.assertContains(response, "Disconnect selected account")
        self.assertContains(response, f'value="{account.pk}"')

    @override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_PROVIDER_SETTINGS)
    def test_disconnect_socialaccount(self):
        user = UserFactory(username="owner")
        account = SocialAccount.objects.create(
            user=user,
            provider="github",
            uid="123",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("socialaccount_connections"), {"account": account.pk}
        )

        self.assertRedirects(
            response,
            reverse("socialaccount_connections"),
            fetch_redirect_response=False,
        )
        self.assertFalse(SocialAccount.objects.filter(pk=account.pk).exists())


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
    def test_home_setup_precedes_workflow(self):
        """Landing-page setup commands appear before the workflow example."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertContains(response, "uvx django-probe init")
        self.assertContains(response, "uvx django-probe scan .")
        self.assertContains(response, "${{ secrets.DJANGO_PROBE_TOKEN }}")
        self.assertLess(
            content.index("uvx django-probe init"),
            content.index("Add it to CI"),
        )

    def test_home_project_count_counts_distinct_projects_with_submissions(self):
        """The landing page counts projects with at least one submission, not all projects."""
        organization = OrganizationFactory()
        project_with_submissions = ProjectFactory(organization=organization)
        ProjectFactory(organization=organization)
        SubmissionFactory(project=project_with_submissions)
        SubmissionFactory(project=project_with_submissions)
        SubmissionFactory(project=None)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.context["project_count"], 1)
        self.assertContains(response, "Project Sharing")

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
