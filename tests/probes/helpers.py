from __future__ import annotations

import textwrap

from django_upgrade.ast import ast_parse
from django_upgrade.data import Settings

from django_probe.ast_probe import count_patterns, probe_names
from django_probe.scan import _TARGET_VERSION


def counts(source: str, filename: str = "views.py") -> dict[str, int]:
    """Run every probe over ``source`` and return its counts."""
    source = textwrap.dedent(source).lstrip("\n")
    settings = Settings(target_version=_TARGET_VERSION, only_fixers=set(probe_names()))
    return dict(count_patterns(ast_parse(source), settings, filename))
