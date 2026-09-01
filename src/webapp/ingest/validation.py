"""Payload validation and plausibility bounds.

Two jobs. The first is ordinary type checking. The second is bounding fabricated
data: anyone can POST anything to a public ingest endpoint, so numbers that cannot
describe a real codebase are rejected outright.

What this deliberately does *not* do is check pattern names against a known
vocabulary. That would couple the server to the client's release cadence and break
third-party probes the moment they appear. Only the ``namespace:name`` shape is
enforced; the count and length caps bound the damage instead.
"""

from __future__ import annotations

import uuid

SCHEMA_VERSION = 1

MAX_BODY_BYTES = 256 * 1024
MAX_DEPENDENCIES = 2000
MAX_PATTERNS = 500
MAX_PROBE_SOURCES = 100
MAX_STRING = 128
MAX_COUNT = 1_000_000
MAX_FILES = 200_000


class ValidationError(Exception):
    pass


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if len(value) > MAX_STRING:
        raise ValidationError(f"{field} exceeds {MAX_STRING} characters")
    return value


def _str_map(value: object, field: str, max_entries: int) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object")
    if len(value) > max_entries:
        raise ValidationError(f"{field} exceeds {max_entries} entries")
    for key, item in value.items():
        _string(key, f"{field} key")
        _string(item, f"{field}[{key}]")
    return value


def _patterns(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValidationError("patterns must be an object")
    if len(value) > MAX_PATTERNS:
        raise ValidationError(f"patterns exceeds {MAX_PATTERNS} entries")

    for key, count in value.items():
        _string(key, "patterns key")
        namespace, separator, name = key.partition(":")
        if not separator or not namespace or not name or ":" in name:
            raise ValidationError(
                f"pattern key {key!r} must have the form 'namespace:name'"
            )
        # bool is a subclass of int, and `True` is not a count.
        if not isinstance(count, int) or isinstance(count, bool):
            raise ValidationError(f"patterns[{key}] must be an integer")
        if not 0 <= count <= MAX_COUNT:
            raise ValidationError(f"patterns[{key}] out of range")
    return value


def validate_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError(f"unsupported schema_version, expected {SCHEMA_VERSION}")

    files_scanned = payload.get("files_scanned")
    if not isinstance(files_scanned, int) or isinstance(files_scanned, bool):
        raise ValidationError("files_scanned must be an integer")
    if not 0 <= files_scanned <= MAX_FILES:
        raise ValidationError("files_scanned out of range")

    project_key = payload.get("project_key")
    if project_key is not None:
        try:
            project_key = uuid.UUID(str(project_key))
        except (ValueError, AttributeError, TypeError):
            raise ValidationError("project_key must be a UUID") from None

    return {
        "schema_version": SCHEMA_VERSION,
        "client_version": _string(payload.get("client_version", ""), "client_version"),
        "python_version": _string(payload.get("python_version", ""), "python_version"),
        "django_version": _string(payload.get("django_version", ""), "django_version"),
        "project_key": project_key,
        "files_scanned": files_scanned,
        "probe_sources": _str_map(
            payload.get("probe_sources", {}), "probe_sources", MAX_PROBE_SOURCES
        ),
        "patterns": _patterns(payload.get("patterns", {})),
        "dependencies": _str_map(
            payload.get("dependencies", {}), "dependencies", MAX_DEPENDENCIES
        ),
    }
