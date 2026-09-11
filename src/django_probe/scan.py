"""Walk a project directory and tally probe hits across its Python files."""

from __future__ import annotations

import ast
import os
import warnings
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import django_probe.probes  # noqa: F401  -- importing registers the probes
from django_probe.ast_probe import count_patterns
from django_probe.config import django_settings_enabled, packages
from django_probe.settings import configured_django_settings, django_settings_vocabulary
from django_probe.usage import count_package_usage

#: `migrations` is skipped deliberately: generated code would swamp the counts with
#: model classes and `.filter()` calls nobody wrote by hand.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "site-packages",
        "migrations",
        "build",
        "dist",
    }
)


def ast_parse(contents_text: str) -> ast.Module:
    # Real projects contain files with syntax warnings (e.g. invalid escape
    # sequences); we can't do anything about them, so don't let them reach the user.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(contents_text.encode())


class ScanResult:
    def __init__(
        self,
        patterns: Counter[str],
        files_scanned: int,
        files_skipped: int,
        usage: Counter[str],
        usage_packages: tuple[str, ...],
        django_settings: Counter[str],
        django_settings_scanned: bool,
    ) -> None:
        self.patterns = patterns
        self.files_scanned = files_scanned
        self.files_skipped = files_skipped
        self.usage = usage
        self.usage_packages = usage_packages
        self.django_settings = django_settings
        self.django_settings_scanned = django_settings_scanned


def iter_python_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def scan_path(root: Path) -> ScanResult:
    patterns: Counter[str] = Counter()
    usage: Counter[str] = Counter()
    usage_packages = packages(root)
    settings_files: list[ast.Module] = []
    scanned = skipped = 0

    needs_django_vocabulary = (
        django_settings_enabled(root) or "django" in usage_packages
    )
    django_vocabulary = (
        django_settings_vocabulary() if needs_django_vocabulary else None
    )

    for path in iter_python_files(root):
        try:
            tree = ast_parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            # Real projects contain templates, fixtures and Python 2 leftovers.
            skipped += 1
            continue

        # Relative path only. Filename heuristics need it, and it never leaves here.
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else path.name
        patterns.update(count_patterns(tree, rel))
        usage.update(
            count_package_usage(
                tree,
                usage_packages,
                django_vocabulary.names
                if django_vocabulary is not None
                else frozenset(),
            )
        )
        if "settings" in rel.lower():
            settings_files.append(tree)
        scanned += 1

    django_settings, django_settings_scanned = configured_django_settings(
        root, settings_files, django_vocabulary
    )
    return ScanResult(
        patterns,
        scanned,
        skipped,
        usage,
        usage_packages,
        django_settings,
        django_settings_scanned,
    )
