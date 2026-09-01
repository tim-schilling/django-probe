from __future__ import annotations

import uuid

from ingest.models import Submission
from ingest.throttle import ANONYMOUS_IP_RATE
from tests.ingest.helpers import IngestTestCase, payload


class RateLimitTests(IngestTestCase):
    def test_anonymous_flood_blocked(self):
        limit = int(ANONYMOUS_IP_RATE.split("/")[0])

        for _ in range(limit):
            self.assertEqual(self.post(payload()).status_code, 201)

        self.assertEqual(self.post(payload()).status_code, 429)
        self.assertEqual(Submission.objects.count(), limit)

    def test_project_key_limited_independently(self):
        key = str(uuid.uuid4())

        statuses = {self.post(payload(project_key=key)).status_code for _ in range(20)}

        self.assertIn(429, statuses)

    def test_token_guessing_limited(self):
        """Wrong tokens must spend the bucket.

        Returning 401 before applying the limit would make guessing unlimited.
        """
        statuses = [
            self.post(payload(), HTTP_AUTHORIZATION=f"Token guess{i}").status_code
            for i in range(40)
        ]
        self.assertIn(429, statuses)
