from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from ingest.models import (
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
    list_display = ("name", "organization", "token", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "token", "organization__name")


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
    search_fields = ("project__name",)
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
