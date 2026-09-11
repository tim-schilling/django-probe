from __future__ import annotations

from django.test import override_settings
from django.urls import reverse

from ingest.models import Submission
from ingest.tests.factories import (
    OrganizationFactory,
    ProjectFactory,
    UserFactory,
)
from ingest.tests.helpers import IngestTestCase, payload


class AnonymousSubmissionTests(IngestTestCase):
    def test_accepted(self):
        response = self.post(payload())

        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertEqual(submission.patterns, {"probe:queryset_filter": 3})
        self.assertEqual(submission.usage_packages, [])
        self.assertEqual(submission.usage, {})
        self.assertEqual(submission.django_settings, {})
        self.assertEqual(submission.files_scanned, 12)

    def test_body_token_field_is_ignored(self):
        """Only the Authorization header can attribute a submission to a project."""
        owner = UserFactory(username="owner")
        organization = OrganizationFactory(name="Django team", owner=owner)
        project = ProjectFactory(organization=organization, name="Website")

        response = self.post(payload(token=project.token))

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(Submission.objects.get().project)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class ProjectTokenTests(IngestTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.owner)
        cls.project = ProjectFactory(organization=cls.organization, name="Website")

    def test_registered_project(self):
        response = self.post(
            payload(), HTTP_AUTHORIZATION=f"Token {self.project.token}"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Submission.objects.get().project, self.project)
        submission = Submission.objects.get()
        self.assertEqual(submission.pk.version, 7)

    def test_unknown_token_rejected(self):
        """A wrong token is an error, not a silent downgrade to anonymous."""
        response = self.post(payload(), HTTP_AUTHORIZATION="Token nope")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Submission.objects.count(), 0)

    def test_malformed_header_rejected(self):
        response = self.post(payload(), HTTP_AUTHORIZATION="Bearer something")
        self.assertEqual(response.status_code, 401)


class SubmissionDetailTests(IngestTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = UserFactory(username="member")
        cls.outsider = UserFactory(username="outsider")
        cls.organization = OrganizationFactory(owner=cls.member)
        cls.project = ProjectFactory(organization=cls.organization)
        cls.submission = Submission.objects.create(
            project=cls.project,
            **payload(),
        )

    def test_member_can_view_detail(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse("submission-detail", args=[self.submission.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "probe:queryset_filter")

    def test_package_usage_is_displayed(self):
        self.submission.usage_packages = ["django"]
        self.submission.usage = {"django.shortcuts.render": 2}
        self.submission.save(update_fields=["usage_packages", "usage"])
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("submission-detail", args=[self.submission.pk])
        )

        self.assertContains(response, "Configured packages: django")
        self.assertContains(response, "django.shortcuts.render")

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        response = self.client.get(
            reverse("submission-detail", args=[self.submission.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_redirects(self):
        response = self.client.get(
            reverse("submission-detail", args=[self.submission.pk])
        )
        self.assertEqual(response.status_code, 302)

    def test_project_deletion_revokes_detail_access(self):
        """A retained submission's organization link is not recoverable."""
        submission_id = self.submission.pk
        self.project.delete()
        self.client.force_login(self.member)
        response = self.client.get(reverse("submission-detail", args=[submission_id]))
        self.assertEqual(response.status_code, 404)


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
