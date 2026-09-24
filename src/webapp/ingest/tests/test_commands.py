from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from ingest.management.commands.seed_data import SETTING_NAMES, USAGE_NAMES
from ingest.models import CliCredential, Submission
from ingest.tests.factories import (
    CliCredentialFactory,
    OrganizationFactory,
    UserFactory,
    issue_cli_credential,
)


def _aged(credential: CliCredential, days: int) -> CliCredential:
    """Backdate `created_at`, which is auto_now_add and so can't be set on create."""
    return _backdate(credential, created_at=days)


def _backdate(credential: CliCredential, **fields: int) -> CliCredential:
    """Set each named timestamp to the given number of days ago."""
    now = timezone.now()
    CliCredential.objects.filter(pk=credential.pk).update(
        **{name: now - timedelta(days=days) for name, days in fields.items()}
    )
    return credential


class PurgeCliCredentialsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory(username="owner")
        cls.organization = OrganizationFactory(name="Django team", owner=cls.user)

    def credential(self) -> tuple[CliCredential, str]:
        return issue_cli_credential(organization=self.organization, user=self.user)

    def purge(self, *args: str) -> str:
        out = StringIO()
        call_command("purge_cli_credentials", *args, stdout=out)
        return out.getvalue()

    def test_deletes_requests_older_than_the_retention_window(self):
        stale = _aged(CliCredentialFactory(), days=30)

        output = self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=stale.pk).exists())
        self.assertIn("Deleted 1 CLI credential row(s)", output)

    def test_keeps_recent_requests(self):
        recent = _aged(CliCredentialFactory(), days=1)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=recent.pk).exists())

    def test_keeps_pending_requests(self):
        pending = CliCredentialFactory()

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=pending.pk).exists())

    def test_never_deletes_an_active_credential(self):
        """A credential still within its lifetime stays however old the row is;
        deleting one would silently break a working CLI install."""
        credential, _ = self.credential()
        _aged(credential, days=365)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_deletes_long_expired_credentials(self):
        credential, _ = self.credential()
        _backdate(credential, created_at=120, token_expires_at=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_deletes_long_revoked_credentials(self):
        credential, _ = self.credential()
        _backdate(credential, created_at=30, revoked_at=30)

        self.purge()

        self.assertFalse(CliCredential.objects.filter(pk=credential.pk).exists())

    def test_keeps_recently_dead_credentials(self):
        """The account page shows expired and revoked devices, so a window's worth
        of them stays around for someone auditing a lost laptop."""
        expired, _ = self.credential()
        _backdate(expired, created_at=90, token_expires_at=1)
        revoked, _ = self.credential()
        _backdate(revoked, created_at=30, revoked_at=1)

        self.purge()

        self.assertTrue(CliCredential.objects.filter(pk=expired.pk).exists())
        self.assertTrue(CliCredential.objects.filter(pk=revoked.pk).exists())

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

        self.assertIn("Would delete 1 CLI credential row(s)", output)
        self.assertTrue(CliCredential.objects.filter(pk=stale.pk).exists())

    def test_rejects_a_nonsensical_window(self):
        with self.assertRaises(SystemExit):
            call_command("purge_cli_credentials", "--days", "0", stderr=StringIO())


class SeedDataTests(TestCase):
    def test_seeds_settings_and_usage(self):
        """Names come from the installed Django, so the stats pages have data to show."""
        call_command("seed_data", stdout=StringIO())

        submissions = Submission.objects.all()
        self.assertTrue(submissions.exists())
        settings = {
            name for submission in submissions for name in submission.django_settings
        }
        usage = {name for submission in submissions for name in submission.usage}
        self.assertTrue(settings)
        self.assertTrue(usage)
        self.assertLessEqual(settings, set(SETTING_NAMES))
        self.assertLessEqual(usage, set(USAGE_NAMES))
