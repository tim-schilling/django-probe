from __future__ import annotations

from django.conf import settings
from django.core import checks
from django.test import SimpleTestCase, override_settings

from config.middleware import (
    ACCESS_LOG_MIDDLEWARE,
    SESSION_MIDDLEWARE,
)


class AccessLogOrderTests(SimpleTestCase):
    def test_order(self):
        """The access log middleware must sit outside ``SessionMiddleware``."""
        self.assertEqual(checks.run_checks(tags=[checks.Tags.security]), [])

        reordered = [
            name for name in settings.MIDDLEWARE if name != ACCESS_LOG_MIDDLEWARE
        ]
        reordered.insert(reordered.index(SESSION_MIDDLEWARE) + 1, ACCESS_LOG_MIDDLEWARE)
        with override_settings(MIDDLEWARE=reordered):
            self.assertIn(
                "config.E001",
                [error.id for error in checks.run_checks(tags=[checks.Tags.security])],
            )
