from __future__ import annotations

import io
import json
import urllib.error
from contextlib import redirect_stdout
from unittest import TestCase, mock

from django_probe.auth import Credential
from django_probe.login import login


def _response(payload: dict) -> mock.Mock:
    response = mock.Mock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = mock.Mock(return_value=response)
    response.__exit__ = mock.Mock(return_value=False)
    return response


STARTED = {"code": "abc", "verify_url": "https://x/cli-auth/abc/", "expires_in": 600}


class LoginTests(TestCase):
    def setUp(self):
        mock.patch("webbrowser.open").start()
        mock.patch("time.sleep").start()
        self.save_credential = mock.patch("django_probe.login.save_credential").start()
        self.addCleanup(mock.patch.stopall)

    def test_approved_reports_when_the_credential_expires(self):
        approved = {
            "status": "approved",
            "token": "tok",
            "expires_at": "2027-01-15T09:30:00+00:00",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        buffer = io.StringIO()
        with (
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[_response(STARTED), _response(approved)],
            ),
            redirect_stdout(buffer),
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 0)
        self.assertIn("expires on 2027-01-15", buffer.getvalue())

    def test_approved_without_an_expiry_still_succeeds(self):
        """An older server doesn't send one; the credential is still usable."""
        approved = {
            "status": "approved",
            "token": "tok",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        buffer = io.StringIO()
        with (
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[_response(STARTED), _response(approved)],
            ),
            redirect_stdout(buffer),
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 0)
        self.assertIn("Logged in to Django team.", buffer.getvalue())
        self.assertNotIn("expires on", buffer.getvalue())

    def test_approved_saves_credential(self):
        approved = {
            "status": "approved",
            "token": "tok",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[_response(STARTED), _response(approved)],
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 0)
        self.save_credential.assert_called_once_with(
            Credential(
                server_url="https://x",
                token="tok",
                org_slug="django-team",
                org_name="Django team",
            )
        )

    def test_denied_returns_error_without_saving(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[_response(STARTED), _response({"status": "denied"})],
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 1)
        self.save_credential.assert_not_called()

    def test_expired_returns_error(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[_response(STARTED), _response({"status": "expired"})],
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 1)

    def test_keeps_polling_while_pending(self):
        approved = {
            "status": "approved",
            "token": "tok",
            "organization": {"slug": "s", "name": "N"},
        }
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=[
                _response(STARTED),
                _response({"status": "pending"}),
                _response(approved),
            ],
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 0)

    def test_unknown_org_slug_fails_before_polling(self):
        error = urllib.error.HTTPError(
            "https://x/api/cli/auth/",
            400,
            "Bad Request",
            None,
            io.BytesIO(b"unknown org_slug"),
        )
        try:
            with mock.patch("urllib.request.urlopen", side_effect=error):
                code = login("https://x", "nope", "laptop")
        finally:
            error.close()

        self.assertEqual(code, 1)
        self.save_credential.assert_not_called()

    def test_gives_up_after_the_expiry_window(self):
        with (
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[_response(STARTED), _response({"status": "pending"})],
            ),
            mock.patch("time.monotonic", side_effect=[0, 0, 700]),
        ):
            code = login("https://x", None, "laptop")

        self.assertEqual(code, 1)
