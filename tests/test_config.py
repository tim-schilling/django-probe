from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest import TestCase

from django_probe.config import read_project_key, write_project_key


class ProjectKeyTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_absent_without_pyproject(self):
        self.assertIsNone(read_project_key(self.root))

    def test_write_read_round_trip(self):
        key = write_project_key(self.root)
        uuid.UUID(key)  # raises if not a real UUID
        self.assertEqual(read_project_key(self.root), key)

    def test_preserves_existing_content(self):
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n', encoding="utf-8"
        )
        key = write_project_key(self.root)

        content = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "demo"', content)
        self.assertEqual(read_project_key(self.root), key)

    def test_idempotent(self):
        first = write_project_key(self.root)
        self.assertEqual(write_project_key(self.root), first)

    def test_populates_existing_tool_table(self):
        (self.root / "pyproject.toml").write_text(
            "[tool.django_probe]\n", encoding="utf-8"
        )
        key = write_project_key(self.root)
        self.assertEqual(read_project_key(self.root), key)
