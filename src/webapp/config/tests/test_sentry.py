from __future__ import annotations

import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from sentry_sdk.integrations.django import DjangoIntegration

from config.sentry import DEFAULT_TRACES_SAMPLE_RATE, initialize_sentry


class SentryConfigurationTests(SimpleTestCase):
    @mock.patch("config.sentry.sentry_sdk.init")
    def test_no_dsn_disables_sentry(self, init):
        with mock.patch.dict(os.environ, {}, clear=True):
            enabled = initialize_sentry()

        self.assertIs(enabled, False)
        init.assert_not_called()

    @mock.patch("config.sentry.sentry_sdk.init")
    def test_blank_dsn_disables_sentry(self, init):
        with mock.patch.dict(os.environ, {"SENTRY_DSN": "  "}, clear=True):
            enabled = initialize_sentry()

        self.assertIs(enabled, False)
        init.assert_not_called()

    @mock.patch("config.sentry.sentry_sdk.init")
    def test_dsn_enables_error_and_performance_monitoring(self, init):
        environment = {
            "SENTRY_DSN": "https://public@example.invalid/1",
            "DJANGO_PROBE_ENVIRONMENT": "staging",
            "SENTRY_RELEASE": "django-probe@abc123",
            "SENTRY_TRACES_SAMPLE_RATE": "0.25",
        }

        with mock.patch.dict(os.environ, environment, clear=True):
            enabled = initialize_sentry()

        self.assertIs(enabled, True)
        init.assert_called_once()
        options = init.call_args.kwargs
        self.assertEqual(options["dsn"], environment["SENTRY_DSN"])
        self.assertEqual(options["environment"], "staging")
        self.assertEqual(options["release"], "django-probe@abc123")
        self.assertEqual(options["traces_sample_rate"], 0.25)
        self.assertIs(options["send_default_pii"], False)
        self.assertEqual(options["max_request_body_size"], "never")
        self.assertEqual(len(options["integrations"]), 1)
        integration = options["integrations"][0]
        self.assertIsInstance(integration, DjangoIntegration)
        self.assertEqual(integration.transaction_style, "url")
        self.assertIs(integration.middleware_spans, True)
        self.assertIs(integration.signals_spans, True)
        self.assertIs(integration.cache_spans, True)

    @mock.patch("config.sentry.sentry_sdk.init")
    def test_trace_sample_rate_defaults_to_ten_percent(self, init):
        with mock.patch.dict(
            os.environ, {"SENTRY_DSN": "https://public@example.invalid/1"}, clear=True
        ):
            initialize_sentry()

        options = init.call_args.kwargs
        self.assertEqual(options["traces_sample_rate"], DEFAULT_TRACES_SAMPLE_RATE)
        self.assertEqual(options["environment"], "dev")
        self.assertIsNone(options["release"])

    @mock.patch("config.sentry.sentry_sdk.init")
    def test_invalid_trace_sample_rate_fails_fast(self, init):
        for sample_rate in ("invalid", "-0.1", "1.1", "nan", "inf"):
            with self.subTest(sample_rate=sample_rate):
                environment = {
                    "SENTRY_DSN": "https://public@example.invalid/1",
                    "SENTRY_TRACES_SAMPLE_RATE": sample_rate,
                }
                with (
                    mock.patch.dict(os.environ, environment, clear=True),
                    self.assertRaisesMessage(
                        ImproperlyConfigured,
                        "SENTRY_TRACES_SAMPLE_RATE must be a number between 0 and 1",
                    ),
                ):
                    initialize_sentry()

        init.assert_not_called()
