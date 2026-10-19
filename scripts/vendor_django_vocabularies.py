from __future__ import annotations

import argparse
import ast
import gzip
import io
import json
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import django

_SETTINGS_PROXY_ATTRIBUTES = frozenset({"SETTINGS_MODULE"})

# These public singleton proxies delegate attributes to interfaces that cannot be
# inferred from their assignments alone.
_DELEGATED_API_CLASSES = {
    "django.contrib.admin.site": "django.contrib.admin.sites.AdminSite",
    "django.core.cache.cache": "django.core.cache.backends.base.BaseCache",
    "django.db.connection": "django.db.backends.base.base.BaseDatabaseWrapper",
}


@dataclass
class Module:
    """Static public bindings and re-exports found in one Django module."""

    name: str
    package: str
    bindings: dict[str, str | None] = field(default_factory=dict)
    star_imports: set[str] = field(default_factory=set)
    all_names: set[str] | None = None


def _public(name: str) -> bool:
    """Return whether a Python name is public by Django's naming convention."""
    return not name.startswith("_")


def _targets(node: ast.AST) -> set[str]:
    """Return names bound by a simple or unpacked assignment target."""
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.List, ast.Tuple)):
        return set().union(*(_targets(element) for element in node.elts))
    return set()


def _literal_names(node: ast.AST) -> set[str] | None:
    """Read a literal collection of strings, such as a module's __all__."""
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    if not all(isinstance(element, ast.Constant) for element in node.elts):
        return None
    values = {element.value for element in node.elts}
    if not all(isinstance(value, str) for value in values):
        return None
    return values


def _relative_module(package: str, level: int, name: str | None) -> str:
    """Resolve an ImportFrom node to its absolute module path."""
    parts = package.split(".")
    base = parts[: len(parts) - level + 1]
    if name:
        base.extend(name.split("."))
    return ".".join(base)


def _expression_path(node: ast.AST, module: Module) -> str | None:
    """Resolve a name or attribute expression through known module bindings."""
    if isinstance(node, ast.Name):
        return module.bindings.get(node.id) or f"{module.name}.{node.id}"
    if isinstance(node, ast.Attribute):
        parent = _expression_path(node.value, module)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def _class_members(node: ast.ClassDef) -> set[str]:
    """Collect the public members declared directly on a class."""
    members: set[str] = set()
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if _public(item.name):
                members.add(item.name)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                members.update(name for name in _targets(target) if _public(name))
        elif isinstance(item, ast.AnnAssign):
            members.update(name for name in _targets(item.target) if _public(name))
    return members


def _module_name(root: Path, path: Path) -> tuple[str, str] | None:
    """Return a public module's import path and containing package."""
    relative = path.relative_to(root)
    parts = list(relative.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    if any(part.startswith("_") for part in parts):
        return None
    name = ".".join(("django", *parts))
    package = name if is_package else name.rpartition(".")[0]
    return name, package


def _parse_module(
    root: Path,
    path: Path,
    class_members: dict[str, set[str]],
) -> Module | None:
    """Parse one module into bindings, star imports, and class members."""
    identity = _module_name(root, path)
    if identity is None:
        return None
    name, package = identity
    module = Module(name, package)
    tree = ast.parse(path.read_bytes(), filename=str(path))

    # Build a symbol table from source instead of importing Django modules. Some
    # modules require optional database or GIS libraries just to import.
    for node in tree.body:
        if isinstance(node, ast.Import):
            # Direct imports only expose Django names when resolving Django's API.
            for alias in node.names:
                local = alias.asname or alias.name.partition(".")[0]
                target = alias.name if alias.asname else local
                if _public(local) and target.startswith("django"):
                    module.bindings[local] = target
        elif isinstance(node, ast.ImportFrom):
            # Resolve explicit re-exports now and defer star imports until every
            # module has a symbol table.
            target_module = (
                _relative_module(package, node.level, node.module)
                if node.level
                else node.module
            )
            if not target_module or not target_module.startswith("django"):
                continue
            for alias in node.names:
                if alias.name == "*":
                    module.star_imports.add(target_module)
                    continue
                local = alias.asname or alias.name
                if _public(local):
                    module.bindings[local] = f"{target_module}.{alias.name}"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Functions are terminal API names; they do not expose nested members.
            if _public(node.name):
                module.bindings[node.name] = None
        elif isinstance(node, ast.ClassDef):
            # Class members are retained only when declared directly. Expanding
            # inherited members under every subclass creates tens of thousands of
            # duplicate paths that are not useful as a sanitization allowlist.
            if not _public(node.name):
                continue
            class_path = f"{name}.{node.name}"
            module.bindings[node.name] = class_path
            class_members[class_path] = _class_members(node)
        elif isinstance(node, ast.Assign):
            # Assignments can expose constants, aliases, or instances whose class
            # members should also be available from the assigned public path.
            names = set().union(*(_targets(target) for target in node.targets))
            if "__all__" in names:
                module.all_names = _literal_names(node.value)
            value = node.value.func if isinstance(node.value, ast.Call) else node.value
            reference = _expression_path(value, module)
            for target_name in names:
                if _public(target_name):
                    module.bindings[target_name] = reference
        elif isinstance(node, ast.AnnAssign):
            # An annotation without a resolvable value still declares a public name.
            for target_name in _targets(node.target):
                if _public(target_name):
                    module.bindings[target_name] = None
    if module.all_names:
        for public_name in module.all_names:
            module.bindings.setdefault(public_name, None)
    return module


def _resolve_alias(path: str, aliases: dict[str, str | None]) -> str:
    """Follow a re-export chain while protecting against alias cycles."""
    seen: set[str] = set()
    target = aliases.get(path)
    while path not in seen and target:
        seen.add(path)
        path = target
        target = aliases.get(path)
    return path


def build_api_vocabulary(root: Path) -> frozenset[str]:
    """Build every public API path exposed by a Django source tree."""
    modules: dict[str, Module] = {}
    class_members: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        module = _parse_module(root, path, class_members)
        if module is not None:
            modules[module.name] = module

    # Package __init__ modules frequently re-export several layers of star
    # imports. Expand them until a pass adds no new public bindings.
    changed = True
    while changed:
        changed = False
        for module in modules.values():
            for imported_name in module.star_imports:
                imported = modules.get(imported_name)
                if imported is None:
                    continue
                names = imported.all_names or set(imported.bindings)
                for name in names:
                    if not _public(name) or name in module.bindings:
                        continue
                    module.bindings[name] = f"{imported_name}.{name}"
                    changed = True

    aliases = {
        f"{module.name}.{name}": target
        for module in modules.values()
        for name, target in module.bindings.items()
    }
    # Preserve the public path callers use for re-exported classes and
    # module-level instances, rather than only the object's defining path.
    names = set(modules)
    names.update(aliases)
    for alias, target in aliases.items():
        if target is None:
            continue
        resolved = _resolve_alias(target, aliases)
        names.update(
            f"{alias}.{member}" for member in class_members.get(resolved, set())
        )
    for class_path, members in class_members.items():
        names.update(f"{class_path}.{member}" for member in members)
    for public_path, class_path in _DELEGATED_API_CLASSES.items():
        names.update(
            f"{public_path}.{member}" for member in class_members.get(class_path, set())
        )
    return frozenset(names)


def _referenced_settings(root: Path) -> set[str]:
    """Collect setting names Django reads through its settings proxy."""
    names: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "django.conf"
            for alias in node.names
            if alias.name == "settings"
        }
        if not aliases:
            continue

        for node in ast.walk(tree):
            # Most settings are ordinary attributes on django.conf.settings.
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
                and node.attr.isupper()
                and _public(node.attr)
            ):
                names.add(node.attr)
            # Optional settings are also commonly accessed with getattr or hasattr.
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "hasattr"}
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in aliases
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value.isupper()
                and _public(node.args[1].value)
            ):
                names.add(node.args[1].value)
    return names - _SETTINGS_PROXY_ATTRIBUTES


def build_settings_vocabulary(root: Path) -> frozenset[str]:
    """Build the global and optional setting names recognized by Django."""
    path = root / "conf" / "global_settings.py"
    tree = ast.parse(path.read_bytes(), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(
                    name
                    for name in _targets(target)
                    if name.isupper() and _public(name)
                )
        elif isinstance(node, ast.AnnAssign):
            names.update(
                name
                for name in _targets(node.target)
                if name.isupper() and _public(name)
            )
    names.update(_referenced_settings(root))
    return frozenset(names)


def _write_compressed_json(path: Path, payload: dict[str, object]) -> None:
    """Write deterministic compressed JSON for an API vocabulary."""
    contents = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    # gzip.compress sets the header's OS byte differently across Python versions,
    # and the catalogs are written by several interpreters. GzipFile always
    # writes the same header.
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as file:
        file.write(contents)
    path.write_bytes(buffer.getvalue())


def _write_combined_api_vocabulary(output_dir: Path) -> int:
    """Combine the versioned API catalogs into one sorted vocabulary."""
    names: set[str] = set()
    versions: dict[str, str] = {}
    for path in sorted(output_dir.glob("[0-9]*.json.gz")):
        payload = json.loads(gzip.decompress(path.read_bytes()))
        version = path.name.removesuffix(".json.gz")
        versions[version] = payload["django_version"]
        names.update(payload["names"])
    _write_compressed_json(
        output_dir / "all.json.gz",
        {"django_versions": versions, "names": sorted(names)},
    )
    return len(names)


def main() -> None:
    """Write API and settings catalogs for the installed Django release."""
    parser = argparse.ArgumentParser(
        description="Vendor the installed Django release's vocabularies."
    )
    parser.add_argument(
        "--api-output-dir",
        type=Path,
        default=Path(__file__).parents[1] / "src" / "webapp" / "ingest" / "django_api",
    )
    parser.add_argument(
        "--settings-output-dir",
        type=Path,
        default=Path(__file__).parents[1]
        / "src"
        / "django_probe"
        / "_vendor"
        / "django_settings",
    )
    args = parser.parse_args()

    version = ".".join(str(part) for part in django.VERSION[:2])
    distribution_version = metadata.version("Django")
    root = Path(django.__path__[0])
    api_names = build_api_vocabulary(root)
    settings_names = build_settings_vocabulary(root)

    # API catalogs are large, while settings catalogs stay plain for readable
    # diffs during Django release updates.
    args.api_output_dir.mkdir(parents=True, exist_ok=True)
    api_destination = args.api_output_dir / f"{version}.json.gz"
    _write_compressed_json(
        api_destination,
        {"django_version": distribution_version, "names": sorted(api_names)},
    )
    combined_api_count = _write_combined_api_vocabulary(args.api_output_dir)
    args.settings_output_dir.mkdir(parents=True, exist_ok=True)
    settings_destination = args.settings_output_dir / f"{version}.json"
    settings_destination.write_text(
        json.dumps(
            {
                "django_version": distribution_version,
                "names": sorted(settings_names),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Vendored {len(api_names)} API and {len(settings_names)} setting names "
        f"from Django {distribution_version}; the combined API vocabulary contains "
        f"{combined_api_count} names."
    )


if __name__ == "__main__":
    main()
