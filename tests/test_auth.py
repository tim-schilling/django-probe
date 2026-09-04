from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from django_probe.auth import (
    Credential,
    load_any_credential,
    load_credential,
    save_credential,
)

CREDENTIAL = Credential(
    server_url="https://example.test",
    token="abc123",
    org_slug="django-team",
    org_name="Django team",
)


class CredentialStorageTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Nested so save_credential has a directory to create, and its mode to set.
        self.path = (
            Path(self._tmp.name) / "config" / "django-probe" / "credentials.json"
        )
        patcher = mock.patch(
            "django_probe.auth.credentials_path", return_value=self.path
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_round_trips(self):
        save_credential(CREDENTIAL)

        self.assertEqual(load_credential(CREDENTIAL.server_url), CREDENTIAL)

    def test_absent_without_a_stored_credential(self):
        self.assertIsNone(load_credential(CREDENTIAL.server_url))

    def test_none_for_a_different_server(self):
        save_credential(CREDENTIAL)

        self.assertIsNone(load_credential("https://other.test"))

    def test_file_is_only_readable_by_the_owner(self):
        save_credential(CREDENTIAL)

        mode = self.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_load_any_credential_ignores_server(self):
        """Unlike load_credential, this doesn't require knowing the server first."""
        save_credential(CREDENTIAL)

        self.assertEqual(load_any_credential(), CREDENTIAL)

    def test_load_any_credential_absent_without_a_stored_credential(self):
        self.assertIsNone(load_any_credential())


class CredentialPermissionTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = (
            Path(self._tmp.name) / "config" / "django-probe" / "credentials.json"
        )
        patcher = mock.patch(
            "django_probe.auth.credentials_path", return_value=self.path
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def mode(self, path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    def test_credential_is_owner_only(self):
        save_credential(CREDENTIAL)

        self.assertEqual(self.mode(self.path), 0o600)

    def test_containing_directory_is_owner_only(self):
        save_credential(CREDENTIAL)

        self.assertEqual(self.mode(self.path.parent), 0o700)

    def test_tightens_a_credential_left_loose_by_an_earlier_version(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{}", encoding="utf-8")
        os.chmod(self.path, 0o644)

        save_credential(CREDENTIAL)

        self.assertEqual(self.mode(self.path), 0o600)

    def test_rewriting_leaves_no_trailing_content(self):
        """A shorter credential must not leave the tail of a longer one behind."""
        save_credential(
            Credential(
                server_url="https://example.test",
                token="a-considerably-longer-token-than-the-next-one",
                org_slug="django-team",
                org_name="Django team",
            )
        )

        save_credential(CREDENTIAL)

        self.assertEqual(load_credential(CREDENTIAL.server_url), CREDENTIAL)
