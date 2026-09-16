from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from django_probe.scan import scan_path
from django_probe.settings import (
    DJANGO_SETTING_NAMES,
    DJANGO_SETTING_NAMES_BY_VERSION,
    DJANGO_SETTINGS_VERSIONS,
)


class ScanPathTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, relative: str, source: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")

    def test_scans_migrations_and_survives_syntax_errors(self):
        source = "x = Book.objects.filter(a=1)\n"
        self.write("app/views.py", source)
        self.write("app/migrations/0001_initial.py", source)
        self.write("app/broken.py", "def oops(:\n")

        result = scan_path(self.root)

        self.assertEqual(result.files_scanned, 2)
        self.assertEqual(result.files_skipped, 1)
        self.assertEqual(result.patterns, {"probe:queryset_filter": 2})
        self.assertEqual(result.usage, {})
        self.assertEqual(result.usage_packages, ("django",))
        self.assertEqual(result.django_settings, {})
        self.assertTrue(result.django_settings_scanned)

    def test_migration_operations_do_not_inflate_counts(self):
        # `CreateModel`/`AddField` describe generated schema state, not something
        # anyone wrote by hand, so they must not be mistaken for real usage. A
        # `RunPython` data migration, by contrast, is hand-written and should count
        # like any other file.
        self.write(
            "app/migrations/0001_initial.py",
            """
            from django.db import migrations, models


            def backfill(apps, schema_editor):
                Book = apps.get_model("app", "Book")
                for book in Book.objects.filter(slug__isnull=True):
                    book.save()


            class Migration(migrations.Migration):
                operations = [
                    migrations.CreateModel(
                        name="Book",
                        fields=[
                            ("id", models.AutoField(primary_key=True)),
                            ("slug", models.SlugField(null=True)),
                        ],
                    ),
                    migrations.RunPython(backfill, migrations.RunPython.noop),
                ]
            """,
        )

        result = scan_path(self.root)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.files_skipped, 0)
        self.assertEqual(result.patterns, {"probe:queryset_filter": 1})
        self.assertEqual(
            result.usage,
            {
                "django.db.migrations": 1,
                "django.db.models": 1,
                "django.db.migrations.Migration": 1,
                "django.db.migrations.CreateModel": 1,
                "django.db.models.AutoField": 1,
                "django.db.models.SlugField": 1,
                "django.db.migrations.RunPython": 1,
                "django.db.migrations.RunPython.noop": 1,
            },
        )
        self.assertEqual(result.usage_packages, ("django",))
        self.assertEqual(result.django_settings, {})
        self.assertTrue(result.django_settings_scanned)

    def test_django_settings_only_include_known_module_level_names(self):
        (self.root / "pyproject.toml").write_text(
            "[tool.django_probe]\ndjango_settings = true\n",
            encoding="utf-8",
        )
        self.write(
            "config/settings/base.py",
            """
            DEBUG = False
            AUTH_USER_MODEL = "internal_accounts.PrivateUser"
            CSRF_COOKIE_MASKED = False
            TASKS = {}
            USE_BLANK_CHOICE_DASH = True
            INTERNAL_BILLING_REGION = "eu-west"
            THIRD_PARTY_API_TOKEN = "private-value"

            def configure():
                INSTALLED_APPS = ["internal_billing"]
            """,
        )

        result = scan_path(self.root)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.files_skipped, 0)
        self.assertEqual(result.patterns, {"probe:auth_user_model_setting": 1})
        self.assertTrue(result.django_settings_scanned)
        self.assertEqual(
            result.django_settings,
            {
                "DEBUG": 1,
                "AUTH_USER_MODEL": 1,
                "CSRF_COOKIE_MASKED": 1,
                "TASKS": 1,
                "USE_BLANK_CHOICE_DASH": 1,
            },
        )

    def test_catalog_versions(self):
        """The catalog records each supported and development feature release."""
        self.assertEqual(
            DJANGO_SETTINGS_VERSIONS,
            ("4.2", "5.0", "5.1", "5.2", "6.0", "6.1", "6.2"),
        )
        self.assertEqual(
            {
                version: len(names)
                for version, names in DJANGO_SETTING_NAMES_BY_VERSION.items()
            },
            {
                "4.2": 149,
                "5.0": 147,
                "5.1": 145,
                "5.2": 146,
                "6.0": 149,
                "6.1": 150,
                "6.2": 150,
            },
        )
        self.assertEqual(
            DJANGO_SETTING_NAMES,
            frozenset().union(*DJANGO_SETTING_NAMES_BY_VERSION.values()),
        )

    def test_catalog_changes(self):
        """Each release's catalog reflects its exact additions and removals."""
        changes = {
            ("4.2", "5.0"): (
                {"FORMS_URLFIELD_ASSUME_HTTPS"},
                {"CSRF_COOKIE_MASKED", "USE_DEPRECATED_PYTZ", "USE_L10N"},
            ),
            ("5.0", "5.1"): (
                set(),
                {"DEFAULT_FILE_STORAGE", "STATICFILES_STORAGE"},
            ),
            ("5.1", "5.2"): ({"SIGNED_COOKIE_LEGACY_SALT_FALLBACK"}, set()),
            ("5.2", "6.0"): (
                {
                    "SECURE_CSP",
                    "SECURE_CSP_REPORT_ONLY",
                    "TASKS",
                    "URLIZE_ASSUME_HTTPS",
                },
                {"FORMS_URLFIELD_ASSUME_HTTPS"},
            ),
            ("6.0", "6.1"): ({"USE_BLANK_CHOICE_DASH"}, set()),
            ("6.1", "6.2"): (set(), set()),
        }
        for (old_version, new_version), (added, removed) in changes.items():
            old_names = DJANGO_SETTING_NAMES_BY_VERSION[old_version]
            new_names = DJANGO_SETTING_NAMES_BY_VERSION[new_version]
            self.assertEqual(new_names - old_names, added)
            self.assertEqual(old_names - new_names, removed)

    def test_collects_configured_package_usage(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.django_probe]\npackages = ["django"]\n',
            encoding="utf-8",
        )
        self.write(
            "app/views.py",
            """
            from django.shortcuts import render

            def home(request):
                return render(request, "home.html")
            """,
        )

        result = scan_path(self.root)

        self.assertEqual(result.usage_packages, ("django",))
        self.assertEqual(result.usage, {"django.shortcuts.render": 2})

    def test_package_usage_defaults_to_django(self):
        self.write("app/views.py", "from django.shortcuts import render\n")

        result = scan_path(self.root)

        self.assertEqual(result.usage_packages, ("django",))
        self.assertEqual(result.usage, {"django.shortcuts.render": 1})

    def test_package_usage_can_be_disabled(self):
        (self.root / "pyproject.toml").write_text(
            "[tool.django_probe]\npackages = []\n",
            encoding="utf-8",
        )
        self.write("app/views.py", "from django.shortcuts import render\n")

        result = scan_path(self.root)

        self.assertEqual(result.usage_packages, ())
        self.assertEqual(result.usage, {})
