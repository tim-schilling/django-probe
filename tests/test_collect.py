from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase, mock

from django_probe.collect import (
    dependencies,
    exclude_by_pattern,
    normalize,
    python_version,
)


class FakeDistribution:
    """Enough of `importlib.metadata.Distribution` for `collect.dependencies`."""

    def __init__(self, name: str, version: str, *, direct_url: str | None = None):
        self.metadata = {"Name": name}
        self.version = version
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        if filename == "direct_url.json":
            return self._direct_url
        return None


class DependenciesTests(TestCase):
    def test_includes_index_installed_packages(self):
        dists = [FakeDistribution("Django", "5.0")]

        with mock.patch("importlib.metadata.distributions", return_value=dists):
            result = dependencies()

        self.assertEqual(result, {"django": "5.0"})

    def test_excludes_editable_local_install(self):
        dists = [
            FakeDistribution(
                "my-app",
                "0.1",
                direct_url='{"url": "file:///home/dev/my-app", '
                '"dir_info": {"editable": true}}',
            )
        ]

        with mock.patch("importlib.metadata.distributions", return_value=dists):
            result = dependencies()

        self.assertEqual(result, {})

    def test_excludes_vcs_install(self):
        dists = [
            FakeDistribution(
                "internal-lib",
                "1.2.3",
                direct_url='{"url": "git+https://github.com/acme/internal-lib", '
                '"vcs_info": {"vcs": "git", "commit_id": "abc"}}',
            )
        ]

        with mock.patch("importlib.metadata.distributions", return_value=dists):
            result = dependencies()

        self.assertEqual(result, {})

    def test_excludes_direct_url_archive_install(self):
        dists = [
            FakeDistribution(
                "some-pkg",
                "2.0",
                direct_url='{"url": "https://example.com/some-pkg-2.0.tar.gz"}',
            )
        ]

        with mock.patch("importlib.metadata.distributions", return_value=dists):
            result = dependencies()

        self.assertEqual(result, {})

    def test_mixed_installs_keeps_only_index_installed(self):
        dists = [
            FakeDistribution("django", "5.0"),
            FakeDistribution(
                "my-app", "0.1", direct_url='{"dir_info": {"editable": true}}'
            ),
        ]

        with mock.patch("importlib.metadata.distributions", return_value=dists):
            result = dependencies()

        self.assertEqual(result, {"django": "5.0"})


class ExcludeByPatternTests(TestCase):
    def test_no_patterns_is_a_no_op(self):
        deps = {"django": "5.0"}
        self.assertEqual(exclude_by_pattern(deps, []), deps)

    def test_drops_matching_names(self):
        deps = {"django": "5.0", "acme-internal-lib": "1.0", "acme-other": "2.0"}

        result = exclude_by_pattern(deps, ["acme-*"])

        self.assertEqual(result, {"django": "5.0"})

    def test_pattern_is_normalized_like_names(self):
        deps = {"acme-internal-lib": "1.0", "django": "5.0"}

        result = exclude_by_pattern(deps, ["Acme_Internal.*"])

        self.assertEqual(result, {"django": "5.0"})


class NormalizeTests(TestCase):
    def test_pep503_normalization(self):
        self.assertEqual(normalize("Django_Extensions.Foo"), "django-extensions-foo")


class PythonVersionTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_missing_version(self):
        self.assertEqual(python_version(self.root), "")

    def test_explicit_version_overrides_file(self):
        (self.root / ".python-version").write_text("3.14", encoding="utf-8")
        self.assertEqual(python_version(self.root, override="3.15.0"), "3.15.0")

    def test_empty_override_uses_file(self):
        (self.root / ".python-version").write_text("3.15", encoding="utf-8")
        self.assertEqual(python_version(self.root, override=""), "3.15")

    def test_invalid_override_does_not_fall_back(self):
        (self.root / ".python-version").write_text("3.15", encoding="utf-8")
        with self.assertRaises(ValueError):
            python_version(self.root, override="system")

    def test_configured_version(self):
        for version in ("3.15", "3.15.0", "3.15.0rc1"):
            with self.subTest(version=version):
                (self.root / ".python-version").write_text(
                    version + "\n", encoding="utf-8"
                )
                self.assertEqual(python_version(self.root), version)

    def test_invalid_version(self):
        for version in (
            "system",
            "/private/python",
            "3.14\n3.15",
            "",
            "3." + "1" * 128,
        ):
            with self.subTest(version=version):
                (self.root / ".python-version").write_text(version, encoding="utf-8")
                self.assertEqual(python_version(self.root), "")

    def test_invalid_utf8(self):
        (self.root / ".python-version").write_bytes(b"\xff")
        self.assertEqual(python_version(self.root), "")

    def test_unreadable_version(self):
        with mock.patch.object(Path, "read_text", side_effect=PermissionError):
            self.assertEqual(python_version(self.root), "")
