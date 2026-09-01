"""django-probe's probes.

A probe answers "how often does this codebase do X?" for an X no tool will rewrite
away. Probes are registered as django-upgrade ``Fixer`` objects to reuse its registry
and ``condition`` gating, but never rewrite anything: a probe yields once per
occurrence and the visitor tallies the yields.

Third-party packages will later ship probes the same way, under their own namespace::

    probe = Probe("periodic_task", namespace="django-celery-beat")
"""

from __future__ import annotations

import ast
import pkgutil
from collections.abc import Callable, Iterable

from django_upgrade.ast import ast_start_offset
from django_upgrade.data import FIXERS, Fixer, State
from tokenize_rt import Offset

from django_probe.ast_probe import ProbeFunc, register_probe

DEFAULT_NAMESPACE = "probe"


class Probe:
    """A named counter over AST nodes."""

    def __init__(
        self,
        name: str,
        namespace: str = DEFAULT_NAMESPACE,
        condition: Callable[[State], bool] | None = None,
    ) -> None:
        if name in FIXERS:
            raise RuntimeError(f"probe {name!r} collides with an existing name")
        if ":" in name or ":" in namespace:
            raise RuntimeError("probe names and namespaces must not contain ':'")
        # min_version is irrelevant: probes measure usage, not upgrade eligibility.
        self.fixer = Fixer(name, min_version=(1, 0), condition=condition)
        register_probe(name, namespace)

    def register(self, type_: type[ast.AST]) -> Callable[[ProbeFunc], ProbeFunc]:
        return self.fixer.register(type_)


def hit(node: ast.AST) -> Iterable[Offset]:
    """Yield a single countable occurrence at ``node``'s start offset."""
    yield ast_start_offset(node)  # type: ignore[arg-type]


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

    Aliased imports are not resolved, matching django-upgrade: tracking rebindings
    would need real scope analysis.
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
