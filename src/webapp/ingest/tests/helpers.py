from __future__ import annotations

import json
from typing import Any

from django.core.cache import cache
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

VALID: dict[str, Any] = {
    "schema_version": 1,
    "client_version": "0.1.0",
    "project_key": None,
    "python_version": "3.12.3",
    "django_version": "5.1.2",
    "files_scanned": 12,
    "probe_sources": {"django-upgrade": "1.32.0"},
    "patterns": {"probe:queryset_filter": 3},
    "dependencies": {"django": "5.1.2"},
}


def payload(**overrides: Any) -> dict[str, Any]:
    return {**VALID, **overrides}


class IngestTestCase(TestCase):
    def setUp(self):
        # Rate limits are cache-backed; a leaked bucket would fail later tests.
        cache.clear()
        self.url = reverse("submissions")

    def post(self, body: Any, **extra: Any) -> HttpResponse:
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            **extra,
        )
