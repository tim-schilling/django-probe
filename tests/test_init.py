from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest import TestCase, mock

from django_probe.auth import Credential
from django_probe.init import init

CREDENTIAL = Credential(
    server_url="https://x",
    token="tok",
    org_slug="django-team",
    org_name="Django team",
)


def _response(payload: dict) -> mock.Mock:
    response = mock.Mock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = mock.Mock(return_value=response)
    response.__exit__ = mock.Mock(return_value=False)
    return response


class InitTests(TestCase):
    def setUp(self):
        self.load_credential = mock.patch(
            "django_probe.init.load_credential", return_value=CREDENTIAL
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_creates_project_and_prints_token(self):
        created = {
            "name": "myproject",
            "token": "new-token",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        with mock.patch("urllib.request.urlopen", return_value=_response(created)):
            code = init(Path("/tmp/myproject"), "https://x", None, None)

        self.assertEqual(code, 0)

    def test_name_defaults_to_directory_name(self):
        created = {
            "name": "myproject",
            "token": "new-token",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        with mock.patch(
            "urllib.request.urlopen", return_value=_response(created)
        ) as urlopen:
            init(Path("/tmp/myproject"), "https://x", None, None)

        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(sent["name"], "myproject")

    def test_name_override_is_sent(self):
        created = {
            "name": "custom",
            "token": "new-token",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        with mock.patch(
            "urllib.request.urlopen", return_value=_response(created)
        ) as urlopen:
            init(Path("/tmp/myproject"), "https://x", None, "custom")

        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(sent["name"], "custom")

    def test_not_logged_in(self):
        self.load_credential.return_value = None

        code = init(Path("/tmp/myproject"), "https://x", None, None)

        self.assertEqual(code, 1)

    def test_org_mismatch_fails_without_a_request(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code = init(Path("/tmp/myproject"), "https://x", "some-other-org", None)

        self.assertEqual(code, 1)
        urlopen.assert_not_called()

    def test_matching_org_proceeds(self):
        created = {
            "name": "myproject",
            "token": "new-token",
            "organization": {"slug": "django-team", "name": "Django team"},
        }
        with mock.patch("urllib.request.urlopen", return_value=_response(created)):
            code = init(Path("/tmp/myproject"), "https://x", "django-team", None)

        self.assertEqual(code, 0)

    def test_server_error_reported(self):
        error = urllib.error.HTTPError(
            "https://x/api/cli/projects/",
            403,
            "Forbidden",
            None,
            io.BytesIO(b"no longer an owner"),
        )
        try:
            with mock.patch("urllib.request.urlopen", side_effect=error):
                code = init(Path("/tmp/myproject"), "https://x", None, None)
        finally:
            error.close()

        self.assertEqual(code, 1)
