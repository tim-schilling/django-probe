"""django-probe's probes.

A probe answers "how often does this codebase do X?" for an X no tool will rewrite
away: a probe yields once per occurrence and the visitor tallies the yields.

Third-party packages will later ship probes the same way, under their own namespace::

    probe = Probe("periodic_task", namespace="django-celery-beat")
"""

from __future__ import annotations

import ast
import pkgutil
from collections.abc import Callable, Iterable

from django_probe.ast_probe import ProbeFunc, State, register_probe

DEFAULT_NAMESPACE = "probe"


class Probe:
    """A named counter over AST nodes."""

    def __init__(
        self,
        name: str,
        namespace: str = DEFAULT_NAMESPACE,
        condition: Callable[[State], bool] | None = None,
    ) -> None:
        if any(c in name or c in namespace for c in ":."):
            raise RuntimeError(
                "probe names and namespaces must not contain ':' or '.': "
                "':' separates them in the registry key"
            )
        self._registration = register_probe(f"{namespace}:{name}", condition)

    def register(self, type_: type[ast.AST]) -> Callable[[ProbeFunc], ProbeFunc]:
        def decorator(func: ProbeFunc) -> ProbeFunc:
            self._registration.ast_funcs[type_].append(func)
            return func

        return decorator


def hit(node: ast.AST) -> Iterable[None]:
    """Yield a single countable occurrence.

    ``count_patterns`` only tallies how many times a probe yields, not what it yields;
    ``node`` documents at the call site what was hit.
    """
    yield None


def dotted_name(node: ast.expr) -> str | None:
    """Return the dotted path of a decorator or call target.

    ``@task`` gives ``"task"`` and ``@django.tasks.task`` gives the full path. None if
    any segment is not a plain name or attribute.
    """
    target = node.func if isinstance(node, ast.Call) else node
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if not isinstance(target, ast.Name):
        return None
    parts.append(target.id)
    return ".".join(reversed(parts))


def resolves_to(state: State, node: ast.expr, module: str, name: str) -> bool:
    """Whether a decorator or call target refers to ``module.name``.

    Handles the three import forms reaching the same object::

        from django.tasks import task      ->  @task
        from django import tasks           ->  @tasks.task
        import django.tasks                ->  @django.tasks.task

    Aliased imports are not resolved: tracking rebindings would need real scope
    analysis.
    """
    dotted = dotted_name(node)
    if dotted is None:
        return False

    if dotted == name:
        return name in state.from_imports[module]

    parent, _, leaf = module.rpartition(".")
    if parent and dotted == f"{leaf}.{name}":
        return leaf in state.from_imports[parent]

    if dotted == f"{module}.{name}":
        root = module.partition(".")[0]
        return root in state.from_imports[root]

    return False


def _import_probes() -> None:
    for _, name, _ in pkgutil.walk_packages(__path__, f"{__name__}."):
        __import__(name, fromlist=["_trash"])


_import_probes()
