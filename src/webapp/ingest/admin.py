from __future__ import annotations

from django.contrib import admin

from ingest.models import (
    ApiToken,
    Organization,
    OrganizationMembership,
    Project,
    Submission,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("organization__name", "user__username")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "key", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "key", "organization__name")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "project",
        "project_key",
        "django_version",
        "python_version",
        "files_scanned",
        "total_occurrences",
    )
    list_filter = ("created_at", "django_version", "client_version")
    search_fields = ("project_key", "project__name", "user__username")
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


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__username",)
