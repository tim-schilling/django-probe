from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

USER_LOG_KEY = "django_probe.user"


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
