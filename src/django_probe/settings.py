"""Collect Django setting names without inspecting setting values."""

from __future__ import annotations

import ast
import warnings
from collections import Counter
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from django_probe.config import django_settings_enabled


@dataclass(frozen=True)
class DjangoSettingsVocabulary:
    names: frozenset[str]
    source: str | None


def _assignment_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_assignment_names(element))
        return names
    return []


def django_settings_vocabulary() -> DjangoSettingsVocabulary:
    """Parse the installed Django global settings module, failing closed."""
    try:
        distribution = metadata.distribution("django")
        path = Path(str(distribution.locate_file("django/conf/global_settings.py")))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                names.update(
                    name for name in _assignment_names(target) if name.isupper()
                )
    except (
        OSError,
        UnicodeDecodeError,
        SyntaxError,
        ValueError,
        metadata.PackageNotFoundError,
    ):
        warnings.warn(
            "Django settings vocabulary unavailable; settings inventory omitted.",
            RuntimeWarning,
            stacklevel=2,
        )
        return DjangoSettingsVocabulary(frozenset(), None)
    return DjangoSettingsVocabulary(frozenset(names), metadata.version("django"))


def configured_django_settings(
    root: Path, settings_files: list[ast.Module]
) -> tuple[Counter[str], bool]:
    """Count recognized module-level assignments in settings-like files."""
    if not django_settings_enabled(root):
        return Counter(), False

    vocabulary = django_settings_vocabulary()
    if vocabulary.source is None:
        return Counter(), False

    counts: Counter[str] = Counter()
    for tree in settings_files:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                counts.update(
                    name
                    for name in _assignment_names(target)
                    if name in vocabulary.names
                )
    return counts, True
