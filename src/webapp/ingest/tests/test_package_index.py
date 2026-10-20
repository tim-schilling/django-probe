from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase

from ingest.package_index import (
    DJANGO_FRAMEWORK_CLASSIFIER,
    PACKAGE_INDEX_URL,
    PackageInfo,
    _package_info,
    package_info,
)


class PackageIndexTests(SimpleTestCase):
    def setUp(self):
        _package_info.cache_clear()
        self.addCleanup(_package_info.cache_clear)

    def respond(self, urlopen, classifiers=(), error: Exception | None = None):
        if error is not None:
            urlopen.side_effect = error
            return
        body = json.dumps({"info": {"classifiers": list(classifiers)}}).encode()
        urlopen.return_value.__enter__.return_value = BytesIO(body)

    def http_error(self, code: int, message: str) -> HTTPError:
        """An error that is closed after the test, unlike a real response."""
        error = HTTPError("https://pypi.org", code, message, {}, BytesIO())
        self.addCleanup(error.close)
        return error

    @patch("ingest.package_index.urlopen")
    def test_django_package(self, urlopen):
        self.respond(urlopen, [DJANGO_FRAMEWORK_CLASSIFIER, "License :: OSI Approved"])

        self.assertEqual(package_info("celery"), PackageInfo(is_django=True))
        self.assertEqual(package_info("celery"), PackageInfo(is_django=True))

        urlopen.assert_called_once()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://pypi.org/pypi/celery/json")
        self.assertEqual(request.get_header("User-agent"), "django-probe")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2)

    @patch("ingest.package_index.urlopen")
    def test_other_package(self, urlopen):
        self.respond(urlopen, ["License :: OSI Approved"])

        self.assertEqual(package_info("celery"), PackageInfo(is_django=False))
        self.assertEqual(package_info("celery"), PackageInfo(is_django=False))

        urlopen.assert_called_once()

    @patch("ingest.package_index.urlopen")
    def test_name_is_quoted(self, urlopen):
        self.respond(urlopen)

        package_info("some package")

        self.assertEqual(
            urlopen.call_args.args[0].full_url,
            PACKAGE_INDEX_URL.format(name="some%20package"),
        )

    @patch("ingest.package_index.urlopen")
    def test_not_found(self, urlopen):
        self.respond(urlopen, error=self.http_error(404, "Not Found"))

        self.assertIsNone(package_info("celery"))
        self.assertIsNone(package_info("celery"))

        urlopen.assert_called_once()

    @patch("ingest.package_index.urlopen")
    def test_http_error(self, urlopen):
        self.respond(urlopen, error=self.http_error(503, "Service Unavailable"))

        with self.assertLogs("ingest.package_index", "WARNING") as logs:
            self.assertIsNone(package_info("celery"))
            self.assertIsNone(package_info("celery"))

        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("HTTPError", logs.output[0])

    @patch("ingest.package_index.urlopen")
    def test_network_error(self, urlopen):
        self.respond(urlopen, error=URLError("offline"))

        with self.assertLogs("ingest.package_index", "WARNING") as logs:
            self.assertIsNone(package_info("celery"))
            self.assertIsNone(package_info("celery"))

        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("URLError", logs.output[0])

    @patch("ingest.package_index.urlopen")
    def test_invalid_response(self, urlopen):
        urlopen.return_value.__enter__.return_value = BytesIO(b"<html>")

        with self.assertLogs("ingest.package_index", "WARNING") as logs:
            self.assertIsNone(package_info("celery"))

        self.assertIn("JSONDecodeError", logs.output[0])
