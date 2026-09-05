from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from django_probe.config import django_settings_enabled, read_token, resolve_token


class ReadTokenTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_absent_without_pyproject(self):
        self.assertIsNone(read_token(self.root))

    def test_reads_from_tool_table(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.django_probe]\ntoken = "from-file"\n', encoding="utf-8"
        )
        self.assertEqual(read_token(self.root), "from-file")


class ResolveTokenTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_falls_back_to_pyproject(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.django_probe]\ntoken = "from-file"\n', encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DJANGO_PROBE_TOKEN", None)
            self.assertEqual(resolve_token(self.root), "from-file")

    def test_env_var_takes_precedence(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.django_probe]\ntoken = "from-file"\n', encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"DJANGO_PROBE_TOKEN": "from-env"}):
            self.assertEqual(resolve_token(self.root), "from-env")

    def test_env_var_works_without_pyproject(self):
        with mock.patch.dict(os.environ, {"DJANGO_PROBE_TOKEN": "from-env"}):
            self.assertEqual(resolve_token(self.root), "from-env")


class DjangoSettingsEnabledTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_requires_explicit_opt_in(self):
        self.assertFalse(django_settings_enabled(self.root))

    def test_reads_usage_opt_in(self):
        (self.root / "pyproject.toml").write_text(
            "[tool.django_probe.usage]\ndjango_settings = true\n",
            encoding="utf-8",
        )
        self.assertTrue(django_settings_enabled(self.root))
