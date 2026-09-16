from __future__ import annotations

from unittest import TestCase

from django import VERSION as DJANGO_VERSION
from django.conf import global_settings

from django_probe.settings import DJANGO_SETTING_NAMES_BY_VERSION


class DjangoSettingCatalogTests(TestCase):
    def test_installed_settings(self):
        """The installed Django release matches its committed setting catalog."""
        version = ".".join(str(part) for part in DJANGO_VERSION[:2])

        self.assertIn(version, DJANGO_SETTING_NAMES_BY_VERSION)
        self.assertEqual(
            frozenset(name for name in vars(global_settings) if name.isupper()),
            DJANGO_SETTING_NAMES_BY_VERSION[version],
        )
