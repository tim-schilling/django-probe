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

    def test_skips_migrations_and_survives_syntax_errors(self):
        source = "x = Book.objects.filter(a=1)\n"
        self.write("app/views.py", source)
        self.write("app/migrations/0001_initial.py", source)
        self.write("app/broken.py", "def oops(:\n")

        result = scan_path(self.root)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.files_skipped, 1)
        self.assertEqual(result.patterns["probe:queryset_filter"], 1)

    def test_django_settings_only_include_known_module_level_names(self):
        (self.root / "pyproject.toml").write_text(
            "[tool.django_probe.usage]\ndjango_settings = true\n",
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

        self.assertTrue(result.django_settings_scanned)
        self.assertEqual(result.django_settings["DEBUG"], 1)
        self.assertEqual(result.django_settings["AUTH_USER_MODEL"], 1)
        self.assertNotIn("INTERNAL_BILLING_REGION", result.django_settings)
        self.assertNotIn("THIRD_PARTY_API_TOKEN", result.django_settings)
        self.assertNotIn("INSTALLED_APPS", result.django_settings)
