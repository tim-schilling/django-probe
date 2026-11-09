from __future__ import annotations

from django.apps import AppConfig
from django.core import checks

from config.middleware import check_access_log_order


class IngestConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ingest"

    def ready(self) -> None:
        checks.register(check_access_log_order, checks.Tags.security)
