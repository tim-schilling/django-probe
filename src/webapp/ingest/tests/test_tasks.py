from __future__ import annotations

from datetime import timedelta
from email.message import Message
from io import BytesIO
from unittest import mock
from urllib.error import HTTPError

from django.test import TestCase
from django.utils import timezone

from ingest.models import CliCredential, PyPIPackage
from ingest.stats import MINIMUM_PROJECTS
from ingest.tasks import (
    MAX_ATTEMPTS,
    RETRY_AFTER,
    check_pypi_packages,
    is_published,
    purge_cli_credentials,
)
from ingest.tests.factories import (
    CliCredentialFactory,
    OrganizationFactory,
    ProjectFactory,
    SubmissionFactory,
    UserFactory,
    issue_cli_credential,
)

Status = PyPIPackage.Status


def http_error(code: int) -> HTTPError:
    return HTTPError("https://pypi.org/simple/", code, "", Message(), BytesIO())


class IsPublishedTests(TestCase):
    @mock.patch("ingest.tasks.urlopen")
    def test_published(self, urlopen):
        self.assertTrue(is_published("celery"))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://pypi.org/simple/celery/")
        self.assertEqual(request.get_method(), "HEAD")

    @mock.patch("ingest.tasks.urlopen", side_effect=http_error(404))
    def test_missing(self, urlopen):
        self.assertFalse(is_published("acme-internal"))

    @mock.patch("ingest.tasks.urlopen", side_effect=http_error(503))
    def test_error(self, urlopen):
        """Anything but a 404 says nothing about the package, so it's raised."""
        with self.assertRaises(HTTPError):
            is_published("celery")


def pypi(name: str) -> bool:
    if name == "flaky":
        raise TimeoutError
    return name in {"celery", "sentry-sdk"}


class CheckPyPIPackagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        names = [
            "Celery",
            "acme-internal",
            "excluded",
            "flaky",
            "psycopg",
            "recent",
            "sentry-sdk",
        ]
        for _ in range(MINIMUM_PROJECTS):
            SubmissionFactory(
                project=ProjectFactory(),
                dependencies={"django": "5.1.2", **dict.fromkeys(names, "1.0")},
            )
        SubmissionFactory(
            project=ProjectFactory(), dependencies={"django": "5.1.2", "rare": "1.0"}
        )
        due = timezone.now() - RETRY_AFTER
        PyPIPackage.objects.filter(name="psycopg").update(status=Status.PUBLISHED)
        PyPIPackage.objects.filter(name="excluded").update(status=Status.EXCLUDED)
        PyPIPackage.objects.filter(name="sentry-sdk").update(attempts=1, checked_at=due)
        PyPIPackage.objects.filter(name="flaky").update(
            attempts=MAX_ATTEMPTS - 1, checked_at=due
        )
        PyPIPackage.objects.filter(name="recent").update(
            attempts=1, checked_at=due + timedelta(days=1)
        )

    @mock.patch("ingest.tasks.is_published", side_effect=pypi)
    def test_check(self, is_published):
        """Only pending packages that are due and used by the minimum are checked.

        Failures count as attempts, and the last one marks the package missing.
        """
        with self.assertLogs("ingest.tasks", "WARNING"):
            check_pypi_packages.call()

        self.assertCountEqual(
            [call.args[0] for call in is_published.call_args_list],
            ["acme-internal", "celery", "flaky", "sentry-sdk"],
        )
        self.assertEqual(
            {
                name: (status, attempts)
                for name, status, attempts in PyPIPackage.objects.values_list(
                    "name", "status", "attempts"
                )
            },
            {
                "acme-internal": (Status.PENDING, 1),
                "celery": (Status.PUBLISHED, 1),
                "django": (Status.PENDING, 0),
                "excluded": (Status.EXCLUDED, 0),
                "flaky": (Status.MISSING, MAX_ATTEMPTS),
                "psycopg": (Status.PUBLISHED, 0),
                "rare": (Status.PENDING, 0),
                "recent": (Status.PENDING, 1),
                "sentry-sdk": (Status.PUBLISHED, 2),
            },
        )


def _aged(credential: CliCredential, days: int) -> CliCredential:
    """Backdate `created_at`, which is auto_now_add and so can't be set on create."""
    return _backdate(credential, created_at=days)


def _backdate(credential: CliCredential, **fields: int) -> CliCredential:
    """Set each named timestamp to the given number of days ago."""
    now = timezone.now()
    CliCredential.objects.filter(pk=credential.pk).update(
        **{name: now - timedelta(days=days) for name, days in fields.items()}
    )
    return credential


class PurgeCliCredentialsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.user)

    def credential(self) -> tuple[CliCredential, str]:
        return issue_cli_credential(organization=self.organization, user=self.user)

    def purge(self) -> None:
        with self.assertLogs("ingest.tasks", "INFO"):
            purge_cli_credentials.call()

    def test_deletes_requests_older_than_the_retention_window(self):
        stale = _aged(CliCredentialFactory(), days=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=stale.pk).exists())

    def test_keeps_recent_requests(self):
        recent = _aged(CliCredentialFactory(), days=1)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=recent.pk).exists())

    def test_keeps_pending_requests(self):
        pending = CliCredentialFactory()

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=pending.pk).exists())

    def test_never_deletes_an_active_credential(self):
        """A credential still within its lifetime stays however old the row is;
        deleting one would silently break a working CLI install."""
        credential, _ = self.credential()
        _aged(credential, days=365)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_deletes_long_expired_credentials(self):
        credential, _ = self.credential()
        _backdate(credential, created_at=120, token_expires_at=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_deletes_long_revoked_credentials(self):
        credential, _ = self.credential()
        _backdate(credential, created_at=30, revoked_at=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_keeps_recently_dead_credentials(self):
        """The account page shows expired and revoked devices, so a window's worth
        of them stays around for someone auditing a lost laptop."""
        expired, _ = self.credential()
        _backdate(expired, created_at=90, token_expires_at=1)
        revoked, _ = self.credential()
        _backdate(revoked, created_at=30, revoked_at=1)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=expired.pk).exists())
        self.assertTrue(CliCredential.objects.filter(pk=revoked.pk).exists())

    def test_deletes_denied_requests(self):
        denied = _aged(CliCredentialFactory(denied_at=timezone.now()), days=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=denied.pk).exists())
