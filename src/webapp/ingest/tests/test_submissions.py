from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import override_settings

from ingest.models import ApiToken, Submission
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
        self.assertEqual(Submission.objects.get().project_key, key)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class TokenTests(IngestTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("dev")
        self.token = ApiToken.objects.create(user=self.user)

    def test_attaches_to_account(self):
        response = self.post(payload(), HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Submission.objects.get().user, self.user)

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
