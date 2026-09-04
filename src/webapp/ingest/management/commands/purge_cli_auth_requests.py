"""Delete CLI device-login requests that can never become credentials."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from ingest.models import CliCredential

DEFAULT_RETENTION_DAYS = 7


class Command(BaseCommand):
    help = "Delete expired and denied CLI device-login requests."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_RETENTION_DAYS,
            help=(
                "Delete requests created more than this many days ago "
                f"(default: {DEFAULT_RETENTION_DAYS})."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting it.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["days"]
        if days < 1:
            self.stderr.write("--days must be at least 1.")
            raise SystemExit(2)

        # A row with no digest never had a credential collected, so it is pending, expired or
        # denied - none of which can turn into a credential later. Selecting on age
        # rather than on `expires_at` keeps the query to one condition and puts the
        # in-flight requests (a ten minute TTL) far out of reach of any sane
        # retention window, while leaving recent ones around to debug a failed login.
        # Approved rows are live credentials and are never touched here; those are
        # revoked, not purged.
        cutoff = timezone.now() - timedelta(days=days)
        stale = CliCredential.objects.filter(
            token_digest__isnull=True, created_at__lt=cutoff
        )

        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {stale.count()} CLI auth request(s) created before "
                f"{cutoff:%Y-%m-%d %H:%M} UTC."
            )
            return

        deleted, _ = stale.delete()
        self.stdout.write(
            f"Deleted {deleted} CLI auth request(s) created before "
            f"{cutoff:%Y-%m-%d %H:%M} UTC."
        )
