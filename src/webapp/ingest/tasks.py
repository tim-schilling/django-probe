"""Scheduled tasks, run by ``manage.py crontask``."""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from crontask import cron
from django.tasks import task
from django.utils import timezone

from django_probe import __version__
from ingest.models import CliCredential, PyPIPackage
from ingest.stats import DJANGO_DEPENDENCIES, MINIMUM_PROJECTS

logger = logging.getLogger(__name__)

PYPI_SIMPLE_URL = "https://pypi.org/simple/{name}/"
PYPI_TIMEOUT = 10
MAX_ATTEMPTS = 4
RETRY_AFTER = timedelta(days=7)
# Keeping unusable CLI credentials for a while lets the account page show someone
# that the laptop they lost last week no longer has access.
CLI_CREDENTIAL_RETENTION = timedelta(days=7)


def is_published(name: str) -> bool:
    """Whether PyPI has a project with the normalized ``name``."""
    request = Request(
        PYPI_SIMPLE_URL.format(name=name),
        headers={"User-Agent": f"django-probe/{__version__}"},
        method="HEAD",
    )
    try:
        with urlopen(request, timeout=PYPI_TIMEOUT):
            return True
    except HTTPError as error:
        error.close()
        if error.code == 404:
            return False
        raise


@cron("0 4 * * *")
@task
def check_pypi_packages() -> None:
    """Check on PyPI the pending packages used by enough projects to be shown.

    A package that isn't confirmed is tried again after ``RETRY_AFTER``, and is
    marked missing after ``MAX_ATTEMPTS``. Rarer packages aren't sent to PyPI,
    since their names may be private.
    """
    now = timezone.now()
    pending = (
        PyPIPackage.objects.due(RETRY_AFTER)
        .used_by(MINIMUM_PROJECTS)
        .exclude(name__in=DJANGO_DEPENDENCIES)
    )
    checked = []
    for package in pending:
        try:
            published = is_published(package.name)
        except OSError:
            logger.warning("Couldn't check %s on PyPI", package.name, exc_info=True)
            published = False
        attempts = package.attempts + 1
        if published:
            status = PyPIPackage.Status.PUBLISHED
        elif attempts >= MAX_ATTEMPTS:
            status = PyPIPackage.Status.MISSING
        else:
            status = PyPIPackage.Status.PENDING
        checked.append(
            PyPIPackage(
                name=package.name, status=status, attempts=attempts, checked_at=now
            )
        )
    PyPIPackage.objects.bulk_create(
        checked,
        update_conflicts=True,
        unique_fields=["name"],
        update_fields=["status", "attempts", "checked_at"],
    )
    logger.info("Checked %d packages on PyPI", len(checked))


@cron("30 3 * * *")
@task
def purge_cli_credentials() -> None:
    """Delete CLI device-login rows unusable for longer than the retention."""
    cutoff = timezone.now() - CLI_CREDENTIAL_RETENTION
    deleted, _ = CliCredential.objects.unusable_before(cutoff).delete()
    logger.info("Deleted %d unusable CLI credentials", deleted)
