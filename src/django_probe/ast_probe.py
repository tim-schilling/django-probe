"""Count probe hits with a small dispatch-by-node-type AST visitor."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from functools import cached_property
from typing import Any

ProbeFunc = Callable[["State", Any, tuple[ast.AST, ...]], Iterable[Any]]

settings_re = re.compile(r"(\b|_)settings(\b|_)")


class State:
    """Per-file state threaded through every probe callback."""

    #: ``__weakref__`` lets probes key a ``WeakKeyDictionary`` by ``State`` (see
    #: ``probes.orm``'s per-file ``Library`` tracking); ``__dict__`` backs
    #: ``cached_property``.
    __slots__ = ("filename", "from_imports", "__weakref__", "__dict__")

    def __init__(self, filename: str, from_imports: defaultdict[str, set[str]]) -> None:
        self.filename = filename
        self.from_imports = from_imports

    @cached_property
    def looks_like_settings_file(self) -> bool:
        return settings_re.search(self.filename) is not None


class _Registration:
    """One probe's AST callbacks and optional file-level gate."""

    __slots__ = ("key", "condition", "ast_funcs")

    def __init__(self, key: str, condition: Callable[[State], bool] | None) -> None:
        self.key = key
        self.condition = condition
        self.ast_funcs: dict[type[ast.AST], list[ProbeFunc]] = defaultdict(list)


#: Every probe registered so far, keyed by "namespace:name", populated at import time
#: by ``probes.Probe``.
_REGISTRY: dict[str, _Registration] = {}


def register_probe(
    key: str, condition: Callable[[State], bool] | None
) -> _Registration:
    if key in _REGISTRY:
        raise RuntimeError(f"probe {key!r} is already registered")
    registration = _Registration(key, condition)
    _REGISTRY[key] = registration
    return registration


def probe_names() -> frozenset[str]:
    return frozenset(_REGISTRY)


def _probe_funcs(state: State) -> dict[type[ast.AST], list[tuple[str, ProbeFunc]]]:
    funcs: dict[type[ast.AST], list[tuple[str, ProbeFunc]]] = defaultdict(list)
    for registration in _REGISTRY.values():
        if registration.condition is not None and not registration.condition(state):
            continue
        for type_, type_funcs in registration.ast_funcs.items():
            funcs[type_].extend((registration.key, f) for f in type_funcs)
    return funcs


def _record_imports(node: ast.AST, state: State) -> None:
    """Track imported names by module.

    Every module is tracked, not just ``django.*``, since third-party probes need it;
    and plain ``import a.b`` is recorded, which is what lets a probe match the fully
    dotted ``@django.tasks.task`` form.
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


def count_patterns(tree: ast.Module, filename: str) -> Counter[str]:
    """Return ``{"namespace:probe_name": count}`` for one parsed module."""
    state = State(filename=filename, from_imports=defaultdict(set))
    funcs = _probe_funcs(state)
    counts: Counter[str] = Counter()

    # A stack with reversed fields gives depth-first source order. Probes rely on
    # that, since it guarantees a module's imports are seen before the code using them.
    nodes: list[tuple[ast.AST, tuple[ast.AST, ...]]] = [(tree, ())]
    while nodes:
        node, parents = nodes.pop()

        for probe_name, func in funcs.get(type(node), ()):
            for _ in func(state, node, parents):
                counts[probe_name] += 1

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
