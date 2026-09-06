"""Create dummy organizations, projects and submissions for local development."""

from __future__ import annotations

import random
import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from config import environment
from ingest.models import User
from ingest.tests.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    ProjectFactory,
    SubmissionFactory,
    UserFactory,
)

ORGANIZATIONS = 3
MEMBERS_PER_ORGANIZATION = 2
PROJECTS_PER_ORGANIZATION = 2
SUBMISSIONS_PER_PROJECT = 5

PYTHON_VERSIONS = ["3.10.14", "3.11.9", "3.12.6", "3.13.0"]
DJANGO_VERSIONS = ["4.2.16", "5.0.9", "5.1.2"]
PATTERN_NAMES = [
    "probe:queryset_filter",
    "probe:queryset_exclude",
    "probe:select_related",
    "probe:prefetch_related",
    "probe:raw_sql",
    "probe:bulk_create",
    "probe:signal_receiver",
    "probe:class_based_view",
]
DEPENDENCY_NAMES = [
    "djangorestframework",
    "celery",
    "psycopg",
    "gunicorn",
    "sentry-sdk",
]


def _random_patterns() -> dict[str, int]:
    names = random.sample(PATTERN_NAMES, k=random.randint(3, len(PATTERN_NAMES)))
    return {name: random.randint(1, 40) for name in names}


def _dummy_username(prefix: str) -> str:
    """A username that can't collide with a previous run's leftover dummy users.

    `UserFactory`'s sequence counter restarts at 0 every process, so re-running
    this command would otherwise collide with usernames like "user-0" left over
    from an earlier run.
    """
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _random_dependencies() -> dict[str, str]:
    dependencies = {"django": random.choice(DJANGO_VERSIONS)}
    for name in random.sample(DEPENDENCY_NAMES, k=2):
        dependencies[name] = (
            f"{random.randint(1, 9)}.{random.randint(0, 9)}.{random.randint(0, 9)}"
        )
    return dependencies


class Command(BaseCommand):
    help = (
        "Create dummy organizations, projects, submissions and users for local "
        "development. If a superuser already exists, it is made the owner of the "
        "first organization so seeded data shows up under that account. Refuses to "
        "run in production."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        if environment.is_production():
            raise CommandError("seed_data must not be run in production.")

        superuser = (
            User.objects.filter(is_superuser=True).order_by("date_joined").first()
        )
        if superuser is not None:
            self.stdout.write(
                f"Found superuser {superuser.username!r}; it will own the first organization."
            )
        else:
            self.stdout.write(
                "No superuser found; seeding data for generated users only."
            )

        total_projects = 0
        total_submissions = 0

        for index in range(ORGANIZATIONS):
            owner = (
                superuser
                if index == 0 and superuser is not None
                else UserFactory(username=_dummy_username("owner"))
            )
            organization = OrganizationFactory(owner=owner)

            for _ in range(MEMBERS_PER_ORGANIZATION):
                member = UserFactory(username=_dummy_username("member"))
                OrganizationMembershipFactory(organization=organization, user=member)

            for _ in range(PROJECTS_PER_ORGANIZATION):
                project = ProjectFactory(organization=organization)
                total_projects += 1
                for _ in range(SUBMISSIONS_PER_PROJECT):
                    SubmissionFactory(
                        project=project,
                        organization=organization,
                        python_version=random.choice(PYTHON_VERSIONS),
                        django_version=random.choice(DJANGO_VERSIONS),
                        files_scanned=random.randint(5, 500),
                        patterns=_random_patterns(),
                        dependencies=_random_dependencies(),
                    )
                    total_submissions += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {ORGANIZATIONS} organization(s), {total_projects} project(s) and "
                f"{total_submissions} submission(s)."
            )
        )
