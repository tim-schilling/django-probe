from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest import TestCase, mock

from django_probe.config import read_project_key, resolve_project_key


class ReadProjectKeyTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_absent_without_pyproject(self):
        self.assertIsNone(read_project_key(self.root))

    def test_reads_from_tool_table(self):
        key = str(uuid.uuid4())
        (self.root / "pyproject.toml").write_text(
            f'[tool.django_probe]\nproject_key = "{key}"\n', encoding="utf-8"
        )
        self.assertEqual(read_project_key(self.root), key)


class ResolveProjectKeyTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_falls_back_to_pyproject(self):
        key = str(uuid.uuid4())
        (self.root / "pyproject.toml").write_text(
            f'[tool.django_probe]\nproject_key = "{key}"\n', encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DJANGO_PROBE_PROJECT_KEY", None)
            self.assertEqual(resolve_project_key(self.root), key)

    def test_env_var_takes_precedence(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.django_probe]\nproject_key = "from-file"\n', encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"DJANGO_PROBE_PROJECT_KEY": "from-env"}):
            self.assertEqual(resolve_project_key(self.root), "from-env")

    def test_env_var_works_without_pyproject(self):
        with mock.patch.dict(os.environ, {"DJANGO_PROBE_PROJECT_KEY": "from-env"}):
            self.assertEqual(resolve_project_key(self.root), "from-env")
