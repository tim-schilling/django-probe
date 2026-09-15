from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from ingest.models import (
    CliCredential,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
    User,
)

admin.site.register(User, UserAdmin)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("organization__name", "user__username")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # name is deliberately absent from every surface below: it's the
    # customer's own project name, and nothing an admin does here needs to
    # read it.
    list_display = ("id", "organization", "token", "created_at")
    list_filter = ("organization",)
    search_fields = ("token", "organization__name")
    exclude = ("name",)

    def has_add_permission(self, request) -> bool:
        # Projects are only ever created through the app's own forms, which
        # generate the token and enforce per-organization name uniqueness.
        return False


@admin.register(CliCredential)
class CliCredentialAdmin(admin.ModelAdmin):
    # The token is a bearer credential and is deliberately absent: it authenticates
    # as its owner, and nothing an admin does here needs to read one back.
    list_display = (
        "label",
        "user",
        "requested_org_slug",
        "organization",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
    list_filter = ("organization",)
    search_fields = ("label", "user__username", "organization__name")

    def has_add_permission(self, request) -> bool:
        # Credentials are only ever created through the login/approve flow.
        return False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "project",
        "django_version",
        "python_version",
        "files_scanned",
        "total_occurrences",
    )
    list_filter = ("created_at", "django_version", "client_version")
    readonly_fields = tuple(
        field.name for field in Submission._meta.fields if field.name != "id"
    )
    date_hierarchy = "created_at"

    @admin.display(description="occurrences")
    def total_occurrences(self, obj: Submission) -> int:
        return obj.total_occurrences

    def has_add_permission(self, request) -> bool:
        # Submissions arrive over the API; hand-authoring them would pollute the data.
        return False
