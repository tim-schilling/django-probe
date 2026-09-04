from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from ingest.models import CliCredential
from ingest.tests.factories import (
    CliCredentialFactory,
    OrganizationFactory,
    UserFactory,
    issue_cli_credential,
)


def _aged(credential: CliCredential, days: int) -> CliCredential:
    """Backdate `created_at`, which is auto_now_add and so can't be set on create."""
    CliCredential.objects.filter(pk=credential.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )
    return credential


class PurgeCliAuthRequestsTests(TestCase):
    def purge(self, *args: str) -> str:
        out = StringIO()
        call_command("purge_cli_auth_requests", *args, stdout=out)
        return out.getvalue()

    def test_deletes_requests_older_than_the_retention_window(self):
        stale = _aged(CliCredentialFactory(), days=30)

        output = self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=stale.pk).exists())
        self.assertIn("Deleted 1 CLI auth request(s)", output)

    def test_keeps_recent_requests(self):
        recent = _aged(CliCredentialFactory(), days=1)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=recent.pk).exists())

    def test_keeps_pending_requests(self):
        pending = CliCredentialFactory()

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=pending.pk).exists())

    def test_never_deletes_an_approved_credential(self):
        """Collected rows are live credentials, however old. They get revoked, not
        purged; deleting one would silently break a working CLI install."""
        owner = UserFactory(username="owner")
        organization = OrganizationFactory(name="Django team", owner=owner)
        credential, _ = issue_cli_credential(organization=organization, user=owner)
        _aged(credential, days=365)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_deletes_denied_requests(self):
        denied = _aged(CliCredentialFactory(denied_at=timezone.now()), days=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=denied.pk).exists())

    def test_days_option_sets_the_window(self):
        recent = _aged(CliCredentialFactory(), days=3)

        self.purge("--days", "2")

        self.assertFalse(CliCredential.objects.filter(pk=recent.pk).exists())

    def test_dry_run_reports_without_deleting(self):
        stale = _aged(CliCredentialFactory(), days=30)

        output = self.purge("--dry-run")

        self.assertIn("Would delete 1 CLI auth request(s)", output)
        self.assertTrue(CliCredential.objects.filter(pk=stale.pk).exists())

    def test_rejects_a_nonsensical_window(self):
        with self.assertRaises(SystemExit):
            call_command("purge_cli_auth_requests", "--days", "0", stderr=StringIO())
