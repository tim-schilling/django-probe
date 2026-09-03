from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from ingest import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/submissions/", views.submissions, name="submissions"),
    path("api/cli/auth/", views.cli_auth_start, name="cli-auth-start"),
    path(
        "api/cli/auth/<str:code>/poll/",
        views.cli_auth_poll,
        name="cli-auth-poll",
    ),
    path("account/", views.account, name="account"),
    path("style-guide/", views.style_guide, name="style-guide"),
    path(
        "account/submissions/",
        views.account_submissions,
        name="account-submissions",
    ),
    path("organizations/new/", views.organization_create, name="organization-create"),
    path(
        "organizations/<uuid:organization_id>/",
        views.organization_detail,
        name="organization-detail",
    ),
    path(
        "organizations/<uuid:organization_id>/leave/",
        views.organization_leave,
        name="organization-leave",
    ),
    path(
        "organizations/<uuid:organization_id>/members/",
        views.organization_members,
        name="organization-members",
    ),
    path(
        "organizations/<uuid:organization_id>/members/add/",
        views.organization_member_add,
        name="organization-member-add",
    ),
    path(
        "organizations/<uuid:organization_id>/members/<int:membership_id>/role/",
        views.organization_member_role,
        name="organization-member-role",
    ),
    path(
        "organizations/<uuid:organization_id>/members/<int:membership_id>/remove/",
        views.organization_member_remove,
        name="organization-member-remove",
    ),
    path(
        "organizations/<uuid:organization_id>/projects/new/",
        views.project_create,
        name="project-create",
    ),
    path(
        "organizations/<uuid:organization_id>/projects/<int:project_id>/",
        views.project_detail,
        name="project-detail",
    ),
    path(
        "organizations/<uuid:organization_id>/projects/<int:project_id>/regenerate-token/",
        views.project_token_regenerate,
        name="project-token-regenerate",
    ),
    path(
        "cli-auth/<str:code>/",
        views.cli_auth_verify,
        name="cli-auth-verify",
    ),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
]
