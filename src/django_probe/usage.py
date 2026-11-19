"""Count statically resolved API usage and Monkeypatches."""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from django_probe.django_api import django_api

SETTINGS_PATH = "django.conf.settings"
SETTINGS_PREFIX = f"{SETTINGS_PATH}."


@dataclass
class ImportBinding:
    """A local name bound by one or more imports.

    `import django.db` and `import django.utils` both bind `django`, so the
    binding keeps every imported name to report when it's never referenced.
    """

    target: str
    imported: set[str] = field(default_factory=set)
    used: bool = False


class PackageUsageVisitor(ast.NodeVisitor):
    def __init__(
        self,
        packages: Iterable[str],
        django_setting_names: frozenset[str] = frozenset(),
        collect_monkeypatches: bool = False,
    ) -> None:
        self.packages = frozenset(packages)
        self.django_setting_names = django_setting_names
        self.collect_monkeypatches = collect_monkeypatches
        # Imports are resolved for Django even when its usage isn't counted, so
        # monkeypatches of Django members can still be found.
        self.tracked_packages = (
            self.packages | {"django"} if collect_monkeypatches else self.packages
        )
        self.imports: dict[str, ImportBinding] = {}
        self.bindings: list[ImportBinding] = []
        self.usage: Counter[str] = Counter()
        self.monkeypatches: Counter[str] = Counter()

    @staticmethod
    def _within(name: str, packages: frozenset[str]) -> bool:
        return any(
            name == package or name.startswith(f"{package}.") for package in packages
        )

    def selected(self, name: str) -> bool:
        return self._within(name, self.packages)

    def tracked(self, name: str) -> bool:
        return self._within(name, self.tracked_packages)

    def resolve_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            binding = self.imports.get(node.id)
            if binding is None:
                return None
            binding.used = True
            return binding.target
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

    def public_name(self, name: str) -> str | None:
        """Return the name to report, or None when Django doesn't define it.

        Attributes after an import may be defined by the application, such as a
        monkeypatched method or a reverse relation. Other packages have no API
        catalog, so their names are reported as resolved.
        """
        if name == SETTINGS_PATH or name.startswith(SETTINGS_PREFIX):
            return self.fold_django_setting(name)
        if name == "django" or name.startswith("django."):
            return name if django_api().defines(name) else None
        return name

    def add(self, name: str) -> None:
        if not self.selected(name):
            return
        public_name = self.public_name(name)
        if public_name:
            self.usage[public_name] += 1

    def add_monkeypatch(self, name: str | None) -> None:
        """Count an assignment to a member Django defines.

        Attributes the application adds to Django objects aren't reported.
        """
        if (
            self.collect_monkeypatches
            and name
            and name.startswith("django.")
            and django_api().defines(name)
        ):
            self.monkeypatches[name] += 1

    def _record_monkeypatch(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute):
            self.add_monkeypatch(self.resolve_name(target))
        elif isinstance(target, (ast.List, ast.Tuple)):
            for element in target.elts:
                self._record_monkeypatch(element)
        elif isinstance(target, ast.Starred):
            self._record_monkeypatch(target.value)

    def bind(self, local: str, target: str, imported: str) -> None:
        binding = self.imports.get(local)
        if binding is None or binding.target != target:
            binding = ImportBinding(target)
            self.bindings.append(binding)
            self.imports[local] = binding
        binding.imported.add(imported)

    def visit_Module(self, node: ast.Module) -> None:
        self.generic_visit(node)
        for binding in self.bindings:
            if not binding.used:
                for name in binding.imported:
                    self.add(name)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if not self.tracked(alias.name):
                continue
            local = alias.asname or alias.name.partition(".")[0]
            target = alias.name if alias.asname else local
            self.bind(local, target, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module or not self.tracked(node.module):
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            full_name = f"{node.module}.{alias.name}"
            self.bind(alias.asname or alias.name, full_name, full_name)

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
            self._record_monkeypatch(target)
            self._forget_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        self._record_monkeypatch(node.target)
        self._forget_target(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.generic_visit(node)
        self._record_monkeypatch(node.target)
        self._forget_target(node.target)

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            owner = self.resolve_name(node.args[0])
            if owner:
                self.add_monkeypatch(f"{owner}.{node.args[1].value}")

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
    collect_monkeypatches: bool = False,
) -> PackageUsageVisitor:
    """Return the visitor after it walks ``tree``, holding both of its counters."""
    visitor = PackageUsageVisitor(packages, django_setting_names, collect_monkeypatches)
    visitor.visit(tree)
    return visitor
