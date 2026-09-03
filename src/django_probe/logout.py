"""Revoke and forget the locally stored CLI login credential."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

from django_probe import __version__, auth

ENDPOINT = "/api/cli/credentials/revoke/"

# Identifies the request as coming from this library rather than a browser, so the
# server can allowlist it separately from browser traffic (e.g. Cloudflare's Browser
# Integrity Check, which otherwise 403s Python's default urllib User-Agent).
USER_AGENT = f"django-probe/{__version__}"


def logout() -> int:
    credential = auth.load_any_credential()
    if credential is None:
        print("Not logged in.")
        return 0

    request = urllib.request.Request(
        credential.server_url.rstrip("/") + ENDPOINT,
        data=b"",
        headers={
            "Authorization": f"CliToken {credential.token}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(
            f"warning: could not reach the server to revoke the credential ({exc})",
            file=sys.stderr,
        )

    auth.credentials_path().unlink(missing_ok=True)
    print(f"Logged out of {credential.org_name}.")
    return 0
