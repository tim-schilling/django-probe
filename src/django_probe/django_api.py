"""Fold resolved names to Django's public API using the vendored catalog."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

_CATALOG = files("django_probe._vendor.django_api") / "all.json.gz"


@dataclass(frozen=True)
class DjangoAPI:
    """Public names from every supported Django version.

    Class members are listed only where they're declared, so members reached
    through a subclass, such as `User.save`, are found through `bases`.
    """

    names: frozenset[str]
    bases: dict[str, list[str]]
    types: dict[str, str]
    aliases: dict[str, str]

    def class_of(self, path: str) -> str | None:
        """Return the class whose members are reachable from ``path``."""
        target = self.aliases.get(path, path)
        if target in self.bases:
            return target
        return self.types.get(target)

    def mro(self, class_path: str) -> list[str]:
        order: list[str] = []
        pending = [class_path]
        while pending:
            current = pending.pop(0)
            if current in order:
                continue
            order.append(current)
            pending[:0] = self.bases.get(current, [])
        return order

    def member(self, class_path: str, name: str) -> str | None:
        for base in self.mro(class_path):
            path = f"{base}.{name}"
            if path in self.names:
                return path
        return None

    def fold(self, name: str) -> str | None:
        """Return the longest prefix of ``name`` that is public Django API."""
        parts = name.split(".")
        path = parts[0]
        if path not in self.names:
            return None
        class_path = self.class_of(path)
        for part in parts[1:]:
            candidate = f"{path}.{part}"
            if candidate in self.names:
                member: str | None = candidate
            elif class_path:
                member = self.member(class_path, part)
            else:
                member = None
            if member is None:
                break
            path = candidate
            class_path = self.class_of(member)
        return path


@cache
def django_api() -> DjangoAPI:
    payload = json.loads(gzip.decompress(_CATALOG.read_bytes()))
    return DjangoAPI(
        frozenset(payload["names"]),
        payload["bases"],
        payload["types"],
        payload["aliases"],
    )
