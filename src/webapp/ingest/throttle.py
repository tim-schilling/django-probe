"""Rate limiting for the ingest endpoint.

Two independent axes, so flooding the dataset requires many source addresses *and*
many project keys, not merely many requests.

No IP address is ever written to the database. The per-IP limit keys on a salted
hash that rotates daily, lives only in the cache, and becomes irrecoverable once the
day rolls over.
"""

from __future__ import annotations

import hashlib
from datetime import date

from django.conf import settings
from django_ratelimit.core import is_ratelimited

# Set well above realistic honest use: a project reports on CI runs, not in a loop.
# These exist to bound abuse, never to pressure anyone into creating an account.
ANONYMOUS_IP_RATE = "30/h"
AUTHENTICATED_IP_RATE = "60/h"
PROJECT_RATE = "12/h"


def client_ip(request) -> str:
    # REMOTE_ADDR only. X-Forwarded-For is client-controlled unless a trusted proxy
    # is known to overwrite it, and trusting it blindly would hand attackers an
    # unlimited supply of rate-limit buckets.
    return request.META.get("REMOTE_ADDR", "")


def hashed_ip(request) -> str:
    """A salted, daily-rotating pseudonym for the client address."""
    material = f"{client_ip(request)}|{date.today().isoformat()}|{settings.SECRET_KEY}"
    return hashlib.sha256(material.encode()).hexdigest()


def ip_limited(request, *, authenticated: bool) -> bool:
    rate = AUTHENTICATED_IP_RATE if authenticated else ANONYMOUS_IP_RATE
    return is_ratelimited(
        request,
        group="ingest-ip",
        key=lambda group, req: hashed_ip(req),
        rate=rate,
        method=["POST"],
        increment=True,
    )


def project_limited(request, project_key) -> bool:
    if project_key is None:
        return False
    return is_ratelimited(
        request,
        group="ingest-project",
        key=lambda group, req: str(project_key),
        rate=PROJECT_RATE,
        method=["POST"],
        increment=True,
    )
