from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest
from django.urls import reverse

from django_probe.payload import build_payload
from ingest.stats import MINIMUM_PROJECTS
from ingest.tests.factories import ProjectFactory
from ingest.tests.helpers import IngestTestCase

pytestmark = pytest.mark.webapp


class UsageReportIntegrationTests(IngestTestCase):
    def test_cli_usage_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".python-version").write_text("3.15", encoding="utf-8")
            (root / "usage.py").write_text(
                textwrap.dedent(
                    """
                    from django.contrib import admin
                    from django.core.cache import cache
                    from django.db import connection, transaction

                    admin.site.register(Book)
                    cache.get("book")
                    cache.set("book", value)
                    connection.cursor()
                    transaction.atomic()
                    transaction.on_commit(notify)
                    """
                ),
                encoding="utf-8",
            )
            body = build_payload(root, dependency_mode="none")

        expected = {
            "django.contrib.admin.site.register",
            "django.core.cache.cache.get",
            "django.core.cache.cache.set",
            "django.db.connection.cursor",
            "django.db.transaction.atomic",
            "django.db.transaction.on_commit",
        }
        self.assertLessEqual(expected, body["usage"].keys())

        for _ in range(MINIMUM_PROJECTS):
            project = ProjectFactory()
            response = self.post(
                body,
                HTTP_AUTHORIZATION=f"Token {project.token}",
            )
            self.assertEqual(response.status_code, 201, response.content)

        response = self.client.get(reverse("api-stats-keys"))
        self.assertEqual(response.status_code, 200)
        reported = {
            row["key"]: row["projects"]
            for row in response.json()["keys"]
            if row["source"] == "usage"
        }
        self.assertEqual(
            {name: reported.get(name) for name in expected},
            dict.fromkeys(expected, MINIMUM_PROJECTS),
        )

        response = self.client.get(reverse("stats-apis"))
        for name in expected:
            self.assertContains(response, f"<code>{name}</code>", html=True)
