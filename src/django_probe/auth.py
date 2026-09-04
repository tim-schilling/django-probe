"""Local storage for the CLI's personal login credential.

`django-probe login` stores one credential per machine here: the CLI's own
credential (distinct from a project token, see ``config.py``), used by
`django-probe init` to create projects on the signed-in user's behalf. v1
keeps only the most recently issued one; logging in again, including for a
different org, overwrites it.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

OWNER_ONLY_FILE = stat.S_IRUSR | stat.S_IWUSR
OWNER_ONLY_DIR = stat.S_IRWXU


@dataclass(frozen=True)
class Credential:
    server_url: str
    token: str
    org_slug: str
    org_name: str


def credentials_path() -> Path:
    return Path.home() / ".config" / "django-probe" / "credentials.json"


def save_credential(credential: Credential) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=OWNER_ONLY_DIR)
    # Created owner-only rather than written and then chmod'ed: on a shared machine
    # the gap between the two leaves the token readable to everyone for as long as
    # the write takes. O_TRUNC keeps the rewrite path (logging in again) from
    # leaving a longer credential's tail behind.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, OWNER_ONLY_FILE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(asdict(credential), handle)
    # An existing file keeps its old mode through O_CREAT, so a credential written
    # by an earlier version still gets tightened.
    os.chmod(path, OWNER_ONLY_FILE)


def _read_stored_credential() -> Credential | None:
    path = credentials_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return Credential(
            server_url=data["server_url"],
            token=data["token"],
            org_slug=data["org_slug"],
            org_name=data["org_name"],
        )
    except KeyError:
        return None


def load_credential(server_url: str) -> Credential | None:
    credential = _read_stored_credential()
    if credential is None or credential.server_url != server_url:
        return None
    return credential


def load_any_credential() -> Credential | None:
    """Read whatever credential is stored, regardless of which server it's for.

    Used by `logout`, which needs to revoke and remove the single stored
    credential without already knowing which server it belongs to.
    """
    return _read_stored_credential()
