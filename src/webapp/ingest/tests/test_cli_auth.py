from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ingest.models import CLI_AUTH_REQUEST_TTL
from ingest.tests.factories import CliCredentialFactory


class CliCredentialModelTests(TestCase):
    def test_code_generated_on_create(self):
        credential = CliCredentialFactory()

        self.assertTrue(credential.code)

    def test_code_is_unique(self):
        first = CliCredentialFactory()
        second = CliCredentialFactory()

        self.assertNotEqual(first.code, second.code)

    def test_defaults_to_pending(self):
        credential = CliCredentialFactory()

        self.assertIsNone(credential.token)
        self.assertIsNone(credential.denied_at)
        self.assertGreater(credential.expires_at, timezone.now())

    def test_expires_after_the_request_ttl(self):
        credential = CliCredentialFactory()

        expected = credential.created_at + CLI_AUTH_REQUEST_TTL
        self.assertLess(abs(credential.expires_at - expected), timedelta(seconds=5))
