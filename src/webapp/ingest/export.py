"""Assemble everything an account holds into one JSON document, encoded lazily."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

from django.utils import timezone

from ingest.models import CliCredential, Project, Submission

#: Rows per round trip while streaming a project's submissions.
SUBMISSION_CHUNK_SIZE = 200

_INDENT = "  "


def export_account(user) -> dict[str, Any]:
    """Describe the account.

    The result is lazy: submissions are left as iterators, so it has to be consumed
    once, in order, by `iter_json`.
    """
    return {
        "exported_at": timezone.now().isoformat(),
        "account": _account(user),
        "organizations": _organizations(user),
        "cli_credentials": _cli_credentials(user),
    }


def iter_json(value: Any, level: int = 0) -> Iterator[str]:
    """Encode `value` as JSON, pulling iterables only as they are written out.

    The text matches `json.dumps(value, indent=2)`, except that any iterable stands
    in for a list. That is what keeps a submission queryset flowing to the client a
    chunk at a time instead of being built in full first.
    """
    pad = _INDENT * level
    inner = _INDENT * (level + 1)
    if isinstance(value, dict):
        yield "{"
        empty = True
        for key, item in value.items():
            yield "\n" if empty else ",\n"
            yield f"{inner}{json.dumps(str(key))}: "
            yield from iter_json(item, level + 1)
            empty = False
        if not empty:
            yield f"\n{pad}"
        yield "}"
    elif isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        yield json.dumps(value)
    else:
        yield "["
        empty = True
        for item in value:
            yield "\n" if empty else ",\n"
            yield inner
            yield from iter_json(item, level + 1)
            empty = False
        if not empty:
            yield f"\n{pad}"
        yield "]"


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _account(user) -> dict[str, Any]:
    return {
        "username": user.get_username(),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_joined": _timestamp(user.date_joined),
        "last_login": _timestamp(user.last_login),
        "identities": [
            {
                "provider": account.provider,
                "uid": account.uid,
                "connected_at": _timestamp(account.date_joined),
            }
            for account in user.socialaccount_set.all()
        ],
    }


def _organizations(user) -> list[dict[str, Any]]:
    """Every organization the user belongs to, with its projects and submissions.

    Other members are left out: their usernames and roles are their own data, not
    the exporter's. What remains is the same scope the account page renders.

    Organizations and projects are read up front because an account has few of
    either. Their submissions are not; see `_project`.
    """
    memberships = user.organization_memberships.select_related(
        "organization"
    ).prefetch_related("organization__projects")
    return [
        {
            "name": membership.organization.name,
            "slug": membership.organization.slug,
            "created_at": _timestamp(membership.organization.created_at),
            "your_role": membership.role,
            "joined_at": _timestamp(membership.created_at),
            "projects": [
                _project(project) for project in membership.organization.projects.all()
            ],
        }
        for membership in memberships
    ]


def _project(project: Project) -> dict[str, Any]:
    """The submission token is omitted: it is a live secret that authenticates
    writes, and the project page already shows it to the members who need it.

    `submissions` is a generator over a chunked cursor. A project accumulates a row
    per CI run forever, so this is the one part of an export with no natural bound.
    """
    return {
        "name": project.name,
        "created_at": _timestamp(project.created_at),
        "submissions": (
            _submission(submission)
            for submission in project.submissions.iterator(
                chunk_size=SUBMISSION_CHUNK_SIZE
            )
        ),
    }


def _submission(submission: Submission) -> dict[str, Any]:
    return {
        "id": str(submission.id),
        "created_at": _timestamp(submission.created_at),
        "schema_version": submission.schema_version,
        "client_version": submission.client_version,
        "python_version": submission.python_version,
        "django_version": submission.django_version,
        "files_scanned": submission.files_scanned,
        "probe_sources": submission.probe_sources,
        "patterns": submission.patterns,
        "usage_packages": submission.usage_packages,
        "usage": submission.usage,
        "dependencies": submission.dependencies,
        "dependencies_source": submission.dependencies_source,
        "django_settings": submission.django_settings,
        "django_settings_scanned": submission.django_settings_scanned,
    }


def _cli_credentials(user) -> list[dict[str, Any]]:
    """Revoked and expired rows are included alongside the live ones: this is a
    record of every device the account approved, not only the working ones."""
    return [
        _cli_credential(credential)
        for credential in user.cli_credentials.select_related("organization")
    ]


def _cli_credential(credential: CliCredential) -> dict[str, Any]:
    return {
        "label": credential.label,
        "organization": (
            credential.organization.name
            if credential.organization is not None
            else None
        ),
        "status": credential.status,
        "created_at": _timestamp(credential.created_at),
        "approved_at": _timestamp(credential.approved_at),
        "denied_at": _timestamp(credential.denied_at),
        "retrieved_at": _timestamp(credential.retrieved_at),
        "last_used_at": _timestamp(credential.last_used_at),
        "token_expires_at": _timestamp(credential.token_expires_at),
        "revoked_at": _timestamp(credential.revoked_at),
    }
