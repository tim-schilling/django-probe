from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase, mock

from django_probe.python_version import project_python_version


class PythonVersionTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def assertUnknown(self):
        with self.assertWarnsRegex(RuntimeWarning, "no valid Python version"):
            self.assertEqual(project_python_version(self.root), "")

    def test_missing_version(self):
        self.assertUnknown()

    def test_explicit_version_overrides_file(self):
        (self.root / ".python-version").write_text("3.14", encoding="utf-8")
        self.assertEqual(project_python_version(self.root, override="3.15.0"), "3.15.0")

    def test_invalid_override_does_not_fall_back(self):
        (self.root / ".python-version").write_text("3.15", encoding="utf-8")
        with self.assertRaises(ValueError):
            project_python_version(self.root, override="system")

    def test_configured_version(self):
        for version in ("3.15", "3.15.0", "3.15.0rc1"):
            with self.subTest(version=version):
                (self.root / ".python-version").write_text(
                    version + "\n", encoding="utf-8"
                )
                self.assertEqual(project_python_version(self.root), version)

    def test_sources(self):
        """Each file is read, using the lowest supported version of a range."""
        for filename, content, expected in (
            (".tool-versions", "nodejs 22.1.0\npython 3.13.1 3.12.0\n", "3.13.1"),
            ("runtime.txt", "python-3.13.1\n", "3.13.1"),
            ("runtime.txt", "3.13\n", "3.13"),
            ("Pipfile", '[requires]\npython_version = "3.13"\n', "3.13"),
            (
                "Pipfile",
                '[requires]\npython_version = "3.13"\npython_full_version = "3.13.1"\n',
                "3.13.1",
            ),
            ("Dockerfile", "FROM python:3.13.1-slim AS app\n", "3.13.1"),
            (
                "Dockerfile",
                "FROM --platform=linux/amd64 docker.io/library/python:3.12\n"
                "FROM python:3.13@sha256:abc\n",
                "3.13",
            ),
            ("pyproject.toml", '[project]\nrequires-python = ">=3.12"\n', "3.12"),
            (
                "pyproject.toml",
                '[project]\nrequires-python = "<3.14,!=3.12.1,>=3.11.4"\n',
                "3.11.4",
            ),
            ("pyproject.toml", '[project]\nrequires-python = "~=3.13.0"\n', "3.13.0"),
            ("pyproject.toml", '[project]\nrequires-python = "==3.13.*"\n', "3.13"),
            ("uv.lock", 'requires-python = ">=3.12"\n', "3.12"),
        ):
            with self.subTest(filename=filename, content=content):
                path = self.root / filename
                path.write_text(content, encoding="utf-8")
                self.assertEqual(project_python_version(self.root), expected)
                path.unlink()

    def test_unusable_sources(self):
        """A file without a usable version is skipped."""
        for filename, content in (
            (".tool-versions", "python system\n"),
            (".tool-versions", "# python 3.13\n"),
            ("runtime.txt", "pypy-3.10\n"),
            ("Pipfile", "[packages]\n"),
            ("Pipfile", "not toml ["),
            ("Dockerfile", "FROM node:22\n"),
            ("Dockerfile", "FROM python:${VERSION}\n"),
            ("Dockerfile", "FROM python:latest\n"),
            ("pyproject.toml", "[tool.other]\n"),
            ("pyproject.toml", '[project]\nrequires-python = "<3.14"\n'),
            ("pyproject.toml", '[project]\nrequires-python = ">3.12"\n'),
            ("pyproject.toml", '[project]\nrequires-python = "nonsense"\n'),
            ("pyproject.toml", "[project]\nrequires-python = 3\n"),
            ("uv.lock", "version = 1\n"),
        ):
            with self.subTest(filename=filename, content=content):
                path = self.root / filename
                path.write_text(content, encoding="utf-8")
                self.assertUnknown()
                path.unlink()

    def test_source_precedence(self):
        """Pinned versions win over ranges, and the listed order breaks ties."""
        files = {
            ".python-version": "3.15",
            ".tool-versions": "python 3.14",
            "runtime.txt": "python-3.13",
            "Pipfile": '[requires]\npython_version = "3.12"\n',
            "Dockerfile": "FROM python:3.11\n",
            "pyproject.toml": '[project]\nrequires-python = ">=3.10"\n',
            "uv.lock": 'requires-python = ">=3.9"\n',
        }
        for filename, content in files.items():
            (self.root / filename).write_text(content, encoding="utf-8")
        for filename, expected in (
            (".python-version", "3.14"),
            (".tool-versions", "3.13"),
            ("runtime.txt", "3.12"),
            ("Pipfile", "3.11"),
            ("Dockerfile", "3.10"),
            ("pyproject.toml", "3.9"),
        ):
            with self.subTest(removed=filename):
                (self.root / filename).unlink()
                self.assertEqual(project_python_version(self.root), expected)

    def test_invalid_version(self):
        for version in ("system", "/private/python", "3.14\n3.15", ""):
            with self.subTest(version=version):
                (self.root / ".python-version").write_text(version, encoding="utf-8")
                self.assertUnknown()

    def test_invalid_utf8(self):
        (self.root / ".python-version").write_bytes(b"\xff")
        self.assertUnknown()

    def test_unreadable_version(self):
        with mock.patch.object(Path, "read_text", side_effect=PermissionError):
            self.assertUnknown()
