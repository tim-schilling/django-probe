from __future__ import annotations

import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config import environment


class EnvironmentNameTests(SimpleTestCase):
    def test_defaults_to_dev(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(environment.name(), "dev")
            self.assertIs(environment.is_production(), False)

    def test_reads_the_environment_variable(self):
        with mock.patch.dict(os.environ, {"DJANGO_PROBE_ENVIRONMENT": "staging"}):
            self.assertEqual(environment.name(), "staging")
            self.assertIs(environment.is_production(), False)

    def test_production_is_exact(self):
        for value, expected in [
            ("production", True),
            ("Production", False),
            ("production ", False),
            ("prod", False),
        ]:
            with (
                self.subTest(value=value),
                mock.patch.dict(os.environ, {"DJANGO_PROBE_ENVIRONMENT": value}),
            ):
                self.assertIs(environment.is_production(), expected)


class RequiredTests(SimpleTestCase):
    def test_returns_the_configured_value(self):
        with mock.patch.dict(os.environ, {"DJANGO_PROBE_SECRET_KEY": "from-the-env"}):
            self.assertEqual(
                environment.required("DJANGO_PROBE_SECRET_KEY", default="fallback"),
                "from-the-env",
            )

    def test_falls_back_outside_production(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                environment.required("DJANGO_PROBE_SECRET_KEY", default="fallback"),
                "fallback",
            )

    def test_missing_in_production_fails_fast(self):
        with (
            mock.patch.dict(
                os.environ, {"DJANGO_PROBE_ENVIRONMENT": "production"}, clear=True
            ),
            self.assertRaisesMessage(
                ImproperlyConfigured,
                "DJANGO_PROBE_SECRET_KEY must be set when "
                "DJANGO_PROBE_ENVIRONMENT=production.",
            ),
        ):
            environment.required("DJANGO_PROBE_SECRET_KEY", default="fallback")

    def test_empty_in_production_fails_fast(self):
        environ = {"DJANGO_PROBE_ENVIRONMENT": "production", "DJANGO_PROBE_HOSTS": ""}
        with (
            mock.patch.dict(os.environ, environ, clear=True),
            self.assertRaises(ImproperlyConfigured),
        ):
            environment.required("DJANGO_PROBE_HOSTS", default="*")

    def test_configured_value_is_used_in_production(self):
        environ = {
            "DJANGO_PROBE_ENVIRONMENT": "production",
            "DJANGO_PROBE_ALLOWED_HOSTS": "djangoprobe.org",
        }
        with mock.patch.dict(os.environ, environ, clear=True):
            self.assertEqual(
                environment.required("DJANGO_PROBE_ALLOWED_HOSTS", default="*"),
                "djangoprobe.org",
            )
