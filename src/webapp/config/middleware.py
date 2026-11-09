from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.core import checks
from django.http import HttpRequest, HttpResponse

USER_LOG_KEY = "django_probe.user"
ACCESS_LOG_MIDDLEWARE = "config.middleware.access_log_user"
SESSION_MIDDLEWARE = "django.contrib.sessions.middleware.SessionMiddleware"


def access_log_user(
    get_response: Callable[[HttpRequest], HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    """Record the signed-in user's ID for gunicorn's access log.

    ``request.META`` is the WSGI environ, which gunicorn logs as
    ``%({django_probe.user}e)s``, or ``-`` when the key is missing. This must run
    outside ``SessionMiddleware``, so reading ``request.user`` happens after it has
    set ``Vary`` and the stats pages stay publicly cacheable.
    """

    def middleware(request: HttpRequest) -> HttpResponse:
        response = get_response(request)
        if hasattr(request, "user") and request.user.is_authenticated:
            request.META[USER_LOG_KEY] = str(request.user.pk)
        return response

    return middleware


def check_access_log_order(app_configs, **kwargs) -> list[checks.CheckMessage]:
    """Require ``access_log_user`` to come before ``SessionMiddleware``.

    Otherwise reading ``request.user`` marks the session as accessed, which adds
    ``Vary: Cookie`` to every response, including the publicly cached stats pages.
    """
    middleware = settings.MIDDLEWARE
    if ACCESS_LOG_MIDDLEWARE not in middleware or SESSION_MIDDLEWARE not in middleware:
        return []
    if middleware.index(ACCESS_LOG_MIDDLEWARE) < middleware.index(SESSION_MIDDLEWARE):
        return []
    return [
        checks.Error(
            f"{ACCESS_LOG_MIDDLEWARE} must come before {SESSION_MIDDLEWARE}.",
            hint="Move it above SessionMiddleware in MIDDLEWARE.",
            id="config.E001",
        )
    ]
