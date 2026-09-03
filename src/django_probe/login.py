"""Browser-handoff login: get a personal credential for `django-probe init`.

A lightweight device-authorization-style flow, not full OAuth — the CLI and
web app are both first-party, so there's no client registration or scopes.
The CLI asks the server for a code, the user approves it in a browser, and
the CLI polls until that happens.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Any

from django_probe import __version__
from django_probe.auth import Credential, save_credential

START_ENDPOINT = "/api/cli/auth/"
POLL_INTERVAL_SECONDS = 2.0

# Identifies the request as coming from this library rather than a browser, so the
# server can allowlist it separately from browser traffic (e.g. Cloudflare's Browser
# Integrity Check, which otherwise 403s Python's default urllib User-Agent).
USER_AGENT = f"django-probe/{__version__}"


class LoginError(Exception):
    pass


def _request(url: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LoginError(f"server returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LoginError(f"could not reach {url}: {exc.reason}") from exc


def login(server_url: str, org_slug: str | None, label: str) -> int:
    base = server_url.rstrip("/")
    body: dict[str, Any] = {"label": label}
    if org_slug:
        body["org_slug"] = org_slug

    try:
        started = _request(base + START_ENDPOINT, body=body)
    except LoginError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    verify_url = started["verify_url"]
    print(f"Open this URL to approve access, then return here: {verify_url}")
    webbrowser.open(verify_url)  # best-effort; the printed URL is the real fallback

    poll_url = f"{base}/api/cli/auth/{started['code']}/poll/"
    deadline = time.monotonic() + started["expires_in"]

    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            result = _request(poll_url)
        except LoginError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        status = result.get("status")
        if status == "approved":
            organization = result["organization"]
            save_credential(
                Credential(
                    server_url=base,
                    token=result["token"],
                    org_slug=organization["slug"],
                    org_name=organization["name"],
                )
            )
            print(f"Logged in to {organization['name']}.")
            return 0
        if status == "denied":
            print("Access denied.", file=sys.stderr)
            return 1
        if status == "expired":
            print(
                "The login request expired. Run `django-probe login` again.",
                file=sys.stderr,
            )
            return 1
        # status == "pending": keep polling

    print("Timed out waiting for approval.", file=sys.stderr)
    return 1
