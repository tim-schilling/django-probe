"""Detect a custom user model.

Two signals, kept separate because they answer different questions: a project can set
``AUTH_USER_MODEL`` to a third-party model without defining one itself.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable

from django_probe.ast_probe import State
from django_probe.probes import Probe, hit

BASES = frozenset({"AbstractUser", "AbstractBaseUser"})
MODULE = "django.contrib.auth.models"
BASE_MODULE = "django.contrib.auth.base_user"

custom_user_model = Probe("custom_user_model")
auth_user_model_setting = Probe(
    "auth_user_model_setting",
    condition=lambda state: state.looks_like_settings_file,
)


def _is_user_base(state: State, node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        name = node.attr
    else:
        return False
    if name not in BASES:
        return False
    # AbstractUser lives in auth.models and AbstractBaseUser in auth.base_user, but
    # both are commonly re-exported; accept either path.
    return (
        name in state.from_imports[MODULE]
        or name in state.from_imports[BASE_MODULE]
        or "models" in state.from_imports["django.contrib.auth"]
    )


@custom_user_model.register(ast.ClassDef)
def visit_ClassDef(
    state: State, node: ast.ClassDef, parents: tuple[ast.AST, ...]
) -> Iterable[object]:
    for base in node.bases:
        if _is_user_base(state, base):
            yield from hit(node)
            return


@auth_user_model_setting.register(ast.Assign)
def visit_Assign(
    state: State, node: ast.Assign, parents: tuple[ast.AST, ...]
) -> Iterable[object]:
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "AUTH_USER_MODEL":
            yield from hit(node)
            return
