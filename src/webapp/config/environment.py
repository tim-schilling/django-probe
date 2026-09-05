"""Environment-variable reads that must fail loudly in production.

Kept out of ``settings.py`` so the production guard can be exercised directly in
tests, without re-importing the settings module.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

PRODUCTION = "production"

# The repository root, where a developer's gitignored .env lives. Deployments set
# their variables directly and ship no .env at all - it is excluded from the image
# by .dockerignore - so this path simply doesn't exist there.
DOTENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def load_dotenv_file(path: Path = DOTENV_PATH) -> None:
    """Merge ``path`` into the process environment, if it exists.

    Real environment variables always win over the file: a deployment sets them on
    the container, and a ``.env`` that reaches a server by accident must not be able
    to quietly replace them.
    """
    load_dotenv(path, override=False)


def name() -> str:
    """The deployment environment.

    Defaults to "dev" so a local checkout or test run is never mistaken for a real
    deployment: it gates the security settings and static storage in ``settings``,
    and ``config.sentry`` uses it as the Sentry environment tag so stray local
    events can't page anyone.
    """
    return os.environ.get("DJANGO_PROBE_ENVIRONMENT", "dev")


def is_production() -> bool:
    return name() == PRODUCTION


def required(variable: str, *, default: str) -> str:
    """Read ``variable``, falling back to ``default`` outside production.

    In production a missing value is a hard error rather than a quiet fallback.
    Booting with the development ``SECRET_KEY`` would hand anyone who reads this
    repository a valid signature for every session cookie and password-reset
    token, and nothing in the logs would say so.
    """
    value = os.environ.get(variable, "")
    if value:
        return value
    if is_production():
        raise ImproperlyConfigured(
            f"{variable} must be set when DJANGO_PROBE_ENVIRONMENT={PRODUCTION}."
        )
    return default
