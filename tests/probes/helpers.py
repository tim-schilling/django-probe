from __future__ import annotations

import textwrap

from django_probe.ast_probe import count_patterns
from django_probe.scan import ast_parse


def counts(source: str, filename: str = "views.py") -> dict[str, int]:
    """Run every probe over ``source`` and return its counts."""
    source = textwrap.dedent(source).lstrip("\n")
    return dict(count_patterns(ast_parse(source), filename))
