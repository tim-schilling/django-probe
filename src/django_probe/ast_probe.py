"""Count probe hits by reusing django-upgrade's AST machinery.

We use django-upgrade for its plumbing, not its fixers: ``State`` (import resolution
and filename heuristics), the ``Fixer`` registry with its ``condition`` gating, and
``ast_parse``.

Its 51 fixers are deliberately not counted. They describe patterns that are already
deprecated and can already be fixed automatically, so counting them would measure how
widely django-upgrade is adopted rather than how the APIs are used. Projects that
install django-probe are also more likely to already run django-upgrade, which makes a
count of zero difficult to interpret.
"""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from django_upgrade.data import FIXERS, Settings, State

ProbeFunc = Callable[[State, Any, tuple[ast.AST, ...]], Iterable[Any]]

#: {probe name: namespace}, populated at import time by ``probes.Probe``.
_REGISTERED: dict[str, str] = {}


def register_probe(name: str, namespace: str) -> None:
    _REGISTERED[name] = namespace


def probe_names() -> frozenset[str]:
    return frozenset(_REGISTERED)


def key_for(name: str) -> str:
    return f"{_REGISTERED[name]}:{name}"


def _probe_funcs(
    state: State, settings: Settings
) -> dict[type[ast.AST], list[tuple[str, ProbeFunc]]]:
    """Like ``django_upgrade.data.get_ast_funcs``, but retaining the probe name."""
    funcs: dict[type[ast.AST], list[tuple[str, ProbeFunc]]] = defaultdict(list)
    for fixer in FIXERS.values():
        if fixer.name not in settings.enabled_fixers or fixer.name not in _REGISTERED:
            continue
        if fixer.condition is None or fixer.condition(state):
            for type_, type_funcs in fixer.ast_funcs.items():
                funcs[type_].extend((fixer.name, f) for f in type_funcs)
    return funcs


def _record_imports(node: ast.AST, state: State) -> None:
    """Track imported names by module.

    Two things django-upgrade does not do, because its fixers never need them: every
    module is tracked rather than just ``django.*``, which third-party probes will
    need; and plain ``import a.b`` is recorded, which is what lets a probe match the
    fully dotted ``@django.tasks.task`` form.
    """
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        state.from_imports[node.module].update(
            alias.name
            for alias in node.names
            if alias.asname is None and alias.name != "*"
        )
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname is None:
                root = alias.name.partition(".")[0]
                state.from_imports[root].add(root)


def count_patterns(tree: ast.Module, settings: Settings, filename: str) -> Counter[str]:
    """Return ``{"namespace:probe_name": count}`` for one parsed module."""
    state = State(settings=settings, filename=filename, from_imports=defaultdict(set))
    funcs = _probe_funcs(state, settings)
    counts: Counter[str] = Counter()

    # Same traversal as django_upgrade.data.visit: a stack with reversed fields, which
    # gives depth-first source order. Probes rely on that, since it guarantees a
    # module's imports are seen before the code using them.
    nodes: list[tuple[ast.AST, tuple[ast.AST, ...]]] = [(tree, ())]
    while nodes:
        node, parents = nodes.pop()

        for probe_name, func in funcs.get(type(node), ()):
            for _ in func(state, node, parents):
                counts[key_for(probe_name)] += 1

        _record_imports(node, state)

        subparents = (*parents, node)
        for name in reversed(node._fields):
            value = getattr(node, name, None)
            if isinstance(value, ast.AST):
                nodes.append((value, subparents))
            elif isinstance(value, list):
                for subvalue in reversed(value):
                    if isinstance(subvalue, ast.AST):
                        nodes.append((subvalue, subparents))

    return counts
