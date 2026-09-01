from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import override_settings

from ingest.models import ApiToken, Organization, Project, Submission
from ingest.tests.helpers import IngestTestCase, payload


class AnonymousSubmissionTests(IngestTestCase):
    def test_accepted(self):
        response = self.post(payload())

        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertIsNone(submission.user)
        self.assertEqual(submission.patterns, {"probe:queryset_filter": 3})
        self.assertEqual(submission.files_scanned, 12)

    def test_project_key_stored(self):
        key = uuid.uuid4()

        self.assertEqual(self.post(payload(project_key=str(key))).status_code, 201)
        submission = Submission.objects.get()
        self.assertEqual(submission.project_key, key)
        self.assertIsNone(submission.project)

    def test_registered_project_is_unassigned(self):
        """Anonymous submissions cannot claim a registered project by knowing its key."""
        owner = User.objects.create_user("owner")
        organization = Organization.objects.create_with_owner(
            name="Django team", owner=owner
        )
        project = Project.objects.create(organization=organization, name="Website")

        response = self.post(payload(project_key=str(project.key)))

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(Submission.objects.get().project)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class TokenTests(IngestTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("dev")
        cls.token = ApiToken.objects.create(user=cls.user)

    def setUp(self):
        super().setUp()

    def test_attaches_to_account(self):
        response = self.post(payload(), HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Submission.objects.get().user, self.user)

    def test_registered_project(self):
        """An authenticated organization member can submit to its project."""
        organization = Organization.objects.create_with_owner(
            name="Django team", owner=self.user
        )
        project = Project.objects.create(organization=organization, name="Website")

        response = self.post(
            payload(project_key=str(project.key)),
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Submission.objects.get().project, project)

    def test_unknown_project(self):
        """Authenticated submissions cannot use an unregistered project key."""
        response = self.post(
            payload(project_key=str(uuid.uuid4())),
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.count(), 0)

    def test_inaccessible_project(self):
        """Authenticated submissions cannot target another organization's project."""
        other_user = User.objects.create_user("other")
        organization = Organization.objects.create_with_owner(
            name="Other team", owner=other_user
        )
        project = Project.objects.create(organization=organization, name="Private")

        response = self.post(
            payload(project_key=str(project.key)),
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.count(), 0)

    def test_unknown_token_rejected(self):
        """A wrong token is an error, not a silent downgrade to anonymous."""
        response = self.post(payload(), HTTP_AUTHORIZATION="Token nope")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Submission.objects.count(), 0)

    def test_malformed_header_rejected(self):
        response = self.post(payload(), HTTP_AUTHORIZATION="Bearer something")
        self.assertEqual(response.status_code, 401)


class ForwardCompatibilityTests(IngestTestCase):
    def test_unknown_namespace_stored_verbatim(self):
        """Third-party probes must work without a server release.

        Pins the decision that pattern keys are never checked against a known
        vocabulary, so adding such validation fails here rather than silently
        dropping every third-party package's data.
        """
        patterns = {
            "probe:queryset_filter": 1,
            "somepkg:a_pattern_invented_tomorrow": 7,
        }
        response = self.post(payload(patterns=patterns))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Submission.objects.get().patterns, patterns)


@override_settings(SOCIALACCOUNT_PROVIDERS={})
class AccountsOptionalTests(IngestTestCase):
    def test_works_without_github_credentials(self):
        """A deployment that never configures allauth is a valid deployment."""
        self.assertEqual(self.post(payload()).status_code, 201)
