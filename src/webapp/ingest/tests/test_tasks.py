from __future__ import annotations

from datetime import timedelta
from email.message import Message
from io import BytesIO
from unittest import mock
from urllib.error import HTTPError

from django.test import TestCase
from django.utils import timezone

from ingest.models import PyPIPackage
from ingest.stats import MINIMUM_PROJECTS
from ingest.tasks import (
    MAX_ATTEMPTS,
    RETRY_AFTER,
    check_pypi_packages,
    is_published,
)
from ingest.tests.factories import (
    ProjectFactory,
    SubmissionFactory,
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
