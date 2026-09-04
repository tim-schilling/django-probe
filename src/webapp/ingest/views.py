from __future__ import annotations

import json
import secrets
import uuid

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ingest.forms import (
    MembershipAddForm,
    MembershipDeleteForm,
    MembershipRoleForm,
    OrganizationForm,
    ProjectForm,
)
from ingest.models import (
    CLI_AUTH_REQUEST_TTL,
    CliCredential,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
)
from ingest.validation import MAX_BODY_BYTES, ValidationError, validate_payload


def _error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"status": "error", "detail": message}, status=status)


def _resolve_project(request) -> tuple[Project | None, JsonResponse | None]:
    """Resolve an optional project token from the Authorization header.

    Submitting without a token is the default path and must stay frictionless. A token
    that is present but doesn't match a real project returns an error rather than
    falling back to an anonymous submission, so that a typo does not quietly detach a
    submission from its project.
    """
    header = request.headers.get("Authorization", "")
    if not header:
        return None, None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "token" or not token:
        return None, _error("malformed Authorization header", 401)
    project = Project.objects.filter(token=token).select_related("organization").first()
    if project is None:
        return None, _error("unknown token", 401)
    return project, None


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

    project, auth_error = _resolve_project(request)
    if auth_error is not None:
        return auth_error

    try:
        cleaned = validate_payload(raw)
    except ValidationError as exc:
        return _error(str(exc), 400)

    Submission.objects.create(project=project, **cleaned)
    return JsonResponse({"status": "ok"}, status=201)


@csrf_exempt
@require_POST
def cli_auth_start(request) -> JsonResponse:
    """Begin a device-login flow: `django-probe login` calls this first.

    Issues a pending `CliCredential` and a verify URL for the user to open in a
    browser; the CLI then polls `cli_auth_poll` until it's approved or denied.
    """
    try:
        raw = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("body must be valid UTF-8 JSON", 400)
    if not isinstance(raw, dict):
        return _error("body must be a JSON object", 400)

    org_slug = raw.get("org_slug")
    if org_slug and not Organization.objects.filter(slug=org_slug).exists():
        return _error("unknown org_slug", 400)

    label = raw.get("label")
    label = label[:200] if isinstance(label, str) else ""

    credential = CliCredential.objects.create(
        requested_org_slug=org_slug or "", label=label
    )

    return JsonResponse(
        {
            "code": credential.code,
            "verify_url": request.build_absolute_uri(
                reverse("cli-auth-verify", args=[credential.code])
            ),
            "expires_in": int(CLI_AUTH_REQUEST_TTL.total_seconds()),
        },
        status=201,
    )


@require_GET
def cli_auth_poll(request, code: str) -> JsonResponse:
    credential = (
        CliCredential.objects.filter(code=code).select_related("organization").first()
    )
    if credential is None:
        return _error("unknown code", 404)

    if credential.token is not None:
        # Single-use: the next poll of an already-retrieved code 404s, limiting
        # how long a leaked code could be replayed to fetch the credential.
        if credential.retrieved_at is not None:
            return _error("unknown code", 404)
        credential.retrieved_at = timezone.now()
        credential.save(update_fields=["retrieved_at"])
        return JsonResponse(
            {
                "status": "approved",
                "token": credential.token,
                "organization": {
                    "slug": credential.organization.slug,
                    "name": credential.organization.name,
                },
            }
        )

    if credential.denied_at is not None:
        return JsonResponse({"status": "denied"})

    if credential.expires_at <= timezone.now():
        return JsonResponse({"status": "expired"})

    return JsonResponse({"status": "pending"})


def _resolve_cli_credential(
    request,
) -> tuple[CliCredential | None, JsonResponse | None]:
    """Resolve a personal CLI credential from the Authorization header.

    A distinct `CliToken` scheme from the `Token` used for submissions, so the two
    credential types can never be confused with each other.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "clitoken" or not token:
        return None, _error("malformed Authorization header", 401)
    credential = (
        CliCredential.objects.filter(token=token, revoked_at__isnull=True)
        .select_related("organization", "user")
        .first()
    )
    if credential is None:
        return None, _error("unknown or revoked token", 401)
    return credential, None


@csrf_exempt
@require_POST
def cli_projects_create(request) -> JsonResponse:
    credential, auth_error = _resolve_cli_credential(request)
    if auth_error is not None:
        return auth_error

    # Membership can have been revoked since the credential was issued; re-check it
    # at request time rather than trusting what was true at login.
    if not _is_org_owner(credential.user, credential.organization):
        return _error("no longer an owner of that organization", 403)

    try:
        raw = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("body must be valid UTF-8 JSON", 400)
    if not isinstance(raw, dict):
        return _error("body must be a JSON object", 400)

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return _error("name is required", 400)

    org_slug = raw.get("org_slug")
    if org_slug and org_slug != credential.organization.slug:
        return _error("token is scoped to a different organization", 400)

    project = Project.objects.create(
        organization=credential.organization, name=name.strip()
    )
    credential.last_used_at = timezone.now()
    credential.save(update_fields=["last_used_at"])

    return JsonResponse(
        {
            "name": project.name,
            "token": project.token,
            "organization": {
                "slug": credential.organization.slug,
                "name": credential.organization.name,
            },
        },
        status=201,
    )


@csrf_exempt
@require_POST
def cli_credentials_revoke(request) -> JsonResponse:
    credential, auth_error = _resolve_cli_credential(request)
    if auth_error is not None:
        return auth_error

    credential.revoked_at = timezone.now()
    credential.save(update_fields=["revoked_at"])
    return JsonResponse({"status": "revoked"})


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
        project__organization_id__in=organization_ids
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
    ).select_related("project")[:10]
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
            "submissions": project.submissions.all(),
        },
    )


@login_required
@require_POST
def project_token_regenerate(
    request, organization_id: uuid.UUID, project_id: int
) -> HttpResponse:
    membership = _owner_membership_or_404(request, organization_id)
    project = get_object_or_404(
        Project,
        pk=project_id,
        organization=membership.organization,
    )
    project.regenerate_token()
    return redirect(
        "project-detail", organization_id=organization_id, project_id=project_id
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


def _is_org_owner(user, organization: Organization) -> bool:
    return OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        role=OrganizationMembership.Role.OWNER,
    ).exists()


def _is_org_member(user, organization: Organization) -> bool:
    return OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
    ).exists()


@login_required
@require_http_methods(["GET", "POST"])
def cli_auth_verify(request, code: str) -> HttpResponse:
    credential = get_object_or_404(CliCredential, code=code)

    if request.method == "POST":
        return _cli_auth_verify_post(request, credential)

    if not credential.is_pending:
        return render(
            request,
            "cli_auth_verify.html",
            {"credential": credential, "state": "invalid"},
        )

    requested_organization = None
    if credential.requested_org_slug:
        requested_organization = Organization.objects.filter(
            slug=credential.requested_org_slug
        ).first()

    if requested_organization is not None:
        state = (
            "confirm"
            if _is_org_member(request.user, requested_organization)
            else "forbidden"
        )
        return render(
            request,
            "cli_auth_verify.html",
            {
                "credential": credential,
                "state": state,
                "organization": requested_organization,
            },
        )

    member_organizations = Organization.objects.filter(memberships__user=request.user)
    return render(
        request,
        "cli_auth_verify.html",
        {
            "credential": credential,
            "state": "choose" if member_organizations else "no-organizations",
            "organizations": member_organizations,
        },
    )


def _cli_auth_verify_post(request, credential: CliCredential) -> HttpResponse:
    if not credential.is_pending:
        return render(
            request,
            "cli_auth_verify.html",
            {"credential": credential, "state": "invalid"},
        )

    if request.POST.get("action") == "deny":
        credential.denied_at = timezone.now()
        credential.save(update_fields=["denied_at"])
        return render(
            request,
            "cli_auth_verify.html",
            {"credential": credential, "state": "denied"},
        )

    if credential.requested_org_slug:
        organization = get_object_or_404(
            Organization, slug=credential.requested_org_slug
        )
    else:
        organization = get_object_or_404(
            Organization, pk=request.POST.get("organization_id")
        )

    if not _is_org_member(request.user, organization):
        raise PermissionDenied

    credential.organization = organization
    credential.user = request.user
    credential.token = secrets.token_hex(32)
    credential.save(update_fields=["organization", "user", "token"])
    return render(
        request, "cli_auth_verify.html", {"credential": credential, "state": "approved"}
    )
