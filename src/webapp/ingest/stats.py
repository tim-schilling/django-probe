"""Public aggregate statistics over the latest submission of each project."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum
from functools import cached_property
from typing import Never, TypedDict
from urllib.parse import urlencode

from django import forms
from django.db import connection
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL

from django_probe.settings import DJANGO_SETTING_NAMES
from ingest.django_api import is_django_api_name
from ingest.models import SIZE_BUCKETS, Submission, SubmissionQuerySet

MINIMUM_PROJECTS = 10
POPULAR_LIMIT = 10
MAX_KEYS = 10

# Django and its requirements across every series in DJANGO_VERSIONS.
DJANGO_DEPENDENCIES = frozenset(
    {"asgiref", "backports-zoneinfo", "django", "pytz", "sqlparse", "tzdata"}
)
_NORMALIZED_PACKAGE_NAME_PATTERN = r"^[a-z\d]([a-z\d-]*[a-z\d])?$"
# The PEP 503 normalized form of a stored dependency name ``key``.
_NORMALIZED_PACKAGE_NAME_SQL = "regexp_replace(lower(key), '[-_.]+', '-', 'g')"
# Alphabetical to match Cloudflare query string sorting
FILTER_FIELDS = ("django", "key", "python", "size")

# Older versions are grouped into ``other``, and newer ones appear as soon as a project reports them.
DJANGO_VERSIONS = (
    "2.2",
    "3.0",
    "3.1",
    "3.2",
    "4.0",
    "4.1",
    "4.2",
    "5.0",
    "5.1",
    "5.2",
    "6.0",
    "6.1",
)
PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")

_MINOR_VERSION_PATTERN = r"^[1-9]\d?\.(0|[1-9]\d{0,2})$"


class KeySource(StrEnum):
    """Where a key comes from: a setting name, a ``django.`` usage name or a
    normalized dependency name.

    A key is its source and name joined by a colon, like ``setting:CACHES``.
    """

    SETTING = "setting"
    USAGE = "usage"
    DEPENDENCY = "dependency"

    def key(self, name: str) -> str:
        return f"{self}:{name}"

    @property
    def label(self) -> str:
        return _KEY_LABELS[self]


_KEY_LABELS = {
    KeySource.SETTING: "settings",
    KeySource.USAGE: "Django APIs",
    KeySource.DEPENDENCY: "dependencies",
}

# ``key`` is a list, since a project must use every key to match; the rest are
# strings.
Filters = dict[str, str | list[str]]


class DistributionRow(TypedDict):
    value: str
    label: str
    projects: int


class Distribution(TypedDict):
    values: list[DistributionRow]
    other: int


class MatrixCell(TypedDict):
    python: str | None
    projects: int


class MatrixRow(TypedDict):
    django: str | None
    cells: list[MatrixCell]


class Matrix(TypedDict):
    python: list[str | None]
    rows: list[MatrixRow]


class KeyCount(TypedDict):
    key: str
    name: str
    source: KeySource
    projects: int | None


class Summary(TypedDict):
    minimum_projects: int
    filters: Filters
    withheld: bool
    projects: int | None


class Overview(Summary):
    distributions: dict[str, Distribution]
    django_python: Matrix | dict[str, Never]
    popular: dict[KeySource, list[KeyCount]]


class KeysSummary(Summary):
    keys: list[KeyCount]


def parse_key(key: str) -> tuple[KeySource, str]:
    """The source and name of a valid key."""
    source, _, name = key.partition(":")
    return KeySource(source), name


def is_key(key: str) -> bool:
    """Whether ``key`` names a Django setting or API, or a published package."""
    source, _, name = key.partition(":")
    if source == KeySource.SETTING:
        return name in DJANGO_SETTING_NAMES
    if source == KeySource.USAGE:
        return name.startswith("django.") and is_django_api_name(name)
    if source == KeySource.DEPENDENCY:
        return (
            re.fullmatch(_NORMALIZED_PACKAGE_NAME_PATTERN, name) is not None
            and name not in DJANGO_DEPENDENCIES
        )
    return False


def _with_source(key: str) -> str:
    """``key``, prefixing the bare setting and API names used before prefixes.

    Links with bare names then redirect to their prefixed form.
    """
    if ":" in key:
        return key
    return (KeySource.USAGE if "." in key else KeySource.SETTING).key(key)


class KeysField(forms.Field):
    """Known keys, deduplicated and sorted."""

    widget = forms.MultipleHiddenInput

    def clean(self, value: list[str] | None) -> list[str]:
        keys = sorted({_with_source(key) for key in value or []})
        if len(keys) > MAX_KEYS:
            raise forms.ValidationError(f"At most {MAX_KEYS} keys.")
        if not all(is_key(key) for key in keys):
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

    def filters(self) -> Filters:
        """The non-empty cleaned values, in a stable order."""
        return {
            name: self.cleaned_data[name]
            for name in FILTER_FIELDS
            if self.cleaned_data.get(name)
        }


def filter_keys(filters: Filters) -> list[str]:
    keys = filters.get("key", [])
    return keys if isinstance(keys, list) else [keys]


def query_string(filters: Mapping[str, str | list[str] | None]) -> str:
    """The canonical query string for ``filters``: known fields, fixed order, no blanks."""
    pairs: list[tuple[str, str]] = []
    for name in FILTER_FIELDS:
        value = filters.get(name)
        if isinstance(value, list):
            pairs.extend((name, key) for key in sorted(set(value)))
        elif value:
            pairs.append((name, value))
    return urlencode(pairs, safe=":")


def _uses(key: str) -> Q | RawSQL:
    """A condition matching the submissions that use ``key``.

    Stored dependency names may be spelled in any way that normalizes to ``key``.
    """
    source, name = parse_key(key)
    if source == KeySource.DEPENDENCY:
        return RawSQL(
            f"""EXISTS (
                SELECT 1
                FROM jsonb_object_keys("{Submission._meta.db_table}"."dependencies") AS key
                WHERE {_NORMALIZED_PACKAGE_NAME_SQL} = %s
            )""",
            [name],
            output_field=BooleanField(),
        )
    field = "django_settings" if source == KeySource.SETTING else "usage"
    return Q(**{f"{field}__has_key": name})


def _version_sort_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _shown_versions(
    reported: Iterable[str | None], versions: tuple[str, ...]
) -> list[str]:
    """``versions`` plus any newer ones reported, newest first."""
    oldest = _version_sort_key(versions[0])
    shown = set(versions) | {
        version
        for version in reported
        if version is not None and _version_sort_key(version) >= oldest
    }
    return sorted(shown, key=_version_sort_key, reverse=True)


class Cohort:
    """The projects matching ``filters``, and the statistics published about them."""

    def __init__(self, filters: Filters) -> None:
        self.filters = filters

    @cached_property
    def queryset(self) -> SubmissionQuerySet:
        queryset = (
            Submission.objects.latest_per_project().with_minor_versions().with_size()
        )
        if "django" in self.filters:
            queryset = queryset.filter(django_minor=self.filters["django"])
        if "python" in self.filters:
            queryset = queryset.filter(python_minor=self.filters["python"])
        if "size" in self.filters:
            queryset = queryset.filter(size=self.filters["size"])
        for key in filter_keys(self.filters):
            queryset = queryset.filter(_uses(key))
        return queryset

    @cached_property
    def projects(self) -> int:
        return self.queryset.count()

    @property
    def withheld(self) -> bool:
        return self.projects < MINIMUM_PROJECTS

    def overview(self) -> Overview:
        if self.withheld:
            return {
                **self._summary(),
                "distributions": {},
                "django_python": {},
                "popular": {},
            }
        return {
            **self._summary(),
            "distributions": {
                "django": self._version_distribution("django_minor", DJANGO_VERSIONS),
                "python": self._version_distribution("python_minor", PYTHON_VERSIONS),
                "size": self._size_distribution(),
            },
            "django_python": self._version_matrix(),
            "popular": self._popular_keys(),
        }

    def keys(self, source: KeySource | None = None) -> KeysSummary:
        """Every key in the cohort, for browsing.

        ``source`` limits them to one kind.
        """
        return {
            **self._summary(),
            "keys": [] if self.withheld else self._all_keys(source),
        }

    def _summary(self) -> Summary:
        return {
            "minimum_projects": MINIMUM_PROJECTS,
            "filters": self.filters,
            "withheld": self.withheld,
            "projects": None if self.withheld else self.projects,
        }

    def _version_distribution(
        self, field: str, versions: tuple[str, ...]
    ) -> Distribution:
        """Counts for ``versions`` and anything newer, with older versions as ``other``."""
        counts = self.queryset.count_by(field)
        shown = _shown_versions(counts, versions)
        return {
            "values": [
                {"value": version, "label": version, "projects": counts.get(version, 0)}
                for version in shown
            ],
            "other": sum(
                projects for version, projects in counts.items() if version not in shown
            ),
        }

    def _size_distribution(self) -> Distribution:
        counts = self.queryset.count_by("size")
        return {
            "values": [
                {
                    "value": bucket.value,
                    "label": bucket.label,
                    "projects": counts.get(bucket.value, 0),
                }
                for bucket in SIZE_BUCKETS
            ],
            "other": 0,
        }

    def _version_matrix(self) -> Matrix:
        """Projects by Django and Python version together.

        Rows are Django versions and columns Python versions, shown as in their own
        distributions. None stands for older or unrecognized versions, and is only
        included when some project falls there.
        """
        counts = self.queryset.count_by_versions()
        djangos: list[str | None] = [
            *_shown_versions({django for django, _ in counts}, DJANGO_VERSIONS)
        ]
        pythons: list[str | None] = [
            *_shown_versions({python for _, python in counts}, PYTHON_VERSIONS)
        ]
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

    def _key_counts(self, source: KeySource | None = None) -> list[KeyCount]:
        """Every key with its project count.

        Settings and APIs below ``MINIMUM_PROJECTS`` get a count of None.
        Dependencies below it are left out, since a package name may be private.

        Stored payloads are untrusted, so every value is a bound parameter and
        only known names or valid package names are returned.
        """
        cohort_sql, params = (
            self.queryset.values("django_settings", "usage", "dependencies")
            .order_by()
            .query.sql_with_params()
        )
        sql = f"""
            SELECT
                found.key,
                found.source,
                CASE WHEN COUNT(*) >= %s THEN COUNT(*) END
            FROM ({cohort_sql}) AS cohort
            CROSS JOIN LATERAL (
                SELECT key, %s::text AS source
                FROM jsonb_object_keys(cohort.django_settings) AS key
                WHERE key = ANY(%s)
                UNION ALL
                SELECT key, %s::text AS source
                FROM jsonb_object_keys(cohort.usage) AS key
                WHERE key LIKE 'django.%%'
                UNION ALL
                SELECT DISTINCT name, %s::text AS source
                FROM (
                    SELECT {_NORMALIZED_PACKAGE_NAME_SQL} AS name
                    FROM jsonb_object_keys(cohort.dependencies) AS key
                ) AS dependency
                WHERE name ~ %s AND NOT (name = ANY(%s))
            ) AS found
            WHERE %s::text IS NULL OR found.source = %s
            GROUP BY found.key, found.source
            HAVING found.source <> %s OR COUNT(*) >= %s
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    MINIMUM_PROJECTS,
                    *params,
                    KeySource.SETTING,
                    sorted(DJANGO_SETTING_NAMES),
                    KeySource.USAGE,
                    KeySource.DEPENDENCY,
                    _NORMALIZED_PACKAGE_NAME_PATTERN,
                    sorted(DJANGO_DEPENDENCIES),
                    source,
                    source,
                    KeySource.DEPENDENCY,
                    MINIMUM_PROJECTS,
                ],
            )
            rows: list[KeyCount] = [
                {
                    "key": KeySource(found).key(name),
                    "name": name,
                    "source": KeySource(found),
                    "projects": projects,
                }
                for name, found, projects in cursor.fetchall()
            ]
        return [
            row
            for row in rows
            if row["source"] != KeySource.USAGE or is_django_api_name(row["name"])
        ]

    def _all_keys(self, source: KeySource | None = None) -> list[KeyCount]:
        """Every key in the cohort.

        Sorted by source, then counted keys ahead of those with too few projects,
        then name. Every setting name the client recognizes is listed, including
        those no project defines.
        """
        keys = self._key_counts(source)
        if source in (None, KeySource.SETTING):
            used = {row["name"] for row in keys if row["source"] == KeySource.SETTING}
            keys += [
                {
                    "key": KeySource.SETTING.key(name),
                    "name": name,
                    "source": KeySource.SETTING,
                    "projects": None,
                }
                for name in DJANGO_SETTING_NAMES - used
            ]
        return sorted(
            keys,
            key=lambda row: (
                row["source"],
                row["projects"] is None,
                row["name"].lower(),
                row["name"],
            ),
        )

    def _popular_keys(self) -> dict[KeySource, list[KeyCount]]:
        """The most used names of each source, for the overview page."""
        ranked = sorted(
            (row for row in self._key_counts() if row["projects"] is not None),
            key=lambda row: (-(row["projects"] or 0), row["name"]),
        )
        return {
            source: [row for row in ranked if row["source"] == source][:POPULAR_LIMIT]
            for source in KeySource
        }
