from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from django_probe.scan import scan_path


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
        self.assertEqual(result.django_settings, {"DEBUG": 1, "AUTH_USER_MODEL": 1})

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
        self.assertEqual(result.usage["django.shortcuts.render"], 2)

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
