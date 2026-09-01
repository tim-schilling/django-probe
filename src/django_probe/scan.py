"""Walk a project directory and tally probe hits across its Python files."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from django_upgrade.ast import ast_parse
from django_upgrade.data import Settings
from django_upgrade.main import SUPPORTED_TARGET_VERSIONS

import django_probe.probes  # noqa: F401  -- importing registers the probes
from django_probe.ast_probe import count_patterns, probe_names

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

# Settings requires a target version, but probes measure usage rather than upgrade
# eligibility, so nothing is gated on it.
_TARGET_VERSION = max(SUPPORTED_TARGET_VERSIONS)


class ScanResult:
    def __init__(
        self, patterns: Counter[str], files_scanned: int, files_skipped: int
    ) -> None:
        self.patterns = patterns
        self.files_scanned = files_scanned
        self.files_skipped = files_skipped


def iter_python_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def scan_path(root: Path) -> ScanResult:
    settings = Settings(
        target_version=_TARGET_VERSION,
        # django-upgrade's own fixers register themselves into the shared FIXERS dict
        # on import; restrict the run to our probes.
        only_fixers=set(probe_names()),
    )
    patterns: Counter[str] = Counter()
    scanned = skipped = 0

    for path in iter_python_files(root):
        try:
            tree = ast_parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            # Real projects contain templates, fixtures and Python 2 leftovers.
            skipped += 1
            continue

        # Relative path only. Filename heuristics need it, and it never leaves here.
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else path.name
        patterns.update(count_patterns(tree, settings, rel))
        scanned += 1

    return ScanResult(patterns, scanned, skipped)
