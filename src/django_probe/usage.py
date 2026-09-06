"""Count statically resolved API usage for configured package namespaces."""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable

SETTINGS_PATH = "django.conf.settings"
SETTINGS_PREFIX = f"{SETTINGS_PATH}."


class PackageUsageVisitor(ast.NodeVisitor):
    def __init__(
        self,
        packages: Iterable[str],
        django_setting_names: frozenset[str] = frozenset(),
    ) -> None:
        self.packages = frozenset(packages)
        self.django_setting_names = django_setting_names
        self.imports: dict[str, str] = {}
        self.usage: Counter[str] = Counter()

    def selected(self, name: str) -> bool:
        return any(
            name == package or name.startswith(f"{package}.")
            for package in self.packages
        )

    def resolve_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.imports.get(node.id)
        if isinstance(node, ast.Attribute):
            parent = self.resolve_name(node.value)
            if parent:
                return f"{parent}.{node.attr}"
        return None

    def fold_django_setting(self, resolved: str) -> str:
        if not resolved.startswith(SETTINGS_PREFIX):
            return resolved
        setting = resolved.removeprefix(SETTINGS_PREFIX).partition(".")[0]
        if setting in self.django_setting_names:
            return f"{SETTINGS_PREFIX}{setting}"
        return SETTINGS_PATH

    def add(self, name: str) -> None:
        if self.selected(name):
            self.usage[self.fold_django_setting(name)] += 1

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if not self.selected(alias.name):
                continue
            local = alias.asname or alias.name.partition(".")[0]
            self.imports[local] = alias.name if alias.asname else local
            self.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module or not self.selected(node.module):
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            full_name = f"{node.module}.{alias.name}"
            self.imports[alias.asname or alias.name] = full_name
            self.add(full_name)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            resolved = self.resolve_name(node)
            if resolved:
                self.add(resolved)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        resolved = self.resolve_name(node)
        if resolved and self.selected(resolved):
            self.add(resolved)
            return
        self.generic_visit(node)

    def _forget_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.imports.pop(target.id, None)
        elif isinstance(target, (ast.List, ast.Tuple)):
            for element in target.elts:
                self._forget_target(element)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        for target in node.targets:
            self._forget_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        self._forget_target(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.generic_visit(node)
        self._forget_target(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._forget_target(node.target)

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    ) -> None:
        decorators = getattr(node, "decorator_list", ())
        for decorator in decorators:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        if node.args.vararg is not None:
            arguments = (*arguments, node.args.vararg)
        if node.args.kwarg is not None:
            arguments = (*arguments, node.args.kwarg)
        for argument in arguments:
            if argument.annotation is not None:
                self.visit(argument.annotation)
        returns = getattr(node, "returns", None)
        if returns is not None:
            self.visit(returns)

        outer_imports = self.imports
        self.imports = outer_imports.copy()
        for argument in arguments:
            self.imports.pop(argument.arg, None)
        body = node.body if isinstance(node.body, list) else [node.body]
        for statement in body:
            self.visit(statement)
        self.imports = outer_imports

        name = getattr(node, "name", None)
        if name is not None:
            self.imports.pop(name, None)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

        outer_imports = self.imports
        self.imports = outer_imports.copy()
        for statement in node.body:
            self.visit(statement)
        self.imports = outer_imports
        self.imports.pop(node.name, None)

    def _visit_for(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        self._forget_target(node.target)
        for statement in (*node.body, *node.orelse):
            self.visit(statement)

    def visit_For(self, node: ast.For) -> None:
        self._visit_for(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_for(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._forget_target(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name is not None:
            self.imports.pop(node.name, None)
        for statement in node.body:
            self.visit(statement)

    def _visit_comprehension(
        self, generators: list[ast.comprehension], results: tuple[ast.AST, ...]
    ) -> None:
        outer_imports = self.imports
        self.imports = outer_imports.copy()
        for generator in generators:
            self.visit(generator.iter)
            self._forget_target(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for result in results:
            self.visit(result)
        self.imports = outer_imports

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, (node.elt,))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, (node.elt,))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, (node.key, node.value))


def count_package_usage(
    tree: ast.Module,
    packages: Iterable[str],
    django_setting_names: frozenset[str] = frozenset(),
) -> Counter[str]:
    visitor = PackageUsageVisitor(packages, django_setting_names)
    visitor.visit(tree)
    return visitor.usage
