from __future__ import annotations

from django.contrib import admin

from ingest.models import ApiToken, Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "project_key",
        "django_version",
        "python_version",
        "files_scanned",
        "total_occurrences",
    )
    list_filter = ("created_at", "django_version", "client_version")
    search_fields = ("project_key", "user__username")
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
