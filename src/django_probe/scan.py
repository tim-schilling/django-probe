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
        patterns.update(count_patterns(tree, rel))
        scanned += 1

    return ScanResult(patterns, scanned, skipped)
