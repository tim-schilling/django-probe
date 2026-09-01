"""Count QuerySet method usage.

Matched on method name, since there are no types to consult at parse time. Measured
against Django, Wagtail, django-oscar and djangopackages, about 98% of matches are
genuine ORM calls. ``register.filter(...)`` was the only systematic false positive,
which is why template ``Library`` instances are tracked below.

Do not change this to require a recognisable receiver such as ``.objects``. In real
applications up to a third of ORM calls are made on local variables and custom queryset
methods such as ``page.get_children().filter(...)``, so precision would gain about a
point while recall lost a third.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from weakref import WeakKeyDictionary

from django_upgrade.data import State

from django_probe.probes import Probe, dotted_name, hit

METHODS = ("extra", "filter", "exclude", "alias", "annotate")

LIBRARY_PATHS = frozenset({"Library", "template.Library", "django.template.Library"})

#: Only `filter` collides with the template-tag API; `register.exclude` is not a thing.
LIBRARY_METHODS = frozenset({"filter"})

#: Names bound to a template Library, per file.
_libraries: WeakKeyDictionary[State, set[str]] = WeakKeyDictionary()


def _note_library_assignment(state: State, node: ast.Assign) -> None:
    if not isinstance(node.value, ast.Call):
        return
    if dotted_name(node.value) not in LIBRARY_PATHS:
        return
    names = _libraries.setdefault(state, set())
    for target in node.targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            # `self.library = Library()`, then `@self.library.filter`. Recording only
            # the trailing name is coarse, but scoped to a file that builds a Library.
            names.add(target.attr)


def _is_library_call(state: State, node: ast.Call, method: str) -> bool:
    if method not in LIBRARY_METHODS:
        return False
    receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
    known = _libraries.get(state, set())
    if isinstance(receiver, ast.Name):
        return receiver.id in known
    if isinstance(receiver, ast.Attribute):
        return receiver.attr in known
    return False


def _visitor(method: str) -> Callable[..., Iterable[object]]:
    """Build a visitor bound to one method.

    A single shared visitor would credit every match to all five probes.
    """

    def visit_Call(
        state: State, node: ast.Call, parents: tuple[ast.AST, ...]
    ) -> Iterable[object]:
        if not isinstance(node.func, ast.Attribute) or node.func.attr != method:
            return
        if _is_library_call(state, node, method):
            return
        yield from hit(node)

    return visit_Call


def _visit_Assign(
    state: State, node: ast.Assign, parents: tuple[ast.AST, ...]
) -> Iterable[object]:
    # Registers the name and counts nothing. Assignments are visited before the code
    # below them, so a later `register.filter` sees it.
    _note_library_assignment(state, node)
    return ()


for _method in METHODS:
    _probe = Probe(f"queryset_{_method}")
    _probe.register(ast.Call)(_visitor(_method))
    _probe.register(ast.Assign)(_visit_Assign)
