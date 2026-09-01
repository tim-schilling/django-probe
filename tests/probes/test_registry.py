from __future__ import annotations

from unittest import TestCase

from django_upgrade.data import FIXERS

from django_probe.ast_probe import probe_names
from tests.probes.helpers import counts


class RegistryTests(TestCase):
    def test_upgrade_fixers_excluded(self):
        """django-upgrade's fixers self-register on import, so filtering must hold.

        Counting them would measure codemod adoption rather than API usage.
        """
        self.assertIn("on_delete", FIXERS)
        self.assertNotIn("on_delete", probe_names())

        result = counts(
            """
            from django.db import models

            class Book(models.Model):
                author = models.ForeignKey("Author")

                class Meta:
                    index_together = [["author"]]
            """,
            filename="models.py",
        )
        self.assertEqual(result, {})

    def test_names_have_no_separator(self):
        """The ':' separator is reserved for the namespace prefix."""
        for name in probe_names():
            self.assertNotIn(":", name)
