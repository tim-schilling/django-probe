from __future__ import annotations

import io
import json
import tempfile
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase

from django_probe.main import main

PAYLOAD_KEYS = {
    "schema_version",
    "client_version",
    "project_key",
    "python_version",
    "django_version",
    "files_scanned",
    "probe_sources",
    "patterns",
    "dependencies",
}


class CliTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_scan_prints_json(self):
        (self.root / "m.py").write_text("x = 1\n", encoding="utf-8")

        code, output = self.run_cli(["scan", str(self.root)])

        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(output)), PAYLOAD_KEYS)

    def test_init_prints_uuid(self):
        code, output = self.run_cli(["init"])

        self.assertEqual(code, 0)
        uuid.UUID(output.strip())  # raises if not a real UUID

    def test_missing_directory_errors(self):
        code, _ = self.run_cli(["scan", str(self.root / "nope")])
        self.assertEqual(code, 2)
