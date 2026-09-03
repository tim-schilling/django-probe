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


@dataclass(frozen=True)
class Credential:
    server_url: str
    token: str
    org_slug: str
    org_name: str


def credentials_path() -> Path:
    return Path.home() / ".django-probe" / "credentials.json"


def save_credential(credential: Credential) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(credential)), encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


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
