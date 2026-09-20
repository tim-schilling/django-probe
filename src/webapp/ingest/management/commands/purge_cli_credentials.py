"""Delete CLI device-login rows that can no longer authenticate anything."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from ingest.models import CliCredential

DEFAULT_RETENTION_DAYS = 7


class Command(BaseCommand):
    help = "Delete CLI device-login requests and credentials that are unusable."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_RETENTION_DAYS,
            help=(
                "Delete rows that have been unusable for more than this many days "
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

        # The window is measured from the moment each row stopped being usable, not
        # from `created_at`: a credential that runs its full 90 day term is already
        # months old on the day it dies. Keeping the dead ones around for the window
        # leaves the account page able to show someone that the laptop they lost
        # last week no longer has access.
        cutoff = timezone.now() - timedelta(days=days)
        stale = CliCredential.objects.filter(
            # No digest means the credential was never collected, so the row is a
            # pending, expired or denied request that can never become one. Age
            # those from creation, which puts the ten minute request TTL far out of
            # reach of any sane window and leaves recent ones around to debug a
            # failed login.
            Q(token_digest__isnull=True, created_at__lt=cutoff)
            | Q(revoked_at__lt=cutoff)
            | Q(token_expires_at__lt=cutoff)
        )

        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {stale.count()} CLI credential row(s) unusable for "
                f"more than {days} day(s)."
            )
            return

        deleted, _ = stale.delete()
        self.stdout.write(
            f"Deleted {deleted} CLI credential row(s) unusable for more than "
            f"{days} day(s)."
        )
