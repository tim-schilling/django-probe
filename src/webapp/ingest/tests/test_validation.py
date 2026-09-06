from __future__ import annotations

from typing import Any

from ingest.models import Submission
from ingest.tests.helpers import IngestTestCase, payload
from ingest.validation import MAX_USAGE, MAX_USAGE_PACKAGES


class ValidationTests(IngestTestCase):
    """Plausibility bounds: numbers that cannot describe a real codebase."""

    def assertRejected(self, body: Any) -> None:
        response = self.post(body)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Submission.objects.count(), 0)

    def test_malformed_json(self):
        response = self.client.post(
            self.url, data="{not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_unsupported_schema_version(self):
        self.assertRejected(payload(schema_version=99))

    def test_non_integer_count(self):
        self.assertRejected(payload(patterns={"probe:queryset_filter": "many"}))

    def test_out_of_range_count(self):
        self.assertRejected(payload(patterns={"probe:queryset_filter": -1}))
        self.assertRejected(payload(patterns={"probe:queryset_filter": 10**9}))

    def test_unnamespaced_pattern_key(self):
        self.assertRejected(payload(patterns={"queryset_filter": 1}))
        self.assertRejected(payload(patterns={"a:b:c": 1}))

    def test_implausible_file_count(self):
        self.assertRejected(payload(files_scanned=10**7))

    def test_too_many_dependencies(self):
        self.assertRejected(
            payload(dependencies={f"pkg{i}": "1.0" for i in range(2001)})
        )

    def test_invalid_django_settings(self):
        self.assertRejected(payload(django_settings={"DEBUG": "yes"}))
        self.assertRejected(payload(django_settings_scanned="yes"))

    def test_invalid_usage_packages(self):
        self.assertRejected(payload(usage_packages="django"))
        self.assertRejected(payload(usage_packages=[{"django": 1}]))
        self.assertRejected(payload(usage_packages=["django.contrib"]))
        self.assertRejected(payload(usage_packages=["django", "django"]))
        self.assertRejected(
            payload(
                usage_packages=[
                    f"package_{index}" for index in range(MAX_USAGE_PACKAGES + 1)
                ]
            )
        )

    def test_invalid_usage(self):
        self.assertRejected(
            payload(
                usage_packages=["django"],
                usage={"django.shortcuts.render": "many"},
            )
        )
        self.assertRejected(
            payload(
                usage_packages=["django"],
                usage={"application.internal_name": 1},
            )
        )

    def test_valid_usage(self):
        response = self.post(
            payload(
                usage_packages=["django"],
                usage={"django.shortcuts.render": 2},
            )
        )

        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertEqual(submission.usage_packages, ["django"])
        self.assertEqual(submission.usage, {"django.shortcuts.render": 2})

    def test_too_many_usage_entries(self):
        self.assertRejected(
            payload(
                usage_packages=["django"],
                usage={f"django.api_{index}": 1 for index in range(MAX_USAGE + 1)},
            )
        )

    def test_oversized_body(self):
        response = self.post(payload(client_version="x" * 300_000))
        self.assertEqual(response.status_code, 413)
