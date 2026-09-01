from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ingest.models import ApiToken, Submission
from ingest.throttle import ip_limited, project_limited
from ingest.validation import MAX_BODY_BYTES, ValidationError, validate_payload


def _error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"status": "error", "detail": message}, status=status)


def _resolve_token(request) -> tuple[object | None, JsonResponse | None]:
    """Resolve an optional API token.

    Submitting without a token is the default path and must stay frictionless. A token
    that is present but invalid returns an error rather than falling back to an
    anonymous submission, so that a typo does not quietly detach a user's submissions
    from their account.
    """
    header = request.headers.get("Authorization", "")
    if not header:
        return None, None
    scheme, _, key = header.partition(" ")
    if scheme.lower() != "token" or not key:
        return None, _error("malformed Authorization header", 401)
    token = ApiToken.objects.filter(key=key).select_related("user").first()
    if token is None:
        return None, _error("unknown API token", 401)
    return token.user, None


@csrf_exempt
@require_POST
def submissions(request) -> JsonResponse:
    if len(request.body) > MAX_BODY_BYTES:
        return _error("payload too large", 413)

    try:
        raw = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("body must be valid UTF-8 JSON", 400)

    user, auth_error = _resolve_token(request)

    # Rate limit before surfacing an auth error, not after: otherwise guessing tokens
    # is unlimited, since every wrong guess would return 401 without touching a
    # bucket. A bad token spends the anonymous allowance.
    if ip_limited(request, authenticated=user is not None):
        return _error("rate limit exceeded", 429)

    if auth_error is not None:
        return auth_error

    try:
        cleaned = validate_payload(raw)
    except ValidationError as exc:
        return _error(str(exc), 400)

    if project_limited(request, cleaned["project_key"]):
        return _error("rate limit exceeded for this project", 429)

    Submission.objects.create(user=user, **cleaned)
    return JsonResponse({"status": "ok"}, status=201)


def home(request) -> HttpResponse:
    return render(
        request,
        "home.html",
        {"submission_count": Submission.objects.count()},
    )


@login_required
def token(request) -> HttpResponse:
    """Show the signed-in user's API token, and let them roll it.

    This is the only page that requires a login. Scanning, submitting, and grouping by
    project key all work without visiting it.
    """
    if request.method == "POST":
        ApiToken.objects.filter(user=request.user).delete()
        ApiToken.objects.create(user=request.user)
        return redirect("token")

    api_token = ApiToken.objects.filter(user=request.user).first()
    if api_token is None:
        api_token = ApiToken.objects.create(user=request.user)
    return render(request, "token.html", {"api_token": api_token})
