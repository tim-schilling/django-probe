"""Count @receiver-decorated signal handlers.

Signals are perennially debated and nobody has usage numbers.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from django_probe.ast_probe import State
from django_probe.probes import Probe, hit, resolves_to

signal_receiver = Probe("signal_receiver")


def _visit(
    state: State,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: tuple[ast.AST, ...],
) -> Iterable[object]:
    for decorator in node.decorator_list:
        if resolves_to(state, decorator, "django.dispatch", "receiver"):
            yield from hit(node)


for _node_type in (ast.FunctionDef, ast.AsyncFunctionDef):
    signal_receiver.register(_node_type)(_visit)
