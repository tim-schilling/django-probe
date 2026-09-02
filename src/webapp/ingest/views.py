from __future__ import annotations

import json
import uuid

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from ingest.forms import (
    MembershipAddForm,
    MembershipDeleteForm,
    MembershipRoleForm,
    OrganizationForm,
    ProjectForm,
)
from ingest.models import (
    ApiToken,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
)
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


def _membership_or_404(request, organization_id: uuid.UUID) -> OrganizationMembership:
    return get_object_or_404(
        OrganizationMembership.objects.select_related("organization"),
        organization_id=organization_id,
        user=request.user,
    )


def _owner_membership_or_404(
    request, organization_id: uuid.UUID
) -> OrganizationMembership:
    membership = _membership_or_404(request, organization_id)
    if membership.role != OrganizationMembership.Role.OWNER:
        raise PermissionDenied
    return membership


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
    if auth_error is not None:
        return auth_error

    try:
        cleaned = validate_payload(raw)
    except ValidationError as exc:
        return _error(str(exc), 400)

    project = None
    if user is not None and cleaned["project_key"] is not None:
        project = (
            Project.objects.filter(
                key=cleaned["project_key"],
                organization__memberships__user=user,
            )
            .select_related("organization")
            .first()
        )
        if project is None:
            return _error("unknown or inaccessible project", 403)

    Submission.objects.create(user=user, project=project, **cleaned)
    return JsonResponse({"status": "ok"}, status=201)


def home(request) -> HttpResponse:
    return render(
        request,
        "home.html",
        {"submission_count": Submission.objects.count()},
    )


@staff_member_required
def style_guide(request) -> HttpResponse:
    return render(request, "style_guide.html")


@login_required
def account(request) -> HttpResponse:
    memberships = request.user.organization_memberships.select_related("organization")
    return render(
        request,
        "account.html",
        {"memberships": memberships},
    )


@login_required
def account_submissions(request) -> HttpResponse:
    organization_ids = request.user.organization_memberships.values_list(
        "organization_id", flat=True
    )
    submissions = Submission.objects.filter(
        Q(project__organization_id__in=organization_ids)
        | Q(project__isnull=True, user=request.user)
    ).select_related("project", "project__organization")
    return render(
        request,
        "account_submissions.html",
        {"submissions": submissions},
    )


@login_required
@require_http_methods(["GET", "POST"])
def organization_create(request) -> HttpResponse:
    form = OrganizationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        organization = Organization.objects.create_with_owner(
            name=form.cleaned_data["name"],
            owner=request.user,
        )
        messages.success(request, f"Created {organization.name}.")
        return redirect("organization-detail", organization_id=organization.pk)
    return render(request, "organization_form.html", {"form": form})


@login_required
def organization_detail(request, organization_id: uuid.UUID) -> HttpResponse:
    membership = _membership_or_404(request, organization_id)
    projects = membership.organization.projects.all()
    submissions = Submission.objects.filter(
        project__organization=membership.organization
    ).select_related("project", "user")[:10]
    return render(
        request,
        "organization_detail.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "projects": projects,
            "recent_submissions": submissions,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def project_create(request, organization_id: uuid.UUID) -> HttpResponse:
    membership = _owner_membership_or_404(request, organization_id)
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.organization = membership.organization
        project.save()
        messages.success(request, f"Created project {project.name}.")
        return redirect(
            "project-detail",
            organization_id=membership.organization_id,
            project_id=project.pk,
        )
    return render(
        request,
        "project_form.html",
        {"form": form, "organization": membership.organization},
    )


@login_required
def project_detail(
    request, organization_id: uuid.UUID, project_id: int
) -> HttpResponse:
    membership = _membership_or_404(request, organization_id)
    project = get_object_or_404(
        Project,
        pk=project_id,
        organization=membership.organization,
    )
    return render(
        request,
        "project_detail.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "project": project,
            "submissions": project.submissions.select_related("user"),
        },
    )


@login_required
def organization_members(request, organization_id: uuid.UUID) -> HttpResponse:
    membership = _owner_membership_or_404(request, organization_id)
    return render(
        request,
        "organization_members.html",
        {
            "add_form": MembershipAddForm(),
            "membership": membership,
            "memberships": membership.organization.memberships.select_related("user"),
            "organization": membership.organization,
            "roles": OrganizationMembership.Role.choices,
        },
    )


@login_required
@require_POST
def organization_member_add(request, organization_id: uuid.UUID) -> HttpResponse:
    membership = _owner_membership_or_404(request, organization_id)
    form = MembershipAddForm(request.POST)
    if form.is_valid():
        user_model = get_user_model()
        user = user_model.objects.get(username=form.cleaned_data["username"])
        _, created = OrganizationMembership.objects.get_or_create(
            organization=membership.organization,
            user=user,
            defaults={"role": form.cleaned_data["role"]},
        )
        if created:
            messages.success(request, f"Added {user.get_username()}.")
            return redirect(
                "organization-members", organization_id=membership.organization_id
            )
        form.add_error("username", "That user is already a member.")
    return render(
        request,
        "organization_members.html",
        {
            "add_form": form,
            "membership": membership,
            "memberships": membership.organization.memberships.select_related("user"),
            "organization": membership.organization,
            "roles": OrganizationMembership.Role.choices,
        },
        status=400,
    )


@login_required
@require_POST
def organization_member_role(
    request, organization_id: uuid.UUID, membership_id: int
) -> HttpResponse:
    owner_membership = _owner_membership_or_404(request, organization_id)
    target = get_object_or_404(
        OrganizationMembership,
        pk=membership_id,
        organization=owner_membership.organization,
    )
    form = MembershipRoleForm(request.POST, membership=target)
    if form.is_valid():
        target.role = form.cleaned_data["role"]
        target.save(update_fields=["role"])
        messages.success(request, f"Updated {target.user.get_username()}.")
    else:
        messages.error(request, form.errors["role"][0])
    return redirect(
        "organization-members", organization_id=owner_membership.organization_id
    )


@login_required
@require_POST
def organization_member_remove(
    request, organization_id: uuid.UUID, membership_id: int
) -> HttpResponse:
    owner_membership = _owner_membership_or_404(request, organization_id)
    target = get_object_or_404(
        OrganizationMembership,
        pk=membership_id,
        organization=owner_membership.organization,
    )
    username = target.user.get_username()
    form = MembershipDeleteForm(request.POST, membership=target)
    if form.is_valid():
        form.save()
        messages.success(request, f"Removed {username}.")
    else:
        messages.error(request, form.non_field_errors()[0])
    return redirect(
        "organization-members", organization_id=owner_membership.organization_id
    )


@login_required
@require_POST
def organization_leave(request, organization_id: uuid.UUID) -> HttpResponse:
    membership = _membership_or_404(request, organization_id)
    organization_name = membership.organization.name
    form = MembershipDeleteForm(request.POST, membership=membership)
    if not form.is_valid():
        messages.error(request, form.non_field_errors()[0])
        return redirect("organization-detail", organization_id=organization_id)
    form.save()
    messages.success(request, f"You left {organization_name}.")
    return redirect("account")


@login_required
@require_http_methods(["GET", "POST"])
def token(request) -> HttpResponse:
    """Show the signed-in user's API token, and let them roll it.

    Scanning, submitting, and grouping by project key all work without visiting it.
    """
    if request.method == "POST":
        with transaction.atomic():
            ApiToken.objects.filter(user=request.user).delete()
            ApiToken.objects.create(user=request.user)
        return redirect("token")

    api_token = ApiToken.objects.filter(user=request.user).first()
    if api_token is None:
        api_token = ApiToken.objects.create(user=request.user)
    return render(request, "token.html", {"api_token": api_token})
