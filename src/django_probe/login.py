"""Browser-handoff login: get a personal credential for `django-probe init`.

A lightweight device-authorization flow. The CLI asks the server for a code,
the user approves it in a browser, and the CLI polls until that happens.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any

from django_probe import USER_AGENT
from django_probe.auth import Credential, save_credential

START_ENDPOINT = "/api/cli/auth/"
POLL_INTERVAL_SECONDS = 2.0


class LoginError(Exception):
    pass


def _server_detail(body: str) -> str:
    """Pull the server's own error text out of a response body, if it said any.

    Only Django Probe answers in the `{"status": "error", "detail": ...}` shape.
    A 429 from the edge is `error code: 1015`, and a proxy's 502 is a page of
    HTML - neither tells the user anything, so both come back empty here rather
    than being printed verbatim.
    """
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str):
            return detail
    return ""


def _http_error_message(url: str, exc: urllib.error.HTTPError) -> str:
    host = urllib.parse.urlparse(url).netloc or url
    detail = _server_detail(exc.read().decode("utf-8", errors="replace"))

    if exc.code == 429:
        return (
            f"{host} is rate limiting this login (HTTP 429). This is the server "
            "turning requests away, not a problem with your account. Wait a "
            "minute, then run `django-probe login` again."
        )
    if exc.code >= 500:
        return (
            f"{host} could not answer (HTTP {exc.code}). The server is likely "
            "down or restarting; try again shortly."
        )
    if detail:
        return f"{host} rejected the request (HTTP {exc.code}): {detail}"
    return f"{host} rejected the request (HTTP {exc.code})."


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
        raise LoginError(_http_error_message(url, exc)) from exc
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
            # Older servers don't send this; the credential still works, we just
            # can't say for how long.
            expires_at = result.get("expires_at")
            if isinstance(expires_at, str) and expires_at:
                print(
                    f"This credential expires on {expires_at[:10]}. "
                    "You can revoke it sooner from your account page."
                )
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
