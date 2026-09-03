from __future__ import annotations

import tempfile
import urllib.error
from pathlib import Path
from unittest import TestCase, mock

from django_probe.auth import Credential, save_credential
from django_probe.logout import logout

CREDENTIAL = Credential(
    server_url="https://x",
    token="tok",
    org_slug="django-team",
    org_name="Django team",
)


class LogoutTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "credentials.json"
        mock.patch("django_probe.auth.credentials_path", return_value=self.path).start()
        self.addCleanup(mock.patch.stopall)

    def test_revokes_and_deletes_the_stored_credential(self):
        save_credential(CREDENTIAL)

        with mock.patch("urllib.request.urlopen") as urlopen:
            code = logout()

        self.assertEqual(code, 0)
        self.assertFalse(self.path.exists())
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "CliToken tok")

    def test_without_a_stored_credential_is_a_no_op(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code = logout()

        self.assertEqual(code, 0)
        urlopen.assert_not_called()

    def test_still_deletes_the_file_when_the_server_is_unreachable(self):
        save_credential(CREDENTIAL)

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            code = logout()

        self.assertEqual(code, 0)
        self.assertFalse(self.path.exists())
