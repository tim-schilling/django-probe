"""Count transaction.atomic usage, as a decorator or context manager."""

from __future__ import annotations

import ast
from collections.abc import Iterable

from django_upgrade.data import State

from django_probe.probes import Probe, hit, resolves_to

transaction_atomic = Probe("transaction_atomic")


def _is_atomic(state: State, node: ast.expr) -> bool:
    return resolves_to(state, node, "django.db.transaction", "atomic")


def _visit_with(
    state: State, node: ast.With | ast.AsyncWith, parents: tuple[ast.AST, ...]
) -> Iterable[object]:
    for item in node.items:
        if _is_atomic(state, item.context_expr):
            yield from hit(node)


def _visit_def(
    state: State,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: tuple[ast.AST, ...],
) -> Iterable[object]:
    for decorator in node.decorator_list:
        if _is_atomic(state, decorator):
            yield from hit(node)


for _with_type in (ast.With, ast.AsyncWith):
    transaction_atomic.register(_with_type)(_visit_with)

for _def_type in (ast.FunctionDef, ast.AsyncFunctionDef):
    transaction_atomic.register(_def_type)(_visit_def)
