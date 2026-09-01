"""Count Django Tasks framework usage.

Django 6.0 shipped a built-in Tasks framework. How quickly it is adopted has no other
source of data, and unlike a deprecation the number never goes to zero because someone
ran a codemod.

Scoped to ``django.tasks``. Celery's ``@shared_task`` is a different question.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from django_upgrade.data import State

from django_probe.probes import Probe, hit, resolves_to

MODULE = "django.tasks"

django_task = Probe("django_task")


def _visit(
    state: State,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: tuple[ast.AST, ...],
) -> Iterable[object]:
    for decorator in node.decorator_list:
        if resolves_to(state, decorator, MODULE, "task"):
            yield from hit(node)


for _node_type in (ast.FunctionDef, ast.AsyncFunctionDef):
    django_task.register(_node_type)(_visit)
