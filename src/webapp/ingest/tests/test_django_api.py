from __future__ import annotations

from unittest import TestCase

from django import VERSION as DJANGO_VERSION

from ingest.django_api import (
    DJANGO_API_VERSIONS,
    _combined_api_names,
    _read_api_names,
    is_django_api_name,
)


class DjangoAPICatalogTests(TestCase):
    def test_installed_api(self):
        version = ".".join(str(part) for part in DJANGO_VERSION[:2])
        names = set(_read_api_names(version))

        self.assertIn(version, DJANGO_API_VERSIONS)
        self.assertTrue(
            {
                "django.contrib.admin.site.register",
                "django.core.cache.cache.get",
                "django.db.connection.cursor",
                "django.db.models.CharField",
                "django.db.models.Model.save",
                "django.db.transaction.atomic",
                "django.shortcuts.get_object_or_404",
                "django.utils.timezone.now",
            }
            <= names
        )
        self.assertFalse(
            any(part.startswith("_") for name in names for part in name.split(".")[1:])
        )

    def test_catalog_versions(self):
        self.assertEqual(
            DJANGO_API_VERSIONS,
            (
                "2.2",
                "3.0",
                "3.1",
                "3.2",
                "4.0",
                "4.1",
                "4.2",
                "5.0",
                "5.1",
                "5.2",
                "6.0",
                "6.1",
                "6.2",
            ),
        )

    def test_combined_catalog(self):
        _combined_api_names.cache_clear()
        self.addCleanup(_combined_api_names.cache_clear)

        names = _combined_api_names()
        expected = tuple(
            sorted(
                {
                    name
                    for version in DJANGO_API_VERSIONS
                    for name in _read_api_names(version)
                }
            )
        )

        self.assertEqual(names, expected)
        self.assertEqual(len(names), 47819)
        self.assertTrue(is_django_api_name("django.shortcuts.render"))
        # Removed in Django 4.0, but still used by projects on older releases.
        self.assertTrue(is_django_api_name("django.conf.urls.url"))
        self.assertFalse(is_django_api_name("django.my_random.offensive_statement"))

    def test_common_usage_paths(self):
        expected = {
            "django.contrib.admin.site.register",
            "django.core.cache.cache.get",
            "django.core.cache.cache.set",
            "django.db.connection.cursor",
            "django.db.transaction.atomic",
            "django.db.transaction.on_commit",
        }
        for version in DJANGO_API_VERSIONS:
            self.assertLessEqual(expected, set(_read_api_names(version)))

    def test_catalog_counts(self):
        self.assertEqual(
            {version: len(_read_api_names(version)) for version in DJANGO_API_VERSIONS},
            {
                "2.2": 33296,
                "3.0": 33121,
                "3.1": 34233,
                "3.2": 35090,
                "4.0": 35920,
                "4.1": 37044,
                "4.2": 38325,
                "5.0": 38978,
                "5.1": 39413,
                "5.2": 40552,
                "6.0": 41326,
                "6.1": 42166,
                "6.2": 42272,
            },
        )
