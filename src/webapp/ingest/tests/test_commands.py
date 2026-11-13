from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from django_probe.settings import DJANGO_SETTING_NAMES_BY_VERSION
from ingest.management.commands.seed_data import DEPENDENCY_NAMES, USAGE_NAMES
from ingest.models import PyPIPackage, Submission
from ingest.stats import POPULAR_LIMIT, Cohort, KeySource


class SeedDataTests(TestCase):
    def test_seeds_settings_and_usage(self):
        """One run gives the stats pages settings, APIs and dependencies to show."""
        call_command("seed_data", stdout=StringIO())

        submissions = Submission.objects.all()
        self.assertTrue(submissions.exists())
        for submission in submissions:
            major, minor, *_ = submission.django_version.split(".")
            self.assertLessEqual(
                set(submission.django_settings),
                DJANGO_SETTING_NAMES_BY_VERSION[f"{major}.{minor}"],
            )
            self.assertLessEqual(set(submission.usage), set(USAGE_NAMES))
            self.assertEqual(
                submission.dependencies["django"], submission.django_version
            )

        popular = Cohort({}).overview()["popular"]
        self.assertEqual(len(popular[KeySource.SETTING]), POPULAR_LIMIT)
        self.assertEqual(len(popular[KeySource.USAGE]), POPULAR_LIMIT)
        self.assertCountEqual(
            PyPIPackage.objects.filter(status=PyPIPackage.Status.PUBLISHED).values_list(
                "name", flat=True
            ),
            DEPENDENCY_NAMES,
        )
