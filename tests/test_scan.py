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
