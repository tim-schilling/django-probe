"""Public aggregate statistics over the latest submission of each project.

Nothing here may return a project, organization or submission identifier. A
filter combination matching fewer than ``MINIMUM_PROJECTS`` projects is withheld
entirely, so no result can be narrowed down to a single project. Within a result,
counts are exact: a small count doesn't say which projects it is.

Usage keys are limited to ``django.`` names. Projects can collect usage of their
own packages, whose names must never be published.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from django import forms
from django.db import connection
from django.db.models import Case, CharField, Count, F, Func, Q, QuerySet, Value, When

from django_probe.settings import DJANGO_SETTING_NAMES
from ingest.models import Submission

MINIMUM_PROJECTS = 5
POPULAR_KEYS_LIMIT = 10
#: Each key narrows the cohort, so a handful is plenty; the cap keeps URLs sane.
MAX_KEYS = 10
FILTER_FIELDS = ("django", "python", "size", "key")
KEY_FIELDS = {"setting": "django_settings", "usage": "usage"}
KEY_SOURCES = tuple(KEY_FIELDS)

#: Always listed, even when no project uses them. Older versions are grouped into
#: ``other``, and newer ones appear as soon as a project reports them.
DJANGO_VERSIONS = ("4.2", "5.0", "5.1", "5.2", "6.0", "6.1")
PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")


@dataclass(frozen=True)
class SizeBucket:
    value: str
    label: str
    lower: int
    upper: int | None


#: Provisional groupings of ``files_scanned``. Expect these to change as the data
#: shows where the meaningful boundaries are.
SIZE_BUCKETS = (
    SizeBucket("small", "Small (under 50 files)", 0, 50),
    SizeBucket("medium", "Medium (50-249 files)", 50, 250),
    SizeBucket("large", "Large (250-999 files)", 250, 1000),
    SizeBucket("very-large", "Very large (1000+ files)", 1000, None),
)
SIZE_LABELS = {bucket.value: bucket.label for bucket in SIZE_BUCKETS}

_MINOR_VERSION_PATTERN = r"^[1-9]\d?\.(0|[1-9]\d{0,2})$"
_SETTING_PATTERN = r"^[A-Z][A-Z0-9_]{0,99}$"
_USAGE_PATTERN = r"^django(\.[A-Za-z_][A-Za-z0-9_]*){1,10}$"


def key_source(key: str) -> str:
    return "usage" if "." in key else "setting"


class KeysField(forms.Field):
    """Setting names or ``django.`` usage keys, validated, deduplicated and sorted."""

    widget = forms.MultipleHiddenInput

    def clean(self, value: list[str] | None) -> list[str]:
        keys = sorted(set(value or []))
        if len(keys) > MAX_KEYS:
            raise forms.ValidationError(f"At most {MAX_KEYS} keys.")
        if not all(
            re.fullmatch(_SETTING_PATTERN, key) or re.fullmatch(_USAGE_PATTERN, key)
            for key in keys
        ):
            raise forms.ValidationError("Invalid key.")
        return keys


class StatsFilterForm(forms.Form):
    django = forms.RegexField(regex=_MINOR_VERSION_PATTERN, required=False)
    python = forms.RegexField(regex=_MINOR_VERSION_PATTERN, required=False)
    size = forms.ChoiceField(
        choices=[(bucket.value, bucket.label) for bucket in SIZE_BUCKETS],
        required=False,
    )
    key = KeysField(required=False)

    def filters(self) -> dict[str, Any]:
        """The non-empty cleaned values, in a stable order.

        ``key`` is a list, since a project must use every key to match; the rest
        are strings.
        """
        return {
            name: self.cleaned_data[name]
            for name in FILTER_FIELDS
            if self.cleaned_data.get(name)
        }


def query_string(filters: dict[str, Any]) -> str:
    """The canonical query string for ``filters``: known fields, fixed order, no blanks."""
    pairs = []
    for name in FILTER_FIELDS:
        value = filters.get(name)
        if name == "key":
            pairs.extend((name, key) for key in sorted(set(value or [])))
        elif value:
            pairs.append((name, value))
    return urlencode(pairs)


class MinorVersion(Func):
    """The leading ``major.minor`` of a version string, or NULL if it has none."""

    function = "substring"
    output_field = CharField()

    def __init__(self, expression, **extra):
        super().__init__(expression, Value(r"^\d+\.\d+"), **extra)


def _size_bucket() -> Case:
    whens = []
    for bucket in SIZE_BUCKETS:
        condition = Q(files_scanned__gte=bucket.lower)
        if bucket.upper is not None:
            condition &= Q(files_scanned__lt=bucket.upper)
        whens.append(When(condition, then=Value(bucket.value)))
    return Case(*whens, output_field=CharField())


def latest_submissions() -> QuerySet[Submission]:
    """Each project's most recent submission, annotated with its facet values.

    Anonymous submissions are left out because there is no way to tell whether two
    of them came from the same project.
    """
    latest_ids = (
        Submission.objects.filter(project__isnull=False)
        .order_by("project_id", "-created_at")
        .distinct("project_id")
        .values("id")
    )
    return Submission.objects.filter(id__in=latest_ids).annotate(
        django_minor=MinorVersion(F("django_version")),
        python_minor=MinorVersion(F("python_version")),
        size=_size_bucket(),
    )


def cohort(filters: dict[str, Any]) -> QuerySet[Submission]:
    queryset = latest_submissions()
    if "django" in filters:
        queryset = queryset.filter(django_minor=filters["django"])
    if "python" in filters:
        queryset = queryset.filter(python_minor=filters["python"])
    if "size" in filters:
        queryset = queryset.filter(size=filters["size"])
    for key in filters.get("key", []):
        field = KEY_FIELDS[key_source(key)]
        queryset = queryset.filter(**{f"{field}__has_key": key})
    return queryset


def _version_sort_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _row(value: str, label: str, projects: int) -> dict[str, Any]:
    return {"value": value, "label": label, "projects": projects}


def _counts(queryset: QuerySet[Submission], field: str) -> dict[str | None, int]:
    return dict(queryset.values_list(field).annotate(Count("id")).order_by())


def _shown_versions(reported, versions: tuple[str, ...]) -> list[str]:
    """``versions`` plus any newer ones reported, newest first."""
    oldest = _version_sort_key(versions[0])
    shown = set(versions) | {
        version
        for version in reported
        if version is not None and _version_sort_key(version) >= oldest
    }
    return sorted(shown, key=_version_sort_key, reverse=True)


def _version_distribution(
    queryset: QuerySet[Submission], field: str, versions: tuple[str, ...]
) -> dict[str, Any]:
    """Counts for ``versions`` and anything newer, with older versions as ``other``."""
    counts = _counts(queryset, field)
    shown = _shown_versions(counts, versions)
    other = sum(
        projects for version, projects in counts.items() if version not in shown
    )
    return {
        "values": [_row(version, version, counts.get(version, 0)) for version in shown],
        "other": other,
    }


def _version_matrix(queryset: QuerySet[Submission]) -> dict[str, Any]:
    """Projects by Django and Python version together.

    Rows are Django versions and columns Python versions, shown as in their own
    distributions. None stands for older or unrecognized versions, and is only
    included when some project falls there.
    """
    rows = (
        queryset.values_list("django_minor", "python_minor")
        .annotate(Count("id"))
        .order_by()
    )
    counts = {(django, python): projects for django, python, projects in rows}
    djangos = _shown_versions({django for django, _ in counts}, DJANGO_VERSIONS)
    pythons = _shown_versions({python for _, python in counts}, PYTHON_VERSIONS)
    cells: Counter[tuple[str | None, str | None]] = Counter()
    for (django, python), projects in counts.items():
        cells[
            django if django in djangos else None,
            python if python in pythons else None,
        ] += projects

    if any(cells[None, python] for python in [*pythons, None]):
        djangos.append(None)
    if any(cells[django, None] for django in djangos):
        pythons.append(None)
    return {
        "python": pythons,
        "rows": [
            {
                "django": django,
                "cells": [
                    {"python": python, "projects": cells[django, python]}
                    for python in pythons
                ],
            }
            for django in djangos
        ],
    }


def _size_distribution(queryset: QuerySet[Submission]) -> dict[str, Any]:
    counts = _counts(queryset, "size")
    return {
        "values": [
            _row(bucket.value, bucket.label, counts.get(bucket.value, 0))
            for bucket in SIZE_BUCKETS
        ],
        "other": 0,
    }


def list_keys(
    queryset: QuerySet[Submission], source: str | None = None
) -> list[dict[str, Any]]:
    """Setting names and ``django.`` usage keys used in ``queryset``, with counts.

    ``source`` limits them to either ``"setting"`` or ``"usage"``.
    """
    cohort_sql, params = queryset.values(
        "django_settings", "usage"
    ).query.sql_with_params()
    sql = f"""
        SELECT found.key, found.source, COUNT(*)
        FROM ({cohort_sql}) AS cohort
        CROSS JOIN LATERAL (
            SELECT key, 'setting' AS source
            FROM jsonb_object_keys(cohort.django_settings) AS key
            UNION ALL
            SELECT key, 'usage' AS source
            FROM jsonb_object_keys(cohort.usage) AS key
            WHERE key LIKE 'django.%%'
        ) AS found
        WHERE %s::text IS NULL OR found.source = %s
        GROUP BY found.key, found.source
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [*params, source, source])
        return [
            {"key": key, "source": source, "projects": projects}
            for key, source, projects in cursor.fetchall()
        ]


def _summary(filters: dict[str, Any]) -> tuple[QuerySet[Submission], dict[str, Any]]:
    queryset = cohort(filters)
    projects = queryset.count()
    withheld = projects < MINIMUM_PROJECTS
    return queryset, {
        "minimum_projects": MINIMUM_PROJECTS,
        "filters": filters,
        "withheld": withheld,
        "projects": None if withheld else projects,
    }


def _all_keys(
    queryset: QuerySet[Submission], source: str | None = None
) -> list[dict[str, Any]]:
    """Every setting and usage key in the cohort, sorted by source, then name.

    Every setting name the client recognizes is listed, including those no project
    defines.
    """
    keys = list_keys(queryset, source=source)
    if source in (None, "setting"):
        used = {row["key"] for row in keys if row["source"] == "setting"}
        keys += [
            {"key": name, "source": "setting", "projects": 0}
            for name in DJANGO_SETTING_NAMES - used
        ]
    return sorted(keys, key=lambda row: (row["source"], row["key"].lower(), row["key"]))


def _popular_keys(queryset: QuerySet[Submission]) -> dict[str, list[dict[str, Any]]]:
    """The most used names of each source, for the overview page."""
    ranked = sorted(list_keys(queryset), key=lambda row: (-row["projects"], row["key"]))
    return {
        source: [row for row in ranked if row["source"] == source][:POPULAR_KEYS_LIMIT]
        for source in KEY_SOURCES
    }


def summarize(filters: dict[str, Any]) -> dict[str, Any]:
    queryset, summary = _summary(filters)
    if summary["withheld"]:
        return summary | {"distributions": {}, "django_python": {}, "popular": {}}
    return summary | {
        "distributions": {
            "django": _version_distribution(queryset, "django_minor", DJANGO_VERSIONS),
            "python": _version_distribution(queryset, "python_minor", PYTHON_VERSIONS),
            "size": _size_distribution(queryset),
        },
        "django_python": _version_matrix(queryset),
        "popular": _popular_keys(queryset),
    }


def summarize_keys(
    filters: dict[str, Any], source: str | None = None
) -> dict[str, Any]:
    """Every setting and usage key in the cohort, for browsing."""
    queryset, summary = _summary(filters)
    summary["keys"] = [] if summary["withheld"] else _all_keys(queryset, source)
    return summary
