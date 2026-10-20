"""Public aggregate statistics over the latest submission of each project."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from functools import cached_property
from typing import Never, TypedDict
from urllib.parse import urlencode

from django import forms
from django.db import connection

from django_probe.settings import DJANGO_SETTING_NAMES
from ingest.django_api import is_django_api_name
from ingest.models import SIZE_BUCKETS, Submission, SubmissionQuerySet
from ingest.package_index import package_info

MINIMUM_PROJECTS = 10
POPULAR_LIMIT = 10
# Extra candidates so unknown names do not shrink the published list.
DEPENDENCY_CANDIDATE_LIMIT = POPULAR_LIMIT * 2
MAX_KEYS = 10

# Django and its requirements across every series in DJANGO_VERSIONS. pytz until 4.0 and tzdata only on Windows. Names normalized like the payload.
DJANGO_DEPENDENCIES = frozenset(
    {"asgiref", "backports-zoneinfo", "django", "pytz", "sqlparse", "tzdata"}
)
_NORMALIZED_PACKAGE_NAME_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
# Alphabetical to match Cloudflare query string sorting
FILTER_FIELDS = ("dependency", "django", "key", "python", "size")

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
    """Where a key comes from: a setting name or a ``django.`` usage name."""

    SETTING = "setting"
    USAGE = "usage"

    @classmethod
    def of(cls, key: str) -> KeySource:
        return cls.USAGE if "." in key else cls.SETTING

    @property
    def field(self) -> str:
        """The ``Submission`` field holding this source's keys."""
        return _KEY_FIELDS[self]


_KEY_FIELDS = {KeySource.SETTING: "django_settings", KeySource.USAGE: "usage"}

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
    source: KeySource
    projects: int | None


class DependencyCount(TypedDict):
    name: str
    projects: int


class Dependencies(TypedDict):
    django: list[DependencyCount]
    other: list[DependencyCount]


class Summary(TypedDict):
    minimum_projects: int
    filters: Filters
    withheld: bool
    projects: int | None


class Overview(Summary):
    distributions: dict[str, Distribution]
    django_python: Matrix | dict[str, Never]
    popular: dict[KeySource, list[KeyCount]]
    dependencies: Dependencies | dict[str, Never]


class KeysSummary(Summary):
    keys: list[KeyCount]


class KeysField(forms.Field):
    """Known Django setting or API names, deduplicated and sorted."""

    widget = forms.MultipleHiddenInput

    def clean(self, value: list[str] | None) -> list[str]:
        keys = sorted(set(value or []))
        if len(keys) > MAX_KEYS:
            raise forms.ValidationError(f"At most {MAX_KEYS} keys.")
        if not all(
            key in DJANGO_SETTING_NAMES
            or (key.startswith("django.") and is_django_api_name(key))
            for key in keys
        ):
            raise forms.ValidationError("Invalid key.")
        return keys


class StatsFilterForm(forms.Form):
    dependency = forms.RegexField(
        regex=_NORMALIZED_PACKAGE_NAME_PATTERN, required=False
    )
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
    return urlencode(pairs)


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
        if "dependency" in self.filters:
            queryset = queryset.filter(dependencies__has_key=self.filters["dependency"])
        if "django" in self.filters:
            queryset = queryset.filter(django_minor=self.filters["django"])
        if "python" in self.filters:
            queryset = queryset.filter(python_minor=self.filters["python"])
        if "size" in self.filters:
            queryset = queryset.filter(size=self.filters["size"])
        for key in filter_keys(self.filters):
            queryset = queryset.filter(**{f"{KeySource.of(key).field}__has_key": key})
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
                "dependencies": {},
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
            "dependencies": self._popular_dependencies(),
        }

    def keys(self, source: KeySource | None = None) -> KeysSummary:
        """Every setting and usage key in the cohort, for browsing.

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
        """Setting names and ``django.`` usage keys with their project counts.

        The count is None for a key used by fewer than ``MINIMUM_PROJECTS`` projects.

        Stored payloads are untrusted. The only SQL interpolated here is the cohort
        query Django compiled; every value, including the filters, is a bound
        parameter. Stored keys are only ever read as data. Only names in
        ``DJANGO_SETTING_NAMES`` and the vendored Django API vocabulary are
        returned, since anything else is untrusted or may be private to a project.
        """
        cohort_sql, params = (
            self.queryset.values("django_settings", "usage")
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
            ) AS found
            WHERE %s::text IS NULL OR found.source = %s
            GROUP BY found.key, found.source
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
                    source,
                    source,
                ],
            )
            rows = [
                {"key": key, "source": KeySource(found), "projects": projects}
                for key, found, projects in cursor.fetchall()
            ]
        return [
            row
            for row in rows
            if row["source"] == KeySource.SETTING or is_django_api_name(row["key"])
        ]

    def _all_keys(self, source: KeySource | None = None) -> list[KeyCount]:
        """Every setting and usage key in the cohort.

        Sorted by source, then counted keys ahead of those with too few projects,
        then name. Every setting name the client recognizes is listed, including
        those no project defines.
        """
        keys = self._key_counts(source)
        if source in (None, KeySource.SETTING):
            used = {row["key"] for row in keys if row["source"] == KeySource.SETTING}
            keys += [
                {"key": name, "source": KeySource.SETTING, "projects": None}
                for name in DJANGO_SETTING_NAMES - used
            ]
        return sorted(
            keys,
            key=lambda row: (
                row["source"],
                row["projects"] is None,
                row["key"].lower(),
                row["key"],
            ),
        )

    def _popular_keys(self) -> dict[KeySource, list[KeyCount]]:
        """The most used names of each source, for the overview page."""
        ranked = sorted(
            (row for row in self._key_counts() if row["projects"] is not None),
            key=lambda row: (-(row["projects"] or 0), row["key"]),
        )
        return {
            source: [row for row in ranked if row["source"] == source][:POPULAR_LIMIT]
            for source in KeySource
        }

    def _popular_dependencies(self) -> Dependencies:
        """The ten most used dependencies, split into Django and other packages."""
        cohort_sql, params = (
            self.queryset.values("id", "dependencies")
            .order_by()
            .query.sql_with_params()
        )
        sql = f"""
            SELECT found.name, COUNT(DISTINCT cohort.id)
            FROM ({cohort_sql}) AS cohort
            CROSS JOIN LATERAL (
                SELECT regexp_replace(lower(key), '[-_.]+', '-', 'g') AS name
                FROM jsonb_object_keys(cohort.dependencies) AS key
            ) AS found
            WHERE found.name ~ %s
            AND NOT (found.name = ANY(%s))
            GROUP BY found.name
            HAVING COUNT(DISTINCT cohort.id) >= %s
            ORDER BY COUNT(DISTINCT cohort.id) DESC, found.name
            LIMIT %s
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    *params,
                    _NORMALIZED_PACKAGE_NAME_PATTERN,
                    sorted(DJANGO_DEPENDENCIES),
                    MINIMUM_PROJECTS,
                    DEPENDENCY_CANDIDATE_LIMIT,
                ],
            )
            rows = cursor.fetchall()
        if not rows:
            return {"django": [], "other": []}
        with ThreadPoolExecutor(max_workers=min(len(rows), POPULAR_LIMIT)) as pool:
            infos = list(pool.map(package_info, (name for name, _ in rows)))
        ranked = [
            ({"name": name, "projects": projects}, info)
            for (name, projects), info in zip(rows, infos)
            if info is not None
        ][:POPULAR_LIMIT]
        return {
            "django": [row for row, info in ranked if info.is_django],
            "other": [row for row, info in ranked if not info.is_django],
        }
