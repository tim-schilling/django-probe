from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import TestCase

from django_probe.main import insecure_server_url, main

PAYLOAD_KEYS = {
    "schema_version",
    "client_version",
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

    def test_missing_directory_errors(self):
        code, _ = self.run_cli(["scan", str(self.root / "nope")])
        self.assertEqual(code, 2)


class InsecureServerUrlTests(TestCase):
    def test_https_is_accepted(self):
        self.assertIsNone(insecure_server_url("https://djangoprobe.org"))

    def test_plain_http_to_a_remote_host_is_refused(self):
        self.assertIn("plain HTTP", insecure_server_url("http://probe.example.com"))

    def test_plain_http_to_loopback_is_accepted(self):
        for url in (
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://[::1]:8000",
        ):
            with self.subTest(url=url):
                self.assertIsNone(insecure_server_url(url))

    def test_other_schemes_are_refused(self):
        for url in ("ftp://probe.example.com", "probe.example.com", "file:///etc"):
            with self.subTest(url=url):
                self.assertIn("expected http:// or https://", insecure_server_url(url))


class InsecureServerUrlCliTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stderr(buffer), redirect_stdout(io.StringIO()):
            code = main(argv)
        return code, buffer.getvalue()

    def test_submit_over_plain_http_exits_without_sending(self):
        code, stderr = self.run_cli(
            ["submit", str(self.root), "--server-url", "http://probe.example.com"]
        )

        self.assertEqual(code, 2)
        self.assertIn("plain HTTP", stderr)

    def test_login_over_plain_http_exits_without_sending(self):
        code, stderr = self.run_cli(
            ["login", "--server-url", "http://probe.example.com"]
        )

        self.assertEqual(code, 2)
        self.assertIn("plain HTTP", stderr)

    def test_init_over_plain_http_exits_without_sending(self):
        code, stderr = self.run_cli(
            ["init", str(self.root), "--server-url", "http://probe.example.com"]
        )

        self.assertEqual(code, 2)
        self.assertIn("plain HTTP", stderr)

    def test_scan_needs_no_server_url(self):
        code, stderr = self.run_cli(["scan", str(self.root)])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")

    def test_dry_run_sends_nothing_so_the_url_is_not_checked(self):
        code, stderr = self.run_cli(
            [
                "submit",
                str(self.root),
                "--dry-run",
                "--server-url",
                "http://probe.example.com",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
