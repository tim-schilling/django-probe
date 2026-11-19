from __future__ import annotations

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from ingest.tests.factories import SubmissionFactory

drop_undefined_django_usage = import_module(
    "ingest.migrations.0017_drop_undefined_django_usage"
)


class DropUndefinedDjangoUsageTests(TestCase):
    def test_drop_undefined_usage(self):
        """Undefined Django names are removed from stored submissions."""
        submission = SubmissionFactory(
            usage_packages=["django", "ninja"],
            usage={
                "django.shortcuts.render": 2,
                "django.conf.settings.DEBUG": 1,
                "django.contrib.auth.models.User.private_profile": 3,
                "ninja.Router.private_hook": 1,
            },
        )

        drop_undefined_django_usage.drop_undefined_usage(apps, None)

        submission.refresh_from_db()
        self.assertEqual(
            submission.usage,
            {
                "django.shortcuts.render": 2,
                "django.conf.settings.DEBUG": 1,
                "ninja.Router.private_hook": 1,
            },
        )
