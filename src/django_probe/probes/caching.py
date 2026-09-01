"""Count @cache_page usage.

Covers the direct decorator, the ``method_decorator`` wrapping used on class-based
views, and bare calls in URLconfs.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from django_probe.ast_probe import State
from django_probe.probes import Probe, hit, resolves_to

MODULE = "django.views.decorators.cache"

cache_page = Probe("cache_page")


def _is_cache_page(state: State, node: ast.expr) -> bool:
    return resolves_to(state, node, MODULE, "cache_page")


def _visit_def(
    state: State,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: tuple[ast.AST, ...],
) -> Iterable[object]:
    for decorator in node.decorator_list:
        if _is_cache_page(state, decorator):
            yield from hit(node)


@cache_page.register(ast.Call)
def visit_Call(
    state: State, node: ast.Call, parents: tuple[ast.AST, ...]
) -> Iterable[object]:
    """`method_decorator(cache_page(60))` and `cache_page(60)(view)`.

    Only counts calls that wrap or are passed to another call. Decorators are handled
    above and would otherwise be counted twice.
    """
    if isinstance(node.func, ast.Call) and _is_cache_page(state, node.func):
        yield from hit(node)
        return
    for arg in node.args:
        if isinstance(arg, ast.Call) and _is_cache_page(state, arg):
            yield from hit(node)
            return


for _node_type in (ast.FunctionDef, ast.AsyncFunctionDef):
    cache_page.register(_node_type)(_visit_def)
