from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase, mock

from django_probe.dependencies import resolve, unresolved_message

UV_LOCK = """
version = 1

[[package]]
name = "django"
version = "5.2.17"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "sqlparse"
version = "0.6.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "acme-internal"
version = "2.0"
source = { registry = "https://packages.acme.test/simple" }

[[package]]
name = "my-app"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "tablib"
version = "3.10.1"
source = { git = "https://github.com/jazzband/tablib.git" }
"""

POETRY_LOCK = """
[[package]]
name = "django"
version = "5.2.17"
groups = ["main"]

[[package]]
name = "acme-internal"
version = "2.0"
groups = ["main"]

[package.source]
type = "legacy"
url = "https://packages.acme.test/simple"

[[package]]
name = "tablib"
version = "3.10.1"
groups = ["main"]

[package.source]
type = "git"
url = "https://github.com/jazzband/tablib.git"
"""

PDM_LOCK = """
[metadata]
lock_version = "4.5.1"

[[package]]
name = "django"
version = "5.2.17"
groups = ["default"]

[[package]]
name = "tablib"
version = "3.10.1.dev3"
git = "https://github.com/jazzband/tablib.git"
revision = "a36c9654742d0cf07675a79df10581b3e1344555"
groups = ["default"]
"""


class ResolveTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write_lock(self, filename: str, contents: str) -> None:
        (self.root / filename).write_text(contents, encoding="utf-8")

    @contextmanager
    def installed(self, packages: dict[str, str], *, django_version: str | None = None):
        """Stand in for the environment. Django's version is reported even when a
        VCS install keeps it out of `packages`."""
        if django_version is None:
            django_version = packages.get("django", "")
        with (
            mock.patch(
                "django_probe.dependencies.collect.django_version",
                return_value=django_version,
            ),
            mock.patch(
                "django_probe.dependencies.collect.dependencies", return_value=packages
            ) as dependencies,
        ):
            yield dependencies

    def test_uv_lock_keeps_only_packages_resolved_from_pypi(self):
        """Editable, VCS and private-index entries all stay out of the payload."""
        self.write_lock("uv.lock", UV_LOCK)

        resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"django": "5.2.17", "sqlparse": "0.6.0"})
        self.assertEqual(resolved.source, "uv")

    def test_poetry_lock_excludes_private_index_packages(self):
        """A "legacy" source names a custom index, which may be an internal one."""
        self.write_lock("poetry.lock", POETRY_LOCK)

        resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"django": "5.2.17"})
        self.assertEqual(resolved.source, "poetry")

    def test_poetry_lock_keeps_a_legacy_source_pointing_at_pypi(self):
        self.write_lock(
            "poetry.lock",
            """
[[package]]
name = "django"
version = "5.2.17"

[package.source]
type = "legacy"
url = "https://pypi.org/simple"
""",
        )

        self.assertEqual(resolve(self.root).packages, {"django": "5.2.17"})

    def test_pdm_lock_excludes_vcs_packages(self):
        self.write_lock("pdm.lock", PDM_LOCK)

        resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"django": "5.2.17"})
        self.assertEqual(resolved.source, "pdm")

    def test_pdm_lock_excludes_every_source_it_can_name(self):
        """pdm marks an entry with its VCS backend, "path" or "url"; index entries
        carry none of those, so each one has to be recognized by name."""
        self.write_lock(
            "pdm.lock",
            """
[[package]]
name = "django"
version = "5.2.17"

[[package]]
name = "from-hg"
version = "1.0"
hg = "https://hg.example.test/pkg"

[[package]]
name = "from-svn"
version = "1.0"
svn = "https://svn.example.test/pkg"

[[package]]
name = "from-bzr"
version = "1.0"
bzr = "https://bzr.example.test/pkg"

[[package]]
name = "from-path"
version = "1.0"
path = "../vendored"

[[package]]
name = "from-url"
version = "1.0"
url = "https://example.test/pkg-1.0-py3-none-any.whl"
""",
        )

        self.assertEqual(resolve(self.root).packages, {"django": "5.2.17"})

    def test_uv_lock_wins_when_several_lock_files_exist(self):
        self.write_lock("uv.lock", UV_LOCK)
        self.write_lock("poetry.lock", POETRY_LOCK)

        self.assertEqual(resolve(self.root).source, "uv")

    def test_duplicate_entries_resolve_to_the_highest_version(self):
        """Markers split a resolution, so one lock can pin several versions at once."""
        self.write_lock(
            "uv.lock",
            """
[[package]]
name = "django"
version = "4.2.9"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "django"
version = "4.2.30"
source = { registry = "https://pypi.org/simple" }
""",
        )

        self.assertEqual(resolve(self.root).packages, {"django": "4.2.30"})

    def test_lock_file_takes_precedence_over_the_environment(self):
        self.write_lock("uv.lock", UV_LOCK)

        with self.installed({"django": "3.2"}):
            resolved = resolve(self.root)

        self.assertEqual(resolved.packages["django"], "5.2.17")

    def test_unparsable_lock_falls_back_to_the_environment(self):
        self.write_lock("uv.lock", "this is not toml {{{")

        with self.installed({"django": "5.0"}):
            resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"django": "5.0"})
        self.assertEqual(resolved.source, "installed")

    def test_environment_is_used_without_a_lock_file(self):
        with self.installed({"django": "5.0", "requests": "2.32.0"}):
            resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"django": "5.0", "requests": "2.32.0"})
        self.assertEqual(resolved.source, "installed")

    def test_django_locked_from_a_vcs_checkout_still_counts_as_found(self):
        """Projects tracking Django main lock it from git, which we don't report."""
        self.write_lock(
            "uv.lock",
            """
[[package]]
name = "django"
version = "6.2.dev20260901201541"
source = { git = "https://github.com/django/django.git" }

[[package]]
name = "sqlparse"
version = "0.6.0"
source = { registry = "https://pypi.org/simple" }
""",
        )

        resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"sqlparse": "0.6.0"})
        self.assertEqual(resolved.source, "uv")

    def test_django_installed_from_a_vcs_checkout_still_counts_as_found(self):
        with self.installed(
            {"sqlparse": "0.6.0"}, django_version="6.2.dev20260901201541"
        ):
            resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {"sqlparse": "0.6.0"})
        self.assertEqual(resolved.source, "installed")

    def test_missing_django_drops_the_whole_set(self):
        """Without Django we resolved some other environment, so report none of it."""
        with self.installed({"requests": "2.32.0"}):
            resolved = resolve(self.root)

        self.assertEqual(resolved.packages, {})
        self.assertEqual(resolved.source, "")

    def test_disabled_mode_skips_resolution_entirely(self):
        with self.installed({}) as dependencies:
            resolved = resolve(self.root, mode="none")

        self.assertEqual(resolved.packages, {})
        self.assertEqual(resolved.source, "none")
        dependencies.assert_not_called()

    def test_names_mode_blanks_versions(self):
        self.write_lock("uv.lock", UV_LOCK)

        resolved = resolve(self.root, mode="names")

        self.assertEqual(resolved.packages, {"django": "", "sqlparse": ""})
        self.assertEqual(resolved.source, "uv")

    def test_exclude_patterns_apply_to_lock_files(self):
        self.write_lock("uv.lock", UV_LOCK)

        resolved = resolve(self.root, exclude_patterns=["sqlpar*"])

        self.assertEqual(resolved.packages, {"django": "5.2.17"})


class UnresolvedMessageTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_names_the_lock_file_that_came_up_short(self):
        (self.root / "pdm.lock").write_text(PDM_LOCK, encoding="utf-8")

        message = unresolved_message(self.root)

        self.assertIn("pdm.lock", message)
        self.assertIn("pdm lock command", message)

    def test_points_at_the_environment_without_a_lock_file(self):
        message = unresolved_message(self.root)

        self.assertIn("installed", message)
        self.assertIn('dependencies = "none"', message)
