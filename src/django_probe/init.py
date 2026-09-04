"""Create a project via the stored login credential, non-interactively.

Pairs with `django-probe login`: login happens once per org (a browser
round-trip), then `init` can run unattended across many repos.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from django_probe import USER_AGENT
from django_probe.auth import load_credential

ENDPOINT = "/api/cli/projects/"


class InitError(Exception):
    pass


def _create_project(url: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"CliToken {token}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise InitError(f"server returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise InitError(f"could not reach {url}: {exc.reason}") from exc


def init(root: Path, server_url: str, org_slug: str | None, name: str | None) -> int:
    base = server_url.rstrip("/")
    credential = load_credential(base)
    if credential is None:
        print(
            "Not logged in to this server. Run `django-probe login` first.",
            file=sys.stderr,
        )
        return 1

    if org_slug and org_slug != credential.org_slug:
        print(
            f"Logged in for '{credential.org_slug}', but --org '{org_slug}' was "
            f"given. Run `django-probe login --org {org_slug}` to switch.",
            file=sys.stderr,
        )
        return 1

    project_name = name or root.name

    try:
        result = _create_project(
            base + ENDPOINT,
            credential.token,
            {"name": project_name, "org_slug": credential.org_slug},
        )
    except InitError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Created project '{result['name']}' in {result['organization']['name']}.")
    print(f"Token: {result['token']}")
    print("Set this as DJANGO_PROBE_TOKEN wherever you run `django-probe submit`.")
    return 0
