"""POST a payload to a Django Probe server, using only the standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django_probe import USER_AGENT

ENDPOINT = "/api/submissions/"


class SubmitError(Exception):
    pass


def submit(
    payload: dict[str, Any], server_url: str, token: str | None = None
) -> dict[str, Any]:
    url = server_url.rstrip("/") + ENDPOINT
    body = json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Token {token}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SubmitError(f"server returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SubmitError(f"could not reach {url}: {exc.reason}") from exc
